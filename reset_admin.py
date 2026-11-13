
from app import app
from models import db, User

with app.app_context():
    admin = User.query.filter_by(username="admin").first()

    if admin is None:
        admin = User(
            username="admin",
            full_name="Administrator",
            role="admin",
            active=True
        )
        db.session.add(admin)

    admin.set_password("Admin123!")
    admin.active = True
    admin.role = "admin"

    db.session.commit()

    print("Admin hisobi muvaffaqiyatli yaratildi yoki tiklandi!")
    print("Login: admin")
    print("Parol: Admin123!")
