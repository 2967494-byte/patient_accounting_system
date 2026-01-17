from app import create_app,db
from sqlalchemy import text

app = create_app()

with app.app_context():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN doctor_id INTEGER REFERENCES doctors(id)"))
            conn.commit()
        print("Migration successful: added doctor_id to users table")
    except Exception as e:
        print(f"Migration failed (maybe column exists?): {e}")
