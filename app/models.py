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
    role = db.Column(db.String(20), default='org', nullable=False) # 'superadmin', 'admin', 'manager', 'org', 'lab_tech'
    is_confirmed = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True) # made nullable for existing users or flexible registration
    city_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    center_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinics.id'), nullable=True) # New mapping
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    city = db.relationship('Location', foreign_keys=[city_id])
    center = db.relationship('Location', foreign_keys=[center_id])
    clinic = db.relationship('Clinic', foreign_keys=[clinic_id]) # Relationship
    doctor_details = db.relationship('Doctor', foreign_keys=[doctor_id], backref='user_account')

    def __repr__(self):
        return f'<User {self.username}>'

    def is_admin(self):
        # Maps to Superadmin (Admin Panel Access)
        return self.role == 'superadmin'
    
    def is_administrator(self):
        # Maps to new Admin role (Calendar Access)
        return self.role == 'admin'

    def is_manager(self):
        # Maps to new Manager role (User list management)
        return self.role == 'manager'

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


# Association Object for Main Services
class AppointmentService(db.Model):
    __tablename__ = 'appointment_main_services'
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), primary_key=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), primary_key=True)
    quantity = db.Column(db.Integer, default=1)
    
    service = db.relationship("Service")
    appointment = db.relationship("Appointment", back_populates="service_associations")

# Association Object for Additional Services (keeping table name 'appointment_services' for legacy compat)
class AppointmentAdditionalService(db.Model):
    __tablename__ = 'appointment_services'
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), primary_key=True)
    additional_service_id = db.Column(db.Integer, db.ForeignKey('additional_services.id'), primary_key=True)
    quantity = db.Column(db.Integer, default=1)
    
    additional_service = db.relationship("AdditionalService")
    appointment = db.relationship("Appointment", back_populates="additional_service_associations")

class Patient(db.Model):
    __tablename__ = 'patients'
    
    id = db.Column(db.Integer, primary_key=True)
    surname = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    patronymic = db.Column(db.String(64), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    gender = db.Column(db.String(10), nullable=True) # 'male', 'female'
    birth_date = db.Column(db.Date, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    appointments = db.relationship('Appointment', backref='patient_record', lazy=True)

    @property
    def full_name(self):
        parts = [self.surname, self.name]
        if self.patronymic:
            parts.append(self.patronymic)
        return " ".join(parts)
        
    @property
    def age(self):
        if not self.birth_date:
            return None
        today = datetime.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))

    def to_dict(self):
        return {
            'id': self.id,
            'surname': self.surname,
            'name': self.name,
            'patronymic': self.patronymic,
            'full_name': self.full_name,
            'phone': self.phone,
            'email': self.email,
            'gender': self.gender,
            'birth_date': self.birth_date.strftime('%d.%m.%Y') if self.birth_date else None,
            'age': self.age,
            'comment': self.comment
        }


class Appointment(db.Model):
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(100), nullable=False)
    patient_phone = db.Column(db.String(50), nullable=True) # made nullable just in case
    doctor = db.Column(db.String(100), nullable=True) 
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=True)
    
    # Legacy/Primary service string (for display/search if needed, or migration)
    service = db.Column(db.String(200), nullable=True) 
    
    # New M2M relationship via Association Object
    service_associations = db.relationship('AppointmentService', back_populates='appointment', cascade='all, delete-orphan')
    
    # Helper property to access services directly (Legacy Compat)
    @property
    def services(self):
        return [assoc.service for assoc in self.service_associations]
        
    @services.setter
    def services(self, value):
        self.service_associations = []
        for s in value:
            self.service_associations.append(AppointmentService(service=s, quantity=1))

    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(5), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # made nullable
    clinic_id = db.Column(db.Integer, db.ForeignKey('clinics.id'), nullable=True)
    center_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True) # New Link
    
    contract_number = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Integer, default=1) # Visit quantity (legacy)
    
    # New M2M relationship via Association Object for Additional Services
    additional_service_associations = db.relationship('AppointmentAdditionalService', back_populates='appointment', cascade='all, delete-orphan')
    
    @property
    def additional_services(self):
        return [assoc.additional_service for assoc in self.additional_service_associations]

    @additional_services.setter
    def additional_services(self, value):
        self.additional_service_associations = []
        for s in value:
            self.additional_service_associations.append(AppointmentAdditionalService(additional_service=s, quantity=1))
    
    additional_service_quantity = db.Column(db.Integer, default=1)
    duration = db.Column(db.Integer, default=15) # Duration in minutes (15 or 30)
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
    
    history = db.relationship('AppointmentHistory', backref='appointment', lazy=True, cascade='all, delete-orphan')




    def to_dict(self):
        return {
            'id': self.id,
            'patient_name': self.patient_name,
            'patient_phone': self.patient_phone,
            'patient_id': self.patient_id,
            'duration': self.duration,
            'doctor_id': self.doctor_id, # return ID for form pre-fill
            'doctor_name': self.doctor_rel.name if self.doctor_rel else (self.doctor or 'Unknown'),
            # Include the legacy 'service' string field for frontend display (Dashboard relies on it)
            'service': self.service if self.service else ", ".join([assoc.service.name for assoc in self.service_associations]),
            'services': [{
                'id': assoc.service.id, 
                'name': assoc.service.name, 
                'price': assoc.service.price,
                'parent_id': assoc.service.parent_id,
                'quantity': assoc.quantity
            } for assoc in self.service_associations],
            # Services
            'additional_services': [{
                 'id': assoc.additional_service.id,
                 'name': assoc.additional_service.name,
                 'price': assoc.additional_service.price,
                 'parent_id': assoc.additional_service.parent_id,
                 'quantity': assoc.quantity
            } for assoc in self.additional_service_associations],
             
            'date': self.date.strftime('%Y-%m-%d'),
            'time': self.time,
            'status': 'completed' if self.payment_method_id else 'pending', # Basic status for edit modal (not dashboard logic)
            'payment_method_id': self.payment_method_id,
            'center_id': self.center_id,
            'amount_paid': self.amount_paid,
            'cost': self.cost,
            'discount': self.discount,
            'comment': self.comment,
            'author_name': self.author.username if self.author else 'Unknown',
            'author_role': self.author.role if self.author else 'Unknown', # For permission checks
            'is_restricted': False, # Default, will be overridden by logic if needed
            'is_child': self.is_child,
             # Return history
            'history': [h.to_dict() for h in self.history]
        }

    def to_dict_lite(self):
        """Lighter dictionary for dashboard rendering to avoid N+1"""
        return {
            'id': self.id,
            'patient_name': self.patient_name,
            'patient_phone': self.patient_phone,
            'date': self.date.isoformat(),
            'time': self.time,
            'duration': self.duration or 15,
            'service': self.service,
            'doctor': self.doctor,
            'author_id': self.author_id,
            'author_role': self.author.role if self.author else 'Unknown',
            'payment_method_id': self.payment_method_id,
            'center_id': self.center_id
        }

class AppointmentHistory(db.Model):
    __tablename__ = 'appointment_history'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(50), nullable=True) # e.g. 'created', 'updated'
    
    user = db.relationship('User')

    def to_dict(self):
        return {
            'user': self.user.username if self.user else 'Unknown',
            'action': self.action,
            'timestamp': self.timestamp.isoformat() + 'Z'
        }

# Many-to-Many Association for Doctors and Clinics
doctor_clinics = db.Table('doctor_clinics',
    db.Column('doctor_id', db.Integer, db.ForeignKey('doctors.id'), primary_key=True),
    db.Column('clinic_id', db.Integer, db.ForeignKey('clinics.id'), primary_key=True)
)

class Doctor(db.Model):
    __tablename__ = 'doctors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialization = db.Column(db.String(100), nullable=True)
    manager = db.Column(db.String(100), nullable=True)
    
    # Legacy/Old field pointing to Location (Center)
    clinic_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    bonus_type = db.Column(db.Integer, nullable=True)
    
    # Relationship to Location (Center)
    clinic = db.relationship('Location', foreign_keys=[clinic_id])
    
    # New M2M Relation to Clinics
    clinics = db.relationship('Clinic', secondary=doctor_clinics, backref=db.backref('doctors', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'specialization': self.specialization,
            'manager': self.manager,
            'bonus_type': self.bonus_type,
            'clinics': [c.to_dict() for c in self.clinics]
        }

class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    is_hidden = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=True)
    
    children = db.relationship('Service', backref=db.backref('parent', remote_side=[id]), lazy=True)
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
            
        if self.price > 0:
            return self.price
            
        if self.parent:
            return self.parent.get_price(date_obj)
            
        return self.price

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'price': self.price,
            'parent_id': self.parent_id
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
    parent_id = db.Column(db.Integer, db.ForeignKey('additional_services.id'), nullable=True)
    
    children = db.relationship('AdditionalService', backref=db.backref('parent', remote_side=[id]), lazy=True)
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
            
        if self.price > 0:
            return self.price
            
        if self.parent:
            return self.parent.get_price(date_obj)
            
        return self.price

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'price': self.price,
            'parent_id': self.parent_id
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
    is_cashless = db.Column(db.Boolean, default=False)
    
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
    value = db.Column(db.Text, nullable=True)

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

class BonusPeriod(db.Model):
    __tablename__ = 'bonus_periods'
    
    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    columns = db.Column(db.Integer, default=1)
    
    # Relationship to values
    values = db.relationship('BonusValue', backref='period', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'startDate': self.start_date.isoformat(),
            'endDate': self.end_date.isoformat() if self.end_date else None,
            'columns': self.columns,
            'values': [v.to_dict() for v in self.values]
        }

class BonusValue(db.Model):
    __tablename__ = 'bonus_values'
    
    id = db.Column(db.Integer, primary_key=True)
    period_id = db.Column(db.Integer, db.ForeignKey('bonus_periods.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    column_index = db.Column(db.Integer, nullable=False) 
    value = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            'serviceId': self.service_id,
            'col': self.column_index,
            'val': self.value
        }

class SystemMetrics(db.Model):
    __tablename__ = 'system_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Disk usage
    disk_total_gb = db.Column(db.Float, nullable=False)
    disk_used_gb = db.Column(db.Float, nullable=False)
    disk_percent = db.Column(db.Float, nullable=False)
    
    # System counts
    users_count = db.Column(db.Integer, default=0)
    appointments_count = db.Column(db.Integer, default=0)
    journal_entries_count = db.Column(db.Integer, default=0)
    doctors_count = db.Column(db.Integer, default=0)
    clinics_count = db.Column(db.Integer, default=0)
    organizations_count = db.Column(db.Integer, default=0)
    services_count = db.Column(db.Integer, default=0)
    
    # Resource usage
    cpu_percent = db.Column(db.Float, nullable=True)
    ram_percent = db.Column(db.Float, nullable=True)
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp.isoformat(),
            'disk_total_gb': self.disk_total_gb,
            'disk_used_gb': self.disk_used_gb,
            'disk_percent': self.disk_percent,
            'users_count': self.users_count,
            'appointments_count': self.appointments_count,
            'journal_entries_count': self.journal_entries_count,
            'doctors_count': self.doctors_count,
            'clinics_count': self.clinics_count,
            'organizations_count': self.organizations_count,
            'services_count': self.services_count,
            'cpu_percent': self.cpu_percent,
            'ram_percent': self.ram_percent
        }

class MedicalCertificate(db.Model):
    __tablename__ = 'medical_certificates'
    
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    patient_name = db.Column(db.String(200), nullable=False)
    
    # Manual input fields
    inn = db.Column(db.String(20), nullable=True)  # ИНН
    birth_date = db.Column(db.Date, nullable=True)  # Дата рождения
    doc_series = db.Column(db.String(20), nullable=True)  # Серия документа
    doc_number = db.Column(db.String(20), nullable=True)  # Номер документа
    doc_issue_date = db.Column(db.Date, nullable=True)  # Дата выдачи
    
    # Auto-filled fields
    amount = db.Column(db.Float, default=0.0)  # Сумма
    
    # File info
    filename = db.Column(db.String(255), nullable=False)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Relationships
    appointment = db.relationship('Appointment', backref='certificates')
    created_by = db.relationship('User', backref='created_certificates')
    

    def to_dict(self):
        return {
            'id': self.id,
            'patient_name': self.patient_name,
            'amount': self.amount,
            'filename': self.filename,
            'generated_at': self.generated_at.isoformat(),
            'created_by': self.created_by.username if self.created_by else None
        }

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    
    # Target Logic
    # 'all', 'role:role_name', 'user:user_id'
    target_type = db.Column(db.String(50), nullable=False) 
    target_value = db.Column(db.String(50), nullable=True) # e.g. 'admin' or '15' or NULL for all
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    statuses = db.relationship('NotificationStatus', backref='notification', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Notification {self.title}>'

class NotificationStatus(db.Model):
    __tablename__ = 'notification_statuses'

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notifications.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref='notification_statuses')


class RemoteVM(db.Model):
    __tablename__ = 'remote_vms'
    
    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(128), unique=True) # Selectel UUID 또는 Identifier
    name = db.Column(db.String(64))
    ip_address = db.Column(db.String(45))
    status = db.Column(db.String(20), default='suspended') # 'active', 'suspended', 'starting', 'error'
    guacamole_connection_id = db.Column(db.String(128)) # Connection ID in Guacamole
    last_active = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'ip_address': self.ip_address
        }


class VMSession(db.Model):
    __tablename__ = 'vm_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    vm_id = db.Column(db.Integer, db.ForeignKey('remote_vms.id'), nullable=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref='vm_sessions')
    vm = db.relationship('RemoteVM', backref='active_sessions')
    appointment = db.relationship('Appointment')

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False) # 'error', 'suggestion', 'request', 'other'
    message = db.Column(db.Text, nullable=False)
    screenshot_filename = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='new') # 'new', 'viewed', 'in_progress', 'completed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='support_tickets')

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.username,
            'type': self.type,
            'message': self.message,
            'screenshot': self.screenshot_filename,
            'status': self.status,
            'created_at': self.created_at.strftime('%d.%m.%Y %H:%M')
        }



class ElectronicReferral(db.Model):
    __tablename__ = "electronic_referrals"
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=True)
    comments = db.Column(db.Text, nullable=True)
    form_data = db.Column(db.Text, nullable=True) # Stores JSON representation of selected checkboxes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship("Patient", backref="electronic_referrals")
    doctor = db.relationship("Doctor", backref="electronic_referrals")
    clinic = db.relationship("Clinic", backref="electronic_referrals")
    teeth = db.relationship("ReferralTooth", backref="referral", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "clinic_id": self.clinic_id,
            "comments": self.comments,
            "created_at": self.created_at.isoformat(),
            "teeth": [t.tooth_number for t in self.teeth]
        }

class ReferralTooth(db.Model):
    __tablename__ = "referral_teeth"
    
    id = db.Column(db.Integer, primary_key=True)
    referral_id = db.Column(db.Integer, db.ForeignKey("electronic_referrals.id"), nullable=False)
    tooth_number = db.Column(db.String(10), nullable=False)

