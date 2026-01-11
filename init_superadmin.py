from app import create_app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

def create_superadmin():
    with app.app_context():
        try:
            print("Checking for existing superadmin...")
            admin = User.query.filter_by(role='superadmin').first()
            if admin:
                print(f"Superadmin user already exists: {admin.username}. Checking status...")
                # Continue to update logic
            else:
                print("Superadmin not found. Creating default superadmin user...")
            
            # Check if user 'superadmin' already exists
            user = User.query.filter_by(username='superadmin').first()
            if user:
                print("User 'superadmin' found. Updating role to 'superadmin' and confirming.")
                user.role = 'superadmin'
                user.is_confirmed = True
                user.password_hash = generate_password_hash('superadmin') # Reset password to be sure
            else:
                print("Creating new user 'superadmin' with password 'superadmin'...")
                user = User(
                    username='superadmin',
                    email='superadmin@example.com',
                    password_hash=generate_password_hash('superadmin'),
                    role='superadmin',
                    is_confirmed=True
                )
                db.session.add(user)
            
            db.session.commit()
            print("SUCCESS: Superadmin user ready.")
            print("Login: superadmin")
            print("Password: superadmin")
            
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    create_superadmin()
