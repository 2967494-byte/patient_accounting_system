from datetime import datetime, timedelta
import difflib

def get_appointments_with_status_logic(appointments, user_role, user_id):
    """
    Consolidated logic for calculating appointment statuses.
    Optimized for high-volume dashboard rendering.
    """
    # Group paid appointments by date for Fast O(1) date lookup and O(N) daily lookup
    paid_by_date = {}
    for pa in appointments:
        if pa.payment_method_id is not None:
            d = pa.date
            if d not in paid_by_date:
                paid_by_date[d] = []
            paid_by_date[d].append(pa.patient_name.lower().strip() if pa.patient_name else '')

    current_dt = (datetime.utcnow() + timedelta(hours=3))
    
    results = []
    import difflib
    
    for appt in appointments:
        # Use to_dict_lite to avoid heavy N+1 relation queries
        data = appt.to_dict_lite()
        
        # Org restriction check
        if user_role == 'org' and appt.author_id != user_id:
            data['patient_name'] = ""
            data['patient_phone'] = ""
            # doctor and service are NOT in to_dict_lite, so we skip clearing them or add them if needed.
            # Dashboard actually needs patient_name.
            data['is_restricted'] = True
        else:
            data['is_restricted'] = False

        # --- Status Calculation ---
        status = 'pending' 
        
        # 1. Is it explicitly paid/registered?
        if appt.payment_method_id is not None:
            status = 'completed'
        else:
            # 2. Match in Journal (Paid Appointments on same date)
            appt_raw_name = appt.patient_name.lower().strip() if appt.patient_name else ''
            
            if appt_raw_name:
                paid_names = paid_by_date.get(appt.date, [])
                
                # Direct match (Fast)
                if appt_raw_name in paid_names:
                    status = 'completed'
                else:
                    # Smart matching logic
                    appt_parts = appt_raw_name.split()
                    
                    for p_full_name in paid_names:
                        if not p_full_name: continue
                        
                        # 1. Start-with match (e.g. "Ivanov" matches "Ivanov Ivan")
                        if p_full_name.startswith(appt_raw_name):
                            status = 'completed'
                            break
                            
                        # 2. Surname + Initial check (e.g. "Ivanov I." matches "Ivanov Ivan")
                        p_parts = p_full_name.split()
                        if len(appt_parts) >= 1 and len(p_parts) >= 1:
                            surname_match = (appt_parts[0] == p_parts[0])
                            
                            if surname_match:
                                # If Calendar has only surname, and it matches Journal's surname - it's a match
                                if len(appt_parts) == 1:
                                    status = 'completed'
                                    break
                                
                                # If Calendar has surname + something else (initial?)
                                if len(appt_parts) > 1 and len(p_parts) > 1:
                                    # Check if second part of Calendar entry is an initial of the Journal entry
                                    if appt_parts[1].startswith(p_parts[1][0]) or p_parts[1].startswith(appt_parts[1][0]):
                                        status = 'completed'
                                        break

                        # 3. Fuzzy match (Final fallback)
                        # We use compressed names for fuzzy to stay consistent with previous behavior for typos
                        appt_compressed = appt_raw_name.replace(' ', '')
                        p_compressed = p_full_name.replace(' ', '')
                        if difflib.SequenceMatcher(None, appt_compressed, p_compressed).ratio() > 0.8:
                            status = 'completed'
                            break

            if status != 'completed':
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
