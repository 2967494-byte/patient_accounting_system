import os
from pdf2image import convert_from_path

pdf_path = r'c:\Users\Matvey\Documents\Projects\patient_accounting_system\orbital logo files\certificate_blank.pdf'
output_dir = r'c:\Users\Matvey\Documents\Projects\patient_accounting_system\app\static\uploads'
output_filename = 'certificate_bg.png'

print(f"Converting {pdf_path}...")

try:
    pages = convert_from_path(pdf_path, 300) # 300 DPI for high quality
    if pages:
        output_path = os.path.join(output_dir, output_filename)
        pages[0].save(output_path, 'PNG')
        print(f"Success! Saved to {output_path}")
    else:
        print("Error: No pages found in PDF.")
except Exception as e:
    print(f"Error during conversion: {e}")
