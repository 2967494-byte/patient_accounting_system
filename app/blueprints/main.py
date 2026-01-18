from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, abort, current_app, send_file
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from app.models import Location, Organization, Doctor, Service, Appointment, AdditionalService, Clinic, PaymentMethod, GlobalSetting, MedicalCertificate, NotificationStatus
from app import db
from app.extensions import csrf
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import extract
import os
import random
import base64
from PIL import Image, ImageEnhance, ImageFilter

def to_base64_src(filename):
    if not filename: return None
    try:
        # Static folder path correction
        abspath = os.path.join(current_app.static_folder, filename)
        if not os.path.exists(abspath):
            # Try without leading slash if present
            alt_path = os.path.join(current_app.static_folder, filename.lstrip('/'))
            if os.path.exists(alt_path):
                abspath = alt_path
            else:
                print(f"DEBUG: Base64 fail - {abspath} not found")
                return None
        with open(abspath, 'rb') as f:
            b64data = base64.b64encode(f.read()).decode('utf-8')
            ext = filename.split('.')[-1].lower()
            mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png' if ext == 'png' else 'image/gif' if ext == 'gif' else 'application/octet-stream'
            return f"data:{mime};base64,{b64data}"
    except Exception as e:
        print(f"DEBUG: Base64 error for {filename}: {e}")
        return None

main = Blueprint('main', __name__)

def calculate_stats(appointments, breakdown_by=None):
    # breakdown_by: 'day' (for month view) or 'month' (for year view)
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.name).all()
    
    summary_stats = {
        'total_count': 0,
        'total_sum': 0.0,
        'methods': {},
        'breakdown': []
    }

    # Initialize methods dict
    for pm in payment_methods:
        summary_stats['methods'][pm.name] = {'count': 0, 'sum': 0.0}
    
    FINANCIAL_METHODS = ['наличные', 'карта']
    
    summary_stats.update({
        'adults_count': 0, 'children_count': 0,
        'kt_count': 0, 'kt_adults': 0, 'kt_children': 0,
        'optg_count': 0, 'optg_adults': 0, 'optg_children': 0
    })

    # Prepare breakdown aggregation
    breakdown_map = {} # Key: date/month -> stats dict

    for appt in appointments:
        # --- Totals ---
        summary_stats['total_count'] += 1
        val = (appt.cost or 0.0)
        
        pm_name_lower = ''
        pm_name = ''
        if appt.payment_method:
             pm_name_lower = appt.payment_method.name.lower().strip()
             pm_name = appt.payment_method.name
             
             if pm_name_lower in FINANCIAL_METHODS:
                 summary_stats['total_sum'] += val
        
             if pm_name not in summary_stats['methods']:
                 summary_stats['methods'][pm_name] = {'count': 0, 'sum': 0.0}
             
             summary_stats['methods'][pm_name]['count'] += 1
             
             if pm_name_lower in FINANCIAL_METHODS:
                 summary_stats['methods'][pm_name]['sum'] += val

        if appt.is_child:
            summary_stats['children_count'] += 1
        else:
            summary_stats['adults_count'] += 1
            
        qty = appt.quantity if appt.quantity else 1
        
        def categorize_service(name, is_child, stats_dict):
             if not name: return
             if 'КТ' in name or 'KT' in name:
                 stats_dict['kt_count'] += qty
                 if is_child: stats_dict['kt_children'] += qty
                 else: stats_dict['kt_adults'] += qty
             else:
                 stats_dict['optg_count'] += qty
                 if is_child: stats_dict['optg_children'] += qty
                 else: stats_dict['optg_adults'] += qty

        # Do main categorization for summary
        if appt.services:
            for s in appt.services: categorize_service(s.name, appt.is_child, summary_stats)
        elif appt.service:
             categorize_service(appt.service, appt.is_child, summary_stats)

        # --- Breakdown Logic ---
        if breakdown_by:
            key = None
            label = None
            sort_key = None
            
            if breakdown_by == 'day':
                # Group by Day: "DD.MM"
                key = appt.date.strftime('%d.%m')
                label = key
                sort_key = appt.date
            elif breakdown_by == 'month':
                # Group by Month: "MonthName"
                month_names = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
                m = appt.date.month
                key = m
                label = month_names[m]
                sort_key = m
            
            if key not in breakdown_map:
                breakdown_map[key] = {
                    'label': label,
                    'sort_key': sort_key,
                    'total_count': 0, 'total_sum': 0.0,
                    'cash_count': 0, 'cash_sum': 0.0,
                    'card_count': 0, 'card_sum': 0.0,
                    'cashless_count': 0, 'cashless_sum': 0.0,
                    'free_count': 0, 'free_sum': 0.0,
                    'adults': 0, 'children': 0
                }
            
            s = breakdown_map[key]
            s['total_count'] += 1
            if pm_name_lower in FINANCIAL_METHODS:
                 s['total_sum'] += val
            
            # Payment Buckets
            if pm_name_lower == 'наличные':
                s['cash_count'] += 1; s['cash_sum'] += val
            elif pm_name_lower == 'карта':
                s['card_count'] += 1; s['card_sum'] += val
            elif 'безнал' in pm_name_lower:
                s['cashless_count'] += 1; s['cashless_sum'] += val
            elif 'б/п' in pm_name_lower or 'бесплатно' in pm_name_lower:
                s['free_count'] += 1; s['free_sum'] += val # Sum likely 0
            
            # Demographics
            if appt.is_child: s['children'] += 1
            else: s['adults'] += 1

    if breakdown_by:
        summary_stats['breakdown'] = sorted(breakdown_map.values(), key=lambda x: x['sort_key'])
             
    return summary_stats

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

@main.route('/statistics')
@login_required
def statistics():
    # Allow Superadmin and LabTech
    if current_user.role not in ['superadmin', 'lab_tech']:
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Context (Center logic)
    current_center_id = None
    if current_user.role == 'lab_tech':
        if current_user.center:
            current_center_id = current_user.center_id
        else:
             flash('Ваш аккаунт не привязан к центру.', 'error')
    elif current_user.city_id:
        pass # Admin/Superadmin context could be broader, but usually filtered by center selector if implemented. 
             # For now, let's assume current_user's center or handle all?
             # Requirement says "available to lab tech of this center and superadmin".
             # If superadmin, maybe show selector? Or just all? 
             # Let's stick to "Center" based statistics.
             # If superadmin visits, we might need a center selector, but user just said "filters year/month".
             # Getting data for *current_center* seems appropriate if passed, or all?
             # "Statistics ... center" implies specific center.
    
    # To keep it simple and consistent with Dashboard/Journal:
    # We check if there is a center_id arg, otherwise default.
    
    centers = []
    if current_user.role == 'lab_tech':
         if current_user.center: centers = [current_user.center]
    elif current_user.city_id:
         centers = Location.query.filter_by(parent_id=current_user.city_id, type='center').all()
    
    center_id_arg = request.args.get('center_id')
    if center_id_arg:
        try:
            current_center_id = int(center_id_arg)
        except ValueError:
            current_center_id = None
            
    if not current_center_id and centers:
        current_center_id = centers[0].id
        
    # Date Filtering
    current_year = (datetime.utcnow() + timedelta(hours=3)).year
    current_month = (datetime.utcnow() + timedelta(hours=3)).month
    
    selected_year = request.args.get('year', type=int, default=current_year)
    selected_month = request.args.get('month', type=int, default=None) # None = All Year
    
    # Query
    query = Appointment.query
    
    if current_center_id:
        query = query.filter_by(center_id=current_center_id)
        
    # Filter by Year
    query = query.filter(extract('year', Appointment.date) == selected_year)
    
    # Filter by Month if selected
    if selected_month:
        query = query.filter(extract('month', Appointment.date) == selected_month)
        
    appointments = query.all()
    
    breakdown_by = 'day' if selected_month else 'month'
    summary_stats = calculate_stats(appointments, breakdown_by=breakdown_by)
    
    # Years for selector (2024 to current + 1)
    years = range(2024, (datetime.utcnow() + timedelta(hours=3)).year + 2)
    
    return render_template('statistics.html', 
                           summary_stats=summary_stats, 
                           centers=centers, 
                           current_center_id=current_center_id,
                           selected_year=selected_year,
                           selected_month=selected_month,
                           years=years,
                           months=range(1, 13),
                           breakdown_by=breakdown_by,
                           appointments=appointments)

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
            today = (datetime.utcnow() + timedelta(hours=3))
    else:
        today = (datetime.utcnow() + timedelta(hours=3))
    
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
        
        # Exclude Lunch Break (13:00 - 14:00)
        # Skip 13:00, 13:15, 13:30, 13:45
        if hour == 13:
            current_time += interval
            continue

        time_slots.append(f"{hour:02d}:{minute:02d}")
        current_time += interval

    # Restriction for 'org' and 'doctor' roles: Only show *:15 and *:45 slots
    if current_user.role in ['org', 'doctor']:
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

    # Fetch for dropdowns - Sorted Alphabetically
    # Fetch for dropdowns - Sorted Alphabetically
    doctors = Doctor.query.order_by(Doctor.name).all()
    # Filter hidden services for new appointments
    # Use isnot(True) to include False and NULL (existing records)
    services = Service.query.filter(Service.is_hidden.isnot(True)).order_by(Service.name).all()
    clinics = Clinic.query.order_by(Clinic.name).all()

    # Pass current actual date for highlighting
    today_iso = (datetime.utcnow() + timedelta(hours=3)).strftime('%Y-%m-%d')
    
    # Calculate current time slot (nearest 15 minutes breakdown)
    now = (datetime.utcnow() + timedelta(hours=3))
    # Round down to nearest 15
    minute_floored = (now.minute // 15) * 15
    current_time_slot = f"{now.hour:02d}:{minute_floored:02d}"

    # Pre-render initial appointments for instant loading
    initial_appts = []
    if current_center_id:
        end_of_week = start_of_week + timedelta(days=7)
        from sqlalchemy.orm import joinedload
        query = Appointment.query.options(joinedload(Appointment.author)).filter_by(center_id=current_center_id)\
                .filter(Appointment.date >= start_of_week.date(), Appointment.date < end_of_week.date())
        

        
        raw_appts = query.all()
        from app.utils.appointment_logic import get_appointments_with_status_logic
        initial_appts = get_appointments_with_status_logic(raw_appts, current_user.role, current_user.id)

    import json
    initial_appointments_json = json.dumps(initial_appts)

    return render_template('dashboard.html', 
                          dates=dates_data, 
                          time_slots=time_slots, 
                          centers=centers, 
                          current_center_id=current_center_id, 
                          prev_week=prev_week, 
                          next_week=next_week, 
                          doctors=doctors, 
                          services=services, 
                          clinics=clinics, 
                          today_iso=today_iso, 
                          current_time_slot=current_time_slot,
                          initial_appointments=initial_appointments_json)

@main.route('/journal')
@login_required
def journal():
    if current_user.role in ['org', 'admin', 'doctor']:
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
            current_date = (datetime.utcnow() + timedelta(hours=3)).date()
    else:
        current_date = (datetime.utcnow() + timedelta(hours=3)).date()
    
    query = Appointment.query.filter_by(date=current_date)
    
    if current_center_id:
        query = query.filter_by(center_id=current_center_id)
        
    appointments = query.order_by(Appointment.time.asc()).all()
    
    # Filter hidden services for editor dropdowns
    services = Service.query.filter(Service.is_hidden.isnot(True)).order_by(Service.name).all()
    additional_services = AdditionalService.query.order_by(AdditionalService.name).all()
    clinics = Clinic.query.order_by(Clinic.name).all()
    payment_methods = PaymentMethod.query.order_by(PaymentMethod.name).all()
    doctors = Doctor.query.order_by(Doctor.name).all()

    # Filter for "Select Appointment" modal: Only show appointments that are NOT "registered" (no payment method)
    # This prevents creating duplicates if the user thinks of "Journal" as "Completed" 
    # and "Appointment" as "Scheduled".
    unregistered_appointments = [a for a in appointments if a.payment_method_id is None]
    
    # Filter for Journal Table: Only show "registered" appointments (those with a payment method)
    # This solves the issue where "Booked" appointments appearing in the Journal were being 
    # deleted by the user, accidentally removing the Calendar event.
    registered_appointments = [a for a in appointments if a.payment_method_id is not None]

    summary_stats = calculate_stats(registered_appointments)

    # Determine Lab Tech name from entries
    lab_tech_name = None
    if registered_appointments:
        # Try to find the first non-empty lab_tech field
        for appt in registered_appointments:
            if appt.lab_tech:
                lab_tech_name = appt.lab_tech
                break
        
        # Fallback: if no lab_tech string, check if author is lab_tech
        if not lab_tech_name:
             for appt in registered_appointments:
                 if appt.author and appt.author.role == 'lab_tech':
                     lab_tech_name = appt.author.username
                     break

    return render_template('journal.html', centers=centers, current_center_id=current_center_id, todays_appointments=unregistered_appointments, appointments=registered_appointments, current_date=current_date, services=services, additional_services=additional_services, clinics=clinics, payment_methods=payment_methods, doctors=doctors, summary_stats=summary_stats, lab_tech_name=lab_tech_name)


# ========== Stamp Tool Routes ==========

@main.route('/stamp-tool')
@login_required
def stamp_tool():
    """Render the document stamp tool page"""
    stamp_setting = GlobalSetting.query.get('stamp_image')
    stamp_image = stamp_setting.value if stamp_setting else None
    
    current_center_id = request.args.get('center_id', type=int)
    centers = Location.query.filter_by(type='center').all()
    
    return render_template('admin_stamp_tool.html', stamp_image=stamp_image, centers=centers, current_center_id=current_center_id)


@main.route('/stamp-tool/template-image')
@login_required
def get_certificate_template():
    """Serve certificate template image for calibration"""
    template_path = os.path.join(current_app.root_path, '..', 'orbital logo files', 'Без заказчика.png')
    if not os.path.exists(template_path):
        abort(404)
    return send_file(template_path, mimetype='image/png')


@main.route('/stamp-tool/upload', methods=['POST'])
@login_required
@csrf.exempt
def stamp_tool_upload():
    """Upload and convert PDF document to PNG images"""
    from pdf2image import convert_from_path
    import tempfile
    import uuid
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Invalid file format. Only PDF files are supported'}), 400
    
    try:
        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp()
        session_id = str(uuid.uuid4())
        
        # Save uploaded PDF file
        filename = secure_filename(file.filename)
        pdf_path = os.path.join(temp_dir, filename)
        file.save(pdf_path)
        
        # Create output directory for this session
        output_dir = os.path.join(current_app.static_folder, 'uploads', 'temp_docs', session_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert PDF to images using poppler
        images = convert_from_path(pdf_path, dpi=200)
        
        page_paths = []
        for i, image in enumerate(images):
            page_filename = f'page_{i+1}.png'
            page_path = os.path.join(output_dir, page_filename)
            image.save(page_path, 'PNG')
            page_paths.append(f'static/uploads/temp_docs/{session_id}/{page_filename}')
        
        # Clean up temp directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'pages': page_paths,
            'total_pages': len(page_paths)
        })
            
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500


@main.route('/stamp-tool/apply-stamp', methods=['POST'])
@login_required
@csrf.exempt
def stamp_tool_apply_stamp():
    """Apply stamp to document page and return PNG"""
    from PIL import Image
    
    data = request.get_json()
    session_id = data.get('session_id')
    page_index = data.get('page_index', 0)
    stamp_x = data.get('stamp_x', 100)
    stamp_y = data.get('stamp_y', 100)
    stamp_size = data.get('stamp_size', 150)
    rotation = data.get('rotation', 0)
    
    if not session_id:
        return jsonify({'error': 'No session ID provided'}), 400
    
    try:
        # Get stamp image
        stamp_setting = GlobalSetting.query.get('stamp_image')
        if not stamp_setting or not stamp_setting.value:
            return jsonify({'error': 'No stamp image uploaded'}), 400
        
        stamp_path = os.path.join(current_app.static_folder, stamp_setting.value)
        
        # Get document page
        page_filename = f'page_{page_index + 1}.png'
        doc_page_path = os.path.join(current_app.static_folder, 'uploads', 'temp_docs', session_id, page_filename)
        
        if not os.path.exists(doc_page_path):
            return jsonify({'error': 'Document page not found'}), 404
        
        # Open images
        doc_image = Image.open(doc_page_path).convert('RGBA')
        stamp_image = Image.open(stamp_path).convert('RGBA')
        
        # Resize stamp
        stamp_image = stamp_image.resize((stamp_size, stamp_size), Image.Resampling.LANCZOS)
        
        # Rotate stamp if needed
        if rotation != 0:
            stamp_image = stamp_image.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
        
        # Create a copy of document image
        result = doc_image.copy()
        
        # Paste stamp at specified position
        result.paste(stamp_image, (int(stamp_x), int(stamp_y)), stamp_image)
        
        # Save result
        output_filename = f'stamped_page_{page_index + 1}.png'
        output_path = os.path.join(current_app.static_folder, 'uploads', 'temp_docs', session_id, output_filename)
        result.save(output_path, 'PNG')
        
        return jsonify({
            'success': True,
            'output_path': f'static/uploads/temp_docs/{session_id}/{output_filename}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Stamp application failed: {str(e)}'}), 500


# ========== Medical Certificate Generator ==========

@main.route('/stamp-tool/patients', methods=['GET'])
@login_required
def get_patients_for_certificate():
    """Generic search for appointments by Year + Query for Certificate Tool"""
    try:
        year = request.args.get('year', type=int)
        query_str = request.args.get('query', type=str, default='').strip()
        
        if not year:
            return jsonify({'success': False, 'error': 'Year is required'})

        # Base query
        query = Appointment.query
        
        # Filter by Year
        start_date = date(year, 1, 1)
        end_date = date(year + 1, 1, 1)
        query = query.filter(Appointment.date >= start_date, Appointment.date < end_date)

        # Filter by Search Query (Patient Name)
        if query_str:
            query = query.filter(Appointment.patient_name.ilike(f'%{query_str}%'))
        
        # FILTER: Only show appointments that are creating "Journal entries"
        # i.e., have a payment method selected (Paid or Free).
        # Unregistered/Calendar-only appointments should not appear.
        query = query.filter(Appointment.payment_method_id.isnot(None))

        # Security/Scope: If not superadmin/admin, restrict to own center?
        # User said "Remove center choice at top", implying global search is desired or user has specific rights?
        # Assuming existing logic: if user is 'org', restrict to org's clinics/centers? 
        # For now, let's keep it open or restrict by current_user's center if they aren't admin.
        if not current_user.is_admin() and not current_user.is_administrator() and current_user.role != 'lab_tech':
             # If simple user, maybe restrict? 
             # The tool is for 'admin_stamp_tool', usually accessed by admins/lab_techs.
             if current_user.center_id:
                  query = query.filter(Appointment.center_id == current_user.center_id)

        appointments = query.order_by(Appointment.date.desc()).limit(200).all()
        
        results = []
        for apt in appointments:
            # Determine service name
            service_name = apt.service
            if not service_name and apt.service_associations:
                service_name = ", ".join([a.service.name for a in apt.service_associations])
            
            # Cost Calculation Logic:
            # 1. If method is "Free" (Б/П) -> 0
            # 2. If 'amount_paid' is recorded (>0) -> Use it
            # 3. Fallback to 'cost' (price list)
            
            pm_name_lower = apt.payment_method.name.lower() if apt.payment_method else ""
            
            final_cost = apt.cost
            if 'б/п' in pm_name_lower:
                final_cost = 0
            elif apt.amount_paid and apt.amount_paid > 0:
                final_cost = apt.amount_paid
            
            results.append({
                'id': apt.id,
                'date': apt.date.strftime('%d.%m.%Y'),
                'patient_name': apt.patient_name,
                'center_name': apt.center.name if apt.center else '-',
                'service': service_name or '-',
                'cost': final_cost,
                # hidden data for filing
                'inn': apt.patient_record.inn if apt.patient_record and hasattr(apt.patient_record, 'inn') else '', # Model might not have INN yet, handled in frontend manual input
                'birth_date': apt.patient_record.birth_date.strftime('%Y-%m-%d') if apt.patient_record and apt.patient_record.birth_date else ''
            })
            
        return jsonify({'success': True, 'appointments': results})
            
        return jsonify({'success': True, 'appointments': results})
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@main.route('/stamp-tool/certificate/edit/<int:appointment_id>')
@login_required
def certificate_edit(appointment_id):
    """Render the interactive certificate editor with pre-filled data"""
    appointment = Appointment.query.get_or_404(appointment_id)
    
    # Split name parts
    full_name = appointment.patient_name or ""
    parts = full_name.split()
    surname = parts[0].upper() if len(parts) > 0 else ""
    name = parts[1].upper() if len(parts) > 1 else ""
    patronymic = parts[2].upper() if len(parts) > 2 else ""
    
    # Look for previous certificate for this patient to pre-fill INN, Birth Date, etc.
    prev_cert = MedicalCertificate.query.filter_by(patient_name=appointment.patient_name).order_by(MedicalCertificate.generated_at.desc()).first()
    
    c_date = date.today()

    # Priority: Query params > Previous certificate data
    q_inn = request.args.get('inn')
    q_b_date = request.args.get('b_date') # YYYY-MM-DD
    q_series = request.args.get('series')
    q_number = request.args.get('number')
    q_issue_date = request.args.get('issue_date') # YYYY-MM-DD
    q_form_type = request.args.get('form_type', 'knd1151156') # Default to original
    
    # Payer specific args
    q_payer_fio = request.args.get('payer_fio')
    q_payer_inn = request.args.get('payer_inn')
    q_payer_b_date = request.args.get('payer_b_date')
    q_payer_series = request.args.get('payer_series')
    q_payer_number = request.args.get('payer_number')
    q_payer_issue_date = request.args.get('payer_issue_date')

    # Process dates checking for both Patient and Payer
    b_day = b_month = b_year = ""
    # Payer dates
    payer_b_day = payer_b_month = payer_b_year = ""
    if q_payer_b_date:
        try:
             pb = datetime.strptime(q_payer_b_date, '%Y-%m-%d')
             payer_b_day = pb.strftime('%d')
             payer_b_month = pb.strftime('%m')
             payer_b_year = pb.strftime('%Y')
        except: pass
    
    if q_b_date:
        try:
            bd = datetime.strptime(q_b_date, '%Y-%m-%d')
            b_day = bd.strftime('%d')
            b_month = bd.strftime('%m')
            b_year = bd.strftime('%Y')
        except: pass
    elif prev_cert and prev_cert.birth_date:
        b_day = prev_cert.birth_date.strftime('%d')
        b_month = prev_cert.birth_date.strftime('%m')
        b_year = prev_cert.birth_date.strftime('%Y')

    i_day = i_month = i_year = ""
    if q_issue_date:
        try:
            idat = datetime.strptime(q_issue_date, '%Y-%m-%d')
            i_day = idat.strftime('%d')
            i_month = idat.strftime('%m')
            i_year = idat.strftime('%Y')
        except: pass

    # Payer Issue Date
    payer_i_day = payer_i_month = payer_i_year = ""
    if q_payer_issue_date:
        try:
             pidat = datetime.strptime(q_payer_issue_date, '%Y-%m-%d')
             payer_i_day = pidat.strftime('%d')
             payer_i_month = pidat.strftime('%m')
             payer_i_year = pidat.strftime('%Y')
        except: pass

    # Process document info
    doc_info = ""
    if q_series or q_number:
        doc_info = (q_series or "") + (q_number or "")
    elif prev_cert and prev_cert.doc_series:
        doc_info = f"{prev_cert.doc_series}{prev_cert.doc_number}".strip()

    # Process amount
    total_amount_override = request.args.get('total_amount', type=float)
    
    if total_amount_override is not None:
        amount_val = total_amount_override
    else:
        amount_val = appointment.cost or 0
        
    cost_str = f"{amount_val:.2f}"
    rub, kop = cost_str.split('.')
    rub_formatted = str(int(rub)).ljust(13, '-') # Left align and pad with dashes to 13 cells

    # Fetch stamp image from GlobalSetting
    stamp_setting = GlobalSetting.query.get('stamp_image')
    stamp_path = stamp_setting.value if stamp_setting else 'uploads/stamps/orbital_stamp.png'
    
    patient_data = {
        'surname': surname,
        'name': name,
        'patronymic': patronymic,
        'inn': q_inn if q_inn else (prev_cert.inn if prev_cert and prev_cert.inn else ""),
        'b_day': b_day,
        'b_month': b_month,
        'b_year': b_year,
        'i_day': i_day,
        'i_month': i_month,
        'i_year': i_year,
        'doc_info': doc_info,
        'amount': rub_formatted,
        'amount_kop': kop,
        'amount_raw': f"{amount_val:.2f}",
        'c_day': c_date.strftime('%d'),
        'c_month': c_date.strftime('%m'),
        'c_year': c_date.strftime('%Y'),
        'exam_year': str(appointment.date.year),
        'contract_no': appointment.contract_number or "",
        'stamp': '1',
        'stamp_url': url_for('static', filename=stamp_path, _external=True)
    }

    # Split Payer Name
    payer_surname = payer_name = payer_patronymic = ""
    if q_payer_fio:
        parts = q_payer_fio.split()
        payer_surname = parts[0].upper() if len(parts) > 0 else ""
        payer_name = parts[1].upper() if len(parts) > 1 else ""
        payer_patronymic = parts[2].upper() if len(parts) > 2 else ""

    payer_doc_info = (q_payer_series or "") + " " + (q_payer_number or "")

    payer_data = {
        'surname': payer_surname,
        'name': payer_name,
        'patronymic': payer_patronymic,
        'inn': q_payer_inn or "",
        'b_day': payer_b_day,
        'b_month': payer_b_month,
        'b_year': payer_b_year,
        'i_day': payer_i_day,
        'i_month': payer_i_month,
        'i_year': payer_i_year,
        'doc_info': payer_doc_info.strip()
    }
    
    is_op = (q_form_type == 'knd1151156_op')
    bg_filename = 'uploads/stampz_page-0001.jpg' if is_op else 'uploads/certificate_bg.png'
    bg_filename_p2 = 'uploads/stampz_page-0002.jpg' if is_op else None

    return render_template('certificate_editor.html', 
                          appointment_id=appointment_id, 
                          patient_data=patient_data,
                          payer_data=payer_data,
                          form_type=q_form_type,
                          bg_url=url_for('static', filename=bg_filename),
                          bg_url_p2=url_for('static', filename=bg_filename_p2) if bg_filename_p2 else None)


@main.route('/stamp-tool/certificate/generate', methods=['POST'])
@login_required
def generate_certificate():
    """Receive form data and generate JPEG using Playwright"""
    try:
        from playwright.sync_api import sync_playwright
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        form_data = data.get('form_data', {})
        
        appointment = Appointment.query.get_or_404(appointment_id)
        
        # Fetch stamp image from GlobalSetting
        stamp_setting = GlobalSetting.query.get('stamp_image')
        stamp_path = stamp_setting.value if stamp_setting else 'uploads/stamps/orbital_stamp.png'
        
        # Prepare render data for Playwright
        is_op = (data.get('form_type') == 'knd1151156_op')
        
        bg_filename = 'uploads/stampz_page-0001.jpg' if is_op else 'uploads/certificate_bg.png'
        bg_filename_p2 = 'uploads/stampz_page-0002.jpg' if is_op else None
        
        render_data = {
            'form_data': form_data,
            'calibration': data.get('calibration', {'x': 0, 'y': 0}),
            'bg_url': to_base64_src(bg_filename),
            'bg_url_p2': to_base64_src(bg_filename_p2) if bg_filename_p2 else None,
            'stamp_url': to_base64_src(stamp_path),
            'is_op': is_op
        }
        
        # We need a tiny template strictly for Playwright to "Photograph"
        render_data['form_type'] = data.get('form_type')
        html_to_screenshot = render_template('certificate_render.html', **render_data)
        
        # Save temp HTML
        temp_dir = os.path.join(current_app.static_folder, 'uploads', 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_html_path = os.path.join(temp_dir, f'render_{int(datetime.now().timestamp())}.html')
        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_to_screenshot)
            
        # Prepare output paths
        cert_dir = os.path.join(current_app.static_folder, 'uploads', 'certificates')
        os.makedirs(cert_dir, exist_ok=True)
        
        safe_name = "".join([c for c in appointment.patient_name if c.isalnum() or c in (' ', '_')]).rstrip()
        timestamp = int(datetime.now().timestamp())
        
        is_op = (data.get('form_type') == 'knd1151156_op')
        
        final_filename = f'cert_{safe_name}_{timestamp}.jpg'
        final_filepath = os.path.join(cert_dir, final_filename)
        
        captured_images = []

        import time
        with sync_playwright() as p:
            print(f"DEBUG: Launching Playwright for form_type: {data.get('form_type')}")
            browser = p.chromium.launch()
            # Viewport height double if OP
            v_height = 3170 if is_op else 1585
            page = browser.new_page(viewport={'width': 1121, 'height': v_height})
            
            # Use absolute path for file://
            file_url = 'file:///' + temp_html_path.replace('\\', '/')
            print(f"DEBUG: Navigating to {file_url}")
            page.goto(file_url)
            
            # Wait for network idle AND a small buffer for rendering
            page.wait_for_load_state('networkidle') 
            print("DEBUG: Network idle reached, waiting 1.5s for rendering...")
            time.sleep(1.5) 
            
            if is_op:
                # Capture 2 pages separately
                print("DEBUG: Capturing 2-page OP form...")
                # Page 1
                p1_path = os.path.join(temp_dir, f'p1_{timestamp}.jpg')
                page.screenshot(path=p1_path, type='jpeg', quality=95, clip={'x':0, 'y':0, 'width':1121, 'height':1585})
                captured_images.append(p1_path)
                
                # Page 2
                p2_path = os.path.join(temp_dir, f'p2_{timestamp}.jpg')
                page.screenshot(path=p2_path, type='jpeg', quality=95, clip={'x':0, 'y':1585, 'width':1121, 'height':1585})
                captured_images.append(p2_path)
            else:
                # Single capture
                print("DEBUG: Capturing single-page form...")
                p1_path = os.path.join(temp_dir, f'p1_{timestamp}.jpg')
                page.screenshot(path=p1_path, type='jpeg', quality=95)
                captured_images.append(p1_path)

            browser.close()
            
        # Post-process images
        processed_pil_images = []
        for img_path in captured_images:
            try:
                with Image.open(img_path) as img:
                    img = img.convert('RGB')
                    # 1. Subtle random rotation
                    angle = random.uniform(-0.3, 0.3)
                    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor='white')
                    
                    # 2. Enhance contrast
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(1.1)
                    
                    # 3. Adjust brightness
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(0.98)
                    
                    # 4. Filter
                    img = img.filter(ImageFilter.GaussianBlur(radius=0.1))
                    
                    # Store in memory for PDF saving or save back
                    # We need to copy it to keep it open in memory or save to temp
                    # For PDF list we need open images
                    processed_pil_images.append(img.copy())
            except Exception as e:
                print(f"Img process error: {e}")

        # Save File and Records
        download_urls = []
        if processed_pil_images:
            if is_op and len(processed_pil_images) >= 2:
                # Save both pages to disk
                p1_filename = f'cert_{safe_name}_{timestamp}_p1.jpg'
                p2_filename = f'cert_{safe_name}_{timestamp}_p2.jpg'
                
                processed_pil_images[0].save(os.path.join(cert_dir, p1_filename), "JPEG", quality=90)
                processed_pil_images[1].save(os.path.join(cert_dir, p2_filename), "JPEG", quality=90)
                
                # Create SINGLE record with joined filenames
                new_cert = MedicalCertificate(
                    appointment_id=appointment.id,
                    patient_name=appointment.patient_name,
                    filename=f"{p1_filename}|{p2_filename}",
                    created_by_id=current_user.id,
                    amount=appointment.cost or 0
                )
                db.session.add(new_cert)
                db.session.commit()
                
                download_urls = [
                    url_for('static', filename=f'uploads/certificates/{p1_filename}'),
                    url_for('static', filename=f'uploads/certificates/{p2_filename}')
                ]
                print(f"DEBUG: Saved 2 pages into one record: {new_cert.filename}")
            else:
                # Save single page
                processed_pil_images[0].save(final_filepath, "JPEG", quality=90)
                new_cert = MedicalCertificate(
                    appointment_id=appointment.id,
                    patient_name=appointment.patient_name,
                    filename=final_filename,
                    created_by_id=current_user.id,
                    amount=appointment.cost or 0
                )
                db.session.add(new_cert)
                db.session.commit()
                download_urls = [url_for('static', filename=f'uploads/certificates/{final_filename}')]
                print(f"DEBUG: Saved single-page JPEG to {final_filepath}")
            
        # Cleanup temp
        os.remove(temp_html_path)
        for p in captured_images:
             if os.path.exists(p): os.remove(p)

        return jsonify({
            'success': True, 
            'download_urls': download_urls,
            'download_url': download_urls[0] if download_urls else None # for compatibility
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/stamp-tool/certificate/<int:cert_id>/download')
@login_required
def download_certificate(cert_id):
    """Download generated certificate (handles multi-page via page query param)"""
    cert = MedicalCertificate.query.get_or_404(cert_id)
    page = request.args.get('page', 0, type=int)
    
    filenames = cert.filename.split('|')
    if page >= len(filenames):
        page = 0
        
    filename = filenames[page]
    filepath = os.path.join(current_app.static_folder, 'uploads', 'certificates', filename)
    
    if not os.path.exists(filepath):
        abort(404)
    
    suffix = f"_p{page+1}" if len(filenames) > 1 else ""
    return send_file(filepath, as_attachment=True, download_name=f'certificate_{cert.patient_name}{suffix}_{cert.id}.jpg')


@main.route('/stamp-tool/certificates', methods=['GET'])
@login_required
def list_certificates():
    """List generated certificates"""
    certificates = MedicalCertificate.query.order_by(
        MedicalCertificate.generated_at.desc()
    ).limit(50).all()
    
    return jsonify({
        'success': True,
        'certificates': [cert.to_dict() for cert in certificates]
    })


@main.route('/stamp-tool/certificate/<int:cert_id>/delete', methods=['POST'])
@login_required
def delete_certificate(cert_id):
    """Delete a generated certificate"""
    cert = MedicalCertificate.query.get_or_404(cert_id)
    
    # Delete file if exists
    if cert.filename:
        filepath = os.path.join(current_app.static_folder, 'uploads', 'certificates', cert.filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"[WARN] Could not delete cert file: {e}")
    
    db.session.delete(cert)
    db.session.commit()
    
    return jsonify({'success': True})
@main.route('/notifications/read/<int:status_id>', methods=['POST'])
@login_required
def read_notification(status_id):
    status = NotificationStatus.query.get(status_id)
    if status and status.user_id == current_user.id:
        status.is_read = True
        status.read_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 403
