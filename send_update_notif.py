from app import create_app, db
from app.models import Notification, NotificationStatus, User

app = create_app()

with app.app_context():
    # 1. Create Notification Object
    title = "Обновление интерфейса"
    message = "Улучшен дизайн выбора филиалов (вкладки заменены на компактные кнопки) и добавлена система важных оповещений от администратора."
    
    # We will simulate sending to 'all' active users for this widespread change
    notif = Notification(
        title=title,
        message=message,
        target_type='all',
        target_value=None, 
        author_id=1 # Assuming ID 1 is superadmin, fallback if not exists logic is skipped for brevity
    )
    
    db.session.add(notif)
    db.session.commit() # Commit to get ID
    
    # 2. Add Status for all active users
    users = User.query.filter_by(is_blocked=False).all()
    count = 0
    for user in users:
        status = NotificationStatus(
            notification_id=notif.id,
            user_id=user.id
        )
        db.session.add(status)
        count += 1
        
    db.session.commit()
    print(f"Notification sent to {count} users.")
