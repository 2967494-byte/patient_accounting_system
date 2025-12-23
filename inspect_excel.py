import openpyxl
import os

file_path = 'Lush-Oct-25.xlsx'

if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
else:
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        
        print(f"Sheet Name: {sheet.title}")
        
        # Print first 5 rows to understand structure
        print("First 5 rows:")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            print(f"Row {i+1}: {row}")
            if i >= 4:
                break
                
    except Exception as e:
        print(f"Error reading file: {e}")
