import os
import sys

# Add current directory to path so config can be imported
sys.path.append(os.getcwd())

from config import Config

print("-" * 30)
print("Database Configuration Debugger")
print("-" * 30)
print(f"Is Production (Config): {Config.is_production}")
print(f"SQLALCHEMY_DATABASE_URI: {Config.SQLALCHEMY_DATABASE_URI}")
print("-" * 30)
print(f"Environment Variables:")
print(f"DATABASE_URL: {os.environ.get('DATABASE_URL')}")
print("-" * 30)

if 'postgres' in Config.SQLALCHEMY_DATABASE_URI and 'localhost' in Config.SQLALCHEMY_DATABASE_URI:
    print("\n[INFO] It seems you are using the default local database configuration.")
    print("If you are receiving authentication errors, the password 'postgres' is likely incorrect for your local PostgreSQL server.")
    print("Please create a .env file with the correct DATABASE_URL.")
