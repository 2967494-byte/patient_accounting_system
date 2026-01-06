import openpyxl
import sys

file_path = r"C:\Users\Orbital\patient_accounting_system\uploads\Декабрь.xlsx"

try:
    wb = openpyxl.load_workbook(file_path)
    sheet = wb.active
    
    rows = list(sheet.iter_rows(values_only=True))
    
    if not rows:
        print("File is empty")
        sys.exit()
        
    print("--- HEADERS (Row 1) ---")
    headers = [str(h).strip() if h else 'None' for h in rows[0]]
    for idx, h in enumerate(headers):
        print(f"Index {idx}: {h}")
        
    print("\n--- HEADERS (Row 2, if exists) ---")
    if len(rows) > 1:
        headers2 = [str(h).strip() if h else 'None' for h in rows[1]]
        for idx, h in enumerate(headers2):
            print(f"Index {idx}: {h}")

    print("\n--- FIRST DATA ROW (Row 3, if exists) ---")
    if len(rows) > 2:
        data = rows[2]
        for idx, val in enumerate(data):
            print(f"Index {idx}: {val} (Type: {type(val)})")

except Exception as e:
    print(f"Error: {e}")
