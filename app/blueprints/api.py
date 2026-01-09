from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models import Appointment, Service, AdditionalService, AppointmentService, AppointmentAdditionalService, Doctor, Clinic
from datetime import datetime

api = Blueprint('api', __name__)

@api.route('/appointments', methods=['POST'])
@login_required # Ensure user is logged in
def create_appointment():
    data = request.get_json()
    try:
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

        appointment = Appointment(
            center_id=safe_int(data.get('center_id')),
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            time=data.get('time', '09:00'),
            patient_name=data['patient_name'],
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
            timestamp=datetime.utcnow()
        )
        db.session.add(history)

        db.session.commit()

        return jsonify(appointment.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api.route('/appointments', methods=['GET'])
@login_required
def get_appointments():
    import difflib # Import here to avoid modifying top of file extensively

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    clinic_id_str = request.args.get('clinic_id')

    query = Appointment.query

    if clinic_id_str:
         try:
             query = query.filter_by(clinic_id=int(clinic_id_str))
         except ValueError:
             pass
    
    center_id_str = request.args.get('center_id')
    
    if center_id_str and center_id_str != 'null': # Allow override if param provided
         try:
             query = query.filter_by(center_id=int(center_id_str))
         except ValueError:
             pass
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

    # Pre-process for fuzzy matching: Get all "Paid" appointments in this set
    # We use this local set for correlation.
    paid_appointments = [a for a in appointments if a.payment_method_id is not None]
    
    # Helper for name normalization
    def normalize_name(name):
        return name.lower().replace(' ', '') if name else ''

    current_dt = datetime.now()

    results = []
    for appt in appointments:
        data = appt.to_dict()
        
        # Org restriction check
        if current_user.role == 'org' and appt.author_id != current_user.id:
            data['patient_name'] = ""
            data['patient_phone'] = ""
            data['doctor'] = ""
            data['service'] = ""
            data['is_restricted'] = True
            # Status for restricted? Maybe hide it or show generic. 
            # Let's show real status but hidden details.
        else:
            data['is_restricted'] = False

        # --- Status Calculation ---
        status = 'pending' # Default
        
        # 1. Is it explicitly paid/registered?
        if appt.payment_method_id is not None:
            status = 'completed'
        else:
            # 2. Fuzzy Search in Paid Appointments (same date)
            # Find if there is ANY paid appointment on the same date with similar name
            is_found_in_journal = False
            
            # Optimization: Only check against paid appts of SAME DATE
            # (Assuming `appointments` list might cover a week, we filter `paid_appointments` or just iterate)
            # Since `paid_appointments` is from the same query, it respects date range.
            
            appt_norm_name = normalize_name(appt.patient_name)
            
            if appt_norm_name: # Only check if name exists
                for paid_appt in paid_appointments:
                    if paid_appt.date != appt.date: continue 
                    # Don't match with self (though self is unpaid here, so it won't be in paid_list)
                    
                    paid_norm_name = normalize_name(paid_appt.patient_name)
                    
                    # Direct check or Fuzzy
                    if appt_norm_name == paid_norm_name:
                         is_found_in_journal = True
                         break
                    
                    # Fuzzy
                    ratio = difflib.SequenceMatcher(None, appt_norm_name, paid_norm_name).ratio()
                    if ratio > 0.85: # Threshold for "Insigificant errors"
                        is_found_in_journal = True
                        break
            
            if is_found_in_journal:
                status = 'completed'
            else:
                # 3. Time Check
                # Construct appointment datetime
                try:
                    appt_dt_str = f"{appt.date.isoformat()} {appt.time}"
                    appt_dt = datetime.strptime(appt_dt_str, "%Y-%m-%d %H:%M")
                    
                    # Add 25 minutes tolerance
                    time_diff = current_dt - appt_dt
                    minutes_passed = time_diff.total_seconds() / 60
                    
                    if minutes_passed > 25:
                        status = 'late'
                except ValueError:
                    pass # Invalid time format, keep pending

        data['status'] = status
        results.append(data)

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
    
    if 'patient_name' in data: appointment.patient_name = data['patient_name']
    if 'patient_phone' in data: appointment.patient_phone = data['patient_phone']
    
    # Update doctor and clinic (IDs preferred)
    if 'doctor_id' in data: 
        appointment.doctor_id = data['doctor_id']
        # Also update legacy string if needed, or leave it to be resolved via relation
        # But if we want consistent string for legacy views:
        doc = Doctor.query.get(data['doctor_id'])
        if doc: appointment.doctor = doc.name
        elif data.get('doctor'): appointment.doctor = data['doctor'] # fallback text
    
    if 'clinic_id' in data: appointment.clinic_id = data['clinic_id']

    if 'date' in data: appointment.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    if 'doctor' in data: appointment.doctor = data['doctor']
    if 'doctor' in data: appointment.doctor = data['doctor']
    
    # Update Service String AND Relationship if name provided but IDs not provided
    if 'service' in data: 
        appointment.service = data['service']
        
        # If services_ids NOT provided, try to validly link this service by name
        # This mirrors POST logic and ensures Dashboard edits (which only send name) 
        # update the M2M relationship correctly.
        if 'services_ids' not in data:
             svc = Service.query.filter_by(name=data['service']).first()
             if svc:
                 appointment.services = [svc]
             else:
                 # If name doesn't match a generic service, we might want to keep existing?
                 # Or clear? For Dashboard, we assume single service replacement.
                 # If we can't find it, we just clear the relation (it's a text-only service)
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
             cid = int(data['center_id'])
             appointment.center_id = cid
         except (ValueError, TypeError):
             pass # or return error
    
    if 'contract_number' in data: appointment.contract_number = data['contract_number']
    if 'clinic_id' in data: appointment.clinic_id = data['clinic_id']
    if 'doctor_id' in data: appointment.doctor_id = data['doctor_id'] # Added doctor_id
    if 'quantity' in data: appointment.quantity = int(data['quantity'])
    if 'cost' in data: appointment.cost = float(data['cost'])
    if 'payment_method_id' in data: appointment.payment_method_id = data['payment_method_id']
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
        timestamp=datetime.utcnow()
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
    for appt in existing:
        if exclude_appt_id and str(appt.id) == str(exclude_appt_id):
            continue
        occupied.add(appt.time)

    # Filter available
    available = [s for s in slots if s not in occupied]
    
    return jsonify(available)
