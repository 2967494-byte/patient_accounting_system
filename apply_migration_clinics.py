from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Applying migration...")
    try:
        # Use simple string for text()
        sql = text("ALTER TABLE clinics ADD COLUMN is_cashless BOOLEAN DEFAULT FALSE;")
        
        with db.engine.connect() as conn:
            conn.execute(sql)
            conn.commit()
        print("Migration applied successfully!")
        
    except Exception as e:
        print(f"Migration failed (might already exist): {e}")
