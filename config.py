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
    is_production = hostname == 'maryam'  # ваш продакшен сервер
    
    if is_production:
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
    
    # Создаем папку uploads если не существует
    if not os.path.exists(UPLOAD_FOLDER):
        try:
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create upload folder: {e}")