from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Location, Doctor, Service, AdditionalService, ServicePrice, AdditionalServicePrice, Clinic, Manager, PaymentMethod, Appointment, Organization, GlobalSetting
from app.telegram_bot import telegram_bot
import psutil
from werkzeug.security import generate_password_hash
import os

from datetime import datetime
import csv
import openpyxl
from werkzeug.utils import secure_filename
import io
import calendar
from datetime import date

admin = Blueprint('admin', __name__, template_folder='templates')

@admin.before_request
@login_required
def require_admin():
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))

@admin.route('/additional')
def additional():
    managers = Manager.query.all()
    payment_methods = PaymentMethod.query.all()
    centers = Location.query.filter_by(type='center').all()
    chat_setting = GlobalSetting.query.get('chat_image')
    chat_image = chat_setting.value if chat_setting else None
    return render_template('admin_additional.html', managers=managers, payment_methods=payment_methods, centers=centers, chat_image=chat_image)

@admin.route('/journal/clear', methods=['POST'])
@login_required
def clear_journal_data():
    center_id = request.form.get('center_id')
    month_str = request.form.get('month')
    password = request.form.get('password')
    
    if not center_id or not month_str:
        flash('Центр и Месяц обязательны', 'error')
        return redirect(url_for('admin.additional'))
        
    if password != 'NikolEnikeeva':
        flash('Неверный пароль', 'error')
        return redirect(url_for('admin.additional'))

    try:
        year, month = map(int, month_str.split('-'))
        start_date = date(year, month, 1)
        # Handle end of month
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)
        
        # Delete appointments
        num_deleted = Appointment.query.filter(
            Appointment.center_id == int(center_id),
            Appointment.date >= start_date,
            Appointment.date <= end_date
        ).delete(synchronize_session=False)
        
        db.session.commit()
        flash(f'Удалено записей: {num_deleted}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')

    return redirect(url_for('admin.additional'))

@admin.route('/journal/recalculate', methods=['POST'])
@login_required
def recalculate_journal_data():
    center_id = request.form.get('center_id')
    month_str = request.form.get('month')
    
    if not center_id or not month_str:
        flash('Центр и Месяц обязательны', 'error')
        return redirect(url_for('admin.additional'))
        
    try:
        year, month = map(int, month_str.split('-'))
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        appointments = Appointment.query.filter(
            Appointment.center_id == int(center_id),
            Appointment.date >= start_date,
            Appointment.date <= end_date
        ).all()
        
        updated_count = 0
        
        for appt in appointments:
            if not appt.service: continue
            
            # Find service object by name to get price logic
            # Note: appt.service is string name. 
            service_obj = Service.query.filter(Service.name.ilike(appt.service)).first()
            
            price = 0.0
            if service_obj:
               price = service_obj.get_price(appt.date)
               
            # Additional services cost
            add_svc_cost = 0.0
            for add_svc in appt.additional_services:
                add_svc_cost += add_svc.get_price(appt.date)
                
            qty = appt.quantity if appt.quantity else 1
            add_qty = appt.additional_service_quantity if appt.additional_service_quantity else 1
            
            discount = appt.discount if appt.discount else 0.0
            
            # Recalculate Total
            # Formula: (ServicePrice * Qty) + (AddServicePriceTotal * AddQty) - Discount
            # Note: AddServicePriceTotal is sum of unit prices of all attached additional services
            
            # Wait, additional_services is a list. Do we multiply sum by add_qty OR 
            # does add_qty apply to each? 
            # In API create_appointment: 
            # add_services_cost = sum(add_svc.get_price(appt.date) for add_svc in appt.additional_services)
            # total_cost = (service_price * appt.quantity) + (add_services_cost * appt.additional_service_quantity)
            # This matches plan.
            
            new_cost = (price * qty) + (add_svc_cost * add_qty) - discount
            if new_cost < 0: new_cost = 0.0
            
            appt.cost = new_cost
            updated_count += 1
            
        db.session.commit()
        flash(f'Пересчитано записей: {updated_count}', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
        
    return redirect(url_for('admin.additional'))

# --- Managers Management ---

@admin.route('/managers/add', methods=['POST'])
def add_manager():
    name = request.form.get('name')
    if not name:
        flash('Имя менеджера обязательно', 'error')
        return redirect(url_for('admin.additional'))
    
    manager = Manager(name=name)
    db.session.add(manager)
    db.session.commit()
    flash(f'Менеджер {name} добавлен', 'success')
    return redirect(url_for('admin.additional'))

@admin.route('/managers/<int:id>/update', methods=['POST'])
def update_manager(id):
    manager = Manager.query.get_or_404(id)
    manager.name = request.form.get('name')
    db.session.commit()
    flash(f'Менеджер {manager.name} обновлен', 'success')
    return redirect(url_for('admin.additional'))

@admin.route('/managers/<int:id>/delete', methods=['POST'])
def delete_manager(id):
    manager = Manager.query.get_or_404(id)
    db.session.delete(manager)
    db.session.commit()
    flash('Менеджер удален', 'success')
    return redirect(url_for('admin.additional'))

# --- Payment Methods Management ---

@admin.route('/payment_methods/add', methods=['POST'])
def add_payment_method():
    name = request.form.get('name')
    if not name:
        flash('Название способа оплаты обязательно', 'error')
        return redirect(url_for('admin.additional'))
    
    method = PaymentMethod(name=name)
    db.session.add(method)
    db.session.commit()
    flash(f'Способ оплаты {name} добавлен', 'success')
    return redirect(url_for('admin.additional'))

@admin.route('/payment_methods/<int:id>/update', methods=['POST'])
def update_payment_method(id):
    method = PaymentMethod.query.get_or_404(id)
    method.name = request.form.get('name')
    db.session.commit()
    flash(f'Способ оплаты {method.name} обновлен', 'success')
    return redirect(url_for('admin.additional'))

@admin.route('/payment_methods/<int:id>/delete', methods=['POST'])
def delete_payment_method(id):
    method = PaymentMethod.query.get_or_404(id)
    db.session.delete(method)
    db.session.commit()
    flash('Способ оплаты удален', 'success')
    return redirect(url_for('admin.additional'))



@admin.route('/')
def index():
    return redirect(url_for('admin.users'))

@admin.route('/chat/settings', methods=['POST'])
@login_required
def update_chat_settings():
    if 'chat_image' not in request.files:
        flash('Нет файла', 'error')
        return redirect(url_for('admin.additional'))
    
    file = request.files['chat_image']
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('admin.additional'))
        
    if file:
        filename = secure_filename(file.filename)
        # Save to static/uploads/chat_icons or similar
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'chat')
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        # Save relative path to DB
        relative_path = f"uploads/chat/{filename}"
        
        setting = GlobalSetting.query.get('chat_image')
        if not setting:
            setting = GlobalSetting(key='chat_image')
            db.session.add(setting)
        
        setting.value = relative_path
        db.session.commit()
        
        flash('Иконка чата обновлена', 'success')
        
    return redirect(url_for('admin.additional'))



@admin.route('/monitoring')
@login_required
def monitoring():
    # Database Status
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = True
    except Exception:
        db_status = False
    
    # Bot Status
    bot_configured = bool(telegram_bot.token and telegram_bot.chat_id)
    
    # System Stats
    cpu_percent = psutil.cpu_percent(interval=None) # Non-blocking
    
    mem = psutil.virtual_memory()
    ram_total_gb = round(mem.total / (1024**3), 2)
    ram_used_gb = round(mem.used / (1024**3), 2)
    ram_percent = mem.percent
    
    disk = psutil.disk_usage('/')
    disk_total_gb = round(disk.total / (1024**3), 2)
    disk_free_gb = round(disk.free / (1024**3), 2)
    disk_percent = disk.percent
    
    return render_template('admin_monitoring.html', 
                           db_status=db_status,
                           bot_configured=bot_configured,
                           cpu_percent=cpu_percent,
                           ram_total_gb=ram_total_gb,
                           ram_used_gb=ram_used_gb,
                           ram_percent=ram_percent,
                           disk_total_gb=disk_total_gb,
                           disk_free_gb=disk_free_gb,
                           disk_percent=disk_percent
                           )

@admin.route('/monitoring/test-message', methods=['POST'])
@login_required
def test_telegram_message():
    success = telegram_bot.send_message("✅ <b>ТЕСТОВОЕ СООБЩЕНИЕ</b>\n\nБот работает корректно!")
    return jsonify({'success': success})

@admin.route('/users/add', methods=['POST'])
def add_user():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    organization_id = request.form.get('organization_id')
    city_id = request.form.get('city_id')
    center_id = request.form.get('center_id')

    if User.query.filter_by(username=username).first():
        flash('Пользователь с таким именем уже существует', 'error')
        return redirect(url_for('admin.users'))
    if User.query.filter_by(email=email).first():
        flash('Пользователь с таким email уже существует', 'error')
        return redirect(url_for('admin.users'))

    new_user = User(
        username=username,
        email=email,
        role=role,
        is_confirmed=True # Admin created users are auto-confirmed
    )
    new_user.password_hash = generate_password_hash(password)
    
    if organization_id:
        new_user.organization_id = int(organization_id)
    if city_id:
        new_user.city_id = int(city_id)
    if center_id:
        new_user.center_id = int(center_id)

    db.session.add(new_user)
    db.session.commit()
    
    flash(f'Пользователь {username} успешно создан', 'success')
    return redirect(url_for('admin.users'))

# --- User Management ---

@admin.route('/users')
def users():
    role_filter = request.args.get('role')
    query = User.query
    
    if role_filter:
        query = query.filter_by(role=role_filter)
        
    users = query.all()
    centers = Location.query.filter_by(type='center').all()
    cities = Location.query.filter_by(type='city').all()
    organizations = Organization.query.all()
    return render_template('admin_users.html', users=users, centers=centers, cities=cities, organizations=organizations, current_role=role_filter)

@admin.route('/users/<int:user_id>/role', methods=['POST'])
def update_user_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    role_map = {
        'superadmin': 'Суперадмин',
        'admin': 'Админ',
        'org': 'Организация',
        'lab_tech': 'Лаборант'
    }
    
    if new_role not in ['superadmin', 'admin', 'org', 'lab_tech']:
        flash('Недопустимая роль', 'error')
    else:
        user.role = new_role
        db.session.commit()
        role_name = role_map.get(new_role, new_role)
        flash(f'Роль пользователя {user.username} обновлена на "{role_name}"', 'success')
    
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:user_id>/center', methods=['POST'])
def update_user_center(user_id):
    user = User.query.get_or_404(user_id)
    center_id = request.form.get('center_id')
    
    if center_id:
        user.center_id = int(center_id)
    else:
        user.center_id = None
        
    db.session.commit()
    flash(f'Центр пользователя {user.username} обновлен', 'success')
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:user_id>/block', methods=['POST'])
def block_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash('Нельзя заблокировать администратора', 'error')
    else:
        user.is_blocked = True
        db.session.commit()
        flash(f'Пользователь {user.username} заблокирован', 'success')
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:user_id>/unblock', methods=['POST'])
def unblock_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    db.session.commit()
    flash(f'Пользователь {user.username} разблокирован', 'success')
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:user_id>/confirm', methods=['POST'])
def confirm_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_confirmed = True
    db.session.commit()
    flash(f'Пользователь {user.username} подтвержден', 'success')
    return redirect(url_for('admin.users'))

# --- Location Management ---

@admin.route('/locations')
def locations():
    cities = Location.query.filter_by(type='city').all()
    return render_template('admin_locations.html', cities=cities)

@admin.route('/locations/add', methods=['POST'])
def add_location():
    name = request.form.get('name')
    type = request.form.get('type')
    parent_id = request.form.get('parent_id')
    color = request.form.get('color')

    if not name or type not in ['city', 'center']:
        return jsonify({'error': 'Неверные данные'}), 400

    loc = Location(name=name, type=type)
    if parent_id:
        loc.parent_id = int(parent_id)
    if color:
        loc.color = color
    
    db.session.add(loc)
    db.session.commit()
    return jsonify(loc.to_dict()), 201

@admin.route('/locations/<int:id>/edit', methods=['PUT'])
def edit_location(id):
    loc = Location.query.get_or_404(id)
    data = request.get_json()
    
    if 'name' in data:
        loc.name = data['name']
    if 'color' in data:
        loc.color = data['color']
    
    db.session.commit()
    return jsonify(loc.to_dict())

@admin.route('/locations/<int:id>/delete', methods=['DELETE'])
def delete_location(id):
    loc = Location.query.get_or_404(id)
    # Optional: Check for children or related data before deleting
    db.session.delete(loc)
    db.session.commit()
    return '', 204

# --- Doctor Management ---

@admin.route('/doctors')
def doctors():
    doctors = Doctor.query.all()
    managers = Manager.query.all()
    return render_template('admin_doctors.html', doctors=doctors, managers=managers)

@admin.route('/doctors/add', methods=['POST'])
def add_doctor():
    name = request.form.get('name')
    specialization = request.form.get('specialization')
    manager = request.form.get('manager')
    
    if not name:
        flash('Имя врача обязательно', 'error')
        return redirect(url_for('admin.doctors'))
        
    doctor = Doctor(name=name, specialization=specialization, manager=manager)
    db.session.add(doctor)
    db.session.commit()
    flash(f'Врач {name} добавлен', 'success')
    return redirect(url_for('admin.doctors'))

@admin.route('/doctors/<int:id>/update', methods=['POST'])
def update_doctor(id):
    doctor = Doctor.query.get_or_404(id)
    doctor.name = request.form.get('name')
    doctor.specialization = request.form.get('specialization')
    doctor.manager = request.form.get('manager')
    db.session.commit()
    flash(f'Данные врача {doctor.name} обновлены', 'success')
    return redirect(url_for('admin.doctors'))

@admin.route('/doctors/<int:id>/delete', methods=['POST'])
def delete_doctor(id):
    doctor = Doctor.query.get_or_404(id)
    db.session.delete(doctor)
    db.session.commit()
    flash('Врач удален', 'success')
    return redirect(url_for('admin.doctors'))

@admin.route('/doctors/import', methods=['POST'])
def import_doctors():
    if 'file' not in request.files:
        flash('Нет файла', 'error')
        return redirect(url_for('admin.doctors'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('admin.doctors'))

    if file:
        filename = secure_filename(file.filename)
        doctors_created = 0
        errors = 0
        
        try:
            # Determine file type
            if filename.endswith('.csv'):
                # Handle CSV
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.reader(stream)
                # Assume header: Name, Specialization, Manager
                # Or just skip first row if it looks like header?
                # Let's assume with header if "Name" is in first row, or just simple loop.
                # Simplest: Assume Header exists.
                header = next(csv_input, None)
                
                for row in csv_input:
                    if len(row) >= 1: # At least name
                        name = row[0].strip()
                        if not name: continue
                        specialization = row[1].strip() if len(row) > 1 else None
                        manager = row[2].strip() if len(row) > 2 else None
                        
                        # Check exist
                        if not Doctor.query.filter_by(name=name).first():
                            doc = Doctor(name=name, specialization=specialization, manager=manager)
                            db.session.add(doc)
                            doctors_created += 1
                        
            elif filename.endswith('.xlsx'):
                # Handle Excel
                wb = openpyxl.load_workbook(file)
                sheet = wb.active
                
                # Iterate rows, skipping header (min_row=2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]: continue
                    name = str(row[0]).strip()
                    specialization = str(row[1]).strip() if len(row) > 1 and row[1] else None
                    manager = str(row[2]).strip() if len(row) > 2 and row[2] else None
                    
                    if not Doctor.query.filter_by(name=name).first():
                        doc = Doctor(name=name, specialization=specialization, manager=manager)
                        db.session.add(doc)
                        doctors_created += 1

            else:
                 flash('Неподдерживаемый формат файла. Используйте CSV или XLSX.', 'error')
                 return redirect(url_for('admin.doctors'))

            db.session.commit()
            flash(f'Импортировано врачей: {doctors_created}', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка импорта: {str(e)}', 'error')
            
    return redirect(url_for('admin.doctors'))

# --- Service Management ---

@admin.route('/services')
def services():
    services = Service.query.all()
    return render_template('admin_services.html', services=services)

@admin.route('/services/add', methods=['POST'])
def add_service():
    name = request.form.get('name')
    price = request.form.get('price')
    
    if not name or not price:
        flash('Все поля обязательны', 'error')
        return redirect(url_for('admin.services'))
        
    service = Service(name=name, price=float(price))
    db.session.add(service)
    db.session.commit()
    flash(f'Услуга {name} добавлена', 'success')
    return redirect(url_for('admin.services'))

@admin.route('/services/<int:id>/update', methods=['POST'])
def update_service(id):
    service = Service.query.get_or_404(id)
    service.name = request.form.get('name')
    service.price = float(request.form.get('price'))
    db.session.commit()
    flash(f'Услуга {service.name} обновлена', 'success')
    return redirect(url_for('admin.services'))

@admin.route('/services/<int:id>/delete', methods=['POST'])
def delete_service(id):
    service = Service.query.get_or_404(id)
    db.session.delete(service)
    db.session.commit()
    flash('Услуга удалена', 'success')
    return redirect(url_for('admin.services'))

@admin.route('/services/import', methods=['POST'])
def import_services():
    if 'file' not in request.files:
        flash('Нет файла', 'error')
        return redirect(url_for('admin.services'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('admin.services'))

    if file:
        filename = secure_filename(file.filename)
        services_created = 0
        
        try:
            # Determine file type
            if filename.endswith('.csv'):
                # Handle CSV
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.reader(stream)
                header = next(csv_input, None)
                
                for row in csv_input:
                    if len(row) >= 2: # Name, Price required
                        name = row[0].strip()
                        if not name: continue
                        try:
                            price = float(row[1].strip())
                        except ValueError:
                            continue
                            
                        # Check exist
                        if not Service.query.filter_by(name=name).first():
                            service = Service(name=name, price=price)
                            db.session.add(service)
                            services_created += 1
                        
            elif filename.endswith('.xlsx'):
                # Handle Excel
                wb = openpyxl.load_workbook(file)
                sheet = wb.active
                
                # Iterate rows, skipping header (min_row=2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]: continue
                    name = str(row[0]).strip()
                    try:
                        price = float(row[1]) if len(row) > 1 and row[1] is not None else 0.0
                    except (ValueError, TypeError):
                        continue
                    
                    if not Service.query.filter_by(name=name).first():
                        service = Service(name=name, price=price)
                        db.session.add(service)
                        services_created += 1

            else:
                 flash('Неподдерживаемый формат файла. Используйте CSV или XLSX.', 'error')
                 return redirect(url_for('admin.services'))

            db.session.commit()
            flash(f'Импортировано услуг: {services_created}', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка импорта: {str(e)}', 'error')
            
    return redirect(url_for('admin.services'))

@admin.route('/services/<int:id>/prices')
def service_prices(id):
    service = Service.query.get_or_404(id)
    # Sort prices by start_date desc
    prices = ServicePrice.query.filter_by(service_id=id).order_by(ServicePrice.start_date.desc()).all()
    return render_template('admin_service_prices.html', service=service, prices=prices)

@admin.route('/services/<int:id>/prices/add', methods=['POST'])
def add_service_price(id):
    service = Service.query.get_or_404(id)
    price_val = request.form.get('price')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    
    if not price_val or not start_date_str:
        flash('Цена и Дата начала обязательны', 'error')
        return redirect(url_for('admin.service_prices', id=id))
        
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = None
        if end_date_str:
             end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
             
        # Basic Validation: Start date must be before end date
        if end_date and start_date > end_date:
            flash('Дата начала не может быть позже даты окончания', 'error')
            return redirect(url_for('admin.service_prices', id=id))

        new_price = ServicePrice(
            service_id=service.id,
            price=float(price_val),
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(new_price)
        db.session.commit()
        flash('Период действия цены добавлен', 'success')
        
    except ValueError:
        flash('Ошибка формата данных', 'error')
        
    return redirect(url_for('admin.service_prices', id=id))

@admin.route('/services/prices/<int:price_id>/delete', methods=['POST'])
def delete_service_price(price_id):
    price_entry = ServicePrice.query.get_or_404(price_id)
    service_id = price_entry.service_id
    db.session.delete(price_entry)
    db.session.commit()
    flash('Период удален', 'success')
    return redirect(url_for('admin.service_prices', id=service_id))

# --- Additional Service Management ---

@admin.route('/additional_services')
def additional_services():
    services = AdditionalService.query.all()
    return render_template('admin_additional_services.html', additional_services=services)

@admin.route('/additional_services/add', methods=['POST'])
def add_additional_service():
    name = request.form.get('name')
    price = request.form.get('price')
    
    if not name or not price:
        flash('Все поля обязательны', 'error')
        return redirect(url_for('admin.additional_services'))
        
    service = AdditionalService(name=name, price=float(price))
    db.session.add(service)
    db.session.commit()
    flash(f'Доп. услуга {name} добавлена', 'success')
    return redirect(url_for('admin.additional_services'))

@admin.route('/additional_services/<int:id>/update', methods=['POST'])
def update_additional_service(id):
    service = AdditionalService.query.get_or_404(id)
    service.name = request.form.get('name')
    service.price = float(request.form.get('price'))
    db.session.commit()
    flash(f'Доп. услуга {service.name} обновлена', 'success')
    return redirect(url_for('admin.additional_services'))

@admin.route('/additional_services/<int:id>/delete', methods=['POST'])
def delete_additional_service(id):
    service = AdditionalService.query.get_or_404(id)
    db.session.delete(service)
    db.session.commit()
    flash('Доп. услуга удалена', 'success')
    return redirect(url_for('admin.additional_services'))

@admin.route('/additional_services/import', methods=['POST'])
def import_additional_services():
    if 'file' not in request.files:
        flash('Нет файла', 'error')
        return redirect(url_for('admin.additional_services'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('admin.additional_services'))

    if file:
        filename = secure_filename(file.filename)
        services_created = 0
        
        try:
            # Determine file type
            if filename.endswith('.csv'):
                # Handle CSV
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.reader(stream)
                header = next(csv_input, None)
                
                for row in csv_input:
                    if len(row) >= 2: # Name, Price required
                        name = row[0].strip()
                        if not name: continue
                        try:
                            price = float(row[1].strip())
                        except ValueError:
                            continue
                            
                        # Check exist
                        if not AdditionalService.query.filter_by(name=name).first():
                            service = AdditionalService(name=name, price=price)
                            db.session.add(service)
                            services_created += 1
                        
            elif filename.endswith('.xlsx'):
                # Handle Excel
                wb = openpyxl.load_workbook(file)
                sheet = wb.active
                
                # Iterate rows, skipping header (min_row=2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]: continue
                    name = str(row[0]).strip()
                    try:
                        price = float(row[1]) if len(row) > 1 and row[1] is not None else 0.0
                    except (ValueError, TypeError):
                        continue
                    
                    if not AdditionalService.query.filter_by(name=name).first():
                        service = AdditionalService(name=name, price=price)
                        db.session.add(service)
                        services_created += 1

            else:
                 flash('Неподдерживаемый формат файла. Используйте CSV или XLSX.', 'error')
                 return redirect(url_for('admin.additional_services'))

            db.session.commit()
            flash(f'Импортировано доп. услуг: {services_created}', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка импорта: {str(e)}', 'error')
            
    return redirect(url_for('admin.additional_services'))

@admin.route('/additional_services/<int:id>/prices')
def additional_service_prices(id):
    service = AdditionalService.query.get_or_404(id)
    # Sort prices by start_date desc
    prices = AdditionalServicePrice.query.filter_by(additional_service_id=id).order_by(AdditionalServicePrice.start_date.desc()).all()
    return render_template('admin_additional_service_prices.html', service=service, prices=prices)

@admin.route('/additional_services/<int:id>/prices/add', methods=['POST'])
def add_additional_service_price(id):
    service = AdditionalService.query.get_or_404(id)
    price_val = request.form.get('price')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    
    if not price_val or not start_date_str:
        flash('Цена и Дата начала обязательны', 'error')
        return redirect(url_for('admin.additional_service_prices', id=id))
        
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = None
        if end_date_str:
             end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
             
        if end_date and start_date > end_date:
            flash('Дата начала не может быть позже даты окончания', 'error')
            return redirect(url_for('admin.additional_service_prices', id=id))

        new_price = AdditionalServicePrice(
            additional_service_id=service.id,
            price=float(price_val),
            start_date=start_date,
            end_date=end_date
        )
        db.session.add(new_price)
        db.session.commit()
        flash('Период действия цены добавлен', 'success')
        
    except ValueError:
        flash('Ошибка формата данных', 'error')
        
    return redirect(url_for('admin.additional_service_prices', id=id))

@admin.route('/additional_services/prices/<int:price_id>/delete', methods=['POST'])
def delete_additional_service_price(price_id):
    price_entry = AdditionalServicePrice.query.get_or_404(price_id)
    service_id = price_entry.additional_service_id
    db.session.delete(price_entry)
    db.session.commit()
    flash('Период удален', 'success')
    return redirect(url_for('admin.additional_service_prices', id=service_id))

    flash('Период удален', 'success')
    return redirect(url_for('admin.service_prices', id=service_id))

# --- Journal Import ---

@admin.route('/journal/import', methods=['POST'])
@login_required
def import_journal():
    if 'file' not in request.files:
        flash('Нет файла', 'error')
        return redirect(url_for('main.journal'))
    
    file = request.files['file']
    center_id = request.form.get('center_id')
    
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('main.journal'))
        
    if not center_id:
        flash('Не выбран Центр', 'error')
        return redirect(url_for('main.journal'))

    if file:
        filename = secure_filename(file.filename)
        created_count = 0
        try:
             if filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(file, data_only=True)
                sheet = wb.active
                
                # Iterate rows, skipping header (min_row=2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    # Check Row Structure: 
                    # 0: Date, 1: Month, 2: Lab Tech, 3: Contract, 4: Patient, 5: Child (BOOL), 
                    # 6: Doctor, 7: Manager, 8: Clinic, 9: Service, 10: Add Svc, 11: Qty, 
                    # 12: Add Svc Qty, 13: Cost (Text?), 14: Payment, 15: Discount, 16: Sum, 17: Comment
                    
                    if not row or not row[0]: continue
                    
                    # 1. Date
                    date_val = row[0]
                    if isinstance(date_val, datetime):
                        appt_date = date_val.date()
                    else:
                        # Try parse string?
                        try:
                            # Try common formats or just skip
                             appt_date = datetime.strptime(str(date_val), '%Y-%m-%d').date() # fallback
                        except:
                            continue # Skip invalid date
                            
                    # 2. Service
                    service_name = str(row[9]).strip() if len(row) > 9 and row[9] else None
                    if not service_name: continue
                    
                    # Find Service object for price calc
                    service = Service.query.filter(Service.name.ilike(service_name)).first()
                    # If service not found, creating it might be dangerous for price calc. 
                    # But we need it for the record. 
                    # Let's create if missing with 0 price? Or skip?
                    # Plan said: "Search by name. If found, link service_id? Wait, Appointment stores Service Name string primarily in old model, 
                    # but we moved to ID in form. 
                    # Model: service = db.Column(db.String(200)) ... wait, check model.
                    # Model: service = db.Column(db.String(200), nullable=False)
                    # It does NOT have service_id foreign key? 
                    # Checking model... "service = db.Column(db.String(200), nullable=False)"
                    # Ah, so we just store name. BUT we need price.
                    # So we find the Service model to get price.
                    
                    price = 0.0
                    if service:
                        price = service.get_price(appt_date)
                    
                    # 3. Quantity
                    try:
                        qty = int(row[11]) if len(row) > 11 and row[11] else 1
                    except:
                        qty = 1
                        
                    # 4. Discount
                    try:
                        discount = float(row[15]) if len(row) > 15 and row[15] else 0.0
                    except:
                        discount = 0.0
                        
                    # 5. Calculate Cost
                    final_cost = (price * qty) - discount
                    if final_cost < 0: final_cost = 0.0
                    
                    # 6. Patient
                    patient_name = str(row[4]).strip() if len(row) > 4 and row[4] else "Unknown"
                    
                    # 7. Doctor
                    doctor_name = str(row[6]).strip() if len(row) > 6 and row[6] else "Unknown"
                    doctor_obj = Doctor.query.filter(Doctor.name.ilike(doctor_name)).first()
                    doctor_id = doctor_obj.id if doctor_obj else None
                    
                    # 8. Clinic
                    clinic_name = str(row[8]).strip() if len(row) > 8 and row[8] else None
                    clinic_id = None
                    if clinic_name:
                        clinic = Clinic.query.filter(Clinic.name.ilike(clinic_name)).first()
                        if clinic:
                            clinic_id = clinic.id
                            
                    # 9. Payment Method
                    payment_name = str(row[14]).strip() if len(row) > 14 and row[14] else None
                    payment_method_id = None
                    if payment_name:
                        pm = PaymentMethod.query.filter(PaymentMethod.name.ilike(payment_name)).first()
                        if pm:
                            payment_method_id = pm.id
                            
                    # 10. Contract
                    contract = str(row[3]).strip() if len(row) > 3 and row[3] else None
                    
                    # 11. Child
                    is_child_val = str(row[5]).strip().upper() if len(row) > 5 and row[5] else "FALSE"
                    is_child = (is_child_val == 'TRUE' or is_child_val == 'YES' or is_child_val == '1')
                    
                    # 12. Lab Tech
                    lab_tech_val = str(row[2]).strip() if len(row) > 2 and row[2] else None
                    
                    comment = str(row[17]).strip() if len(row) > 17 and row[17] else ""
                             
                    # Create Appointment
                    appt = Appointment(
                        patient_name=patient_name,
                        patient_phone='-', # No phone in excel
                        doctor=doctor_name,
                        doctor_id=doctor_id,
                        service=service_name,
                        date=appt_date,
                        time="00:00", # Default
                        author_id=current_user.id,
                        clinic_id=clinic_id,
                        center_id=int(center_id),
                        contract_number=contract,
                        quantity=qty,
                        cost=final_cost,
                        discount=discount,
                        comment=comment,
                        lab_tech=lab_tech_val,
                        payment_method_id=payment_method_id,
                        is_child=is_child
                    )
                    db.session.add(appt)
                    created_count += 1
                
                db.session.commit()
                flash(f'Загружено записей: {created_count}', 'success')
                
             else:
                 flash('Только .xlsx файлы поддерживаются для журнала', 'error')

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка импорта: {str(e)}', 'error')

    return redirect(url_for('main.journal', center_id=center_id))

# --- Clinic Management ---

@admin.route('/clinics')
def clinics():
    # Use Clinic model
    clinics = Clinic.query.all()
    cities = Location.query.filter_by(type='city').all()
    return render_template('admin_clinics.html', clinics=clinics, cities=cities)

@admin.route('/clinics/add', methods=['POST'])
def add_clinic():
    name = request.form.get('name')
    city_id = request.form.get('city_id')
    phone = request.form.get('phone')
    
    if not name or not city_id:
        flash('Название и Город обязательны', 'error')
        return redirect(url_for('admin.clinics'))
        
    clinic = Clinic(
        name=name,
        city_id=int(city_id),
        phone=phone
    )
    db.session.add(clinic)
    db.session.commit()
    flash(f'Клиника {name} добавлена', 'success')
    return redirect(url_for('admin.clinics'))

@admin.route('/clinics/<int:id>/update', methods=['POST'])
def update_clinic(id):
    clinic = Clinic.query.get_or_404(id)
    
    clinic.name = request.form.get('name')
    clinic.city_id = request.form.get('city_id')
    clinic.phone = request.form.get('phone')
    
    db.session.commit()
    flash(f'Клиника {clinic.name} обновлена', 'success')
    return redirect(url_for('admin.clinics'))

@admin.route('/clinics/<int:id>/delete', methods=['POST'])
def delete_clinic(id):
    clinic = Clinic.query.get_or_404(id)
    db.session.delete(clinic)
    db.session.commit()
    flash('Клиника удалена', 'success')
    return redirect(url_for('admin.clinics'))

@admin.route('/clinics/import', methods=['POST'])
def import_clinics():
    if 'file' not in request.files:
        flash('Нет файла', 'error')
        return redirect(url_for('admin.clinics'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'error')
        return redirect(url_for('admin.clinics'))

    if file:
        filename = secure_filename(file.filename)
        clinics_created = 0
        cities_created = 0
        
        try:
            # Determine file type
            if filename.endswith('.csv'):
                # Handle CSV
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_input = csv.reader(stream)
                header = next(csv_input, None)
                
                for row in csv_input:
                    if len(row) >= 1: # Name required
                        name = row[0].strip()
                        if not name: continue
                        city_name = row[1].strip() if len(row) > 1 else None
                        phone = row[2].strip() if len(row) > 2 else None
                        
                        # Process City
                        city = None
                        if city_name:
                             city = Location.query.filter(Location.name.ilike(city_name)).first()
                             if not city:
                                 city = Location(name=city_name)
                                 db.session.add(city)
                                 db.session.flush() # Get ID
                                 cities_created += 1

                        # Check exist
                        if not Clinic.query.filter_by(name=name).first():
                            # If city is None, we can't create Clinic because city_id is nullable=False in Model?
                            # Model says: city_id = db.Column(..., nullable=False)
                            # So we MUST have a city. 
                            # If no city in file, what to do? Skip or Default?
                            # Skip for now if no city.
                            if city:
                                clinic = Clinic(name=name, city_id=city.id, phone=phone)
                                db.session.add(clinic)
                                clinics_created += 1
                        
            elif filename.endswith('.xlsx'):
                # Handle Excel
                wb = openpyxl.load_workbook(file)
                sheet = wb.active
                
                # Iterate rows, skipping header (min_row=2)
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]: continue
                    name = str(row[0]).strip()
                    city_name = str(row[1]).strip() if len(row) > 1 and row[1] else None
                    phone = str(row[2]).strip() if len(row) > 2 and row[2] else None
                    
                    # Process City
                    city = None
                    if city_name:
                         city = Location.query.filter(Location.name.ilike(city_name)).first()
                         if not city:
                             city = Location(name=city_name)
                             db.session.add(city)
                             db.session.flush() # Get ID
                             cities_created += 1
                    
                    if not Clinic.query.filter_by(name=name).first():
                        if city: # City required
                            clinic = Clinic(name=name, city_id=city.id, phone=phone)
                            db.session.add(clinic)
                            clinics_created += 1

            else:
                 flash('Неподдерживаемый формат файла. Используйте CSV или XLSX.', 'error')
                 return redirect(url_for('admin.clinics'))

            db.session.commit()
            flash(f'Импортировано клиник: {clinics_created} (Новых городов: {cities_created})', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка импорта: {str(e)}', 'error')
            
    return redirect(url_for('admin.clinics'))
