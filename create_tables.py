from app import create_app, db
from app.models import Notification, NotificationStatus

app = create_app()

with app.app_context():
    # This will create tables for models that are defined but don't exist in DB
    db.create_all()
    print("Database tables created successfully.")
