from flask import Blueprint, render_template, abort, request, flash, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import User, Location, Doctor, Service, Clinic, Appointment, Patient
from app import db
from flask import jsonify
from app.utils.appointment_logic import get_appointments_with_status_logic
import json

doctor_bp = Blueprint('doctor', __name__, url_prefix='/doctor')

def doctor_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'doctor':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@doctor_bp.before_request
@login_required
def before_request():
    pass

@doctor_bp.route('/')
@doctor_required
def dashboard():
    return render_template('doctor/dashboard.html')

@doctor_bp.route('/patients')
@doctor_required
def patients():
    patients_list = Patient.query.order_by(Patient.surname, Patient.name).all()
    # Or filter by doctor if needed, but for now show all as per "My Patients" context might imply clinic's patients or personal.
    # If "My" implies only those they treated:
    # patients_list = Patient.query.join(Appointment).filter(Appointment.doctor_id == current_user.doctor_id).distinct().all()
    # But for now, let's fetch all to see something.
    patients_list = Patient.query.order_by(Patient.created_at.desc()).all()
    return render_template('doctor/patients.html', patients=patients_list)

@doctor_bp.route('/api/patients/create', methods=['POST'])
@doctor_required
def create_patient():
    data = request.get_json()
    
    # Validation
    required_fields = ['surname', 'name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'success': False, 'error': f'Поле {field} обязательно'}), 400
            
    try:
        birth_date = None
        if data.get('birth_date'):
            birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()
            
        new_patient = Patient(
            surname=data['surname'].strip().title(),
            name=data['name'].strip().title(),
            patronymic=data.get('patronymic', '').strip().title() if data.get('patronymic') else None,
            phone=data.get('phone'),
            email=data.get('email'),
            gender=data.get('gender'),
            birth_date=birth_date,
            comment=data.get('comment')
        )
        
        db.session.add(new_patient)
        db.session.commit()
        
        return jsonify({'success': True, 'patient': new_patient.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@doctor_bp.route('/patients/<int:patient_id>')
@doctor_required
def patient_details(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    # Fetch appointments for history. 
    # Assuming Appointment model has a relationship or we filter by patient_id if added
    # Since I added patient_id to Appointment, I can use relationship if defined, or filter
    appointments = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.date.desc(), Appointment.time.desc()).all()
    
    # Process appointments to get status (using same logic as calendar)
    # Note: get_appointments_with_status_logic returns a list of dictionaries, not objects.
    processed_appointments = get_appointments_with_status_logic(appointments, current_user.role, current_user.id)
    
    # Post-process for template: Convert string date back to object for strftime support
    for appt in processed_appointments:
        if isinstance(appt.get('date'), str):
            try:
                appt['date'] = datetime.strptime(appt['date'], '%Y-%m-%d').date()
            except ValueError:
                pass # Keep as string if parsing fails
    
    return render_template('doctor/patient_details.html', patient=patient, appointments=processed_appointments)

@doctor_bp.route('/orders')
@doctor_required
def orders():
    return render_template('doctor/orders.html')


