from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request, current_app
from flask_login import login_required, current_user
from app.models import Appointment, VMSession, RemoteVM
from app.extensions import db
from app.utils.vm_manager import MedicalVMManager
from app.utils.scaler import ScalingManager
from app.utils.guacamole import GuacamoleAuth
from app.utils.storage_manager import StorageManager

viewer = Blueprint('viewer', __name__, url_prefix='/viewer')
vm_manager = MedicalVMManager()
scaling_manager = ScalingManager()
guac_auth = GuacamoleAuth()

@viewer.route('/launch/<int:appointment_id>')
@login_required
def launch_viewer(appointment_id):
    """
    Находит или запускает ВМ для данного приема и пользователя.
    """
    if current_user.role not in ['doctor', 'superadmin', 'admin']:
        flash('Доступ к просмотрщику ограничен для вашей роли', 'danger')
        return redirect(url_for('main.dashboard'))
        
    appt = Appointment.query.get_or_404(appointment_id)
    
    # 1. Синхронизируем пул (для пилота делаем это при каждом запуске, 
    # в проде это должен делать фоновый шедулер)
    try:
        scaling_manager.sync_pool()
        scaling_manager.cleanup_idle_sessions()
    except Exception as e:
        current_app.logger.error(f"Scaling sync failed: {e}")

    # 2. Пытаемся найти существующую активную сессию
    session = VMSession.query.filter_by(
        user_id=current_user.id, 
        appointment_id=appointment_id, 
        is_active=True
    ).first()
    
    if session and session.vm:
        return redirect(url_for('viewer.session_view', vm_id=session.vm.id))
        
    # 3. Находим свободную ВМ из пула
    vm = RemoteVM.query.filter(RemoteVM.status.in_(['active', 'suspended'])).first()
    
    if not vm:
        flash('В данный момент нет свободных рабочих станций. Пожалуйста, подождите 2-3 минуты.', 'warning')
        return redirect(request.referrer or url_for('main.dashboard'))
        
    # 4. Запускаем, если она была приостановлена
    if vm.status == 'suspended':
        vm_manager.resume_vm(vm.id)
        
    # 5. Подготавливаем данные в хранилище (S3)
    try:
        storage = StorageManager()
        storage.prepare_study_for_vm(appointment_id)
    except Exception as e:
        current_app.logger.warning(f"Storage preparation warning: {e}")
        
    # 6. Создаем новую сессию
    new_session = VMSession(
        user_id=current_user.id,
        vm_id=vm.id,
        appointment_id=appointment_id,
        start_time=datetime.utcnow(),
        is_active=True
    )
    db.session.add(new_session)
    db.session.commit()
    
    return redirect(url_for('viewer.session_view', vm_id=vm.id))

@viewer.route('/session/<int:vm_id>')
@login_required
def session_view(vm_id):
    vm = RemoteVM.query.get_or_404(vm_id)
    
    # Проверка, есть ли у пользователя активная сессия на этой ВМ
    session = VMSession.query.filter_by(
        user_id=current_user.id,
        vm_id=vm_id,
        is_active=True
    ).first()
    
    if not session:
        flash('Сессия просмотра не найдена или была завершена', 'warning')
        return redirect(url_for('main.dashboard'))

    # Обновляем время активности ВМ
    vm.last_active = datetime.utcnow()
    db.session.commit()

    # Генерируем подпись для безопасности
    auth_data = guac_auth.generate_hmac_signature(vm.external_id or str(vm.id), str(current_user.id))
        
    return render_template('viewer/session.html', 
                           vm=vm, 
                           session=session, 
                           guac_signature=auth_data['signature'],
                           guac_timestamp=auth_data['timestamp'])

@viewer.route('/session/close/<int:session_id>', methods=['POST'])
@login_required
def close_session(session_id):
    session = VMSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    session.is_active = False
    session.end_time = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})
