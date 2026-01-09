import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

class Config:
    # Безопасность - всегда через переменные окружения
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this-in-production'
    
    # Определяем среду по hostname (универсально)
    import socket
    hostname = socket.gethostname()
    import socket
    hostname = socket.gethostname()
    IS_PRODUCTION = hostname == 'maryam'  # ваш продакшен сервер
    
    if IS_PRODUCTION:
        # Продакшен на сервере maryam
        database_url = os.environ.get('DATABASE_URL') or 'postgresql+psycopg://patient_user:strong_password_123@localhost:5432/patient_accounting'
        
        # Корректируем URL если нужно
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
        SQLALCHEMY_DATABASE_URI = database_url
        DEBUG = False
        # УНИВЕРСАЛЬНЫЙ путь для продакшена (работает на вашем сервере)
        UPLOAD_FOLDER = '/home/patient/patient_accounting_system/app/static/uploads'
        
    else:
        # Локальная разработка (любой другой сервер)
        SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg://postgres:postgres@localhost:5432/patient_accounting'
        DEBUG = True
        # УНИВЕРСАЛЬНЫЙ путь для разработки
        UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'static', 'uploads')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 128 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

    # Email Config
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Создаем папку uploads если не существует
    if not os.path.exists(UPLOAD_FOLDER):
        try:
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create upload folder: {e}")