import unittest
from app import create_app, db
from app.models import Doctor, Service, AdditionalService

class ModelTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory DB for testing
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_doctor_creation(self):
        doctor = Doctor(name="Dr. Test", specialization="General")
        db.session.add(doctor)
        db.session.commit()
        
        retrieved = Doctor.query.first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Dr. Test")
        self.assertEqual(retrieved.specialization, "General")

    def test_service_creation(self):
        service = Service(name="Test Service", price=100.0)
        db.session.add(service)
        db.session.commit()
        
        retrieved = Service.query.first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Test Service")
        self.assertEqual(retrieved.price, 100.0)

    def test_additional_service_creation(self):
        service = AdditionalService(name="Extra Test", price=50.0)
        db.session.add(service)
        db.session.commit()
        
        retrieved = AdditionalService.query.first()
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Extra Test")
        self.assertEqual(retrieved.price, 50.0)

if __name__ == '__main__':
    unittest.main()
