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

@main.route('/support/chat')
@login_required
def chat_dashboard():
    # Allow Superadmin, Admin, LabTech
    if current_user.role not in ['superadmin', 'admin', 'lab_tech']:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('chat_dashboard.html')

@main.context_processor
def inject_chat_settings():
    from app.models import GlobalSetting
    s = GlobalSetting.query.get('chat_image')
    return dict(chat_image=s.value if s else None)
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
    
    # Allow logic to be simpler: If city_id is set, show city centers.
    # User requested 'lab_tech' to see 'all calendars' (presumably all centers in their city, like Admin/Org).
    if current_user.city_id:
        centers = Location.query.filter_by(parent_id=current_user.city_id, type='center').all()
    else:
        # Fallback if no city (e.g. super admin global? or error)
        # For now just warn as before
        if current_user.role != 'admin': # Admin might not have city?
             flash('Внимание: У вашего пользователя не указан Город. Обратитесь к администратору.', 'warning')

    if True: # Always allow selection if centers exist (removed 'if role != lab_tech' block)
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
    if current_user.role in ['org', 'admin']:
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

    # Statistics for Statistics Table (Adults/Children, KT/OPTG)
    summary_stats['adults_count'] = 0
    summary_stats['children_count'] = 0
    summary_stats['kt_count'] = 0
    summary_stats['kt_adults'] = 0
    summary_stats['kt_children'] = 0
    summary_stats['optg_count'] = 0
    summary_stats['optg_adults'] = 0
    summary_stats['optg_children'] = 0

    for appt in appointments:
        # Adults/Children
        if appt.is_child:
            summary_stats['children_count'] += 1
        else:
            summary_stats['adults_count'] += 1
            
        # Services (KT vs OPTG)
        # "КТ" must be in name. Everything else is "ОПТГ".
        # Check quantity
        qty = appt.quantity if appt.quantity else 1
        
        # Helper to categorize service name
        def categorize_service(name, is_child):
            if not name: return
            if 'КТ' in name or 'KT' in name: # Check Cyrillic and Latin just in case (though requirement said "КТ")
                 summary_stats['kt_count'] += qty
                 if is_child:
                     summary_stats['kt_children'] += qty
                 else:
                     summary_stats['kt_adults'] += qty
            else:
                 summary_stats['optg_count'] += qty
                 if is_child:
                     summary_stats['optg_children'] += qty
                 else:
                     summary_stats['optg_adults'] += qty

        if appt.services:
            for s in appt.services:
                categorize_service(s.name, appt.is_child)
        elif appt.service:
             categorize_service(appt.service, appt.is_child)

    # Filter for "Select Appointment" modal: Only show appointments that are NOT "registered" (no payment method)
    # This prevents creating duplicates if the user thinks of "Journal" as "Completed" 
    # and "Appointment" as "Scheduled".
    unregistered_appointments = [a for a in appointments if a.payment_method_id is None]
    
    # Filter for Journal Table: Only show "registered" appointments (those with a payment method)
    # This solves the issue where "Booked" appointments appearing in the Journal were being 
    # deleted by the user, accidentally removing the Calendar event.
    registered_appointments = [a for a in appointments if a.payment_method_id is not None]

    return render_template('journal.html', centers=centers, current_center_id=current_center_id, todays_appointments=unregistered_appointments, appointments=registered_appointments, current_date=current_date, services=services, additional_services=additional_services, clinics=clinics, payment_methods=payment_methods, doctors=doctors, summary_stats=summary_stats)
