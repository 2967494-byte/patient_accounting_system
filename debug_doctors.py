from app import create_app
from app.extensions import db
from app.models import Doctor

app = create_app()

with app.app_context():
    target_name = 'Гулаев Махмуджон Нурмахмадович'
    print(f"Checking for doctor: '{target_name}'")
    
    # 1. Exact match (case insensitive)
    exact_match = Doctor.query.filter(Doctor.name.ilike(target_name)).first()
    if exact_match:
        print(f"✅ FOUND Exact Match: ID={exact_match.id}, Name='{exact_match.name}'")
    else:
        print("❌ Exact Match NOT FOUND")

    # 2. Fuzzy search (contains 'Гулаев')
    print("\nSearching for doctors containing 'Гулаев':")
    fuzzy_matches = Doctor.query.filter(Doctor.name.ilike('%Гулаев%')).all()
    
    if not fuzzy_matches:
        print("No doctors found with 'Гулаев' in name.")
    else:
        for doc in fuzzy_matches:
            print(f"- ID: {doc.id}")
            print(f"  Name: '{doc.name}'")
            print(f"  Repr: {repr(doc.name)}") # Show hidden chars
            
            # Compare using python string comparison
            if doc.name.strip().lower() == target_name.lower():
                 print("  -> Python string match: YES (Issue might be DB collation or query)")
            else:
                 print("  -> Python string match: NO")
                 
            # Check length
            print(f"  Length in DB: {len(doc.name)}, Target Length: {len(target_name)}")
