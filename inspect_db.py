from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Tables in DB:")
    with db.engine.connect() as conn:
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [row[0] for row in result]
        print(tables)
        
        if 'alembic_version' in tables:
            v = conn.execute(text("SELECT * FROM alembic_version")).fetchall()
            print(f"Alembic version: {v}")
