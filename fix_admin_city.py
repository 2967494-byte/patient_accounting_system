from app import create_app, db
from app.models import User, Location

app = create_app()

with app.app_context():
    # Find Kazan
    kazan = Location.query.filter(Location.name.ilike('%Казань%')).first()
    
    if not kazan:
        print("Error: City 'Казань' not found.")
        print("Available Locations:")
        for loc in Location.query.all():
            print(f" - {loc.name} ({loc.type})")
    else:
        print(f"Found City: {kazan.name} (ID: {kazan.id})")
        
        # Find Admin (assuming username is 'admin' or role is 'admin')
        # Let's try finding by role 'admin'
        admins = User.query.filter_by(role='admin').all()
        
        if not admins:
            print("No users with role 'admin' found.")
            # Fallback to username 'admin'
            admin = User.query.filter_by(username='admin').first()
            if admin:
                admins = [admin]
        
        if not admins:
            print("No admin user found.")
        else:
            for admin in admins:
                print(f"Updating Admin: {admin.username} (ID: {admin.id})")
                print(f"Old City ID: {admin.city_id}")
                admin.city_id = kazan.id
                db.session.commit()
                print(f"New City ID: {admin.city_id}")
