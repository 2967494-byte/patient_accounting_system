import re
from datetime import datetime
import difflib

def parse_ics_content(content):
    """
    Parses ICS content string and extracts events.
    Returns a list of dictionaries with event details.
    """
    events = []
    lines = content.splitlines()
    
    current_event = {}
    in_event = False
    
    # Pre-process unwrapping lines (lines starting with space are continuations)
    unfolded_lines = []
    for line in lines:
        if line.startswith(' '):
            if unfolded_lines:
                unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)
            
    for line in unfolded_lines:
        line = line.strip()
        if line == 'BEGIN:VEVENT':
            in_event = True
            current_event = {}
        elif line == 'END:VEVENT':
            in_event = False
            if 'DTSTART' in current_event and 'SUMMARY' in current_event:
                events.append(current_event)
        elif in_event:
            if ':' in line:
                key, value = line.split(':', 1)
                # Handle parameters in key (e.g., DTSTART;VALUE=DATE)
                if ';' in key:
                    key = key.split(';')[0]
                current_event[key] = value

    parsed_events = []
    
    for event in events:
        summary = event.get('SUMMARY', '')
        description = event.get('DESCRIPTION', '')
        dtstart_str = event.get('DTSTART', '')
        
        # Parse Date/Time
        # Formats: 20250111T073000Z or 20250111
        try:
            if 'T' in dtstart_str:
                dt = datetime.strptime(dtstart_str[:15], '%Y%m%dT%H%M%S')
            else:
                dt = datetime.strptime(dtstart_str, '%Y%m%d')
                dt = dt.replace(hour=9, minute=0) # Default for whole day? or ignore?
        except ValueError:
            continue

        # Parse Summary
        # Expected format: "KEYWORD NAME PHONE" or similar
        # Regex for phone: 10-11 digits, maybe starting with +7 or 8
        phone_match = re.search(r'[\+\(]?[0-9][0-9 .\-\(\)]{8,}[0-9]', summary)
        phone = ''
        if phone_match:
            phone = phone_match.group(0)
            # Remove phone from summary to find name
            summary_no_phone = summary.replace(phone, '').strip()
        else:
            summary_no_phone = summary
            
        # Extract Service (Fuzzy Match stub - will be done in route with DB context)
        # Here we just clean up the text
        
        # Extract Doctor from description if available
        # "Создатель: Магомедов Хаджимурат (Dental center)"
        doctor_name_candidate = ''
        if 'Создатель:' in description:
            try:
                part = description.split('Создатель:')[1]
                if '(' in part:
                    doctor_name_candidate = part.split('(')[0].strip()
                else:
                    doctor_name_candidate = part.strip()
            except IndexError:
                pass
        else:
             # Or check if "Создатель:" is in a different format or missing
             pass

        parsed_events.append({
            'date': dt.strftime('%Y-%m-%d'),
            'time': dt.strftime('%H:%M'),
            'raw_summary': summary,
            'summary_no_phone': summary_no_phone,
            'phone': phone,
            'description': description,
            'doctor_from_desc': doctor_name_candidate
        })
        
    return parsed_events
