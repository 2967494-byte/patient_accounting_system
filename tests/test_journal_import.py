
import unittest
import io
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import openpyxl
from datetime import datetime
from app import create_app, db
from app.models import User, Service, Doctor, Clinic, PaymentMethod, Appointment, Location
from flask_login import login_user

class JournalImportTestCase(unittest.TestCase):
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
        db.session.add(self.admin)
        
        # Create Center
        self.center = Location(name="Test Center", type="center")
        db.session.add(self.center)
        db.session.commit() # ID 1
        
        
        # Create City
        self.city = Location(name="Test City", type="city")
        db.session.add(self.city)
        db.session.commit()

        # Create Entities for Resolution
        self.service = Service(name="Test Service", price=1000.0)
        self.doctor = Doctor(name="Dr. Test")
        self.clinic = Clinic(name="Test Clinic", city_id=self.city.id)
        self.pm = PaymentMethod(name="Cash")
        
        db.session.add_all([self.service, self.doctor, self.clinic, self.pm])
        db.session.commit()
        
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(self.admin.id)
            sess['_fresh'] = True

    def create_test_excel(self):
        # Create a real Excel file in memory
        output = io.BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        # Header
        ws.append(['Дата', 'Месяц', 'Лаборант', 'Договор', 'ФИО Пациента', 'Ребенок', 'ФИО Врача', 'Менеджер', 'Клиника', 'Исследование', 'Доп.услуги', 'Кол-во', 'Ст.доп', 'Стоимость', 'Оплата', 'Скидка', 'Сумма', 'Комметарий'])
        
        # Data Row
        # Date=Today, LabTech=Tech1, Contract=123, Patient=John Doe, Child=FALSE, Doctor=Dr. Test, Clinic=Test Clinic, Service=Test Service, Qty=2, Discount=100, Payment=Cash, Comment=Note
        ws.append([
            datetime.now().date(), # 0 Date
            'October', # 1 Month (ignored)
            'Tech1', # 2 Lab Tech
            '123', # 3 Contract
            'John Doe', # 4 Patient
            'FALSE', # 5 Child
            'Dr. Test', # 6 Doctor
            '', # Manager
            'Test Clinic', # 8 Clinic
            'Test Service', # 9 Service
            '', # Add Svc
            2, # 11 Qty
            '', # Add Svc Qty
            '2000', # 13 Cost (Should be ignored by import logic, calc used instead)
            'Cash', # 14 Payment
            100, # 15 Discount
            '1900', # 16 Sum (Ignored)
            'Note' # 17 Comment
        ])
        
        wb.save(output)
        output.seek(0)
        return output

    def test_import_journal_success(self):
        self.login_admin()
        
        excel_file = self.create_test_excel()
        data = {
            'file': (excel_file, 'import.xlsx'),
            'center_id': self.center.id
        }
        
        response = self.client.post('/admin/journal/import', data=data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Assertions
        appt = Appointment.query.first()
        self.assertIsNotNone(appt)
        self.assertEqual(appt.patient_name, 'John Doe')
        self.assertEqual(appt.doctor, 'Dr. Test')
        self.assertEqual(appt.service, 'Test Service')
        self.assertEqual(appt.quantity, 2)
        
        # Cost Calc: (Price * Qty) - Discount = (1000 * 2) - 100 = 1900
        self.assertEqual(appt.cost, 1900.0)
        
        # Relations
        self.assertEqual(appt.clinic_id, self.clinic.id)
        self.assertEqual(appt.doctor_id, self.doctor.id)
        self.assertEqual(appt.payment_method_id, self.pm.id)
        self.assertEqual(appt.center_id, self.center.id)
        
        # Comment + Lab Tech
        self.assertIn('Note', appt.comment)
        self.assertEqual(appt.lab_tech, 'Tech1')
        self.assertNotIn('Лаборант:', appt.comment) # Should NOT be in comment anymore

if __name__ == '__main__':
    unittest.main()
