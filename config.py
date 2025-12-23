import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-patient-system'

    # Environment determination
    is_production = os.environ.get('DATABASE_URL') is not None
    
    if is_production:
        database_url = os.environ.get('DATABASE_URL', '')
        
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
        SQLALCHEMY_DATABASE_URI = database_url
        DEBUG = False
        UPLOAD_FOLDER = '/opt/patient_accounting_system/app/static/uploads'
        
    else:
        # Local development
        # Using a distinct database name for the new system
        SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg://postgres:postgres@localhost:5432/patient_accounting'
        DEBUG = True
        UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'static', 'uploads')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 128 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Add other configurations as needed (Mail, etc.)
