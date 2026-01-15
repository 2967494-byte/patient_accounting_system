from flask import Blueprint, render_template, redirect, url_for, flash, request, session, Response, jsonify
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
                return jsonify({'success': False, 'errors': {'username': ['Ваш аккаунт заблокирован. Обратитесь к администратору.']}}), 403

            if not user.is_confirmed and user.role != 'admin':
                return jsonify({'success': False, 'errors': {'username': ['Ваш аккаунт ожидает подтверждения администратором']}}), 403
            
            login_user(user, remember=form.remember_me.data)
            session.permanent = True
            next_page = request.args.get('next')
            redirect_url = next_page if next_page else url_for('main.index')
            return jsonify({'success': True, 'redirect': redirect_url})
        else:
            return jsonify({'success': False, 'errors': {'password': ['Неверное имя пользователя или пароль']}}), 401
            
    if form.errors and request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'success': False, 'errors': form.errors}), 400
            
    return render_template('auth/login.html', form=form, registration_form=registration_form, cities=cities)

@auth.route('/register', methods=['POST'])
def register():
    form = RegistrationForm()
    
    # Captcha validation
    captcha_text = session.get('captcha')
    if not captcha_text or form.captcha.data.upper() != captcha_text:
        return jsonify({
            'success': False,
            'errors': {'captcha': ['Неверный код с картинки']}
        }), 400

    if form.validate_on_submit():
        # Get city_id from form (manual field)
        city_id = request.form.get('city_id')
        if not city_id:
            return jsonify({
                'success': False,
                'errors': {'city_id': ['Пожалуйста, выберите город']}
            }), 400

        # Check/Create Organization
        org_name = form.organization_name.data.strip()
        org = Organization.query.filter_by(name=org_name).first()
        if not org:
            org = Organization(name=org_name)
            db.session.add(org)
            db.session.commit()
            
        username = form.username.data.strip()
        user = User(username=username, email=form.email.data, organization_id=org.id)
        user.city_id = int(city_id)
        user.password_hash = generate_password_hash(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Поздравляем, вы успешно зарегистрировались!', 'success')
        
        # Notify Telegram
        from app.telegram_bot import telegram_bot
        telegram_bot.send_new_user_notification(user)
        
        return jsonify({'success': True, 'redirect': url_for('auth.login')})
    
    # If validation fails
    return jsonify({
        'success': False,
        'errors': {field: errors for field, errors in form.errors.items()}
    }), 400

@auth.route('/logout')
@login_required
def logout():
    from flask import get_flashed_messages
    get_flashed_messages() # Consume all pending flashes to avoid leakage after logout
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/captcha')
def captcha():
    # Robust captcha generation with larger size and multiple font candidates
    width = 180
    height = 60
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # Generate random text
    text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    session['captcha'] = text
    
    # Comprehensive font candidates for Windows and Linux
    font_candidates = [
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf"
    ]
    
    font = None
    font_size = 40
    for font_name in font_candidates:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except:
            continue
    
    if font:
        # Calculate text position (center)
        try:
            # Pillow 8.0.0+
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except AttributeError:
            # Older Pillow versions
            tw, th = draw.textsize(text, font=font)
            
        x = (width - tw) // 2
        y = (height - th) // 2 - 5
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
    else:
        # Last resort fallback: default font is tiny (6x10), so we scale it manually
        # Draw text to a small internal mask
        temp_font = ImageFont.load_default()
        temp_img = Image.new('L', (width // 3, height // 3), 0)
        temp_draw = ImageDraw.Draw(temp_img)
        temp_draw.text((5, 2), text, fill=255, font=temp_font)
        
        # Scale up (3x) to fill the main container
        temp_img = temp_img.resize((width, height), resample=Image.NEAREST)
        image.paste((0, 0, 0), mask=temp_img)
    
    # Add some noise (lines and points)
    for _ in range(8):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(random.randint(180, 220), random.randint(180, 220), random.randint(180, 220)), width=2)
        
    for _ in range(100):
        x, y = random.randint(0, width), random.randint(0, height)
        draw.point((x, y), fill=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
        
    buf = io.BytesIO()
    image.save(buf, 'png')
    buf.seek(0)
    
    return Response(buf, mimetype='image/png')

@auth.route('/confirm/<token>')
def confirm_email(token):
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired
    from flask import current_app
    
    ts = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    
    try:
        email = ts.loads(token, salt='email-confirm-key', max_age=86400) # 24 hours link
    except SignatureExpired:
        flash('Ссылка для подтверждения истекла.', 'danger')
        return redirect(url_for('auth.login'))
    except Exception:
        flash('Неверная ссылка для подтверждения.', 'danger')
        return redirect(url_for('auth.login'))
    
    user = User.query.filter_by(email=email).first_or_404()
    
    if user.is_confirmed:
        flash('Аккаунт уже подтвержден.', 'info')
    else:
        user.is_confirmed = True
        db.session.commit()
        flash('Спасибо! Ваш аккаунт подтвержден. Теперь вы можете войти.', 'success')
        
    return redirect(url_for('auth.login'))
