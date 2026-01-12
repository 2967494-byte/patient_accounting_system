import os
from flask import Flask, render_template
from .extensions import db, migrate, login_manager, csrf
from .telegram_bot import telegram_bot
import atexit
import sys


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object('config.Config')
    
    # 1.5 Hours Session Timeout
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=90)
    
    if test_config:
        app.config.update(test_config)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db) 
    login_manager.init_app(app)
    csrf.init_app(app)
    from .extensions import mail
    mail.init_app(app)
    telegram_bot.init_app(app)

    # ProxyFix for production
    if app.config.get('IS_PRODUCTION', False) or os.environ.get('FLASK_ENV') == 'production':
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    
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

    from app.blueprints.chat import chat
    app.register_blueprint(chat, url_prefix='/api/chat')



    # Error Handler
    @app.errorhandler(500)
    def internal_error(error):
        telegram_bot.send_error_notification(error)
        
        # Check if request is API
        from flask import request, jsonify
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal Server Error', 'message': 'An unexpected error occurred'}), 500

        return render_template('500.html'), 500 # Assuming 500.html exists or use generic error

    # Startup Notification (only if not in debug reload mode or use lock)
    # Simple check to avoid double send in dev reloader:
    if (not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true') and app.config.get('TELEGRAM_BOT_TOKEN'):
         with app.app_context():
             telegram_bot.send_startup_notification()

    # Shutdown Notification
    def on_exit():
        # Context might be needed depending on implementation, but requests usually creates one new.
        # However, at exit, app context might be gone. TelegramBot.send_message uses internal valid checks.
        if app.config.get('TELEGRAM_BOT_TOKEN'):
            telegram_bot.send_shutdown_notification()
    
    atexit.register(on_exit)

    return app

