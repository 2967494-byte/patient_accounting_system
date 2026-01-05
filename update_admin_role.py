from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if u:
        u.role = 'superadmin'
        db.session.commit()
        print(f"User {u.username} updated to {u.role}")
    else:
        print("User admin not found")
