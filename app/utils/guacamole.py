import hmac
import hashlib
import base64
import json
from flask import current_app

class GuacamoleAuth:
    """
    Утилита для генерации токенов аутентификации и подписанных URL для Apache Guacamole.
    Используется для безопасного подключения без передачи паролей в открытом виде.
    """
    
    def __init__(self):
        self._secret_key = None

    @property
    def secret_key(self):
        if self._secret_key is None:
            self._secret_key = current_app.config.get('SECRET_KEY')
        return self._secret_key

    def generate_hmac_signature(self, connection_id, user_id):
        """
        Генерирует подпись для HMAC-аутентификации Guacamole (если используется расширение hmac).
        """
        # Формат зависит от настроек Guacamole, обычно это:
        # signature = base64(hmac-sha256(key, timestamp + connectionName))
        import time
        timestamp = str(int(time.time() * 1000))
        message = timestamp + connection_id
        
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        
        return {
            'signature': base64.b64encode(signature).decode(),
            'timestamp': timestamp
        }

    def get_connection_params(self, vm, session):
        """
        Возвращает параметры подключения, которые можно передать в iframe или API.
        """
        # В простейшем случае мы используем идентификатор соединения, 
        # настроенный в Guacamole (который совпадает с external_id ВМ)
        params = {
            'id': vm.external_id,
            'user': session.user.username,
            'appointment': session.appointment_id
        }
        return params

    @staticmethod
    def get_client_url(base_url, connection_id, token=None):
        """
        Формирует URL для клиента Guacamole.
        """
        url = f"{base_url}/#/client/c/{connection_id}"
        if token:
            url += f"?token={token}"
        return url
