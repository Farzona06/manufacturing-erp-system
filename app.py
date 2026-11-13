import os, io
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_file, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func
from config import Config
from models import db, User, Product, RawMaterial, ProductionPlan, BOMItem, InventoryTransaction, CustomerOrder, ProductionStageHistory, MaterialIssue

app = Flask(__name__)
app.config.from_object(Config)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
db.init_app(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Davom etish uchun tizimga kiring."

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

ROLES = {"admin": "Administrator", "production": "Ishlab chiqarish menejeri", "warehouse": "Ombor menejeri"}
STAGES = ["Rejalashtirilgan", "Xomashyo tayyorlash", "Ishlab chiqarilmoqda", "Sifat nazorati", "Yakunlangan"]

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

@app.context_processor
def inject_globals():
    return {"ROLES": ROLES, "STAGES": STAGES}

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if user and user.active and user.check_password(request.form.get("password", "")):
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(url_for("dashboard"))
        flash("Login yoki parol noto‘g‘ri.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Tizimdan chiqdingiz.", "success")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    products = Product.query.count()
    plans = ProductionPlan.query.count()
    active = ProductionPlan.query.filter(ProductionPlan.stage != "Yakunlangan").count()
    orders = CustomerOrder.query.count()
    materials = RawMaterial.query.count()
    low = RawMaterial.query.filter(RawMaterial.quantity <= RawMaterial.min_quantity).all()
    planned = db.session.query(func.coalesce(func.sum(ProductionPlan.planned_qty), 0)).scalar()
    completed = db.session.query(func.coalesce(func.sum(ProductionPlan.completed_qty), 0)).scalar()
    monthly = db.session.query(
        func.strftime("%Y-%m", ProductionPlan.start_date),
        func.sum(ProductionPlan.completed_qty)
    ).group_by(
        func.strftime("%Y-%m", ProductionPlan.start_date)
    ).order_by(
        func.strftime("%Y-%m", ProductionPlan.start_date)
    ).all()

    # SQLAlchemy Row obyektlarini JSON formatiga mos oddiy listga aylantiramiz
    monthly_data = [
        [str(row[0]), int(row[1] or 0)]
        for row in monthly
    ]

    return render_template(
        "dashboard.html",
        products=products,
        plans=plans,
        active=active,
        orders=orders,
        materials=materials,
        low=low,
        planned=planned,
        completed=completed,
        monthly=monthly_data
    )

@app.route("/products", methods=["GET", "POST"])
@roles_required("admin", "production")
def products():
    if request.method == "POST":
        p = Product(code=request.form["code"].strip(), name=request.form["name"].strip(), category=request.form.get("category","Umumiy"), description=request.form.get("description",""), unit=request.form.get("unit","dona"), price=float(request.form.get("price") or 0))
        db.session.add(p)
        try: db.session.commit(); flash("Mahsulot qo‘shildi.", "success")
        except Exception: db.session.rollback(); flash("Mahsulot kodi takrorlangan yoki ma’lumot noto‘g‘ri.", "danger")
        return redirect(url_for("products"))
    q = request.args.get("q","")
    query = Product.query
    if q: query = query.filter(Product.name.ilike(f"%{q}%") | Product.code.ilike(f"%{q}%"))
    return render_template("products.html", items=query.order_by(Product.id.desc()).all())

@app.route("/products/<int:item_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_product(item_id):
    item = db.get_or_404(Product, item_id)
    if ProductionPlan.query.filter_by(product_id=item.id).first() or CustomerOrder.query.filter_by(product_id=item.id).first():
        flash("Mahsulot reja yoki buyurtmalarda ishlatilgan. O‘chirib bo‘lmaydi.", "danger")
    else:
        db.session.delete(item); db.session.commit(); flash("Mahsulot o‘chirildi.", "success")
    return redirect(url_for("products"))

@app.route("/inventory", methods=["GET", "POST"])
@roles_required("admin", "warehouse")
def inventory():
    if request.method == "POST":
        m = RawMaterial(code=request.form["code"].strip(), name=request.form["name"].strip(), unit=request.form.get("unit","kg"), quantity=float(request.form.get("quantity") or 0), min_quantity=float(request.form.get("min_quantity") or 0), unit_price=float(request.form.get("unit_price") or 0))
        db.session.add(m)
        try: db.session.flush()
        except Exception: db.session.rollback(); flash("Material kodi takrorlangan.", "danger"); return redirect(url_for("inventory"))
        if m.quantity:
            db.session.add(InventoryTransaction(material=m, user_id=current_user.id, kind="Kirim", quantity=m.quantity, note="Boshlang‘ich qoldiq"))
        db.session.commit(); flash("Xomashyo qo‘shildi.", "success"); return redirect(url_for("inventory"))
    items = RawMaterial.query.order_by(RawMaterial.name).all()
    transactions = InventoryTransaction.query.order_by(InventoryTransaction.created_at.desc()).limit(30).all()
    return render_template("inventory.html", items=items, transactions=transactions)

@app.route("/inventory/<int:material_id>/transaction", methods=["POST"])
@roles_required("admin", "warehouse")
def inventory_transaction(material_id):
    m = db.get_or_404(RawMaterial, material_id)
    qty = float(request.form.get("quantity") or 0); kind = request.form.get("kind")
    if qty <= 0 or kind not in ("Kirim", "Chiqim"):
        flash("Miqdor musbat bo‘lishi kerak.", "danger")
    elif kind == "Chiqim" and qty > m.quantity:
        flash("Omborda yetarli qoldiq yo‘q.", "danger")
    else:
        try:
            m.quantity += qty if kind == "Kirim" else -qty
            db.session.add(InventoryTransaction(material=m, user_id=current_user.id, kind=kind, quantity=qty, note=request.form.get("note","")))
            db.session.commit(); flash("Ombor tranzaksiyasi saqlandi.", "success")
        except Exception: db.session.rollback(); flash("Tranzaksiya bajarilmadi.", "danger")
    return redirect(url_for("inventory"))

@app.route("/production", methods=["GET", "POST"])
@roles_required("admin", "production")
def production():
    if request.method == "POST":
        p = ProductionPlan(plan_code=request.form["plan_code"].strip(), product_id=int(request.form["product_id"]), planned_qty=float(request.form["planned_qty"]), start_date=date.fromisoformat(request.form["start_date"]), end_date=date.fromisoformat(request.form["end_date"]), notes=request.form.get("notes",""))
        if p.planned_qty <= 0 or p.end_date < p.start_date:
            flash("Miqdor yoki sanalarni tekshiring.", "danger")
        else:
            db.session.add(p)
            try: db.session.flush(); db.session.add(ProductionStageHistory(plan=p, stage=p.stage, user_id=current_user.id)); db.session.commit(); flash("Ishlab chiqarish rejasi yaratildi.", "success")
            except Exception: db.session.rollback(); flash("Reja kodi takrorlangan yoki ma’lumot noto‘g‘ri.", "danger")
        return redirect(url_for("production"))
    return render_template("production.html", items=ProductionPlan.query.order_by(ProductionPlan.id.desc()).all(), products=Product.query.all())

@app.route("/production/<int:plan_id>/update", methods=["POST"])
@roles_required("admin", "production")
def update_production(plan_id):
    p = db.get_or_404(ProductionPlan, plan_id)
    completed = float(request.form.get("completed_qty") or 0)
    stage = request.form.get("stage", p.stage)
    if completed < p.completed_qty or completed > p.planned_qty or stage not in STAGES:
        flash("Bajarilgan miqdor yoki bosqich noto‘g‘ri.", "danger")
    else:
        p.completed_qty = completed
        if completed == p.planned_qty: p.stage = "Yakunlangan"
        else: p.stage = stage
        db.session.add(ProductionStageHistory(plan=p, stage=p.stage, note=request.form.get("note",""), user_id=current_user.id))
        db.session.commit(); flash("Ishlab chiqarish holati yangilandi.", "success")
    return redirect(url_for("production"))

@app.route("/bom", methods=["GET", "POST"])
@roles_required("admin", "production")
def bom():
    if request.method == "POST":
        item = BOMItem(product_id=int(request.form["product_id"]), material_id=int(request.form["material_id"]), quantity_per_unit=float(request.form["quantity_per_unit"]))
        if item.quantity_per_unit <= 0: flash("Sarf miqdori musbat bo‘lishi kerak.", "danger")
        else:
            db.session.add(item)
            try: db.session.commit(); flash("BOM tarkibiga material qo‘shildi.", "success")
            except Exception: db.session.rollback(); flash("BOM saqlanmadi.", "danger")
        return redirect(url_for("bom"))
    return render_template("bom.html", items=BOMItem.query.all(), products=Product.query.all(), materials=RawMaterial.query.all())

@app.route("/bom/<int:item_id>/delete", methods=["POST"])
@roles_required("admin", "production")
def delete_bom_item(item_id):
    db.session.delete(db.get_or_404(BOMItem, item_id)); db.session.commit()
    flash("BOM elementi o‘chirildi.", "success"); return redirect(url_for("bom"))

@app.route("/production/<int:plan_id>/materials", methods=["GET", "POST"])
@roles_required("admin", "production")
def issue_materials(plan_id):
    plan = db.get_or_404(ProductionPlan, plan_id)
    bom_items = BOMItem.query.filter_by(product_id=plan.product_id).all()
    requirements = [{"material": x.material, "required": x.quantity_per_unit * plan.planned_qty} for x in bom_items]
    if request.method == "POST":
        if plan.materials_issued: flash("Ushbu reja uchun materiallar avval chiqarilgan.", "warning")
        elif not bom_items: flash("Mahsulot uchun BOM mavjud emas.", "danger")
        elif any(x["material"].quantity < x["required"] for x in requirements): flash("Xomashyo yetarli emas. Avval omborni to‘ldiring.", "danger")
        else:
            try:
                for x in requirements:
                    m=x["material"]; qty=x["required"]; m.quantity -= qty
                    db.session.add(InventoryTransaction(material=m, user_id=current_user.id, kind="Chiqim", quantity=qty, note=f"{plan.plan_code} uchun BOM"))
                    db.session.add(MaterialIssue(plan=plan, material=m, quantity=qty))
                plan.materials_issued=True; db.session.commit(); flash("BOM bo‘yicha materiallar chiqarildi.", "success")
            except Exception: db.session.rollback(); flash("Material chiqarishda xatolik.", "danger")
        return redirect(url_for("issue_materials", plan_id=plan.id))
    return render_template("materials_issue.html", plan=plan, requirements=requirements)

@app.route("/orders", methods=["GET", "POST"])
@roles_required("admin", "production")
def orders():
    if request.method == "POST":
        o=CustomerOrder(order_code=request.form["order_code"].strip(), customer_name=request.form["customer_name"].strip(), product_id=int(request.form["product_id"]), quantity=float(request.form["quantity"]), order_date=date.fromisoformat(request.form["order_date"]), delivery_date=date.fromisoformat(request.form["delivery_date"]), status=request.form.get("status","Yangi"))
        db.session.add(o)
        try: db.session.commit(); flash("Buyurtma saqlandi.", "success")
        except Exception: db.session.rollback(); flash("Buyurtma kodi takrorlangan yoki ma’lumot noto‘g‘ri.", "danger")
        return redirect(url_for("orders"))
    return render_template("orders.html", items=CustomerOrder.query.order_by(CustomerOrder.id.desc()).all(), products=Product.query.all())

@app.route("/orders/<int:order_id>/status", methods=["POST"])
@roles_required("admin", "production")
def order_status(order_id):
    o=db.get_or_404(CustomerOrder, order_id); status=request.form.get("status")
    if status in ["Yangi","Jarayonda","Bajarilgan","Bekor qilingan"]:
        o.status=status; db.session.commit(); flash("Buyurtma holati yangilandi.", "success")
    return redirect(url_for("orders"))

@app.route("/monitoring")
@roles_required("admin", "production")
def monitoring():
    items=ProductionPlan.query.order_by(ProductionPlan.end_date).all()
    return render_template("monitoring.html", items=items, today=date.today())

@app.route("/forecasting")
@login_required
def forecasting():
    from sklearn.linear_model import LinearRegression
    import numpy as np
    x=np.arange(1,25).reshape(-1,1)
    y=np.array([42,45,43,49,52,51,55,58,56,61,64,63,67,70,69,74,76,75,80,83,82,86,89,91])
    model=LinearRegression().fit(x,y)
    periods=max(1,min(int(request.args.get("periods", "6")),12))
    future=np.arange(25,25+periods).reshape(-1,1)
    predictions=[max(0,round(float(v),1)) for v in model.predict(future)]
    return render_template("forecasting.html", periods=periods, predictions=predictions, history=y.tolist())

@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html", plans=ProductionPlan.query.all(), materials=RawMaterial.query.all(), orders=CustomerOrder.query.all())

@app.route("/reports/excel")
@login_required
def export_excel():
    from openpyxl import Workbook
    wb=Workbook(); ws=wb.active; ws.title="Ishlab chiqarish"
    ws.append(["Reja kodi","Mahsulot","Reja miqdori","Bajarildi","Qoldiq","Holat"])
    for p in ProductionPlan.query.all(): ws.append([p.plan_code,p.product.name,p.planned_qty,p.completed_qty,p.remaining_qty,p.stage])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width=22
    output=io.BytesIO(); wb.save(output); output.seek(0)
    return send_file(output, as_attachment=True, download_name="ishlab_chiqarish_hisoboti.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/reports/pdf")
@login_required
def export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    output=io.BytesIO(); c=canvas.Canvas(output,pagesize=A4)
    c.setFont("Helvetica-Bold",16); c.drawString(45,800,"Manufacturing Production Report")
    y=765; c.setFont("Helvetica",9)
    for p in ProductionPlan.query.all():
        if y < 55: c.showPage(); y=800; c.setFont("Helvetica",9)
        c.drawString(45,y,f"{p.plan_code} | {p.product.name} | Plan: {p.planned_qty} | Done: {p.completed_qty} | {p.stage}")
        y-=18
    c.save(); output.seek(0)
    return send_file(output, as_attachment=True, download_name="production_report.pdf", mimetype="application/pdf")

@app.route("/users", methods=["GET","POST"])
@roles_required("admin")
def users():
    if request.method=="POST":
        u=User(username=request.form["username"].strip(),full_name=request.form["full_name"].strip(),role=request.form["role"])
        u.set_password(request.form["password"]); db.session.add(u)
        try: db.session.commit(); flash("Foydalanuvchi yaratildi.","success")
        except Exception: db.session.rollback(); flash("Login band yoki ma’lumot noto‘g‘ri.","danger")
        return redirect(url_for("users"))
    return render_template("users.html", items=User.query.all())

@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@roles_required("admin")
def toggle_user(user_id):
    u=db.get_or_404(User,user_id)
    if u.id==current_user.id: flash("O‘z hisobingizni o‘chira olmaysiz.","danger")
    else: u.active=not u.active; db.session.commit(); flash("Foydalanuvchi holati yangilandi.","success")
    return redirect(url_for("users"))

@app.errorhandler(403)
def forbidden(e): return render_template("error.html", code=403, message="Bu sahifaga kirish uchun ruxsatingiz yo‘q."),403
@app.errorhandler(404)
def not_found(e): return render_template("error.html", code=404, message="Sahifa topilmadi."),404

def seed_data():
    if User.query.count(): return
    admin=User(username="admin",full_name="Administrator",role="admin"); admin.set_password("Admin123!")
    prod=User(username="manager",full_name="Ishlab chiqarish menejeri",role="production"); prod.set_password("Manager123!")
    wh=User(username="warehouse",full_name="Ombor menejeri",role="warehouse"); wh.set_password("Warehouse123!")
    db.session.add_all([admin,prod,wh]); db.session.flush()
    products=[Product(code=f"PRD-{i:03}",name=n,category=c,unit="dona",price=50000+i*12000) for i,(n,c) in enumerate([("Ofis stuli","Mebel"),("Ish stoli","Mebel"),("Metall javon","Metall"),("Kompyuter stoli","Mebel"),("Yig‘ma stul","Mebel"),("Oshxona stoli","Mebel"),("Kitob javoni","Mebel"),("Metall shkaf","Metall"),("Operator stoli","Mebel"),("Konferensiya stoli","Mebel")],1)]
    mats=[RawMaterial(code=f"MAT-{i:03}",name=n,unit=u,quantity=q,min_quantity=mn,unit_price=pr) for i,(n,u,q,mn,pr) in enumerate([("Metall profil","kg",800,100,12000),("Plastik detal","kg",300,50,18000),("Mato","metr",500,80,25000),("Vint","dona",5000,500,300),("Yog‘och panel","dona",400,60,45000),("Bo‘yoq","litr",120,20,35000),("Ko‘pik","kg",200,30,16000),("Yelim","kg",90,15,22000),("Qadoqlash","dona",600,100,2500),("Rezina oyoq","dona",1000,150,1200)],1)]
    db.session.add_all(products+mats); db.session.flush()
    for p in products[:5]:
        for m,q in zip(mats[:4],[2,1.5,2,12]):
            db.session.add(BOMItem(product_id=p.id,material_id=m.id,quantity_per_unit=q))
    for i,p in enumerate(products[:8],1):
        plan=ProductionPlan(plan_code=f"PLN-{i:03}",product_id=p.id,planned_qty=100+i*10,completed_qty=(i*8),start_date=date.today()-timedelta(days=i*2),end_date=date.today()+timedelta(days=i*3),stage="Ishlab chiqarilmoqda")
        db.session.add(plan)
    for i,p in enumerate(products[:8],1):
        db.session.add(CustomerOrder(order_code=f"ORD-{i:03}",customer_name=f"Mijoz {i}",product_id=p.id,quantity=20+i*5,order_date=date.today()-timedelta(days=i),delivery_date=date.today()+timedelta(days=i*5),status=["Yangi","Jarayonda","Bajarilgan"][i%3]))
    db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1")
