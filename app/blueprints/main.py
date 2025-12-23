from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.models import Location, Organization, Doctor, Service
from app import db
from werkzeug.security import generate_password_hash, check_password_hash

main = Blueprint('main', __name__)

@main.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'change_password':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not check_password_hash(current_user.password_hash, old_password):
                flash('Неверный текущий пароль', 'error')
            elif new_password != confirm_password:
                flash('Новые пароли не совпадают', 'error')
            else:
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash('Пароль успешно изменен', 'success')
                
        else:
            # Update City
            city_id = request.form.get('city_id')
            if city_id:
                 current_user.city_id = int(city_id)
            
            # Update Organization Name
            org_name = request.form.get('organization_name')
            if org_name and current_user.organization:
                 current_user.organization.name = org_name
            
            db.session.commit()
            flash('Профиль обновлен', 'success')
            
        return redirect(url_for('main.profile'))

    cities = Location.query.filter_by(type='city').all()
    return render_template('profile.html', cities=cities)

@main.route('/cabinet')
@login_required
def cabinet():
    # Hardcoded path for demonstration as requested
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(base_dir, 'static', 'uploads', 'Лукоянова_Анастасия_Николаевна', 'ЛУКОЯНОВА АН', 'Data')
    
    dicom_files = []
    if os.path.exists(target_dir):
        files = sorted(os.listdir(target_dir))
        for f in files:
            if f.lower().endswith('.dcm'):
                # Construct relative URL for static file
                # URL path: /static/uploads/...
                url = f"/static/uploads/Лукоянова_Анастасия_Николаевна/ЛУКОЯНОВА АН/Data/{f}"
                dicom_files.append(url)
    
    return render_template('cabinet.html', dicom_files=dicom_files)

@main.route('/')
@login_required
def index():
    return redirect(url_for('main.dashboard'))

@main.route('/dashboard')
@login_required
def dashboard():
    # Calculate dates for the current week (starting Monday)
    start_date_str = request.args.get('start_date')
    if start_date_str:
        try:
            today = datetime.strptime(start_date_str, '%Y-%m-%d')
        except ValueError:
            today = datetime.now()
    else:
        today = datetime.now()
    
    start_of_week = today - timedelta(days=today.weekday())
    
    # Calculate Prev/Next week
    prev_week = (start_of_week - timedelta(weeks=1)).strftime('%Y-%m-%d')
    next_week = (start_of_week + timedelta(weeks=1)).strftime('%Y-%m-%d')

    dates_data = []
    
    days_map = {
        0: 'Понедельник', 1: 'Вторник', 2: 'Среда', 3: 'Четверг',
        4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье'
    }

    for i in range(7):
        current_date = start_of_week + timedelta(days=i)
        dates_data.append({
            'obj': current_date,
            'name': days_map[current_date.weekday()],
            'display_date': current_date.strftime('%d.%m'),
            'iso_date': current_date.strftime('%Y-%m-%d')
        })
    
    # Generate time slots from 8:00 to 19:30 with 15-minute intervals
    start_time = 8 * 60 # 8:00 in minutes
    end_time = 19 * 60 + 30 # 19:30 in minutes
    interval = 15
    
    time_slots = []
    current_time = start_time
    while current_time <= end_time:
        hour = current_time // 60
        minute = current_time % 60
        time_slots.append(f"{hour:02d}:{minute:02d}")
        current_time += interval

    # Restriction for 'org' role: Only show *:15 and *:45 slots
    if current_user.role == 'org':
        time_slots = [t for t in time_slots if t.endswith(':15') or t.endswith(':45')]

    # Centers logic
    centers = []
    current_center_id = None
    
    if current_user.role == 'lab_tech':
        if current_user.center:
            centers = [current_user.center]
            current_center_id = current_user.center_id
        else:
             flash('Ваш аккаунт не привязан к центру. Обратитесь к администратору.', 'error')
    elif current_user.city_id:
        centers = Location.query.filter_by(parent_id=current_user.city_id, type='center').all()
    else:
        flash('Внимание: У вашего пользователя не указан Город. Обратитесь к администратору.', 'warning')
        
    if current_user.role != 'lab_tech':
        center_id_arg = request.args.get('center_id')
        if center_id_arg:
            try:
                current_center_id = int(center_id_arg)
            except ValueError:
                current_center_id = None
            
    # Default to first center if none selected and centers exist
    if not current_center_id and centers:
        current_center_id = centers[0].id

    # Fetch for dropdowns
    doctors = Doctor.query.all()
    services = Service.query.all()

    return render_template('dashboard.html', dates=dates_data, time_slots=time_slots, centers=centers, current_center_id=current_center_id, prev_week=prev_week, next_week=next_week, doctors=doctors, services=services)

@main.route('/journal')
@login_required
def journal():
    if current_user.role == 'org':
        flash('Доступ к журналу запрещен для вашей роли.', 'error')
        return redirect(url_for('main.dashboard'))

    # We still need centers/city context for the header
    centers = []
    current_center_id = None
    
    if current_user.role == 'lab_tech':
        if current_user.center:
            centers = [current_user.center]
            current_center_id = current_user.center_id
        else:
             flash('Ваш аккаунт не привязан к центру. Обратитесь к администратору.', 'error')
    elif current_user.city_id:
        centers = Location.query.filter_by(parent_id=current_user.city_id, type='center').all()
    
    if current_user.role != 'lab_tech':
        center_id_arg = request.args.get('center_id')
        if center_id_arg:
            try:
                current_center_id = int(center_id_arg)
            except ValueError:
                current_center_id = None
            
    # Default to first center if none selected and centers exist
    if not current_center_id and centers:
        current_center_id = centers[0].id

    # Fetch appointments for the journal
    from app.models import Appointment, Service, AdditionalService, Clinic, PaymentMethod, Doctor
    
    date_str = request.args.get('date')
    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            current_date = datetime.now().date()
    else:
        current_date = datetime.now().date()
    
    query = Appointment.query.filter_by(date=current_date)
    
    if current_center_id:
        query = query.filter_by(center_id=current_center_id)
        
    appointments = query.order_by(Appointment.time.asc()).all()
    
    services = Service.query.order_by(Service.name).all()
    additional_services = AdditionalService.query.order_by(AdditionalService.name).all()
    clinics = Clinic.query.order_by(Clinic.name).all()
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.name).all()
    doctors = Doctor.query.order_by(Doctor.name).all()

    # Calculate Summary Stats
    summary_stats = {
        'total_count': 0,
        'total_sum': 0.0,
        'methods': {}
    }

    # Initialize methods dict with all available payment methods
    for pm in payment_methods:
        summary_stats['methods'][pm.name] = {'count': 0, 'sum': 0.0}
    
    # Financial Sum only includes Cash and Card
    FINANCIAL_METHODS = ['наличные', 'карта']

    for appt in appointments:
        summary_stats['total_count'] += 1
        
        val = appt.cost or 0.0
        
        # Check if this appointment counts towards Financial Total Sum
        if appt.payment_method:
             pm_name_lower = appt.payment_method.name.lower().strip()
             if pm_name_lower in FINANCIAL_METHODS:
                 summary_stats['total_sum'] += val
        
             # Breakdown Stats (All methods)
             pm_name = appt.payment_method.name
             if pm_name not in summary_stats['methods']:
                 summary_stats['methods'][pm_name] = {'count': 0, 'sum': 0.0}
             
             summary_stats['methods'][pm_name]['count'] += 1
             
             # Only add to breakdown sum if it's a financial method (or not excluded)
             # User requested "Безнал" row to always show 0.00
             if pm_name_lower in FINANCIAL_METHODS:
                 summary_stats['methods'][pm_name]['sum'] += val

    return render_template('journal.html', centers=centers, current_center_id=current_center_id, appointments=appointments, current_date=current_date.strftime('%Y-%m-%d'), services=services, additional_services=additional_services, clinics=clinics, payment_methods=payment_methods, doctors=doctors, summary_stats=summary_stats)
