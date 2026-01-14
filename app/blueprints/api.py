from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models import Appointment, Service, AdditionalService, AppointmentService, AppointmentAdditionalService, Doctor, Clinic
from datetime import datetime, timedelta

api = Blueprint('api', __name__)

@api.route('/appointments', methods=['POST'])
@login_required # Ensure user is logged in
def create_appointment():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No input data provided'}), 400
            
        # If user sends `quantity`, it applies to the primary service or all? 
        # For now, let's assume quantity applies to the VISIT (so usually 1).
        quantity = int(data.get('quantity', 1))

        # Main Services handling
        service_associations_to_add = []
        services_for_name_str = []
        primary_service_name = ""
        
        # 1. New Format: services_data
        if 'services_data' in data:
            for item in data['services_data']:
                svc = Service.query.get(item['id'])
                if svc:
                    qty = int(item.get('quantity', 1))
                    service_associations_to_add.append(AppointmentService(service=svc, quantity=qty))
                    services_for_name_str.append(svc)
        
        # 2. Legacy Format: services_ids (fallback if no services_data)
        elif 'services_ids' in data and isinstance(data['services_ids'], list):
            for s_id in data['services_ids']:
                svc = Service.query.get(s_id)
                if svc:
                    qty = int(data.get('quantity', 1)) 
                    service_associations_to_add.append(AppointmentService(service=svc, quantity=qty))
                    services_for_name_str.append(svc)
        
        # 3. Last resort: 'service' field (might be Name)
        elif 'service' in data:
            svc = Service.query.filter_by(name=data['service']).first()
            if svc:
                qty = int(data.get('quantity', 1))
                service_associations_to_add.append(AppointmentService(service=svc, quantity=qty))
                services_for_name_str.append(svc)
            else:
                primary_service_name = data['service']

        # Construct helper string for display
        if services_for_name_str:
             primary_service_name = "\n".join([s.name for s in services_for_name_str])

        # Create Appointment
        # Helper to treat empty strings as None
        def safe_int(val):
            if val == '' or val is None:
                return None
            return int(val)
        
        # New: Overlap Check
        def check_overlap(date_obj, time_str, duration_mins, center_id_chk, exclude_id=None):
            if not center_id_chk: return None
            
            # Helper to minutes
            def t_to_m(t):
                try:
                    parts = t.split(':')
                    return int(parts[0]) * 60 + int(parts[1])
                except:
                    return 0

            start_m = t_to_m(time_str)
            end_m = start_m + duration_mins
            
            print(f"DEBUG: Create Check. Date={date_obj}, Center={center_id_chk}, Start={start_m}, Dur={duration_mins}")

            existing_appts = Appointment.query.filter_by(
                date=date_obj,
                center_id=center_id_chk
            ).all()
            
            for ex in existing_appts:
                if exclude_id and str(ex.id) == str(exclude_id): continue
                
                ex_start = t_to_m(ex.time)
                ex_dur = (ex.duration or 15)
                ex_end = ex_start + ex_dur
                
                if (ex_end > start_m) and (ex_start < end_m):
                    clinic_name = ex.clinic.name if ex.clinic else "Unknown Clinic"
                    debug_msg = f"Conflict: Requested {time_str} overlaps with Accession #{ex.contract_number or ex.id} at {ex.time} ({clinic_name})"
                    print(debug_msg)
                    return debug_msg 
            return False

        duration = 30 if data.get('is_double_time') else 15
        
        # Validate Overlap (unless handled elsewhere, e.g. journal)
        if not data.get('ignore_overlap'):
            result = check_overlap(
                datetime.strptime(data['date'], '%Y-%m-%d').date(),
                data.get('time', '09:00'),
                duration,
                safe_int(data.get('center_id'))
            )
            if result:
                 # error message is in result if true (string is truthy)
                 msg = result if isinstance(result, str) else 'Выбранный интервал пересекается с существующей записью'
                 return jsonify({'error': msg}), 400

        appointment = Appointment(
            center_id=safe_int(data.get('center_id')),
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            time=data.get('time', '09:00'),
            patient_name=data['patient_name'].strip().title() if data['patient_name'] else '',
            patient_phone=data.get('patient_phone', ''),
            clinic_id=safe_int(data.get('clinic_id')),
            doctor_id=safe_int(data.get('doctor_id')),
            service=primary_service_name, # joined names
            quantity=quantity,
            contract_number=data.get('contract_number'),
            payment_method_id=safe_int(data.get('payment_method_id')),
            discount=float(data.get('discount', 0) or 0),
            comment=data.get('comment'),
            is_child=data.get('is_child', False),
            duration=duration,
            author_id=current_user.id
        )

        # ASSIGN RELATIONS DIRECTLY (Fixes "Not Saving" issue)
        appointment.service_associations = service_associations_to_add

        # Handle Additional Services
        additional_assoc_to_add = []
        if 'additional_services_data' in data:
             for item in data['additional_services_data']:
                svc = AdditionalService.query.get(item['id'])
                if svc:
                    qty = int(item.get('quantity', 1))
                    additional_assoc_to_add.append(AppointmentAdditionalService(additional_service=svc, quantity=qty))
                    
        elif 'additional_services_ids' in data and isinstance(data['additional_services_ids'], list):
            for as_id in data['additional_services_ids']:
                add_svc = AdditionalService.query.get(as_id)
                if add_svc:
                     qty = int(data.get('additional_service_quantity', 1))
                     additional_assoc_to_add.append(AppointmentAdditionalService(additional_service=add_svc, quantity=qty))
            
        elif 'additional_service' in data and data['additional_service']:
            # Legacy/Fallback
            add_svc = AdditionalService.query.get(data['additional_service'])
            if add_svc:
                qty = int(data.get('additional_service_quantity', 1))
                additional_assoc_to_add.append(AppointmentAdditionalService(additional_service=add_svc, quantity=qty))

        appointment.additional_service_associations = additional_assoc_to_add
        
        # Calculate Cost using associations
        total_service_cost = sum([assoc.service.price * assoc.quantity for assoc in appointment.service_associations])
        total_add_cost = sum([assoc.additional_service.price * assoc.quantity for assoc in appointment.additional_service_associations])
        
        raw_cost = total_service_cost + total_add_cost - appointment.discount
        if raw_cost < 0: raw_cost = 0
        
        # Payment Method Check (Free)
        if appointment.payment_method:
             pm_name = appointment.payment_method.name.lower()
             if pm_name not in ['наличные', 'карта']:
                 raw_cost = 0
        
        appointment.cost = raw_cost

        db.session.add(appointment)
        db.session.flush() # get ID

        # Log History
        from app.models import AppointmentHistory
        history = AppointmentHistory(
            appointment_id=appointment.id,
            user_id=current_user.id,
            action='Создание',
            timestamp=(datetime.utcnow() + timedelta(hours=3))
        )
        db.session.add(history)

        db.session.commit()

        return jsonify(appointment.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api.errorhandler(400)
def handle_400_error(e):
    return jsonify({'error': 'Bad Request', 'message': str(e)}), 400

@api.errorhandler(401)
def handle_401_error(e):
    # If session expired, return JSON so JS can redirect or show clear error
    return jsonify({'error': 'Unauthorized', 'message': 'Session expired or login required'}), 401

@api.errorhandler(403)
def handle_403_error(e):
    return jsonify({'error': 'Forbidden', 'message': str(e)}), 403

@api.errorhandler(404)
def handle_404_error(e):
    return jsonify({'error': 'Not Found', 'message': str(e)}), 404

@api.errorhandler(500)
def handle_500_error(e):
    # This might capture Blueprint local errors
    return jsonify({'error': 'Internal Server Error', 'message': 'An unexpected error occurred'}), 500

from flask_wtf.csrf import CSRFError
@api.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({'error': 'CSRF Error', 'message': e.description}), 400

@api.route('/appointments', methods=['GET'])
@login_required
def get_appointments():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    clinic_id_str = request.args.get('clinic_id')

    query = Appointment.query

    if clinic_id_str:
         try:
             cid = int(clinic_id_str)
             query = query.filter(
                 (Appointment.clinic_id == cid) | (Appointment.clinic_id == None)
             )
         except ValueError:
             pass
    
    center_id_str = request.args.get('center_id')
    
    if center_id_str and center_id_str != 'null':
         try:
             query = query.filter_by(center_id=int(center_id_str))
         except ValueError:
             pass
    
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        query = query.filter(Appointment.date >= start_date)
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        query = query.filter(Appointment.date <= end_date)

    appointments = query.all()
    
    from app.utils.appointment_logic import get_appointments_with_status_logic
    results = get_appointments_with_status_logic(appointments, current_user.role, current_user.id)

    return jsonify(results)

@api.route('/appointments/<int:id>', methods=['GET'])
@login_required
def get_appointment_detail(id):
    appt = Appointment.query.get_or_404(id)
    
    # Restriction check
    # Org sees only own. Admin/Superadmin/LabTech sees all (LabTech logic handled elsewhere? need to check)
    if current_user.role == 'org' and appt.author_id != current_user.id:
        # Return limited or 403?
        # For editing, they likely shouldn't be able to fetch if they can't edit.
        return jsonify({'error': 'Unauthorized'}), 403

    data = appt.to_dict()
    # Add lists of IDs for multi-selects
    data['services_ids'] = [s.id for s in appt.services]
    data['additional_services_ids'] = [s.id for s in appt.additional_services]
    
    # Ensure clinic name is present (helper for display if needed)
    data['clinic_name'] = appt.clinic.name if appt.clinic else ""
    
    # Add missing fields for editing
    data['contract_number'] = appt.contract_number
    data['is_child'] = appt.is_child
    data['clinic_id'] = appt.clinic_id
    data['doctor_id'] = appt.doctor_id
    data['payment_method_id'] = appt.payment_method_id
    data['discount'] = appt.discount
    data['comment'] = appt.comment
    
    return jsonify(data)

@api.route('/appointments/<int:id>', methods=['PUT'])
@login_required
def update_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    
    data = request.get_json()
    
    # Helper to treat empty strings as None
    def safe_int(val):
        if val == '' or val is None:
            return None
        return int(val)

    if 'is_double_time' in data or 'time' in data or 'date' in data or 'center_id' in data:
        new_duration = 30 if data.get('is_double_time') else 15
        appointment.duration = new_duration
        
        chk_date = datetime.strptime(data['date'], '%Y-%m-%d').date() if 'date' in data else appointment.date
        chk_center_id = safe_int(data['center_id']) if 'center_id' in data else appointment.center_id
        chk_time = data['time'] if 'time' in data else appointment.time
        
        # Optimization: Only check if parameters actually changed vs current stored state
        # Note: appointment.time might be "09:00" vs data "9:00", we should normalize or just check logic.
        # We assume checking is cheap enough, but effectively we want to avoid False Positives on "Self".
        
        # Logic:
        # If I am at 09:00 (15m). I save 09:00 (15m).
        # Overlap check loop excludes MY ID.
        # It should return False.
        # If it returns True, it implies it found SOMETHING ELSE.
        
        # But to be safe and avoid issues, we can skip if identical.
        # But comparing times strings is risky if formats differ.
        # Let's trust the exclusion logic BUT print debug info if collision occurs.

        def check_overlap_upd(date_obj, time_str, duration_mins, center_id_chk, exclude_id):
            if not center_id_chk: return None
            def t_to_m(t):
                try:
                    # Handle HH:MM:SS by taking first 2 parts
                    parts = t.split(':')
                    return int(parts[0]) * 60 + int(parts[1])
                except:
                    return 0

            start_m = t_to_m(time_str)
            end_m = start_m + duration_mins
            
            print(f"DEBUG: Check Overlap. Date={date_obj}, Center={center_id_chk}, Start={start_m}, Dur={duration_mins}, ExcludeID={exclude_id}")

            existing_appts = Appointment.query.filter_by(date=date_obj, center_id=center_id_chk).all()
            for ex in existing_appts:
                if str(ex.id) == str(exclude_id): 
                    # print(f"DEBUG: Skipping self {ex.id}")
                    continue
                
                ex_start = t_to_m(ex.time)
                ex_dur = (ex.duration or 15)
                ex_end = ex_start + ex_dur
                
                if (ex_end > start_m) and (ex_start < end_m):
                    clinic_name = ex.clinic.name if ex.clinic else "Unknown Clinic"
                    debug_msg = f"Conflict: Custom ID {exclude_id} ({time_str} - {duration_mins}) overlaps with Existing ID {ex.id} ({ex.time}) at {clinic_name}"
                    print(debug_msg)
                    return debug_msg 
            return False

        if not data.get('ignore_overlap'):
            result = check_overlap_upd(chk_date, chk_time, new_duration, chk_center_id, appointment.id)
            if result:
                 # error message is in result if true (string is truthy)
                 msg = result if isinstance(result, str) else 'Выбранный интервал пересекается с существующей записью'
                 # return jsonify({'error': msg}), 400
                 # EDIT: User requested Journal bypass. For calendar, it should still block. 
                 # But if bypass flag is present (from Journal JS), we skip.
                 return jsonify({'error': msg}), 400
    
                 return jsonify({'error': msg}), 400
    
    if 'patient_name' in data: appointment.patient_name = data['patient_name'].strip().title()
    if 'patient_phone' in data: appointment.patient_phone = data['patient_phone']
    if 'patient_phone' in data: appointment.patient_phone = data['patient_phone']
    
    # Update doctor and clinic (IDs preferred)
    if 'doctor_id' in data: 
        appointment.doctor_id = safe_int(data['doctor_id'])
        # Also update legacy string if needed, or leave it to be resolved via relation
        # But if we want consistent string for legacy views:
        doc = Doctor.query.get(appointment.doctor_id) if appointment.doctor_id else None
        if doc: appointment.doctor = doc.name
        elif data.get('doctor'): appointment.doctor = data['doctor'] # fallback text
    
    if 'clinic_id' in data: appointment.clinic_id = safe_int(data['clinic_id'])

    if 'date' in data: appointment.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    # Duplicate 'doctor' assignment removed/cleaned up below
    if 'doctor' in data: appointment.doctor = data['doctor']
    
    # Update Service String AND Relationship if name provided but IDs not provided
    if 'service' in data: 
        appointment.service = data['service']
        
        # If services_ids NOT provided, try to validly link this service by name
        if 'services_ids' not in data:
             svc = Service.query.filter_by(name=data['service']).first()
             if svc:
                 appointment.services = [svc]
             else:
                 appointment.services = []

    if 'date' in data and data['date']:
        try:
            appointment.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    
    if 'time' in data and data['time']:
        appointment.time = data['time']

    if 'center_id' in data:
         try:
             cid = safe_int(data['center_id'])
             appointment.center_id = cid
         except (ValueError, TypeError):
             pass # or return error
    
    if 'contract_number' in data: appointment.contract_number = data['contract_number']
    # clinic_id and doctor_id handled above, but ensure no double overwrite with unsafe values if repeated keys exist
    # (The original code had duplicates, correcting here by relying on checks above or safe safe_int if repeated)
    
    if 'quantity' in data: appointment.quantity = int(data.get('quantity') or 1)
    if 'cost' in data: appointment.cost = float(data['cost'])
    if 'payment_method_id' in data: appointment.payment_method_id = safe_int(data['payment_method_id'])
    if 'discount' in data: appointment.discount = float(data['discount'])
    if 'comment' in data: appointment.comment = data['comment']
    if 'is_child' in data: appointment.is_child = bool(data['is_child'])

    # Handle Services (M2M) with Quantities
    if 'services_ids' in data and 'services_data' not in data: # Legacy/Simple ID list fallback
        appointment.service_associations = [] # Clear existing
        for sid in data['services_ids']:
             svc = Service.query.get(sid)
             if svc:
                 # Use global quantity if provided, else 1
                 qty = int(data.get('quantity', 1)) 
                 appointment.service_associations.append(AppointmentService(service=svc, quantity=qty))
                 
    # New format: List of objects {id: 1, quantity: 2}
    if 'services_data' in data:
        appointment.service_associations = []
        for item in data['services_data']:
            svc = Service.query.get(item['id'])
            if svc:
                qty = int(item.get('quantity', 1))
                appointment.service_associations.append(AppointmentService(service=svc, quantity=qty))

    # Handle Additional Services with Quantities
    if 'additional_services_ids' in data and 'additional_services_data' not in data: # Legacy
        appointment.additional_service_associations = []
        for sid in data['additional_services_ids']:
            svc = AdditionalService.query.get(sid)
            if svc:
                # Use global additional quantity if provided, else 1
                qty = int(data.get('additional_service_quantity', 1))
                appointment.additional_service_associations.append(AppointmentAdditionalService(additional_service=svc, quantity=qty))

    if 'additional_services_data' in data:
        appointment.additional_service_associations = []
        for item in data['additional_services_data']:
            svc = AdditionalService.query.get(item['id'])
            if svc:
                qty = int(item.get('quantity', 1))
                appointment.additional_service_associations.append(AppointmentAdditionalService(additional_service=svc, quantity=qty))

    # Log Update History
    from app.models import AppointmentHistory
    history = AppointmentHistory(
        appointment_id=appointment.id,
        user_id=current_user.id,
        action='Изменение',
        timestamp=(datetime.utcnow() + timedelta(hours=3))
    )
    db.session.add(history)

    db.session.commit()
    return jsonify(appointment.to_dict())

@api.route('/appointments/<int:id>', methods=['DELETE'])
@login_required
def delete_appointment(id):
    appointment = Appointment.query.get_or_404(id)
    
    # Ownership/Role check? (Assuming Org admins can delete their own orgs data, Admin everyone)
    if current_user.role == 'org' and appointment.author_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        db.session.delete(appointment)
        db.session.commit()
        return jsonify({'message': 'Deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api.route('/search/patients', methods=['GET'])
@login_required
def search_patients():
    query_str = request.args.get('q', '').strip()
    if not query_str:
        return jsonify([])

    # Search by patient name (case insensitive)
    appointments = Appointment.query.filter(
        Appointment.patient_name.ilike(f'%{query_str}%')
    ).order_by(Appointment.date.desc(), Appointment.time.desc()).limit(20).all()

    results = []
    for appt in appointments:
         # Check restrictions
        if current_user.role == 'org' and appt.author_id != current_user.id:
            continue # Don't show results for other orgs if restricted
        
        data = appt.to_dict()
        data['clinic_name'] = appt.clinic.name if appt.clinic else "Unknown"
        results.append(data)

    return jsonify(results)

@api.route('/service-price/<int:service_id>', methods=['GET'])
@login_required
def get_service_price(service_id):
    service = Service.query.get_or_404(service_id)
    date_str = request.args.get('date')
    if date_str:
        try:
            query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            query_date = datetime.now().date()
    else:
        query_date = datetime.now().date()
        
    price = service.get_price(query_date)
    return jsonify({'price': price})

@api.route('/additional-service-price/<int:service_id>', methods=['GET'])
@login_required
def get_additional_service_price(service_id):
    service = AdditionalService.query.get_or_404(service_id)
    date_str = request.args.get('date')
    if date_str:
        try:
            query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            query_date = datetime.now().date()
    else:
        query_date = datetime.now().date()
        
    price = service.get_price(query_date)
    return jsonify({'price': price})

@api.route('/slots', methods=['GET'])
@login_required
def get_slots():
    date_str = request.args.get('date')
    center_id = request.args.get('center_id')
    exclude_appt_id = request.args.get('exclude_id')
    
    if not date_str or not center_id:
        return jsonify([])

    try:
        query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        center_id = int(center_id)
    except ValueError:
        return jsonify([])

    # Generate all possible slots 08:00 - 19:30
    slots = []
    start_minutes = 8 * 60
    end_minutes = 19 * 60 + 30
    for m in range(start_minutes, end_minutes + 1, 15):
        hh = m // 60
        mm = m % 60
        time_str = f"{hh:02d}:{mm:02d}"
        
        # Exclude Lunch Break (13:00 - 14:00)
        if hh == 13:
            continue
        
        # Role restriction for 'org'
        if current_user.role == 'org':
            if not (time_str.endswith(':15') or time_str.endswith(':45')):
                continue
        
        slots.append(time_str)

    # Fetch existing appointments to block slots
    query = Appointment.query.filter_by(
        date=query_date,
        center_id=center_id
    )
    
    existing = query.all()
    occupied = set()
    
    # Helper to calculate end minutes
    def time_to_min(t):
        h, m = map(int, t.split(':'))
        return h * 60 + m

    for appt in existing:
        if exclude_appt_id and str(appt.id) == str(exclude_appt_id):
            continue
        occupied.add(appt.time)
        
        # If appointment has duration > 15 (e.g. 30), block subsequent slots
        if (getattr(appt, 'duration', 15) or 15) > 15:
             start_m = time_to_min(appt.time)
             # slots are 15 min steps.
             # If 30 min, it occupies Start and Start+15.
             # We need to block Start+15.
             extra_slots = (appt.duration // 15) - 1
             for i in range(extra_slots):
                 next_m = start_m + (15 * (i + 1))
                 hh = next_m // 60
                 mm = next_m % 60
                 next_time_str = f"{hh:02d}:{mm:02d}"
                 occupied.add(next_time_str)

    # Filter available
    # ALSO: If a user asks what slots are available, we must ensure if they pick a slot,
    # and they intend to use 30 mins, that slot AND the next one must be free?
    # Usually UI handles "if I pick 30m, do I fit?".
    # But `get_slots` usually just returns start times.
    # However, standard logic: list all start times that are not occupied.
    available = [s for s in slots if s not in occupied]
    
    return jsonify(available)
