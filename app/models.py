from flask_login import UserMixin
from .extensions import db
from datetime import datetime

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    users = db.relationship('User', backref='organization', lazy=True)

    def __repr__(self):
        return f'<Organization {self.name}>'

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='org', nullable=False) # 'superadmin', 'admin', 'org', 'lab_tech'
    is_confirmed = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True) # made nullable for existing users or flexible registration
    city_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    center_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    city = db.relationship('Location', foreign_keys=[city_id])
    center = db.relationship('Location', foreign_keys=[center_id])

    def __repr__(self):
        return f'<User {self.username}>'

    def is_admin(self):
        # Maps to Superadmin (Admin Panel Access)
        return self.role == 'superadmin'
    
    def is_administrator(self):
        # Maps to new Admin role (Calendar Access)
        return self.role == 'admin'

class Location(db.Model):
    __tablename__ = 'locations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'city' or 'center'
    parent_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    manager = db.Column(db.String(100), nullable=True)
    color = db.Column(db.String(7), default='#3b82f6') # Hex color code
    
    children = db.relationship('Location', backref=db.backref('parent', remote_side=[id]), lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'parent_id': self.parent_id,
            'phone': self.phone,
            'manager': self.manager,
            'color': self.color,
            'children': [child.to_dict() for child in self.children]
        }


appointment_services = db.Table('appointment_services',
    db.Column('appointment_id', db.Integer, db.ForeignKey('appointments.id'), primary_key=True),
    db.Column('additional_service_id', db.Integer, db.ForeignKey('additional_services.id'), primary_key=True)
)

# Association table for Main Services (Research)
appointment_main_services = db.Table('appointment_main_services',
    db.Column('appointment_id', db.Integer, db.ForeignKey('appointments.id'), primary_key=True),
    db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
)

# Existing association for Additional Services (renaming variable for clarity if needed, but keeping table name to avoid migration issues if possible, though table name 'appointment_services' is confusing. 
# It maps to additional_services.id. 
# I will NOT touch the existing 'appointment_services' table definition to avoid breaking existing data/schema unless necessary.
# But I will verify what Appointment uses.

class Appointment(db.Model):
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_phone = db.Column(db.String(50), nullable=True) # made nullable just in case
    doctor = db.Column(db.String(100), nullable=True) 
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    
    # Legacy/Primary service string (for display/search if needed, or migration)
    service = db.Column(db.String(200), nullable=True) 
    
    # New M2M relationship
    services = db.relationship('Service', secondary=appointment_main_services, backref='appointments')

    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(5), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # made nullable
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinics.id'), nullable=True)
    center_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    
    contract_number = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Integer, default=1) # Total quantity of main services? Or just legacy?
    
    # Existing Additional Services Relationship (using the 'appointment_services' table defined previously, or 'appointment_additional_services'?)
    # Line 73 defined `appointment_services` table mapping to `additional_services.id`.
    additional_services = db.relationship('AdditionalService', secondary='appointment_services', backref='appointments')
    
    additional_service_quantity = db.Column(db.Integer, default=1)
    cost = db.Column(db.Float, default=0.0)
    amount_paid = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    comment = db.Column(db.Text, nullable=True)
    
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_methods.id'), nullable=True)
    payment_method = db.relationship('PaymentMethod')

    is_child = db.Column(db.Boolean, default=False)
    lab_tech = db.Column(db.String(100), nullable=True)
    
    author = db.relationship('User', foreign_keys=[author_id])
    doctor_rel = db.relationship('Doctor', backref='appointments')

    lab_tech = db.Column(db.String(100), nullable=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_methods.id'), nullable=True)
    is_child = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id], backref=db.backref('appointments', lazy=True))
    manager = db.relationship('User', foreign_keys=[manager_id], backref=db.backref('managed_appointments', lazy=True))
    clinic = db.relationship('Clinic', foreign_keys=[clinic_id])
    center = db.relationship('Location', foreign_keys=[center_id])
    doctor_rel = db.relationship('Doctor', foreign_keys=[doctor_id])
    payment_method = db.relationship('PaymentMethod', foreign_keys=[payment_method_id])
    additional_services = db.relationship('AdditionalService', secondary=appointment_services, lazy='subquery', backref=db.backref('appointments', lazy=True))
    
    history = db.relationship('AppointmentHistory', backref='appointment', lazy=True, cascade='all, delete-orphan')




    def to_dict(self):
        return {
            'id': self.id,
            'patient_name': self.patient_name,
            'patient_phone': self.patient_phone,
            'doctor_id': self.doctor_id, # return ID for form pre-fill
            'doctor_name': self.doctor_rel.name if self.doctor_rel else (self.doctor or 'Unknown'),
            # Include the legacy 'service' string field for frontend display (Dashboard relies on it)
            'service': self.service if self.service else ", ".join([s.name for s in self.services]),
            'services': [{'id': s.id, 'name': s.name} for s in self.services],
            'date': self.date.isoformat(),
            'time': self.time,
            'doctor': self.doctor, # Return raw doctor string too if needed
            'author_name': self.author.username if self.author else 'Unknown',
            'center_id': self.center_id,
            'center_name': self.center.name if self.center else 'Unknown',
            'history': [{
                'user': h.user.username if h.user else 'Unknown',
                'action': h.action,
                'timestamp': h.timestamp.isoformat()
            } for h in self.history]
        }

class AppointmentHistory(db.Model):
    __tablename__ = 'appointment_history'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(50), nullable=True) # e.g. 'created', 'updated'
    
    user = db.relationship('User')

class Doctor(db.Model):
    __tablename__ = 'doctors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialization = db.Column(db.String(100), nullable=True)
    manager = db.Column(db.String(100), nullable=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)

    clinic = db.relationship('Location', foreign_keys=[clinic_id])

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'specialization': self.specialization,
            'manager': self.manager,
            'clinic_name': self.clinic.name if self.clinic else None
        }

class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    prices = db.relationship('ServicePrice', backref='service', lazy=True, cascade="all, delete-orphan")

    def get_price(self, date_obj=None):
        if not date_obj:
            date_obj = datetime.now().date()
            
        # Find a price override for this date
        # Logic: start_date <= date <= end_date (if end_date exists)
        # or start_date <= date (if end_date is None)
        
        # We sort by id desc to get the most recently created applicable price if overlaps exist (simple logic)
        relevant_price = ServicePrice.query.filter(
            ServicePrice.service_id == self.id,
            ServicePrice.start_date <= date_obj
        ).filter(
            (ServicePrice.end_date >= date_obj) | (ServicePrice.end_date == None)
        ).order_by(ServicePrice.id.desc()).first()
        
        if relevant_price:
            return relevant_price.price
            
        return self.price

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'price': self.price
        }

class ServicePrice(db.Model):
    __tablename__ = 'service_prices'
    
    id = db.Column(db.Integer, primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True) # Nullable means indefinitely valid from start_date


class AdditionalService(db.Model):
    __tablename__ = 'additional_services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    prices = db.relationship('AdditionalServicePrice', backref='additional_service', lazy=True, cascade="all, delete-orphan")

    def get_price(self, date_obj=None):
        if not date_obj:
            date_obj = datetime.now().date()
            
        relevant_price = AdditionalServicePrice.query.filter(
            AdditionalServicePrice.additional_service_id == self.id,
            AdditionalServicePrice.start_date <= date_obj
        ).filter(
            (AdditionalServicePrice.end_date >= date_obj) | (AdditionalServicePrice.end_date == None)
        ).order_by(AdditionalServicePrice.id.desc()).first()
        
        if relevant_price:
            return relevant_price.price
            
        return self.price

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'price': self.price
        }

class AdditionalServicePrice(db.Model):
    __tablename__ = 'additional_service_prices'
    
    id = db.Column(db.Integer, primary_key=True)
    additional_service_id = db.Column(db.Integer, db.ForeignKey('additional_services.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True) # Nullable means indefinitely valid from start_date

class Clinic(db.Model):
    __tablename__ = 'clinics'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    
    city = db.relationship('Location', backref='clinics')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'city_id': self.city_id,
            'city_name': self.city.name if self.city else None,
            'phone': self.phone
        }

class Manager(db.Model):
    __tablename__ = 'managers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

class PaymentMethod(db.Model):
    __tablename__ = 'payment_methods'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

class GlobalSetting(db.Model):
    __tablename__ = 'global_settings'
    
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255), nullable=True)

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Null = to Support
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_messages', lazy=True))
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref=db.backref('received_messages', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.username,
            'recipient_id': self.recipient_id,
            'body': self.body,
            'timestamp': self.timestamp.isoformat(),
            'is_read': self.is_read
        }
