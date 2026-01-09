from app import create_app, db
from app.models import PaymentMethod

app = create_app()
with app.app_context():
    methods = PaymentMethod.query.all()
    print("--- Payment Methods ---")
    for pm in methods:
        print(f"ID: {pm.id}, Name: '{pm.name}'")
