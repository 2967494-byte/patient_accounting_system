import unittest
from app import create_app, db
from app.models import User, Doctor
from flask_login import login_user

class AdminRouteTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create Admin User
        self.admin = User(username='admin', email='admin@example.com', role='admin')
        self.admin.password_hash = 'hash' # Mock password
        db.session.add(self.admin)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_admin(self):
        with self.client.session_transaction() as sess:
            # Flask-Login uses user_id in session
            sess['_user_id'] = str(self.admin.id)
            sess['_fresh'] = True

    def test_admin_doctors_page(self):
        self.login_admin()
        response = self.client.get('/admin/doctors')
        if response.status_code == 500:
            print("ERROR: /admin/doctors returned 500")
            # In testing, the exception typically propagates or we can see it
        self.assertEqual(response.status_code, 200)

    def test_admin_services_page(self):
        self.login_admin()
        response = self.client.get('/admin/services')
        if response.status_code == 500:
            print("ERROR: /admin/services returned 500")
        self.assertEqual(response.status_code, 200)

    def test_admin_additional_services_page(self):
        self.login_admin()
        response = self.client.get('/admin/additional_services')
        if response.status_code == 500:
            print("ERROR: /admin/additional_services returned 500")
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
