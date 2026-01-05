from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models import Appointment, Service, AdditionalService
from datetime import datetime

api = Blueprint('api', __name__)

@api.route('/appointments', methods=['POST'])
@login_required # Ensure user is logged in
def create_appointment():
    data = request.get_json()
    try:
        # Default Quantity Logic (for simplicity, we assume 1 visit = 1 of each service unless specified otherwise)
        # If user sends `quantity`, it applies to the primary service or all? 
        # For now, let's assume quantity applies to the VISIT (so usually 1).
        quantity = int(data.get('quantity', 1))

        # Main Services handling
        # Expecting 'services_ids' list. If not, fallback to 'service' (name) -> find ID? 
        # Or 'service' (ID)?
        # Ideally frontend now sends 'services_ids'.
        services_to_add = []
        primary_service_name = ""
        
        # Check for 'services_ids' (List of IDs)
        if 'services_ids' in data and isinstance(data['services_ids'], list):
            for s_id in data['services_ids']:
                svc = Service.query.get(s_id)
                if svc:
                    services_to_add.append(svc)
        
        # Fallback/Legacy: 'service' field (might be Name or ID)
        # If services_ids is empty, try 'service'
        if not services_to_add and 'service' in data:
            # Try to find by ID first? Or Name? 
            # Frontend sends NAME in `service` currently for legacy.
            # But the new Modal sends IDs in `services_ids`.
            # If we receive `service` (name), we try to look it up.
            svc = Service.query.filter_by(name=data['service']).first()
            if svc:
                services_to_add.append(svc)
            else:
                # If just a string and no service found (e.g. freetext?), we still save the string but no relation?
                # The model requires `service` string.
                primary_service_name = data['service']

        if services_to_add:
            # Join names for legacy string
            primary_service_name = "\n".join([s.name for s in services_to_add])

        # Create Appointment
        # Create Appointment
        appointment = Appointment(
            center_id=data.get('center_id'),
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            time=data.get('time', '09:00'),
            patient_name=data['patient_name'],
            patient_phone=data.get('patient_phone', ''),
            clinic_id=data.get('clinic_id'),
            doctor_id=data.get('doctor_id'),
            service=primary_service_name, # joined names
            quantity=quantity,
            contract_number=data.get('contract_number'),
            payment_method_id=data.get('payment_method_id'),
            discount=float(data.get('discount', 0)),
            comment=data.get('comment'),
            is_child=data.get('is_child', False),
            author_id=current_user.id
        )

        # Add Main Services Relations
        for svc in services_to_add:
            appointment.services.append(svc)

        # Handle Additional Services (List)
        if 'additional_services_ids' in data and isinstance(data['additional_services_ids'], list):
            for as_id in data['additional_services_ids']:
                add_svc = AdditionalService.query.get(as_id)
                if add_svc:
                    appointment.additional_services.append(add_svc)
            
            # Additional Service Quantity
            if 'additional_service_quantity' in data:
                 appointment.additional_service_quantity = int(data['additional_service_quantity'])
                 
        elif 'additional_service' in data and data['additional_service']:
            # Legacy/Fallback
            add_svc = AdditionalService.query.get(data['additional_service'])
            if add_svc:
                appointment.additional_services.append(add_svc)
                if 'additional_service_quantity' in data:
                    appointment.additional_service_quantity = int(data['additional_service_quantity'])

        # Calculate Cost
        # Sum of Main Services + Sum of Additional Services - Discount
        # Note: quantity applies to Main Services
        total_service_cost = sum([s.price for s in appointment.services]) * quantity
        
        # Additional Services Cost
        # Assuming additional_service_quantity applies to the batch of additional services? 
        # Or usually it's 1.
        add_qty = appointment.additional_service_quantity or 1
        total_add_cost = sum([a.price for a in appointment.additional_services]) * add_qty
        
        raw_cost = total_service_cost + total_add_cost - appointment.discount
        if raw_cost < 0: raw_cost = 0
        
        # Payment Method Check (Free)
        if appointment.payment_method:
             pm_name = appointment.payment_method.name.lower()
             if pm_name not in ['наличные', 'карта']:
                 raw_cost = 0
        
        appointment.cost = raw_cost

        db.session.add(appointment)
        db.session.commit()

        return jsonify(appointment.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@api.route('/appointments', methods=['GET'])
@login_required
def get_appointments():
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
    
    # Enforce center restriction for Lab Techs
    if current_user.role == 'lab_tech':
        if current_user.center_id:
            query = query.filter_by(center_id=current_user.center_id)
        else:
            # If no center assigned, return empty or error? Empty seems safer.
            query = query.filter(db.false()) 
    elif center_id_str and center_id_str != 'null':
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
    results = []
    for appt in appointments:
        data = appt.to_dict()
        # Org restriction: If role is 'org' and not author -> hide details
        if current_user.role == 'org' and appt.author_id != current_user.id:
            data['patient_name'] = ""
            data['patient_phone'] = ""
            data['doctor'] = ""
            data['service'] = ""
            data['is_restricted'] = True
        else:
            data['is_restricted'] = False
        results.append(data)

    return jsonify(results)

@api.route('/appointments/<int:id>', methods=['GET'])
@login_required
def get_appointment_detail(id):
    appt = Appointment.query.get_or_404(id)
    
    # Restriction check
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
    if 'doctor' in data: appointment.doctor = data['doctor']
    if 'service' in data: appointment.service = data['service']

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
    if 'quantity' in data: appointment.quantity = int(data['quantity'])
    if 'cost' in data: appointment.cost = float(data['cost'])
    if 'payment_method_id' in data: appointment.payment_method_id = data['payment_method_id']
    if 'discount' in data: appointment.discount = float(data['discount'])
    if 'discount' in data: appointment.discount = float(data['discount'])
    if 'comment' in data: appointment.comment = data['comment']
    if 'is_child' in data: appointment.is_child = bool(data['is_child'])

    # Handle Services (M2M)
    if 'services_ids' in data:
        # Clear existing? Or replace? 
        # Usually replace entirely with new list.
        appointment.services = []
        for sid in data['services_ids']:
             svc = Service.query.get(sid)
             if svc:
                 appointment.services.append(svc)
    
    # Handle Additional Services (M2M)
    if 'additional_services_ids' in data:
        appointment.additional_services = []
        for asid in data['additional_services_ids']:
             asvc = AdditionalService.query.get(asid)
             if asvc:
                 appointment.additional_services.append(asvc)

    # Legacy support / Fallback for single 'additional_service' field from old legacy calls
    elif 'additional_service' in data: # Only if plural not provided
        appointment.additional_services = [] 
        if data['additional_service']:
            add_svc = AdditionalService.query.get(data['additional_service'])
            if add_svc:
                appointment.additional_services.append(add_svc)

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
