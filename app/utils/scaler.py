from datetime import datetime, timedelta
from flask import current_app
from app.extensions import db
from app.models import RemoteVM, VMSession
from app.utils.vm_manager import MedicalVMManager

class ScalingManager:
    """
    Автоматическое масштабирование пула ВМ и управление неактивными сессиями.
    """
    
    # Schedule: (Hour, Target Count)
    WEEKDAY_SCHEDULE = [
        (0, 3),   # Night
        (8, 20),  # Morning peak
        (13, 12), # Lunch
        (14, 20), # Afternoon
        (18, 10), # Evening
        (22, 3)   # Late night
    ]
    
    WEEKEND_SCHEDULE = [
        (0, 3),   # Night
        (9, 10),  # Morning
        (13, 6),  # Lunch
        (14, 8),  # Afternoon
        (19, 3)   # Evening
    ]

    def __init__(self):
        self.vm_manager = MedicalVMManager()

    def get_target_vm_count(self):
        """Определяет необходимое количество активных ВМ сейчас."""
        now = datetime.now()
        is_weekend = now.weekday() >= 5
        schedule = self.WEEKEND_SCHEDULE if is_weekend else self.WEEKDAY_SCHEDULE
        
        current_hour = now.hour
        target = 3 # Default minimum
        
        # Находим подходящий интервал в расписании
        for hour, count in sorted(schedule, reverse=True):
            if current_hour >= hour:
                target = count
                break
        return target

    def sync_pool(self):
        """Приводит текущее количество активных ВМ к целевому."""
        target = self.get_target_vm_count()
        active_vms = RemoteVM.query.filter_by(status='active').all()
        active_count = len(active_vms)
        
        current_app.logger.info(f"Scaling Sync: Active={active_count}, Target={target}")
        
        if active_count < target:
            # Нужно запустить дополнительные ВМ
            needed = target - active_count
            suspended_vms = RemoteVM.query.filter_by(status='suspended').limit(needed).all()
            for vm in suspended_vms:
                current_app.logger.info(f"Scaling: Resuming VM {vm.id}")
                self.vm_manager.resume_vm(vm.id)
                
        elif active_count > target:
            # Нужно приостановить лишние ВМ
            # Приостанавливаем самые "старые" (недавно не использовавшиеся)
            excess = active_count - target
            to_suspend = RemoteVM.query.filter_by(status='active').order_by(RemoteVM.last_active.asc()).limit(excess).all()
            for vm in to_suspend:
                # Проверяем, нет ли активной сессии на этой ВМ
                active_session = VMSession.query.filter_by(vm_id=vm.id, is_active=True).first()
                if not active_session:
                    current_app.logger.info(f"Scaling: Suspending excess VM {vm.id}")
                    self.vm_manager.suspend_vm(vm.id)

    def cleanup_idle_sessions(self, idle_minutes=30):
        """Закрывает сессии и приостанавливает ВМ при бездействии."""
        threshold = datetime.utcnow() - timedelta(minutes=idle_minutes)
        
        # Находим активные сессии, которые не обновлялись давно (если мы добавим last_ping)
        # Пока ориентируемся на start_time или last_active в RemoteVM
        idle_vms = RemoteVM.query.filter(
            RemoteVM.status == 'active',
            RemoteVM.last_active < threshold
        ).all()
        
        for vm in idle_vms:
            # Проверяем, есть ли сессия
            session = VMSession.query.filter_by(vm_id=vm.id, is_active=True).first()
            if session:
                current_app.logger.info(f"Idle Detection: Closing session {session.id} due to inactivity")
                session.is_active = False
                session.end_time = datetime.utcnow()
            
            # Приостанавливаем ВМ если она не нужна по расписанию
            target = self.get_target_vm_count()
            current_active = RemoteVM.query.filter_by(status='active').count()
            
            if current_active > target or True: # Для пилота можем быть более агрессивны
                current_app.logger.info(f"Idle Detection: Suspending VM {vm.id}")
                self.vm_manager.suspend_vm(vm.id)
        
        db.session.commit()
