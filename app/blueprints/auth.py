from flask import Blueprint, render_template, redirect, url_for, flash, request, session, Response
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.models import User, Organization, Location
from app.forms import LoginForm, RegistrationForm
from werkzeug.security import generate_password_hash, check_password_hash
import io
import random
import string
from PIL import Image, ImageDraw, ImageFont

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) # Assuming main.index exists
    
    
    form = LoginForm()
    registration_form = RegistrationForm()
    
    # Fetch cities for registration modal (needed for both GET and POST error rendering)
    cities = Location.query.filter_by(type='city').all()
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            if user.is_blocked:
                flash('Ваш аккаунт заблокирован. Обратитесь к администратору.', 'danger')
                return render_template('auth/login.html', form=form, registration_form=registration_form, cities=cities)

            if user.is_blocked:
                flash('Ваш аккаунт заблокирован. Обратитесь к администратору.', 'danger')
                return render_template('auth/login.html', form=form, registration_form=registration_form, cities=cities)

            if not user.is_confirmed and user.role != 'admin': # Admin fallback to avoid lockout
                flash('Ваш аккаунт ожидает подтверждения администратором', 'warning')
                return render_template('auth/login.html', form=form, registration_form=registration_form, cities=cities)
            
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
            

            
    return render_template('auth/login.html', form=form, registration_form=registration_form, cities=cities)

@auth.route('/register', methods=['POST'])
def register():
    form = RegistrationForm()
    
    # Captcha validation
    captcha_text = session.get('captcha')
    if not captcha_text or form.captcha.data.upper() != captcha_text:
        flash('Неверный код с картинки', 'danger')
        return redirect(url_for('auth.login', _anchor='register'))

    if form.validate_on_submit():
        # Check/Create Organization
        org = Organization.query.filter_by(name=form.organization_name.data).first()
        if not org:
            org = Organization(name=form.organization_name.data)
            db.session.add(org)
            db.session.commit()
            
        # Get city_id from form (manual field)
        city_id = request.form.get('city_id')
        
        user = User(username=form.username.data, email=form.email.data, organization_id=org.id)
        if city_id:
            user.city_id = int(city_id)
            
        user.password_hash = generate_password_hash(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Поздравляем, вы успешно зарегистрировались!', 'success')
        return redirect(url_for('auth.login'))
    
    # If validation fails, we need to show errors. 
    # Since it's a modal on the login page, we might need a better way to show errors.
    # For now, simple flash messages and redirecting back to login with anchor.
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Ошибка в поле {field}: {error}", 'danger')
            
    return redirect(url_for('auth.login', _anchor='register'))

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/captcha')
def captcha():
    # Simple captcha generation
    image = Image.new('RGB', (120, 40), color=(255, 255, 255))
    font = ImageFont.load_default()
    draw = ImageDraw.Draw(image)
    
    # Generate random text
    text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    session['captcha'] = text
    
    draw.text((10, 10), text, fill=(0, 0, 0), font=None) # Default font is very small, might need custom font
    
    # Add some noise
    for _ in range(100):
        x = random.randint(0, 120)
        y = random.randint(0, 40)
        draw.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        
    buf = io.BytesIO()
    image.save(buf, 'png')
    buf.seek(0)
    
    return Response(buf, mimetype='image/png')
