import os
from flask import Flask, render_template
from .extensions import db, migrate, login_manager, csrf

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    if test_config:
        app.config.update(test_config)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db) 
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Login manager settings
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите, чтобы получить доступ к этой странице.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return db.session.get(User, int(user_id))
    
    # Create upload folder
    try:
        upload_folder = app.config.get('UPLOAD_FOLDER')
        if upload_folder:
            os.makedirs(upload_folder, exist_ok=True)
    except Exception as e:
        print(f"[ERROR] Upload folder creation failed: {e}")

    # Register blueprints 
    from app.blueprints.auth import auth
    app.register_blueprint(auth, url_prefix='/auth')
    
    from app.blueprints.main import main
    app.register_blueprint(main)

    from app.blueprints.api import api
    app.register_blueprint(api, url_prefix='/api')

    from app.blueprints.admin import admin
    app.register_blueprint(admin, url_prefix='/admin')



    return app
