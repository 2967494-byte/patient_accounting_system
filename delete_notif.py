from app import create_app, db
from app.models import Notification, NotificationStatus

app = create_app()

with app.app_context():
    # Find the notification by title
    notif = Notification.query.filter_by(title="Обновление интерфейса").first()
    
    if notif:
        # Statuses are deleted by cascade usually, but let's be explicit or rely on cascade
        db.session.delete(notif)
        db.session.commit()
        print(f"Notification '{notif.title}' deleted successfully.")
    else:
        print("Notification not found.")
