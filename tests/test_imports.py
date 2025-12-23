import unittest
import io
from app import create_app, db
from app.models import User, Service, AdditionalService
from flask_login import login_user

class ImportTestCase(unittest.TestCase):
    def setUp(self):
        test_config = {
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False
        }
        self.app = create_app(test_config)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create Admin User
        self.admin = User(username='admin', email='admin@test.com', role='admin')
        self.admin.city_id = None # Optional usually
        db.session.add(self.admin)
        db.session.commit()
        
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_admin(self):
        # We can bypass login creation if we use flask-login's test_client logic or just force session?
        # Standard way:
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id)
            sess['_fresh'] = True

    def test_import_services_csv(self):
        self.login_admin()
        
        # Mock CSV File
        csv_content = "Name,Price\nUzi,1500\nRentgen,2000"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')
        }
        
        response = self.client.post('/admin/services/import', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        s1 = Service.query.filter_by(name='Uzi').first()
        s2 = Service.query.filter_by(name='Rentgen').first()
        
        self.assertIsNotNone(s1)
        self.assertEqual(s1.price, 1500.0)
        self.assertIsNotNone(s2)
        self.assertEqual(s2.price, 2000.0)

    def test_import_additional_services_csv(self):
        self.login_admin()
        
        csv_content = "Name,Price\nSyringe,50\nBandage,100"
        data = {
            'file': (io.BytesIO(csv_content.encode('utf-8')), 'test2.csv')
        }
        
        response = self.client.post('/admin/additional_services/import', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        s1 = AdditionalService.query.filter_by(name='Syringe').first()
        self.assertIsNotNone(s1)
        self.assertEqual(s1.price, 50.0)

if __name__ == '__main__':
    unittest.main()
