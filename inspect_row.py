
import openpyxl
import sys
from app import create_app
from app.models import Doctor, Clinic, Service, User

app = create_app()

file_path = r"C:\Users\Orbital\patient_accounting_system\uploads\Декабрь.xlsx"

try:
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))

    target_name = "Хамиев"
    
    found = False
    with app.app_context():
        # Find column indices (assuming standard map or header row 1)
        # Using basic search for now
        
        for i, row in enumerate(rows):
            row_str = str(row)
            if target_name in row_str:
                print(f"\nFOUND ROW {i+1}:")
                for idx, val in enumerate(row):
                    print(f"Col {idx}: {val}")
                
                found = True
                
                # Try to emulate admin.py logic for this row
                # Let's assume typical Layout:
                # Date: 0, Patient: 4, Doctor: 6, Clinic: 8, Service: 9
                
                print("\n--- DB CHECK ---")
                
                # Check Doctor
                doc_name = str(row[6]).strip() if len(row) > 6 and row[6] else ""
                print(f"Checking Doctor: '{doc_name}'")
                doc = Doctor.query.filter(Doctor.name.ilike(doc_name)).first()
                if doc: print(f"  -> FOUND: ID {doc.id}, Name: {doc.name}")
                else: print("  -> NOT FOUND")
                
                # Check Clinic
                clinic_name = str(row[8]).strip() if len(row) > 8 and row[8] else ""
                print(f"Checking Clinic: '{clinic_name}'")
                clinic = Clinic.query.filter(Clinic.name.ilike(clinic_name)).first()
                if clinic: print(f"  -> FOUND: ID {clinic.id}, Name: {clinic.name}")
                else: print("  -> NOT FOUND")
                
                # Check Service
                service_name = str(row[9]).strip() if len(row) > 9 and row[9] else ""
                print(f"Checking Service: '{service_name}'")
                srv = Service.query.filter(Service.name.ilike(service_name)).first()
                if srv: print(f"  -> FOUND: ID {srv.id}, Name: {srv.name}")
                else: print("  -> NOT FOUND")
                
    if not found:
        print(f"Name {target_name} not found in file.")

except Exception as e:
    print(f"Error: {e}")
