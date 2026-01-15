import pdfrw

pdf_path = r'c:\Users\Matvey\Documents\Projects\patient_accounting_system\orbital logo files\certificate_blank.pdf'
try:
    reader = pdfrw.PdfReader(pdf_path)
    fields = []
    if '/AcroForm' in reader.Root:
        for page in reader.pages:
            if '/Annots' in page:
                for annot in page['/Annots']:
                    if annot['/Subtype'] == '/Widget' and annot['/T']:
                        fields.append(str(annot['/T']))
    
    if fields:
        print("Found PDF fields:")
        for f in fields:
            print(f"- {f}")
    else:
        print("No AcroForm fields found in this PDF.")
except Exception as e:
    print(f"Error reading PDF: {e}")
