from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, current_app

from flask_login import login_required, current_user, login_user

from app.extensions import db

from app.models import (

    User, Location, Doctor, Service, AdditionalService, ServicePrice, AdditionalServicePrice,

    Clinic, Manager, PaymentMethod, Appointment, Organization, GlobalSetting,

    AppointmentHistory, AppointmentAdditionalService, AppointmentService

)

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



@admin.route('/journal/import', methods=['POST'])

@login_required

def import_journal_data():

    center_id = request.form.get('center_id')

    if not center_id:

        flash('Не выбран центр', 'error')

        return redirect(url_for('admin.additional'))



    if 'file' not in request.files:

        flash('Нет файла', 'error')

        return redirect(url_for('admin.additional'))

    

    file = request.files['file']

    if file.filename == '':

        flash('Файл не выбран', 'error')

        return redirect(url_for('admin.additional'))

        

    original_filename = file.filename

    if not (original_filename.lower().endswith('.csv') or original_filename.lower().endswith('.xlsx')):

        flash('Неподдерживаемый формат. Используйте CSV или XLSX.', 'error')

        return redirect(url_for('admin.additional'))

        

    filename = secure_filename(file.filename)



    try:

        rows = []

        if original_filename.lower().endswith('.csv'):

            content = file.stream.read()

            text = None

            try:

                text = content.decode("utf-8-sig")

            except UnicodeDecodeError:

                try:

                    text = content.decode("cp1251")

                except UnicodeDecodeError:

                    text = content.decode("utf-8", errors="ignore")

            

            stream = io.StringIO(text, newline=None)

            stream.seek(0)

            

            try:

                sample = stream.read(2048)

                stream.seek(0)

                if not sample: 

                    rows = []

                else:

                    dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")

                    csv_input = csv.reader(stream, dialect)

                    rows = list(csv_input)

            except csv.Error:

                stream.seek(0)

                csv_input = csv.reader(stream)

                rows = list(csv_input)

            except Exception:

                stream.seek(0)

                rows = list(csv.reader(stream))

            

        elif original_filename.lower().endswith('.xlsx'):

            wb = openpyxl.load_workbook(file, data_only=True)

            sheet = wb.active

            for r in sheet.iter_rows(values_only=True):

                rows.append(list(r))

        

        if not rows:

            flash(f'Файл пуст (Filename: {original_filename})', 'error')

            return redirect(url_for('admin.additional'))

            

        delete_old = request.form.get('delete_old') == 'on'



        # Header Detection

        headers = []

        if rows:

            headers = [str(h).strip().lower() if h else '' for h in rows[0]]

        

        header_row_idx = 0

        if 'дата' not in headers and len(rows) > 1:

             headers = [str(h).strip().lower() if h else '' for h in rows[1]]

             header_row_idx = 1

             

        col_map = {}

        for idx, h in enumerate(headers):

            if 'дата' in h and 'рождения' not in h: col_map['date'] = idx

            elif 'пациент' in h: col_map['patient'] = idx

            elif 'врач' in h: col_map['doctor'] = idx

            elif 'исследование' in h or 'услуга' in h: col_map['service'] = idx

            elif 'оплата' in h: col_map['payment'] = idx

            elif 'скидка' in h: col_map['discount'] = idx

            elif 'сумма' in h: col_map['cost'] = idx

            elif 'стоимость' in h and 'cost' not in col_map: col_map['cost'] = idx 

            elif 'договор' in h: col_map['contract'] = idx

            elif 'ребенок' in h: col_map['is_child'] = idx

            elif 'клиника' in h: col_map['clinic'] = idx

            elif 'кол-во' in h: col_map['quantity'] = idx

            elif 'доп' in h and 'услуги' in h: col_map['additional_services'] = idx

            elif 'комментарий' in h: col_map['comment'] = idx

            

        if 'date' not in col_map or 'patient' not in col_map:

            col_map = {

                'date': 0, 'contract': 3, 'patient': 4, 'is_child': 5, 'doctor': 6,

                'clinic': 8, 'service': 9, 'additional_services': 10, 'quantity': 11,

                'payment': 14, 'discount': 15, 'cost': 16, 'comment': 12

            }



        valid_rows_to_insert = []

        unique_dates_to_clean = set()

        warnings = []



        for i in range(header_row_idx + 1, len(rows)):

            row = rows[i]

            if not row or len(row) < 5: continue

            

            def get_val(key):

                idx = col_map.get(key)

                if idx is not None and idx < len(row):

                   return row[idx]

                return None



            date_val = get_val('date')

            if not date_val: continue

            

            appt_date = None

            if isinstance(date_val, datetime): appt_date = date_val.date()

            elif isinstance(date_val, date): appt_date = date_val

            elif isinstance(date_val, str): 

                val_str = date_val.strip()

                if not val_str: continue

                # Remove timestamps if present in string like "2025-12-01 00:00:00"

                # Replace comma with dot (e.g. 09,12.2025 -> 09.12.2025)

                val_str = val_str.replace(',', '.')

                

                for fmt in ['%d.%m.%Y', '%Y-%m-%d', '%d.%m.%y', '%d/%m/%Y']:

                    try:

                        appt_date = datetime.strptime(val_str, fmt).date()

                        break

                    except: pass

            

            if not appt_date: 

                warnings.append(f"Строка {i+1}: Неверный формат даты '{date_val}'.")

                continue

            

            patient = str(get_val('patient') or '').strip()

            if not patient: continue

            

            # --- STRICT LOGIC ---

            

            # 1. DOCTOR MATCHING

            doctor_name = str(get_val('doctor') or '').strip()

            

            # New Rule: Empty doctor -> "Без врача"

            if not doctor_name:

                doctor_name = "Без врача"

            

            doc_obj = None

            if doctor_name:

                doc_obj = Doctor.query.filter(Doctor.name.ilike(doctor_name)).first()

            

            if not doc_obj:

                # 1b. Fuzzy fallback: Clean spaces and try again

                import re

                

                # Normalize spaces (e.g. "Name  Surname" -> "Name Surname")

                clean_name = re.sub(r'\s+', ' ', doctor_name)

                if clean_name != doctor_name:

                    doc_obj = Doctor.query.filter(Doctor.name.ilike(clean_name)).first()

                

                # 1c. Super-fuzzy fallback: Replace spaces with wildcards

                if not doc_obj:

                    # "Ivanov Ivan" -> "Ivanov%Ivan"

                    wildcard_name = clean_name.replace(' ', '%')

                    doc_obj = Doctor.query.filter(Doctor.name.ilike(wildcard_name)).first()



            if not doc_obj:

                warnings.append(f"Строка {i+1}: Врач '{doctor_name}' не найден (даже с нечетким поиском).")

                continue # Skip row

                

            # 2. MANAGER AUTO-ASSIGN

            manager_id = None

            if doc_obj.manager:

                mgr = User.query.filter(User.username.ilike(doc_obj.manager)).first()

                if mgr: manager_id = mgr.id

            

            # 3. CLINIC MATCHING

            clinic_name = str(get_val('clinic') or '').strip()

            clinic_obj = None

            if clinic_name:

                 clinic_obj = Clinic.query.filter(Clinic.name.ilike(clinic_name)).first()

                 

            # Warning if clinic provided but not found? Or just ignore? 

            # Plan said "Match Clinic (skip if not found) or Warning".

            # Let's skip if clinic name was provided but not found, to be safe.

            # 4. SERVICE MATCHING

            service_name = str(get_val('service') or '').strip()

            service_obj = None

            

            if service_name:

                service_obj = Service.query.filter(Service.name.ilike(service_name)).first()

                if not service_obj:

                     warnings.append(f"Строка {i+1}: Услуга '{service_name}' не найдена (игнорируется, так как не найдена в каталоге).")

                     # If service name was present but invalid, should we treat it as "No Service" or "Skip"?

                     # Strict mode usually implies Skip. But let's see if we have Add Services.

                     # If user says "Load data if Add Srv not empty", maybe we treat invalid main service as None?

                     # Let's keep strictness: If valid name provided but not found -> Warning (and effectively None for logic below).

                     pass



            # 5. ADDITIONAL SERVICES MATCHING

            add_services_str = str(get_val('additional_services') or '').strip()

            add_service_objs = []

            if add_services_str:

                # Split by comma

                for raw_name in add_services_str.split(','):

                    name = raw_name.strip()

                    if not name: continue

                    

                    add_srv = AdditionalService.query.filter(AdditionalService.name.ilike(name)).first()

                    if not add_srv:

                         warnings.append(f"Строка {i+1}: Доп. услуга '{name}' не найдена.")

                         # Strict: If explicitly listed but not found, we skip the row to avoid data loss/corruption.

                         add_service_objs = [] # clear to trigger skip

                         service_obj = None # ensure skip

                         break

                    

                    add_service_objs.append(add_srv)



            # VALIDATION: Must have either Main Service OR Additional Services

            if not service_obj and not add_service_objs:

                 if not warnings: # Don't duplicate if we already warned about invalid service

                     warnings.append(f"Строка {i+1}: Не указана ни основная, ни доп. услуга.")

                 continue



            # COST CALCULATION

            # Parse quantity first for cost calc

            excel_qty = 1

            raw_qty = get_val('quantity')

            if raw_qty:

                try: excel_qty = int(float(str(raw_qty).replace(',', '.')))

                except: excel_qty = 1



            cost = 0.0

            if service_obj:

                cost += service_obj.get_price(appt_date) # Main service always quantity 1

            

            for ads in add_service_objs:

                cost += ads.get_price(appt_date) * excel_qty



            

            # --- END STRICT LOGIC ---

            

            valid_rows_to_insert.append({

                'date': appt_date,

                'patient': patient,

                'service_obj': service_obj, # Store obj

                'doctor_obj': doc_obj,      # Store obj

                'clinic_obj': clinic_obj,   # Store obj

                'manager_id': manager_id,

                'contract': str(get_val('contract') or '').strip(),

                'cost': cost, # Catalog price (Main + Additional)

                'discount_raw': get_val('discount'), # Raw discount

                'payment_raw': str(get_val('payment') or '').strip(),

                'is_child_raw': get_val('is_child'),

                'quantity_raw': get_val('quantity'),

                'quantity_raw': get_val('quantity'),

                'add_service_objs': add_service_objs, # List of objects

                'add_services_raw': add_services_str, # For legacy comment if needed?

                'comment_raw': str(get_val('comment') or '').strip()

            })

            unique_dates_to_clean.add(appt_date)

            

        if not valid_rows_to_insert:

            msg = 'Не найдено валидных строк.'

            if warnings: msg += f" Ошибки ({len(warnings)}): " + "; ".join(warnings[:5]) + "..."

            flash(msg, 'warning')

            return redirect(url_for('admin.additional'))



        if delete_old and unique_dates_to_clean:

             # Fetch IDs to delete dependencies first (query.delete bypasses cascade)

             appts_to_delete = db.session.query(Appointment.id).filter(

                 Appointment.center_id == int(center_id),

                 Appointment.date.in_(unique_dates_to_clean)

             ).all()

             

             appt_ids = [a[0] for a in appts_to_delete]

             

             if appt_ids:

                 # Delete associations manually (using models)

                 # AppointmentAdditionalService (Additional Services)

                 AppointmentAdditionalService.query.filter(

                     AppointmentAdditionalService.appointment_id.in_(appt_ids)

                 ).delete(synchronize_session=False)



                 # AppointmentService (Main Services)

                 AppointmentService.query.filter(

                     AppointmentService.appointment_id.in_(appt_ids)

                 ).delete(synchronize_session=False)



                 # History

                 AppointmentHistory.query.filter(

                     AppointmentHistory.appointment_id.in_(appt_ids)

                 ).delete(synchronize_session=False)



                 # Finally delete Appointments

                 Appointment.query.filter(

                     Appointment.id.in_(appt_ids)

                 ).delete(synchronize_session=False)



        created_count = 0

        current_center_id = int(center_id)

        current_user_id = current_user.id

        

        for data in valid_rows_to_insert:

            # Boolean

            is_child = False

            raw_child = data['is_child_raw']

            if raw_child:

                if isinstance(raw_child, bool): is_child = raw_child

                else:

                    s = str(raw_child).lower()

                    if s in ['true', 'yes', 'да', '1', '+']: is_child = True



            # Payment Method

            pm_name = data['payment_raw']

            pm_id = None

            if pm_name:

                pm = PaymentMethod.query.filter(PaymentMethod.name.ilike(pm_name)).first()

                if pm: pm_id = pm.id

                else:

                     pm = PaymentMethod(name=pm_name)

                     db.session.add(pm)

                     db.session.flush()

                     pm_id = pm.id

            

            # Discount

            discount = 0.0

            if data['discount_raw'] is not None:

                if isinstance(data['discount_raw'], (int, float)):

                    discount = float(data['discount_raw'])

                else:

                    d_str = str(data['discount_raw']).replace(u'\xa0', '').replace(' ', '').replace(',', '.')

                    try: discount = float(d_str)

                    except: discount = 0.0

                

            # Quantity parsed above (excel_qty)

            

            # Legacy Quantity (Main Service) set to 1

            main_qty = 1



            appt = Appointment(

                center_id=current_center_id,

                date=data['date'],

                time="09:00",

                patient_name=data['patient'],

                service=data['service_obj'].name if data['service_obj'] else "Доп. услуги", # Fallback name

                # Link M2M service

                doctor=data['doctor_obj'].name,

                doctor_id=data['doctor_obj'].id,

                manager_id=data['manager_id'], # Auto-assigned

                clinic_id=data['clinic_obj'].id if data['clinic_obj'] else None,

                cost=float(data['cost']),

                discount=discount,

                payment_method_id=pm_id,

                is_child=is_child,

                contract_number=data['contract'],

                quantity=main_qty, # Always 1 for main service

                author_id=current_user_id,

                comment=data['comment_raw']

            )

            

            # Add service to M2M relationship (Force Quantity 1 for Main)

            if data['service_obj']:

                appt.service_associations.append(AppointmentService(service=data['service_obj'], quantity=1))

            

            # Add Additional Services to M2M (Use Excel Quantity)

            if data['add_service_objs']:

                for ads in data['add_service_objs']:

                    appt.additional_service_associations.append(AppointmentAdditionalService(additional_service=ads, quantity=excel_qty))

            

            # Legacy comment? Maybe keep strict? 

            # User said "map column... cost substituted". 

            # If mapped, no need for raw text in comment unless unmapped content exists (which we skip now).

            # So we can remove the comment assignment or keep it if strictly necessary. 

            # Let's keep a cleaner comment:

            if data['add_services_raw']:

                 # If we mapped them, maybe we don't need "Доп: ..." in comment?

                 # But sticking to previous behavior is safer, let's just log it if needed.

                 # Actually, better to NOT duplicate logic in comment if it's real data now.

                 pass 

            

            db.session.add(appt)

            created_count += 1

            

        db.session.commit()

        

        success_msg = f'Успешно импортировано: {created_count}.'

        if warnings:

            # flash works with categories. detailed warning list might be too long.

            # let's show top 5 warnings.

            warn_msg = f" Пропущено строк: {len(warnings)}. Примеры: " + "; ".join(warnings[:5])

            flash(success_msg + warn_msg, 'warning') # Use warning color to draw attention

        else:

            flash(success_msg, 'success')



    except Exception as e:

        db.session.rollback()

        flash(f'Ошибка импорта: {str(e)}', 'error')



    return redirect(url_for('admin.additional'))



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
        is_confirmed=False  # Require email confirmation
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
    
    # Send Confirmation Email
    try:
        from app.extensions import mail
        from flask_mail import Message
        from itsdangerous import URLSafeTimedSerializer
        from flask import current_app, url_for

        ts = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        token = ts.dumps(email, salt='email-confirm-key')
        confirm_url = url_for('auth.confirm_email', token=token, _external=True)

        msg = Message('Подтвердите ваш email', recipients=[email])
        msg.body = f'Здравствуйте! Пожалуйста, перейдите по следующей ссылке для подтверждения вашего аккаунта: {confirm_url}'
        
        mail.send(msg)
        flash(f'Пользователь {username} создан. Письмо с подтверждением отправлено на {email}', 'success')
    except Exception as e:
        flash(f'Пользователь создан, но не удалось отправить письмо подтверждения: {str(e)}', 'warning')

    return redirect(url_for('admin.users'))

@admin.route('/users/edit/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role not in ['superadmin', 'admin']:
        flash('У вас нет прав для выполнения этого действия', 'error')
        return redirect(url_for('admin.users'))
        
    user = User.query.get_or_404(user_id)
    
    # Optional: Prevent editing superadmins by non-superadmins, etc. 
    # For now, simplistic check:
    if user.role == 'superadmin' and current_user.role != 'superadmin':
         flash('Вы не можете редактировать суперадминистратора', 'error')
         return redirect(url_for('admin.users'))

    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    organization_id = request.form.get('organization_id')
    city_id = request.form.get('city_id')
    center_id = request.form.get('center_id')

    # Update fields
    if username: user.username = username
    if email: user.email = email
    if role: user.role = role
    
    # Password update only if provided
    if password and password.strip():
        user.password_hash = generate_password_hash(password)

    # Relations
    # Handle "None" or empty strings
    if organization_id: user.organization_id = int(organization_id)
    else: user.organization_id = None
        
    if city_id: user.city_id = int(city_id)
    else: user.city_id = None
        
    if center_id: user.center_id = int(center_id)
    else: user.center_id = None

    try:
        db.session.commit()
        flash(f'Пользователь {user.username} успешно обновлен', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка обновления: {str(e)}', 'error')

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

# --- ICS Import Logic ---

from app.utils.ics_utils import parse_ics_content

import difflib



@admin.route('/import_ics', methods=['GET', 'POST'])

@login_required

def import_ics():

    centers = Location.query.filter_by(type='center').all()

    

    # Default start date: 2 months ago

    from datetime import timedelta

    default_start_date = (date.today() - timedelta(days=60)).strftime('%Y-%m-%d')

    

    if request.method == 'POST':

        if 'ics_file' not in request.files:

            flash('Нет файла', 'error')

            return redirect(request.url)

            

        file = request.files['ics_file']

        if file.filename == '':

            flash('Нет выбранного файла', 'error')

            return redirect(request.url)

            

        center_id = request.form.get('center_id')

        if not center_id:

             flash('Выберите филиал', 'error')

             return redirect(request.url)



        start_date_str = request.form.get('start_date')

        filter_date = None

        if start_date_str:

            try:

                filter_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

            except ValueError:

                pass

        

        if file:

            try:

                content = file.read().decode('utf-8')

                parsed_events = parse_ics_content(content)

                

                # --- Filter by Date ---

                if filter_date:

                    filtered_events = []

                    for event in parsed_events:

                        evt_date = datetime.strptime(event['date'], '%Y-%m-%d').date()

                        if evt_date >= filter_date:

                            filtered_events.append(event)

                    parsed_events = filtered_events

                

                # --- Fuzzy Matching Context ---

                services = Service.query.all()

                doctors = Doctor.query.all()

                

                # Pre-calculate normalized names for matching

                def normalize(s): return s.lower().replace(' ', '') if s else ''

                

                svc_map = {normalize(s.name): s.id for s in services}

                doc_map = {normalize(d.name): d.id for d in doctors}

                

                # Prepare enriched events for preview

                for event in parsed_events:

                    summary = event['raw_summary']

                    norm_summary = normalize(summary)

                    

                    # 1. Match Service

                    event['matched_service_id'] = None

                    # Try direct fuzzy on keywords or specific known substrings

                    # Simple heuristic: Check if any service name is substring of summary

                    best_ratio = 0

                    best_svc_id = None

                    

                    for s in services:

                        # Check "OPTG", "KT", "ORT" special logic because user files use shorthand

                        # This is specific custom logic based on observation

                        s_norm = normalize(s.name)

                        if len(s_norm) < 3: continue # Skip short

                        

                        # Direct containment

                        if s_norm in norm_summary:

                            best_ratio = 1.0

                            best_svc_id = s.id

                            break

                            

                        # Fuzzy

                        ratio = difflib.SequenceMatcher(None, s_norm, norm_summary).ratio()

                        # If summary is long, ratio might be low even if match is good.

                        # Better metric: check word overlap?

                        pass 

                        

                    # Improved Heuristic for key types

                    if not best_svc_id:

                        summary_lower = summary.lower()

                        # Keywords mapping to DB names (approximate)

                        keyword_map = {

                            'оптг': 'ОПТГ', 

                            'кт': 'КТ', 

                            'орт': 'Ортодонт' # Just guessing ID or Name pattern

                        }

                        for kw, target_name in keyword_map.items():

                            if kw in summary_lower:

                                # Find service with this name

                                matched_svc = next((s for s in services if target_name.lower() in s.name.lower()), None)

                                if matched_svc:

                                    best_svc_id = matched_svc.id

                                    break

                    

                    event['matched_service_id'] = best_svc_id

                    

                    # 2. Match Doctor

                    # Use extracted candidate or scan summary

                    event['matched_doctor_id'] = None

                    doc_candidate = event.get('doctor_from_desc')

                    

                    if doc_candidate:

                        # Fuzzy match candidate against DB

                        matches = difflib.get_close_matches(doc_candidate, [d.name for d in doctors], n=1, cutoff=0.6)

                        if matches:

                            target_doc = next(d for d in doctors if d.name == matches[0])

                            event['matched_doctor_id'] = target_doc.id

                    

                    # Fallback: scan summary for doctor names? (Might be expensive/risky)

                

                return render_template(

                    'import_ics.html', 

                    parsed_events=parsed_events, 

                    centers=centers, 

                    services=services, 

                    doctors=doctors,

                    center_id=center_id

                )

                

            except Exception as e:

                flash(f'Ошибка обработки файла: {str(e)}', 'error')

                return redirect(request.url)



    return render_template('import_ics.html', centers=centers, default_start_date=default_start_date)



@admin.route('/import_ics/confirm', methods=['POST'])

@login_required

def confirm_ics_import():

    center_id = request.form.get('center_id')

    

    # Process form list data

    # format: events[0][date], events[0][skip]...

    # Flask doesn't parse nested dicts automatically well for arbitrary lists this way easily without third party lib or manual loop

    # We will manually iterate since we know the structure or expected index count?

    # Actually, easier to iterate keys.

    

    imported_count = 0

    

    # Reconstruct data from flat keys

    events_data = {}

    for key, value in request.form.items():

        if key.startswith('events['):

            # Key format: events[0][field_name]

            try:

                _, index_str, field_part = key.split('[')

                index = int(index_str[:-1]) # remove ]

                field = field_part[:-1] # remove ]

                

                if index not in events_data:

                    events_data[index] = {}

                events_data[index][field] = value

            except ValueError:

                continue

                

    for index, data in events_data.items():

        if 'skip' in data and data['skip'] == '1':

            continue

            

        try:

            date_obj = datetime.strptime(data['date'], '%Y-%m-%d').date()

            time_str = data['time']

            

            # Create Appointment

            new_appt = Appointment(

                center_id=int(center_id),

                date=date_obj,

                time=time_str,

                patient_name=data.get('patient_name', 'Unknown'),

                patient_phone=data.get('patient_phone', ''),

                doctor_id=int(data['doctor_id']) if data.get('doctor_id') else None,

                # Simple service handling (not linking M2M fully if just quick import, or link first one)

                # Ideally we link AppointmentService

                quantity=1,

                author_id=current_user.id

            )

            

            db.session.add(new_appt)

            db.session.flush() # to get ID

            

            svc_id = data.get('service_id')

            if svc_id:

                svc = Service.query.get(int(svc_id))

                if svc:

                    # Link

                    assoc = AppointmentService(service_id=svc.id, appointment_id=new_appt.id, quantity=1)

                    db.session.add(assoc)

                    # Also update summary string

                    new_appt.service = svc.name

            else:

                new_appt.service = "Импорт (Неизвестно)"

            

            imported_count += 1

            

        except Exception as e:

            # Continue or fail?

            # Let's log/print and continue for robust partial import

            print(f"Failed to import row {index}: {e}")

            continue



    try:

        db.session.commit()

        flash(f'Успешно импортировано записей: {imported_count}', 'success')

    except Exception as e:

        db.session.rollback()

        flash(f'Ошибка сохранения: {str(e)}', 'error')

        

    return redirect(url_for('admin.import_ics'))


@admin.route('/users/impersonate/<int:user_id>')
@login_required
def impersonate_user(user_id):
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
        
    user = User.query.get_or_404(user_id)
    login_user(user)
    flash(f'Вы вошли как {user.username}', 'success')
    return redirect(url_for('main.dashboard'))

@admin.route('/reports/api/organizations')
@login_required
def reports_organizations():
    if current_user.role != 'superadmin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    month_str = request.args.get('month')
    if not month_str:
        today = datetime.now()
        month_str = today.strftime('%Y-%m')
        
    try:
        start_date = datetime.strptime(month_str, '%Y-%m').date()
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1)
    except ValueError:
        return jsonify({'error': 'Invalid month format'}), 400

    stats = db.session.query(
        User.username, 
        db.func.count(Appointment.id).label('count')
    ).join(Appointment, Appointment.author_id == User.id)\
     .filter(User.role == 'org')\
     .filter(Appointment.date >= start_date, Appointment.date < end_date)\
     .group_by(User.id)\
     .all()
     
    data = [{'username': s.username, 'count': s.count} for s in stats]
    return jsonify(data)

@admin.route('/reports/api/lab_techs')
@login_required
def reports_lab_techs():
    if current_user.role != 'superadmin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    # Lab Techs are users with role 'lab_tech' OR 'superadmin' (except specific 'admin' user)
    # Workload: Patient Count, Revenue
    
    year_str = request.args.get('year')
    month_str = request.args.get('month')
    day_str = request.args.get('day')
    
    # Default to current month if nothing provided
    if not year_str and not month_str and not day_str:
        today = datetime.now()
        year_str = str(today.year)
        month_str = str(today.month).zfill(2)
        
    query = db.session.query(
        User.username,
        db.func.count(Appointment.id).label('appt_count'),
        db.func.sum(Appointment.cost).label('total_revenue'),
        db.func.count(db.func.distinct(Appointment.patient_name)).label('unique_patients')
    ).join(Appointment, Appointment.author_id == User.id)\
     .filter(User.role.in_(['lab_tech', 'superadmin']))\
     .filter(User.username != 'admin')

    # Date Filtering
    try:
        if year_str and month_str and day_str and day_str != '00':
            # Specific Day
            target_date = datetime.strptime(f"{year_str}-{month_str}-{day_str}", '%Y-%m-%d').date()
            query = query.filter(db.func.date(Appointment.date) == target_date)
        elif year_str and month_str:
            # Whole Month
            start_date = datetime.strptime(f"{year_str}-{month_str}", '%Y-%m').date()
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1, day=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1, day=1)
            query = query.filter(Appointment.date >= start_date, Appointment.date < end_date)
        elif year_str:
            # Whole Year
            start_date = datetime(int(year_str), 1, 1).date()
            end_date = datetime(int(year_str) + 1, 1, 1).date()
            query = query.filter(Appointment.date >= start_date, Appointment.date < end_date)
    except ValueError:
        pass # Ignore invalid dates and define no filter (or return error?)

    stats = query.group_by(User.id).all()
     
    data = [{
        'username': s.username, 
        'appt_count': s.appt_count,
        'total_revenue': s.total_revenue or 0,
        'unique_patients': s.unique_patients
    } for s in stats]
    
    return jsonify(data)

@admin.route('/reports/api/audit')
@login_required
def reports_audit():
    if current_user.role != 'superadmin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    # Recent 100 actions
    history = AppointmentHistory.query.order_by(AppointmentHistory.timestamp.desc()).limit(100).all()
    
    data = []
    for h in history:
        data.append({
            'timestamp': h.timestamp.isoformat(),
            'user': h.user.username if h.user else 'Unknown',
            'action': h.action,
            'details': f"Appt #{h.appointment_id}"
        })
        
    return jsonify(data)

@admin.route('/reports/api/bonuses')
@login_required
def reports_bonuses():
    if current_user.role != 'superadmin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    month_str = request.args.get('month')
    if not month_str:
        today = datetime.now()
        month_str = today.strftime('%Y-%m')
        
    try:
        start_date = datetime.strptime(month_str, '%Y-%m').date()
        # End date is start of next month - 1 day, or just filter by year/month
        # Easier to filter by range
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1)
    except ValueError:
        return jsonify({'error': 'Invalid month format'}), 400
        
    doctor_name_expr = db.func.coalesce(Doctor.name, Appointment.doctor, 'Unknown').label('doctor_name')
    
    try:
        # Simplified query: Doctor -> Total Count, Total Revenue
        results = db.session.query(
            doctor_name_expr,
            db.func.count(Appointment.id).label('total_count'),
            db.func.sum(Appointment.cost).label('total_revenue')
        ).select_from(Appointment)\
         .outerjoin(Doctor, Appointment.doctor_id == Doctor.id)\
         .filter(Appointment.date >= start_date, Appointment.date < end_date)\
         .group_by(doctor_name_expr)\
         .order_by(db.func.count(Appointment.id).desc())\
         .all()
         
        rows = []
        for r in results:
            name = r.doctor_name
            if not name or not name.strip():
                name = 'Не указан'
                
            rows.append({
                'name': name,
                'count': r.total_count,
                'revenue': r.total_revenue or 0
            })
            
        return jsonify({
            'rows': rows,
            'month': month_str
        })
    except Exception as e:
        print(f"Error in reports_bonuses: {e}")
        return jsonify({'error': str(e)}), 500

@admin.route('/reports/api/bonuses/details')
@login_required
def reports_bonuses_details():
    if current_user.role != 'superadmin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    month_str = request.args.get('month')
    doctor_name = request.args.get('doctor_name')
    
    if not month_str or not doctor_name:
        return jsonify({'error': 'Missing parameters'}), 400
        
    try:
        start_date = datetime.strptime(month_str, '%Y-%m').date()
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1, day=1)
    except ValueError:
        return jsonify({'error': 'Invalid month format'}), 400
        
    doctor_name_expr = db.func.coalesce(Doctor.name, Appointment.doctor, 'Unknown')
    
    try:
        # Query: Select Patient Name, Service Name
        results = db.session.query(
            Appointment.patient_name,
            Appointment.date,
            Service.name.label('service_name')
        ).select_from(Appointment)\
         .outerjoin(Doctor, Appointment.doctor_id == Doctor.id)\
         .join(AppointmentService, Appointment.id == AppointmentService.appointment_id)\
         .join(Service, AppointmentService.service_id == Service.id)\
         .filter(Appointment.date >= start_date, Appointment.date < end_date)\
         .filter(doctor_name_expr == doctor_name)\
         .order_by(Appointment.date.desc())\
         .all()
         
        details = []
        for r in results:
            details.append({
                'patient_name': r.patient_name,
                'date': r.date.strftime('%d.%m.%Y'),
                'service_name': r.service_name
            })
            
        return jsonify(details)
    except Exception as e:
        print(f"Error in reports_bonuses_details: {e}")
        return jsonify({'error': str(e)}), 500

@admin.route('/reports/today')
@admin.route('/reports')
@login_required
def reports_today():
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('reports_today.html')

@admin.route('/reports/organizations')
@login_required
def reports_organizations_page():
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('reports_org_activity.html')

@admin.route('/reports/lab_workload')
@login_required
def reports_lab_page():
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('reports_lab_workload.html')

@admin.route('/reports/logs')
@login_required
def reports_logs_page():
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('reports_logs.html')

@admin.route('/reports/bonuses')
@login_required
def reports_bonuses_page():
    if current_user.role != 'superadmin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('reports_bonuses.html')
