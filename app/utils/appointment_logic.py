from datetime import datetime, timedelta
import difflib

def get_appointments_with_status_logic(appointments, user_role, user_id):
    """
    Consolidated logic for calculating appointment statuses.
    Used by both the REST API and the dashboard pre-rendering.
    """
    # Pre-process for fuzzy matching: Get all "Paid" appointments in this set
    paid_appointments = [a for a in appointments if a.payment_method_id is not None]
    
    def normalize_name(name):
        return name.lower().replace(' ', '') if name else ''

    current_dt = (datetime.utcnow() + timedelta(hours=3))
    
    # Cache normalized names for paid appointments to speed up fuzzy matching
    paid_info = []
    for pa in paid_appointments:
        paid_info.append({
            'date': pa.date,
            'norm_name': normalize_name(pa.patient_name)
        })

    results = []
    for appt in appointments:
        data = appt.to_dict()
        
        # Org restriction check
        if user_role == 'org' and appt.author_id != user_id:
            data['patient_name'] = ""
            data['patient_phone'] = ""
            data['doctor'] = ""
            data['service'] = ""
            data['is_restricted'] = True
        else:
            data['is_restricted'] = False

        # --- Status Calculation ---
        status = 'pending' # Default
        
        # 1. Is it explicitly paid/registered?
        if appt.payment_method_id is not None:
            status = 'completed'
        else:
            # 2. Fuzzy Search in Paid Appointments (same date)
            is_found_in_journal = False
            appt_norm_name = normalize_name(appt.patient_name)
            
            if appt_norm_name:
                for pi in paid_info:
                    if pi['date'] != appt.date: 
                        continue 
                    
                    if appt_norm_name == pi['norm_name']:
                         is_found_in_journal = True
                         break
                    
                    # Fuzzy match threshold
                    if difflib.SequenceMatcher(None, appt_norm_name, pi['norm_name']).ratio() > 0.85:
                        is_found_in_journal = True
                        break
            
            if is_found_in_journal:
                status = 'completed'
            else:
                # 3. Time Check (25 minutes tolerance)
                try:
                    appt_dt_str = f"{appt.date.isoformat()} {appt.time}"
                    appt_dt = datetime.strptime(appt_dt_str, "%Y-%m-%d %H:%M")
                    
                    time_diff = current_dt - appt_dt
                    minutes_passed = time_diff.total_seconds() / 60
                    
                    if minutes_passed > 25:
                        status = 'late'
                except (ValueError, TypeError):
                    pass 

        data['status'] = status
        results.append(data)

    return results
