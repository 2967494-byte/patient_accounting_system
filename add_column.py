from app import create_app,db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN clinic_id INTEGER REFERENCES clinics(id)"))
            conn.commit()
            print("Successfully added clinic_id column to users table.")
    except Exception as e:
        print(f"Error: {e}")
