from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        print("Dropping notification_statuses...")
        conn.execute(text("DROP TABLE IF EXISTS notification_statuses CASCADE"))
        print("Dropping notifications...")
        conn.execute(text("DROP TABLE IF EXISTS notifications CASCADE"))
        conn.commit()
        print("Tables dropped.")
