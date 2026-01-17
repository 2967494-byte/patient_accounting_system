from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import RemoteVM
from app.utils.selectel_api import SelectelAPI

class MedicalVMManager:
    """
    Управление жизненным циклом виртуальных машин в облаке Selectel.
    Обрабатывает запуск, приостановку и отслеживание статуса.
    """
    
    def __init__(self):
        self._api = None
        self._is_mock = None

    @property
    def api(self):
        if self._api is None and not self.is_mock:
            self._api = SelectelAPI()
        return self._api

    @property
    def is_mock(self):
        if self._is_mock is None:
            # Check credentials at runtime when first needed
            username = current_app.config.get('SELECTEL_USERNAME')
            password = current_app.config.get('SELECTEL_PASSWORD')
            self._is_mock = not (username and password)
        return self._is_mock

    def resume_vm(self, vm_id):
        """
        Возобновляет работу приостановленной ВМ.
        Возвращает True в случае успеха.
        """
        vm = RemoteVM.query.get(vm_id)
        if not vm:
            return False
            
        if self.is_mock:
            vm.status = 'active'
            vm.last_active = datetime.utcnow()
            db.session.commit()
            return True
        
        try:
            # Если ВМ выключена - стартуем, если в гибернации - пробуждаем
            # В OpenStack Nova 'resume' используется для гибернации, 
            # но мы можем также использовать 'start' для SHUTOFF.
            # Для простоты пробуем resume, если статус SUSPENDED.
            details = self.api.get_vm_details(vm.external_id)
            status = details.get('server', {}).get('status')
            
            if status == 'SUSPENDED':
                self.api.resume_vm(vm.external_id)
            elif status == 'SHUTOFF':
                self.api.start_vm(vm.external_id)
            
            vm.status = 'active' # TODO: Ждать асинхронно подтверждения
            vm.last_active = datetime.utcnow()
            db.session.commit()
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to resume VM {vm.id}: {e}")
            return False

    def suspend_vm(self, vm_id):
        """
        Приостанавливает активную ВМ.
        """
        vm = RemoteVM.query.get(vm_id)
        if not vm:
            return False
            
        if self.is_mock:
            vm.status = 'suspended'
            db.session.commit()
            return True
            
        try:
            self.api.suspend_vm(vm.external_id)
            vm.status = 'suspended'
            db.session.commit()
            return True
        except Exception as e:
            current_app.logger.error(f"Failed to suspend VM {vm.id}: {e}")
            return False

    def get_vm_status(self, vm_id):
        """
        Обновляет и возвращает текущий статус из облака.
        """
        vm = RemoteVM.query.get(vm_id)
        if not vm:
            return None
            
        if self.is_mock:
            return vm.status
            
        try:
            details = self.api.get_vm_details(vm.external_id)
            os_status = details.get('server', {}).get('status', '').upper()
            
            # Mapping OpenStack to local statuses
            mapping = {
                'ACTIVE': 'active',
                'SHUTOFF': 'stopped',
                'SUSPENDED': 'suspended',
                'BUILD': 'starting',
                'PAUSED': 'suspended'
            }
            
            new_status = mapping.get(os_status, 'unknown')
            if vm.status != new_status:
                vm.status = new_status
                db.session.commit()
            return new_status
        except Exception as e:
            current_app.logger.error(f"Failed to get status for VM {vm.id}: {e}")
            return vm.status

    def sync_vm_pool(self):
        """
        Обеспечивает соответствие пула ВМ расписанию (логика масштабирования).
        """
        # Логика для будней и выходных будет реализована в scaler.py
        pass
