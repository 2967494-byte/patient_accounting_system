import requests
import logging
from flask import current_app
import threading

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.token = None
        self.chat_id = None
        self.base_url = None
    
    def init_app(self, app):
        """Initializes the bot with configuration from the app."""
        self.token = app.config.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = app.config.get('TELEGRAM_CHAT_ID')
        if self.token:
            self.base_url = f"https://api.telegram.org/bot{self.token}"
        logger.info(f"Telegram bot initialized: token={bool(self.token)}, chat_id={self.chat_id}")
    
    def _send_async(self, url, json_payload=None, files=None, data=None):
        """Sends a request to Telegram in a separate thread to avoid blocking."""
        def request_task():
            try:
                # If files are present, we cannot use json parameter, we must use data
                # And files dict needs to be opened files
                if files:
                    real_files = {}
                    for key, path in files.items():
                        real_files[key] = open(path, 'rb')
                    
                    try:
                        requests.post(url, data=data, files=real_files, timeout=30)
                    finally:
                        for f in real_files.values():
                            f.close()
                else:
                    requests.post(url, json=json_payload, timeout=10)
            except Exception as e:
                logger.error(f"Failed to send async Telegram message: {e}")

        thread = threading.Thread(target=request_task)
        thread.start()


    def send_message(self, text, parse_mode='HTML', disable_web_page_preview=True):
        """Sends a message to Telegram."""
        if not self.token or not self.chat_id:
            logger.warning("Telegram token or chat_id not configured.")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': disable_web_page_preview
            }
            
            # Use async sending to not block the request loop
            self._send_async(url, payload)
            return True
            
        except Exception as e:
            logger.error(f"Error preparing Telegram message: {e}")
            return False
    
    def send_new_user_notification(self, user):
        """Sends a notification about a new user."""
        if not user:
            return False
        
        try:
            # We avoid querying DB here if possible or minimize it. 
            # Ideally this is called where context is active.
            
            text = f"""
🚀 <b>НОВЫЙ ПОЛЬЗОВАТЕЛЬ!</b>

👤 <b>Логин:</b> {user.username}
📧 <b>Email:</b> {user.email}
🏢 <b>Организация:</b> {user.organization.name if user.organization else 'Не указана'}
🏙️ <b>Город:</b> {user.city.name if user.city else 'Не указан'}
📅 <b>Дата:</b> {user.created_at.strftime('%d.%m.%Y %H:%M') if user.created_at else 'Сейчас'}
            """
            
            return self.send_message(text)
            
        except Exception as e:
            logger.error(f"Error creating new user notification: {e}")
            return False
    
    def send_error_notification(self, error):
        """Sends an error notification."""
        import traceback
        try:
            tb = traceback.format_exc()
            if len(tb) > 3000:
                tb = tb[-3000:]
            
            error_msg = str(error)
            
            text = f"""
❌ <b>ОШИБКА СИСТЕМЫ!</b>

⚠️ <b>Ошибка:</b> {error_msg}

📜 <b>Traceback:</b>
<pre>{tb}</pre>
            """
            return self.send_message(text)
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False

    def send_startup_notification(self):
        """Sends a startup notification."""
        return self.send_message("🟢 <b>СИСТЕМА ЗАПУЩЕНА</b>\n\nПриложение начало работу.")

    def send_shutdown_notification(self):
        """Sends a shutdown notification."""
        return self.send_message("🛑 <b>СИСТЕМА ОСТАНОВЛЕНА</b>\n\nПриложение завершает работу.")

    def send_support_ticket(self, ticket, user):
        """Sends a support ticket notification."""
        if not ticket or not user:
             return False

        try:
            status_map = {'new': 'Новая', 'viewed': 'Просмотрена', 'in_progress': 'В работе', 'completed': 'Выполнена'}
            type_map = {'error': 'Ошибка', 'suggestion': 'Предложение', 'request': 'Запрос', 'other': 'Другое'}
            
            t_type = type_map.get(ticket.type, ticket.type)
            
            text = f"""
🛠 <b>ТЕХ. ПОДДЕРЖКА</b>

👤 <b>Пользователь:</b> {user.username} (ID: {user.id})
🏢 <b>Организация:</b> {user.organization.name if user.organization else 'Нет'}
📌 <b>Тип:</b> {t_type}
📝 <b>Сообщение:</b>
{ticket.message}

📅 <b>Дата:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}
            """
            
            if ticket.screenshot_filename:
                # Send photo
                url = f"{self.base_url}/sendPhoto"
                import os
                
                # Check absolute path
                file_path = None
                if os.path.isabs(ticket.screenshot_filename):
                     file_path = ticket.screenshot_filename
                else:
                     # Assume relative to app static? Or uploads?
                     # We will save uploads to `app/static/uploads/support/...`
                     file_path = os.path.join(current_app.static_folder, ticket.screenshot_filename)
                
                if os.path.exists(file_path):
                     payload = {
                         'chat_id': self.chat_id,
                         'caption': text,
                         'parse_mode': 'HTML'
                     }
                     files = {'photo': file_path}
                     self._send_async(url, data=payload, files=files)
                     return True
            
            # Fallback to text if no photo or photo not found
            return self.send_message(text)
            
        except Exception as e:
            logger.error(f"Error sending support ticket: {e}")
            return False


# Global instance
telegram_bot = TelegramBot()
