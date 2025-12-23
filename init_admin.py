from app import create_app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash

app = create_app()

def create_admin():
    with app.app_context():
        try:
            print("Checking for existing admin...")
            admin = User.query.filter_by(role='admin').first()
            if admin:
                print(f"SUCCESS: Admin user already exists: {admin.username}")
                return

            print("Admin not found. Creating default admin user...")
            
            # Check if default 'admin' user exists but isn't marked as admin
            user = User.query.filter_by(username='admin').first()
            if user:
                print("User 'admin' found. Updating role to 'admin'.")
                user.role = 'admin'
            else:
                print("Creating new user 'admin' with password 'admin'...")
                user = User(
                    username='admin',
                    email='admin@example.com',
                    password_hash=generate_password_hash('admin'),
                    role='admin'
                )
                db.session.add(user)
            
            db.session.commit()
            print("SUCCESS: Admin user ready.")
            print("Login: admin")
            print("Password: admin")
            
        except Exception as e:
            print(f"ERROR: {e}")
            print("\nThe database might be missing tables.")
            print("Please run: python -m flask db upgrade")

if __name__ == "__main__":
    create_admin()
