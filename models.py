from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="warehouse")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.active

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(140), nullable=False)
    category = db.Column(db.String(80), default="Umumiy")
    description = db.Column(db.Text, default="")
    unit = db.Column(db.String(20), default="dona")
    price = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bom_items = db.relationship("BOMItem", backref="product", cascade="all, delete-orphan")

class RawMaterial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(140), nullable=False)
    unit = db.Column(db.String(20), default="kg")
    quantity = db.Column(db.Float, default=0)
    min_quantity = db.Column(db.Float, default=0)
    unit_price = db.Column(db.Float, default=0)

class BOMItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("raw_material.id"), nullable=False)
    quantity_per_unit = db.Column(db.Float, nullable=False)
    material = db.relationship("RawMaterial")

class ProductionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_code = db.Column(db.String(40), unique=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    planned_qty = db.Column(db.Float, nullable=False)
    completed_qty = db.Column(db.Float, default=0)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    stage = db.Column(db.String(40), default="Rejalashtirilgan")
    notes = db.Column(db.Text, default="")
    materials_issued = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship("Product")
    @property
    def remaining_qty(self):
        return max(0, self.planned_qty - self.completed_qty)
    @property
    def progress(self):
        return round((self.completed_qty / self.planned_qty) * 100, 1) if self.planned_qty else 0

class InventoryTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey("raw_material.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    kind = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    material = db.relationship("RawMaterial")
    user = db.relationship("User")

class MaterialIssue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("production_plan.id"), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey("raw_material.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    plan = db.relationship("ProductionPlan")
    material = db.relationship("RawMaterial")

class CustomerOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(40), unique=True, nullable=False)
    customer_name = db.Column(db.String(140), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    order_date = db.Column(db.Date, nullable=False)
    delivery_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(30), default="Yangi")
    product = db.relationship("Product")

class ProductionStageHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("production_plan.id"), nullable=False)
    stage = db.Column(db.String(40), nullable=False)
    note = db.Column(db.Text, default="")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    plan = db.relationship("ProductionPlan")
    user = db.relationship("User")
