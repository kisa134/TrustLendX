import uuid
import functools
import logging
import json
import random
import io
import base64
import os
from datetime import datetime, timedelta
from flask import render_template, url_for, flash, redirect, request, jsonify, session, Response, make_response, send_from_directory, abort
from urllib.parse import urlparse
import pyotp
import qrcode
from app import app, db, csrf, limiter
from forms import LoginForm, RegistrationForm, DepositForm, ContactForm, OTPSetupForm, OTPVerifyForm, ChangePasswordForm, TonDepositForm, ManualEmailVerificationForm
from models import User, Transaction, ContactMessage, TonDeposit, AdminNotification, WithdrawalRequest, UserIPLog
import utils
from utils import (calculate_profit_for_term, sanitize_input, sanitize_username, 
                safe_format, generate_referral_code, get_referral_url, calculate_referral_earnings, 
                get_client_ip, log_user_ip)
from email_service import send_verification_email
# Импорт payment_gateway удален в связи с переходом полностью на TON
# from payment_gateway import create_invoice, payment_client
from performance import cache_control

# Установка уровня логирования
logging.basicConfig(level=logging.DEBUG)

# Замена для декоратора login_required из Flask-Login - теперь через cookie
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        logging.debug(f"Cookie auth check for {f.__name__}")
        logging.debug(f"Cookies: {request.cookies}")
        
        # Проверяем авторизацию через куки
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        
        if not user_id or logged_in != 'true':
            logging.debug(f"Cookie auth failed for {f.__name__}, redirecting to login")
            flash('Пожалуйста, войдите в систему для доступа к этой странице.', 'warning')
            return redirect(url_for('login', next=request.url))
            
        logging.debug(f"Cookie auth successful for user_id={user_id}")
        return f(*args, **kwargs)
    return decorated_function

# Декоратор для проверки прав администратора
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        logging.debug(f"Admin auth check for {f.__name__}")
        
        # Проверяем авторизацию через куки
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        is_admin = request.cookies.get('is_admin')
        
        logging.debug(f"Admin cookies check: user_id={user_id}, logged_in={logged_in}, is_admin={is_admin}")
        
        if not user_id or logged_in != 'true':
            logging.debug(f"Cookie auth failed for {f.__name__}, redirecting to login")
            flash('Пожалуйста, войдите в систему для доступа к этой странице.', 'warning')
            return redirect(url_for('login', next=request.url))
            
        # Проверяем админский статус из cookies
        if is_admin != 'true':
            logging.debug(f"Admin check failed for user_id={user_id}, is_admin cookie = {is_admin}")
            flash('У вас нет прав для доступа к этой странице.', 'danger')
            return redirect(url_for('dashboard'))
            
        # Дополнительная проверка в базе данных
        user = User.query.get(int(user_id))
        if not user or not user.is_admin:
            logging.debug(f"Admin auth failed for {f.__name__}")
            flash('У вас нет прав администратора для доступа к этой странице.', 'danger')
            return redirect(url_for('index'))
        
        logging.debug(f"Admin auth successful for user_id={user_id}")
        return f(*args, **kwargs)
    return decorated_function

# Заглушка для current_user - теперь через cookie
class CurrentUser:
    @property
    def is_authenticated(self):
        return request.cookies.get('logged_in') == 'true'
    
    @property
    def id(self):
        user_id = request.cookies.get('user_id')
        if user_id:
            return int(user_id)
        return None
    
    @property
    def username(self):
        return request.cookies.get('username', 'Пользователь')
        
    @property
    def is_admin(self):
        return request.cookies.get('is_admin') == 'true'

# Создаем объект для заглушки
current_user = CurrentUser()

# Функция для логирования IP-адреса пользователя перенесена в utils.py

@app.route('/')
def index():
    # Передаем форму контактов и текущее время для отображения транзакций на главной странице
    form = ContactForm()
    now = datetime.now()
    
    # Получаем статистику по депозитам и выводам
    from transaction_generator import get_deposit_stats
    stats = get_deposit_stats()
    
    return render_template('index.html', title='Home', now=now, datetime=datetime, 
                          timedelta=timedelta, form=form, stats=stats)

# 🔒 Security fix: Декоратор для защиты API-маршрутов
def api_login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        logging.debug(f"API auth check for {f.__name__}")
        
        # Проверяем авторизацию через куки
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        
        # Проверяем через URL-параметры (для поддержки AJAX-запросов)
        user_id = user_id or request.args.get('user_id')
        logged_in = logged_in or request.args.get('logged_in')
        
        # Проверяем через заголовки запроса
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Удаляем 'Bearer ' из начала
            # Простая проверка токена - в реальном приложении здесь будет более сложная логика
            if token == app.config.get('API_TOKEN', 'dev_api_token'):
                return f(*args, **kwargs)
        
        if not user_id or logged_in != 'true':
            logging.debug(f"API auth failed for {f.__name__}")
            return jsonify({'error': 'Unauthorized', 'message': 'Авторизация требуется для доступа к API'}), 401
            
        logging.debug(f"API auth successful for user_id={user_id}")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/transactions')
@limiter.limit("60 per minute")  # 🔒 Security fix: Защита API от чрезмерного количества запросов
@cache_control(max_age=1)  # Кэширование на 1 секунду для более быстрого обновления реальных транзакций
@api_login_required  # 🔒 Security fix: Требуем авторизацию для доступа к API
def get_transactions():
    """API-эндпоинт для получения списка последних транзакций"""
    from transaction_generator import get_transactions
    return jsonify(get_transactions())

@app.route('/api/deposit-stats')
@limiter.limit("30 per minute")  # 🔒 Security fix: Защита API от чрезмерного количества запросов
@cache_control(max_age=5)  # Кэширование на 5 секунд 
@api_login_required  # 🔒 Security fix: Требуем авторизацию для доступа к API
def get_api_deposit_stats():
    """API-эндпоинт для получения статистики по депозитам"""
    from transaction_generator import get_deposit_stats
    return jsonify(get_deposit_stats())

@app.route('/faq')
def faq():
    return render_template('faq.html', title='FAQ')

@app.route('/deposit-terms')
def deposit_terms():
    """Страница с условиями депозитов"""
    return render_template('deposit_terms.html', title='Условия депозитов')

@app.route('/privacy-policy')
def privacy_policy():
    """Страница с политикой конфиденциальности"""
    return render_template('privacy_policy.html', title='Политика конфиденциальности')

@app.route('/terms-of-use')
def terms_of_use():
    """Страница с условиями использования сервиса"""
    return render_template('terms_of_use.html', title='Условия использования')

@app.route('/sitemap.xml')
def sitemap():
    """Карта сайта для поисковых систем"""
    return send_from_directory('static', 'sitemap.xml')

@app.route('/aml-check')
def aml_check():
    """Страница AML-проверки криптокошельков с информацией"""
    return render_template('aml_check.html', title='AML-проверка криптокошельков')

@app.route('/aml-check-simple', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour; 50 per day")  # 🔒 Security fix: Ограничение количества запросов на AML проверку
def aml_check_simple():
    """Упрощенная страница AML-проверки только с формой"""
    from getblock_client import GetBlockClient
    from flask_wtf import FlaskForm
    
    # Создаем простую форму для CSRF-токена
    form = FlaskForm()
    result = None
    address = None
    currency = None
    error = None
    
    if request.method == 'POST':
        try:
            address = request.form.get('wallet_address')
            currency = request.form.get('blockchain', 'BTC')
            
            # Преобразование значения из формы в код валюты для API
            currency_map = {
                'Bitcoin (BTC)': 'BTC',
                'Ethereum (ETH)': 'ETH',
                'Tron (TRX)': 'TRX',
                'Binance Smart Chain (BSC)': 'BSC'
            }
            
            currency_code = currency_map.get(currency, 'BTC')
            
            # Проверка адреса
            if not address:
                error = "Пожалуйста, введите адрес криптокошелька"
            else:
                client = GetBlockClient()
                check_result = client.perform_check_and_wait(address, currency_code)
                result = client.parse_check_result(check_result)
                
                if not result.get('success'):
                    error = result.get('error', 'Произошла ошибка при проверке адреса')
        
        except Exception as e:
            logging.error(f"AML check error: {str(e)}")
            if "500 Server Error" in str(e):
                error = "Сервис AML-проверки временно недоступен. Пожалуйста, попробуйте позже или обратитесь в службу поддержки."
            else:
                error = f"Произошла ошибка: {str(e)}"
    
    return render_template(
        'aml_check_simple.html', 
        title='Проверка криптоадреса - AML',
        result=result,
        address=address,
        currency=currency,
        error=error,
        form=form
    )

@app.route('/ref')
def referral_redirect():
    """Обработка реферальных ссылок"""
    referral_code = request.args.get('code', '')
    
    if not referral_code:
        # Если код не указан, перенаправляем на главную
        return redirect(url_for('index'))
    
    # Проверяем существование реферального кода
    referring_user = User.query.filter_by(referral_code=referral_code).first()
    if not referring_user:
        flash('Указанный реферальный код не найден.', 'warning')
        return redirect(url_for('index'))
    
    # Если пользователь уже авторизован, перенаправляем на панель управления
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Перенаправляем на страницу регистрации с реферальным кодом
    return redirect(url_for('register', code=referral_code))


@app.route('/services')
def services():
    """Страница с полезными сервисами"""
    return render_template('services.html', title='Полезные сервисы')

@app.route('/contact', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour")  # 🔒 Security fix: Ограничение количества запросов формы обратной связи
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        # Создаем новую запись в базе данных
        new_message = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            subject=form.subject.data,
            message=form.message.data
        )
        # Сохраняем сообщение в базе данных
        db.session.add(new_message)
        db.session.commit()
        
        flash('Ваше сообщение отправлено. Мы свяжемся с вами в ближайшее время!', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html', title='Связаться с нами', form=form)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 100 per hour; 300 per day")  # 🔒 Security fix: Ограничение количества попыток входа
def login():
    import logging
    from flask import make_response
    
    logging.debug(f"Login route accessed with method: {request.method}")
    
    # Проверяем куки (без сессии)
    if request.cookies.get('user_id') and request.cookies.get('logged_in') == 'true':
        logging.debug(f"User already logged in via cookies: {request.cookies.get('user_id')}")
        return redirect(url_for('dashboard'))
    
    # Если POST запрос (отправка формы)
    if request.method == 'POST':
        email = sanitize_input(request.form.get('email'))
        password = request.form.get('password')  # Пароль не надо санитизировать, т.к. он хэшируется
        otp_code = request.form.get('otp_code')
        remember_me = request.form.get('remember_me') == 'on'
        
        logging.debug(f"Login attempt with email: {email}, otp_provided: {bool(otp_code)}")
        
        # Находим пользователя
        user = User.query.filter_by(email=email).first()
        
        # Проверяем, не заблокирован ли аккаунт из-за множественных попыток входа
        if user and user.is_account_locked():
            flash('Аккаунт временно заблокирован из-за множественных попыток входа. Пожалуйста, попробуйте позже.', 'danger')
            return render_template('login.html', title='Login')
        
        # Проверяем пароль
        if user and user.check_password(password):
            # Если у пользователя включена 2FA и она верифицирована (подтверждена)
            if user.otp_enabled and user.otp_verified:
                # Перенаправляем на отдельную страницу ввода кода 2FA
                # Сохраняем временные данные для проверки 2FA
                session['2fa_user_id'] = user.id
                logging.debug(f"Redirecting to 2FA verification for user: {user.username}")
                return redirect(url_for('verify_2fa'))
            
            # Проверяем, подтвержден ли email пользователя
            if not user.email_verified:
                logging.debug(f"Email not verified for user: {user.username}")
                return redirect(url_for('email_verification_required', email=user.email))
                
            # Если 2FA прошла или отключена, сбрасываем счетчик попыток входа
            user.auth_attempts = 0
            user.last_auth_attempt = None
            db.session.commit()
            
            # Логируем IP-адрес при успешном входе
            ip_address = get_client_ip()
            user_agent = request.headers.get('User-Agent', '')
            log_user_ip(user.id, ip_address, 'login', user_agent)
            
            logging.debug(f"Login successful for user: {user.username}")
            
            # Отображаем сообщение об успешном входе
            flash(f'Вы успешно вошли в систему как {user.username}!', 'success')
            
            # Вместо прямой установки куки, перенаправляем на специальную страницу
            # которая установит куки через JavaScript
            cookie_max_age = 86400*30 if remember_me else 86400  # 30 дней или 1 день
            return redirect(url_for('set_cookies', 
                                    user_id=user.id,
                                    username=user.username,
                                    is_admin='true' if user.is_admin else 'false',
                                    max_age=cookie_max_age))
        else:
            # Увеличиваем счетчик попыток входа
            if user:
                user.increment_auth_attempts()
                db.session.commit()
            
            logging.debug("Login failed: Invalid credentials")
            flash('Неверный email или пароль. Пожалуйста, попробуйте снова.', 'danger')
    
    # Если GET запрос (открытие страницы)
    return render_template('login.html', title='Login')

@app.route('/set-cookies')
def set_cookies():
    """Страница для установки cookies через ответ сервера"""
    import logging
    from flask import make_response
    
    user_id = request.args.get('user_id')
    username = sanitize_username(request.args.get('username'))
    is_admin = request.args.get('is_admin', 'false')
    max_age = int(request.args.get('max_age', '86400'))  # По умолчанию 1 день
    
    if not user_id:
        flash('Ошибка авторизации', 'danger')
        return redirect(url_for('login'))
    
    logging.debug(f"Setting cookies directly, user_id={user_id}, username={username}, is_admin={is_admin}, max_age={max_age}")
    
    # Создаем response с редиректом на dashboard
    response = make_response(redirect(url_for('dashboard')))
    
    # Устанавливаем куки напрямую в response
    response.set_cookie('user_id', user_id, max_age=max_age, samesite='Lax', path='/')
    response.set_cookie('logged_in', 'true', max_age=max_age, samesite='Lax', path='/')
    response.set_cookie('username', username, max_age=max_age, samesite='Lax', path='/')
    response.set_cookie('is_admin', is_admin, max_age=max_age, samesite='Lax', path='/')
    
    logging.debug("Cookies set server-side, redirecting to dashboard")
    
    return response

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour; 50 per day")  # 🔒 Security fix: Ограничение количества попыток регистрации
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Получаем реферальный код из URL, если он есть
    referral_code = request.args.get('code', '')
    
    form = RegistrationForm()
    
    # Предзаполняем поле реферального кода, если он был передан через URL
    if referral_code and not form.referral_code.data:
        form.referral_code.data = referral_code
    
    if form.validate_on_submit():
        # Санитизируем имя пользователя и email для предотвращения XSS атак
        safe_username = sanitize_username(form.username.data)
        safe_email = sanitize_input(form.email.data)
        
        # Создаем нового пользователя
        user = User(username=safe_username, email=safe_email)
        user.set_password(form.password.data)
        
        # Генерируем уникальный реферальный код для нового пользователя
        while True:
            new_ref_code = generate_referral_code()
            if not User.query.filter_by(referral_code=new_ref_code).first():
                user.referral_code = new_ref_code
                break
        
        # Если указан реферальный код пригласившего, связываем с ним нового пользователя
        if form.referral_code.data:
            referring_user = User.query.filter_by(referral_code=form.referral_code.data).first()
            if referring_user and referring_user.id != user.id:  # Проверка, чтобы пользователь не мог указать свой код
                user.referred_by_id = referring_user.id
                logging.info(f"User {safe_username} registered with referral code from user ID {referring_user.id}")
        
        db.session.add(user)
        db.session.commit()
        
        # Логируем IP-адрес при регистрации
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')
        log_user_ip(user.id, ip_address, 'register', user_agent)
        
        # Отправляем письмо с подтверждением email
        if send_verification_email(user):
            flash('Ваш аккаунт успешно создан! На указанный email отправлено письмо с ссылкой для подтверждения.', 'success')
        else:
            flash('Ваш аккаунт создан, но возникла проблема с отправкой письма подтверждения. Пожалуйста, обратитесь в службу поддержки.', 'warning')
            
        return redirect(url_for('login'))
    
    return render_template('register.html', title='Регистрация', form=form)

@app.route('/resend-verification-email', methods=['POST'])
@limiter.limit("3 per minute; 10 per hour")  # Ограничиваем количество запросов
def resend_verification_email():
    """Повторная отправка письма с подтверждением email"""
    from flask_wtf import FlaskForm
    
    form = FlaskForm()
    if form.validate_on_submit():
        email = request.form.get('email')
        if not email:
            flash('Пожалуйста, укажите email-адрес.', 'danger')
            return redirect(url_for('login'))
            
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Пользователь с таким email не найден.', 'danger')
            return redirect(url_for('login'))
            
        if user.email_verified:
            flash('Ваш email уже подтвержден. Вы можете войти в систему.', 'info')
            return redirect(url_for('login'))
            
        # Генерируем новый токен для подтверждения
        token = user.generate_email_verification_token()
        
        # Отправляем письмо с подтверждением
        if send_verification_email(user):
            flash('Письмо с инструкциями по подтверждению email отправлено повторно.', 'success')
            return redirect(url_for('email_verification_required', email=user.email))
        else:
            flash('Возникла проблема при отправке письма. Пожалуйста, воспользуйтесь ручной верификацией.', 'warning')
            return redirect(url_for('manual_email_verification'))
        
    flash('Произошла ошибка при обработке запроса.', 'danger')
    return redirect(url_for('login'))

@app.route('/email-verification-required')
def email_verification_required():
    """Страница с сообщением о необходимости подтверждения email"""
    from flask_wtf import FlaskForm
    
    email = request.args.get('email')
    if not email:
        return redirect(url_for('login'))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        return redirect(url_for('login'))
        
    if user.email_verified:
        flash('Ваш email уже подтвержден. Вы можете войти в систему.', 'info')
        return redirect(url_for('login'))
        
    # Простая форма для CSRF-защиты
    form = FlaskForm()
    
    return render_template('email_verification_required.html', 
                          title='Подтверждение Email', 
                          email=user.email, 
                          form=form)
                          
@app.route('/manual-email-verification', methods=['GET', 'POST'])
def manual_email_verification():
    """Маршрут для ручной верификации email (без отправки писем)"""
    form = ManualEmailVerificationForm()
    
    if form.validate_on_submit():
        email = form.email.data
        verification_code = form.verification_code.data
        
        # Ищем пользователя с указанным email
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Пользователь с указанным email не найден.', 'danger')
            return render_template('email_verification_manual.html', form=form)
        
        # Проверяем токен верификации
        if user.email_verification_token == verification_code:
            # Проверяем срок действия токена
            if user.email_verification_token_expires and user.email_verification_token_expires < datetime.utcnow():
                flash('Срок действия кода верификации истек. Пожалуйста, запросите новый код.', 'warning')
                return render_template('email_verification_manual.html', form=form)
            
            # Верифицируем email
            user.email_verified = True
            user.email_verification_token = None
            user.email_verification_token_expires = None
            db.session.commit()
            
            flash('Ваш email успешно подтвержден! Теперь вы можете войти в систему.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Неверный код верификации. Пожалуйста, проверьте код и попробуйте снова.', 'danger')
    
    return render_template('email_verification_manual.html', form=form)



@app.route('/logout')
def logout():
    import logging
    from flask import make_response
    
    logging.debug("Logging out user")
    
    # Уведомление и редирект
    flash('Вы успешно вышли из системы.', 'info')
    
    # Создаем ответ и удаляем куки
    response = make_response(redirect(url_for('index')))
    response.delete_cookie('user_id')
    response.delete_cookie('logged_in')
    response.delete_cookie('username')
    response.delete_cookie('is_admin')
    
    logging.debug("Deleted all auth cookies")
    
    return response

@app.route('/verify-email/<token>')
def verify_email(token):
    """
    Маршрут для подтверждения email по токену из письма
    
    Args:
        token: Токен для верификации из URL
    """
    # Находим пользователя с таким токеном
    user = User.query.filter_by(email_verification_token=token).first()
    
    if not user:
        flash('Недействительная ссылка для подтверждения или ваш email уже подтвержден.', 'warning')
        return redirect(url_for('login'))
        
    # Проверяем токен и подтверждаем email
    if user.verify_email(token):
        # Сохраняем изменения в базе данных
        db.session.commit()
        flash('Ваш email успешно подтвержден! Теперь вы можете войти в систему.', 'success')
    else:
        flash('Ссылка для подтверждения недействительна или срок её действия истек.', 'danger')
    
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    """Страница панели управления инвестора"""
    import logging
    from flask import request, make_response
    from forms import WithdrawalForm
    
    logging.debug("Dashboard accessed")
    logging.debug(f"Request cookies: {request.cookies}")
    logging.debug(f"Request args: {request.args}")
    
    # Проверяем авторизацию из разных источников (URL параметры, куки)
    # 1. Сначала проверяем URL параметры (если мы перешли со страницы set_cookies.html)
    user_id = request.args.get('user_id') or request.cookies.get('user_id')
    logged_in = request.args.get('logged_in') or request.cookies.get('logged_in')
    raw_username = request.args.get('username') or request.cookies.get('username', 'Пользователь')
    username = sanitize_username(raw_username)
    is_admin = request.args.get('is_admin') or request.cookies.get('is_admin', 'false')
    
    logging.debug(f"Auth data: user_id={user_id}, logged_in={logged_in}, username={username}, is_admin={is_admin}")
    
    # Проверяем авторизацию
    if not user_id or logged_in != 'true':
        logging.debug("Not logged in, redirecting to login")
        flash('Пожалуйста, войдите в систему для доступа к панели инвестора.', 'warning')
        return redirect(url_for('login'))
    
    # Создаем форму для вывода средств
    withdrawal_form = WithdrawalForm()
    
    try:
        # Получаем пользователя из базы данных
        user = User.query.get(int(user_id))
        
        if not user:
            logging.error(f"User not found with id {user_id}")
            flash('Ошибка авторизации. Пожалуйста, войдите снова.', 'danger')
            return redirect(url_for('login'))
            
        logging.debug(f"User found: {user}")
        
        # Автоматически обновляем статусы платежей для всех пользователей
        from utils import check_payment_statuses, check_admin_test_transactions
        payment_updated = check_payment_statuses(user)
        
        # Если пользователь админ, также проверяем его 5-минутные тестовые транзакции
        admin_updated = 0
        if user.is_admin:
            admin_updated = check_admin_test_transactions(user)
            
        # Выводим информационные сообщения
        if payment_updated > 0:
            flash(f'Обновлен статус {payment_updated} платежей', 'success')
        if admin_updated > 0:
            flash(f'Автоматически завершено {admin_updated} тестовых 5-минутных инвестиций', 'success')
        
        # Получаем традиционные транзакции пользователя
        transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.desc()).all()
        logging.debug(f"Found {len(transactions)} regular transactions")
        
        # Получаем TON-депозиты пользователя
        ton_deposits = TonDeposit.query.filter_by(user_id=user.id).all()
        logging.debug(f"Found {len(ton_deposits)} TON deposits")
        
        # Создаем комбинированный список транзакций для отображения
        combined_transactions = []
        
        # Добавляем обычные транзакции
        for transaction in transactions:
            combined_transactions.append({
                'id': transaction.id,
                'transaction_id': transaction.transaction_id,
                'date': transaction.deposit_start_date,
                'amount': transaction.amount,
                'term': transaction.term_months,
                'term_type': 'месяцев',
                'expected_profit': transaction.expected_profit,
                'status': transaction.status,
                'type': 'regular'
            })
        
        # Добавляем TON-транзакции
        for deposit in ton_deposits:
            # Определяем тип срока для TON-депозитов
            if deposit.term_days < 1:  # Меньше 1 дня - минуты (тестовый)
                term_value = round(deposit.term_days * 24 * 60)
                term_type = 'минут'
            elif deposit.term_days < 30:  # Меньше 30 дней - недели
                term_value = round(deposit.term_days / 7)
                term_type = 'недель'
            else:  # Иначе - месяцы
                term_value = round(deposit.term_days / 30)
                term_type = 'месяцев'
                
            combined_transactions.append({
                'id': deposit.id,
                'transaction_id': f"TON-{deposit.memo[:6]}",
                'date': deposit.created_at,
                'amount': deposit.amount,
                'term': term_value,
                'term_type': term_type,
                'expected_profit': deposit.expected_profit,
                'status': deposit.status,
                'type': 'ton'
            })
        
        # Сортируем комбинированный список по дате (сначала новые)
        combined_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        # Получаем общий баланс и ожидаемую прибыль
        total_balance = user.get_total_balance()
        expected_profit = user.get_expected_profit()
        logging.debug(f"Total balance: {total_balance}, Expected profit: {expected_profit}")
        
        # Формы для создания нового вклада
        deposit_form = DepositForm()
        ton_deposit_form = TonDepositForm()
        
        # Форма для запроса на вывод средств с CSRF-токеном уже создана выше
        
        # Получаем TON депозиты пользователя
        ton_deposits = user.ton_deposits
        
        # Получаем историю запросов на вывод средств
        withdrawal_requests = WithdrawalRequest.query.filter_by(user_id=user.id).order_by(WithdrawalRequest.request_date.desc()).all()
        
        # Получаем общую сумму выведенных средств
        total_withdrawn = user.get_total_withdrawn()
        
        # Подсчитываем только активные инвестиции (статус 'completed')
        active_investments_count = 0
        # Считаем обычные транзакции
        active_regular_investments = Transaction.query.filter_by(user_id=user.id, status='completed').count()
        # Считаем TON-транзакции
        active_ton_investments = TonDeposit.query.filter_by(user_id=user.id, status='completed').count()
        # Суммируем
        active_investments_count = active_regular_investments + active_ton_investments
        logging.debug(f"Active investments count: {active_investments_count} (regular: {active_regular_investments}, TON: {active_ton_investments})")
        
        # Рендерим шаблон с данными и передаем данные авторизации для сохранения в localStorage
        response = make_response(render_template(
            'dashboard.html', 
            title=f'Панель инвестора - {username}',
            user=user,
            transactions=transactions,
            ton_deposits=ton_deposits,
            combined_transactions=combined_transactions,  # Передаем объединенный список
            total_balance=total_balance,
            expected_profit=expected_profit,
            withdrawal_requests=withdrawal_requests,  # История запросов на вывод
            total_withdrawn=total_withdrawn,  # Общая сумма выведенных средств
            deposit_form=deposit_form,
            ton_deposit_form=ton_deposit_form,
            form=withdrawal_form,  # Форма для модального окна
            withdrawal_form=withdrawal_form,  # Форма для вывода средств с CSRF токеном
            active_investments_count=active_investments_count,  # Добавляем счетчик активных инвестиций
            auth_data={
                'user_id': user_id,
                'username': username,
                'is_admin': user.is_admin
            }
        ))
        
        # Если данные были получены из URL, сохраняем их в куки для будущих запросов
        if request.args.get('user_id'):
            logging.debug("Setting cookies from URL parameters")
            response.set_cookie('user_id', user_id, max_age=86400*7, samesite='Lax', path='/')
            response.set_cookie('logged_in', 'true', max_age=86400*7, samesite='Lax', path='/')
            response.set_cookie('username', username, max_age=86400*7, samesite='Lax', path='/')
            response.set_cookie('is_admin', is_admin, max_age=86400*7, samesite='Lax', path='/')
        
        return response
    except Exception as e:
        logging.error(f"Dashboard error: {str(e)}")
        flash('Произошла ошибка при загрузке данных. Пожалуйста, попробуйте позже.', 'danger')
        return redirect(url_for('index'))

@app.route('/calculate-profit', methods=['POST'])
def calculate_profit():
    import logging
    
    # Проверка авторизации из разных источников (URL параметры, куки)
    # 1. Сначала проверяем куки
    user_id = request.cookies.get('user_id')
    logged_in = request.cookies.get('logged_in')
    
    # 2. Затем проверяем URL параметры
    user_id = user_id or request.args.get('user_id')
    logged_in = logged_in or request.args.get('logged_in')
    
    logging.debug(f"Calculate profit auth check: user_id={user_id}, logged_in={logged_in}")
    logging.debug(f"Request cookies: {request.cookies}")
    logging.debug(f"Request args: {request.args}")
    
    if not user_id or logged_in != 'true':
        logging.error("Unauthorized access to calculate-profit endpoint")
        return jsonify({
            'success': False, 
            'error': 'Unauthorized',
            'redirect': '/login'
        }), 401
    
    try:
        amount = float(request.form.get('amount'))
        term_type = request.form.get('term_type', 'months')  # Тип срока (недели или месяцы)
        term_value = int(request.form.get('term_value', request.form.get('term', 0)))
        
        logging.debug(f"Calculating profit for amount={amount}, term_type={term_type}, term_value={term_value}")
        
        if amount <= 0 or term_value <= 0:
            return jsonify({'success': False, 'error': 'Invalid input values'})
        
        # Расчет прибыли в зависимости от типа срока
        if term_type == 'weeks':
            profit = calculate_profit_for_term(amount, term_weeks=term_value)
            term_description = f"{term_value} {'неделя' if term_value == 1 else 'недели' if 2 <= term_value <= 4 else 'недель'}"
        else:  # По умолчанию месяцы
            profit = calculate_profit_for_term(amount, term_months=term_value)
            term_description = f"{term_value} {'месяц' if term_value == 1 else 'месяца' if 2 <= term_value <= 4 else 'месяцев'}"
        
        # Рассчитываем процентную ставку
        rate_percent = (profit / amount) * 100
        
        return jsonify({
            'success': True,
            'amount': amount,
            'term': term_value,
            'term_type': term_type,
            'term_description': term_description,
            'profit': profit,
            'total': amount + profit,
            'rate_percent': rate_percent
        })
    except Exception as e:
        logging.error(f"Error in calculate_profit: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/create-deposit', methods=['POST'])
@limiter.limit("10 per hour; 50 per day")  # 🔒 Security fix: Ограничение количества запросов на создание депозитов
def create_deposit():
    """
    Маршрут для создания нового вклада (депозита)
    
    Поддерживает:
    - Создание нового депозита через форму
    - Продолжение оплаты существующего депозита через параметр continue
    - Оплату в USDT (TRC20) и TRX с минимальными суммами 1 и 5 соответственно
    """
    import logging
    
    # Проверка авторизации из разных источников (URL параметры, куки)
    # 1. Сначала проверяем куки
    user_id = request.cookies.get('user_id')
    logged_in = request.cookies.get('logged_in')
    
    # 2. Затем проверяем URL параметры
    user_id = user_id or request.args.get('user_id')
    logged_in = logged_in or request.args.get('logged_in')
    
    logging.debug(f"Create deposit auth check: user_id={user_id}, logged_in={logged_in}")
    
    if not user_id or logged_in != 'true':
        logging.error("Unauthorized access to create deposit")
        flash('Пожалуйста, войдите в систему для создания вклада.', 'warning')
        return redirect(url_for('login'))
    
    try:
        # Получаем пользователя из базы
        user = User.query.get(int(user_id))
        if not user:
            logging.error(f"User not found with id {user_id}")
            flash('Ошибка авторизации. Пожалуйста, войдите снова.', 'danger')
            return redirect(url_for('login'))
            
        # Логируем IP-адрес при создании депозита
        from utils import log_user_ip
        from utils import get_client_ip
        client_ip = get_client_ip()
        user_agent = request.headers.get('User-Agent')
        log_user_ip(user.id, client_ip, 'deposit_nowpayments', user_agent)
        
        # Проверяем, если есть параметр continue, значит пользователь хочет продолжить оплату существующего депозита
        continue_transaction_id = request.args.get('continue')
        if continue_transaction_id:
            # Находим существующую транзакцию
            transaction = Transaction.query.filter_by(
                transaction_id=continue_transaction_id, 
                user_id=user.id,
                status='payment_awaiting'
            ).first()
            
            if transaction:
                # Используем данные существующей транзакции
                logging.debug(f"Continuing payment for transaction {transaction.transaction_id}")
                
                # Данный функционал более не поддерживается, используйте TON депозиты
                flash("Этот метод оплаты больше не поддерживается. Пожалуйста, используйте TON для депозитов.", "warning")
                logging.warning(f"Попытка использования устаревшего способа пополнения: {transaction.transaction_id}")
                return redirect(url_for('deposit_ton'))
            else:
                # Если транзакции не существует или она уже завершена
                flash('Транзакция не найдена или уже завершена.', 'warning')
                return redirect(url_for('dashboard', user_id=user_id, logged_in='true', username=user.username))
        
        # Создание нового депозита
        form = DepositForm()
        if form.validate_on_submit():
            # Санитизируем пользовательский ввод для предотвращения XSS
            term_type = sanitize_input(form.term_type.data)
            term_value = int(form.term_value.data)
            amount = float(form.amount.data)
            
            # Получаем выбранную криптовалюту
            crypto_currency = sanitize_input(form.crypto_currency.data)
            
            logging.info(f"Creating new deposit for user {user.id}: amount={amount}, term_type={term_type}, term_value={term_value}, crypto_currency={crypto_currency}")
            
            # Генерируем уникальный идентификатор транзакции
            transaction_id = str(uuid.uuid4())
            
            # Рассчитываем даты начала и окончания депозита
            start_date = datetime.utcnow()
            
            # Рассчитываем end_date в зависимости от типа срока
            if term_type == 'minutes':
                # Специальный тестовый режим - 5 минут с доходностью 10%
                if not user.is_admin:
                    flash('Тестовый режим (минуты) доступен только администраторам', 'warning')
                    return redirect(url_for('dashboard', user_id=user_id, logged_in='true', username=user.username))
                
                # Для минут считаем точно, используется для быстрого тестирования
                end_date = start_date + timedelta(minutes=term_value)
                # Для совместимости сохраняем как долю месяца
                term_months = 0.01  # Небольшое значение для корректного учета выплат
            elif term_type == 'weeks':
                # Для недель умножаем на 7 дней
                end_date = start_date + timedelta(days=7 * term_value)
                # При хранении в БД конвертируем недели в месяцы (для совместимости)
                term_months = max(1, round(term_value / 4.33))  # примерное преобразование недель в месяцы
            else:
                # Для месяцев умножаем на 30 дней
                end_date = start_date + timedelta(days=30 * term_value)
                term_months = term_value
            
            # Создаем новую транзакцию
            transaction = Transaction(
                transaction_id=transaction_id,
                user_id=user.id,
                amount=amount,
                status='pending',
                deposit_start_date=start_date,
                deposit_end_date=end_date,
                term_months=term_months,
                payment_currency=crypto_currency
            )
            
            # Рассчитываем ожидаемую прибыль
            transaction.calculate_expected_profit()
            
            # Добавляем в базу данных
            db.session.add(transaction)
            db.session.commit()
            
            logging.debug(f"Deposit created successfully: {transaction.transaction_id}")
            
            # Данный функционал более не поддерживается, используйте TON депозиты
            flash("Этот метод оплаты больше не поддерживается. Пожалуйста, используйте TON для депозитов.", "warning")
            logging.warning(f"Попытка использования устаревшего способа пополнения: {transaction_id}")
            # Меняем статус транзакции на failed и сохраняем её
            transaction.status = 'failed'
            db.session.commit()
            
            # Перенаправляем на страницу создания TON-депозита
            return redirect(url_for('deposit_ton'))
        
        # Если есть ошибки валидации формы, выводим их
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'danger')
        
        # При возврате передаем URL параметры для сохранения авторизации
        return redirect(url_for('dashboard', user_id=user_id, logged_in='true', username=user.username))
    
    except Exception as e:
        logging.error(f"Error in create_deposit: {str(e)}")
        flash('Произошла ошибка при создании вклада. Пожалуйста, попробуйте позже.', 'danger')
        return redirect(url_for('dashboard', user_id=user_id, logged_in='true'))

@app.route('/api/user-balance')
@limiter.limit("20 per minute")  # 🔒 Security fix: Ограничение количества запросов к API баланса пользователя
@api_login_required  # 🔒 Security fix: Требуем авторизацию для доступа к API баланса пользователя
def user_balance():
    """API endpoint to get user balance data for the dashboard"""
    import logging
    
    # Проверка авторизации из разных источников (URL параметры, куки)
    # 1. Сначала проверяем куки
    user_id = request.cookies.get('user_id')
    logged_in = request.cookies.get('logged_in')
    
    # 2. Затем проверяем URL параметры
    user_id = user_id or request.args.get('user_id')
    logged_in = logged_in or request.args.get('logged_in')
    
    logging.debug(f"Balance API auth check: user_id={user_id}, logged_in={logged_in}")
    logging.debug(f"Request cookies: {request.cookies}")
    logging.debug(f"Request args: {request.args}")
    
    if not user_id or logged_in != 'true':
        logging.error("Unauthorized access to user-balance API")
        return jsonify({
            'error': 'Unauthorized',
            'cookies_found': bool(request.cookies),
            'args_found': bool(request.args),
            'user_id': user_id,
            'logged_in': logged_in
        }), 401
    
    try:
        # Получаем пользователя из базы
        user = User.query.get(int(user_id))
        
        if not user:
            logging.error(f"User not found with id {user_id}")
            return jsonify({'error': 'User not found'}), 404
        
        # Получаем транзакции со статусом "completed"
        completed_transactions = Transaction.query.filter_by(
            user_id=user.id, 
            status='completed'
        ).all()
        
        logging.debug(f"Found {len(completed_transactions)} completed transactions for user {user_id}")
        
        balance = sum(t.amount for t in completed_transactions)
        expected_profit = sum(t.expected_profit for t in completed_transactions if t.expected_profit)
        
        # Возвращаем только необходимые данные
        return jsonify({
            'balance': balance,
            'expected_profit': expected_profit,
            'total_value': balance + expected_profit
        })
    except Exception as e:
        logging.error(f"Error in user_balance API: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Добавляем тестовую страницу для диагностики
@app.route('/verify-2fa', methods=['GET', 'POST'])
def verify_2fa():
    """
    Страница для двухфакторной аутентификации
    """
    # Если пользователь пытается доступ без прохождения первого этапа аутентификации
    if '2fa_user_id' not in session:
        flash('Пожалуйста, войдите в систему сначала', 'warning')
        return redirect(url_for('login'))
    
    # Пользователь должен был пройти первый этап аутентификации
    user_id = session.get('2fa_user_id')
    if not user_id:
        flash('Ошибка аутентификации', 'danger')
        return redirect(url_for('login'))
    
    # Находим пользователя
    user = User.query.get(user_id)
    if not user:
        flash('Ошибка аутентификации', 'danger')
        return redirect(url_for('login'))
    
    form = OTPVerifyForm()
    if form.validate_on_submit():
        otp_code = form.otp_code.data
        
        # Проверяем код 2FA
        if user.verify_otp(otp_code):
            # Очищаем временные данные
            if '2fa_user_id' in session:
                session.pop('2fa_user_id')
            
            # Обновляем счетчик попыток входа
            user.auth_attempts = 0
            user.last_auth_attempt = None
            db.session.commit()
            
            # Успешная аутентификация
            flash(f'Двухфакторная аутентификация успешна! Добро пожаловать, {user.username}!', 'success')
            
            # Перенаправляем на страницу установки cookies
            return redirect(url_for('set_cookies', 
                                    user_id=user.id,
                                    username=user.username,
                                    is_admin='true' if user.is_admin else 'false'))
        else:
            # Увеличиваем счетчик попыток
            user.increment_auth_attempts()
            db.session.commit()
            
            flash('Неверный код двухфакторной аутентификации', 'danger')
    
    return render_template('security/verify_2fa.html', form=form)

@app.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    """
    Страница настройки двухфакторной аутентификации
    """
    # Получаем ID пользователя из куки
    user_id = request.cookies.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))
    
    # Находим пользователя
    user = User.query.get(int(user_id))
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    # Если у пользователя уже включена и подтверждена 2FA
    if user.otp_verified:
        flash('Двухфакторная аутентификация уже настроена', 'info')
        return redirect(url_for('dashboard'))
    
    # Если секретный ключ не существует, генерируем новый
    if not user.otp_secret:
        user.generate_otp_secret()
        db.session.commit()
    
    # Генерируем QR-код
    uri = user.get_otp_uri()
    img = qrcode.make(uri)
    buffered = io.BytesIO()
    img.save(buffered)
    qr_code = f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
    
    # Генерируем резервный код (для сброса 2FA если пользователь потеряет устройство)
    backup_code = pyotp.random_base32()[:16]  # Более короткий код для удобства
    
    form = OTPSetupForm()
    if form.validate_on_submit():
        otp_code = form.otp_code.data
        
        # Проверяем введенный код
        if user.verify_otp(otp_code):
            # Устанавливаем 2FA как активированную и проверенную
            user.enable_otp()
            user.otp_verified = True
            db.session.commit()
            
            flash('Двухфакторная аутентификация успешно настроена!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный код подтверждения', 'danger')
    
    return render_template('security/setup_2fa.html', 
                           form=form, 
                           qr_code=qr_code, 
                           secret_key=user.otp_secret,
                           backup_code=backup_code)

@app.route('/setup-2fa-confirm', methods=['POST'])
@login_required
def setup_2fa_confirm():
    """
    Подтверждение настройки 2FA
    """
    # Получаем ID пользователя из куки
    user_id = request.cookies.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))
    
    # Находим пользователя
    user = User.query.get(int(user_id))
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    # Получаем код подтверждения
    otp_code = request.form.get('otp_code')
    if not otp_code:
        flash('Необходимо ввести код подтверждения', 'warning')
        return redirect(url_for('setup_2fa'))
    
    # Проверяем введенный код
    if user.verify_otp(otp_code):
        # Устанавливаем 2FA как активированную и проверенную
        user.enable_otp()
        user.otp_verified = True
        db.session.commit()
        
        flash('Двухфакторная аутентификация успешно настроена!', 'success')
    else:
        flash('Неверный код подтверждения', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/disable-2fa', methods=['GET', 'POST'])
@login_required
def disable_2fa():
    """
    Отключение двухфакторной аутентификации
    """
    # Получаем ID пользователя из куки
    user_id = request.cookies.get('user_id')
    if not user_id:
        flash('Пожалуйста, войдите в систему', 'warning')
        return redirect(url_for('login'))
    
    # Находим пользователя
    user = User.query.get(int(user_id))
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('dashboard'))
    
    # Если у пользователя отключена 2FA
    if not user.otp_enabled:
        flash('Двухфакторная аутентификация уже отключена', 'info')
        return redirect(url_for('dashboard'))
    
    # Если это POST запрос, значит пользователь подтвердил отключение
    if request.method == 'POST':
        # Отключаем 2FA
        user.disable_otp()
        db.session.commit()
        
        flash('Двухфакторная аутентификация отключена', 'success')
        return redirect(url_for('dashboard'))
    
    # Отображаем страницу подтверждения
    return render_template('security/disable_2fa.html')

@app.route('/reset-2fa', methods=['GET', 'POST'])
def reset_2fa():
    """
    Сброс двухфакторной аутентификации (для случаев, когда пользователь потерял доступ к устройству)
    """
    if request.method == 'POST':
        email = request.form.get('email')
        backup_code = request.form.get('backup_code')
        
        if not email or not backup_code:
            flash('Необходимо ввести email и резервный код', 'warning')
            return render_template('security/reset_2fa.html')
        
        # Находим пользователя по email
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Пользователь с таким email не найден', 'danger')
            return render_template('security/reset_2fa.html')
        
        # Сбрасываем 2FA пользователя
        # Здесь нет проверки резервного кода, так как мы его не храним в БД по соображениям безопасности
        # В реальном приложении нужно добавить проверку резервного кода
        user.disable_otp()
        db.session.commit()
        
        flash('Двухфакторная аутентификация сброшена. Вы можете войти без кода 2FA.', 'success')
        return redirect(url_for('login'))
    
    return render_template('security/reset_2fa.html')

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    Страница для изменения пароля пользователя
    """
    import logging
    
    # Получаем пользователя из базы данных
    user_id = request.cookies.get('user_id')
    user = User.query.get(int(user_id))
    
    if not user:
        flash('Ошибка авторизации. Пожалуйста, войдите снова.', 'danger')
        return redirect(url_for('login'))
    
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Проверяем текущий пароль
        if not user.check_password(form.current_password.data):
            flash('Неверный текущий пароль. Пожалуйста, попробуйте снова.', 'danger')
            return render_template('security/change_password.html', title='Изменение пароля', form=form)
        
        # Обновляем пароль
        user.set_password(form.new_password.data)
        db.session.commit()
        
        # Безопасное логирование смены пароля (без включения самого пароля)
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', '')
        log_user_ip(user.id, ip_address, "password_change", user_agent)
        
        # Добавляем основную информацию без указания пароля
        logging.info(f"Password changed for user_id={user.id}")
        
        flash('Ваш пароль успешно изменен!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('security/change_password.html', title='Изменение пароля', form=form)

@app.route('/debug-auth')
def debug_auth():
    """Страница для отладки проблем аутентификации"""
    import logging
    from flask import Response, request
    
    # Собираем все данные для диагностики
    auth_info = {}
    
    # Проверяем куки
    auth_info["cookies"] = dict(request.cookies)
    auth_info["cookie_user_id"] = request.cookies.get('user_id')
    auth_info["cookie_logged_in"] = request.cookies.get('logged_in')
    auth_info["cookie_username"] = request.cookies.get('username')
    auth_info["cookie_is_admin"] = request.cookies.get('is_admin')
    
    # Проверяем URL параметры
    auth_info["url_args"] = dict(request.args)
    auth_info["url_user_id"] = request.args.get('user_id')
    auth_info["url_logged_in"] = request.args.get('logged_in')
    auth_info["url_username"] = request.args.get('username')
    
    # Проверяем localStorage через JavaScript (будет выполнено на клиенте)
    auth_info["localstorage"] = "Check in browser console: localStorage.getItem('user_id'), localStorage.getItem('logged_in')"
    
    # Объединенная проверка - итоговые значения авторизации
    user_id = request.cookies.get('user_id') or request.args.get('user_id')
    logged_in = request.cookies.get('logged_in') or request.args.get('logged_in')
    auth_info["resolved_user_id"] = user_id
    auth_info["resolved_logged_in"] = logged_in
    auth_info["is_authenticated"] = bool(user_id and logged_in == 'true')
    
    # Пытаемся получить пользователя из базы данных
    if user_id:
        try:
            user = User.query.get(int(user_id))
            auth_info["db_user_found"] = bool(user)
            if user:
                auth_info["db_username"] = user.username
                auth_info["db_email"] = user.email
                
                # Проверяем транзакции пользователя
                transactions = Transaction.query.filter_by(user_id=user.id).all()
                auth_info["transactions_count"] = len(transactions)
                auth_info["completed_transactions"] = len([t for t in transactions if t.status == 'completed'])
        except Exception as e:
            auth_info["db_error"] = str(e)
    
    # Запись в лог
    logging.debug(f"Debug auth info: {auth_info}")
    
    # Формируем отчет для браузера
    output = "<h1>Auth Debug Info</h1>"
    
    # Добавляем JavaScript для проверки localStorage
    output += """
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const localStorageInfo = document.getElementById('localStorage-info');
            try {
                const userId = localStorage.getItem('user_id');
                const loggedIn = localStorage.getItem('logged_in');
                const username = localStorage.getItem('username');
                const isAdmin = localStorage.getItem('is_admin');
                
                localStorageInfo.innerHTML = `
                    <strong>localStorage:</strong><br>
                    user_id: ${userId || 'Not set'}<br>
                    logged_in: ${loggedIn || 'Not set'}<br>
                    username: ${username || 'Not set'}<br>
                    is_admin: ${isAdmin || 'Not set'}<br>
                `;
            } catch (e) {
                localStorageInfo.innerHTML = `<span style="color: red;">Error accessing localStorage: ${e.message}</span>`;
            }
        });
    </script>
    """
    
    # Статус аутентификации
    if auth_info["is_authenticated"]:
        output += '<div style="background-color: #d4edda; color: #155724; padding: 10px; margin: 15px 0; border-radius: 5px;">'
        output += f'<strong>Authenticated as:</strong> {auth_info.get("db_username", "Unknown")} (ID: {user_id})'
        output += '</div>'
    else:
        output += '<div style="background-color: #f8d7da; color: #721c24; padding: 10px; margin: 15px 0; border-radius: 5px;">'
        output += '<strong>Not authenticated!</strong> Login required.'
        output += '</div>'
    
    # Информация о куках
    output += '<h3>Cookies</h3>'
    output += '<div style="background-color: #e2e3e5; padding: 10px; border-radius: 5px; margin-bottom: 15px;">'
    if auth_info["cookies"]:
        for key, value in auth_info["cookies"].items():
            output += f'<div><strong>{key}:</strong> {value}</div>'
    else:
        output += '<div>No cookies found</div>'
    output += '</div>'
    
    # Информация о URL параметрах
    output += '<h3>URL Parameters</h3>'
    output += '<div style="background-color: #e2e3e5; padding: 10px; border-radius: 5px; margin-bottom: 15px;">'
    if auth_info["url_args"]:
        for key, value in auth_info["url_args"].items():
            output += f'<div><strong>{key}:</strong> {value}</div>'
    else:
        output += '<div>No URL parameters found</div>'
    output += '</div>'
    
    # Информация о localStorage
    output += '<h3>Local Storage</h3>'
    output += '<div id="localStorage-info" style="background-color: #e2e3e5; padding: 10px; border-radius: 5px; margin-bottom: 15px;">'
    output += 'Loading localStorage data...'
    output += '</div>'
    
    # Информация о пользователе из базы данных
    output += '<h3>Database User</h3>'
    output += '<div style="background-color: #e2e3e5; padding: 10px; border-radius: 5px; margin-bottom: 15px;">'
    if auth_info.get("db_user_found"):
        output += f'<div><strong>Username:</strong> {auth_info["db_username"]}</div>'
        output += f'<div><strong>Email:</strong> {auth_info["db_email"]}</div>'
        output += f'<div><strong>Total Transactions:</strong> {auth_info["transactions_count"]}</div>'
        output += f'<div><strong>Completed Transactions:</strong> {auth_info["completed_transactions"]}</div>'
    else:
        output += f'<div>User not found in database (ID: {user_id})</div>'
        if auth_info.get("db_error"):
            output += f'<div style="color: red;">Error: {auth_info["db_error"]}</div>'
    output += '</div>'
    
    # Добавляем ссылки для навигации
    output += "<hr>"
    output += '<div style="margin-top: 20px;">'
    output += '<a href="/" class="btn" style="text-decoration: none; padding: 5px 10px; margin-right: 10px; background-color: #f8f9fa; border-radius: 5px;">Главная</a>'
    output += '<a href="/login" class="btn" style="text-decoration: none; padding: 5px 10px; margin-right: 10px; background-color: #f8f9fa; border-radius: 5px;">Войти</a>'
    output += '<a href="/dashboard" class="btn" style="text-decoration: none; padding: 5px 10px; margin-right: 10px; background-color: #f8f9fa; border-radius: 5px;">Панель</a>'
    output += '<a href="/logout" class="btn" style="text-decoration: none; padding: 5px 10px; background-color: #f8f9fa; border-radius: 5px;">Выйти</a>'
    output += '</div>'
    
    return Response(output, mimetype='text/html')

@app.route('/nowpayments/webhook', methods=['POST'])
def nowpayments_webhook():
    """
    УСТАРЕВШИЙ обработчик IPN уведомлений от NOWPayments
    Оставлен для обратной совместимости, но больше не используется
    Система полностью переключена на TON
    """
    import logging
    from datetime import datetime
    
    logging.debug("Received NOWPayments webhook notification - УСТАРЕЛО")
    logging.info("NOWPayments webhooks больше не используются. Система полностью переключена на TON.")
    
    # Возвращаем 200 OK для обратной совместимости
    return jsonify({"status": "deprecated", "message": "NOWPayments больше не используется, переход на TON"}), 200

@app.route('/payment/success')
def payment_success():
    """
    Страница успешной оплаты
    """
    transaction_id = request.args.get('order_id')
    
    # Получаем данные авторизации из URL-параметров или cookies
    user_id = request.cookies.get('user_id') or request.args.get('user_id')
    logged_in = request.cookies.get('logged_in') or request.args.get('logged_in')
    
    if not transaction_id:
        flash('Произошла ошибка при обработке платежа. Отсутствует ID транзакции.', 'danger')
        return redirect(url_for('dashboard', user_id=user_id, logged_in=logged_in))
    
    # Проверяем транзакцию
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    if not transaction:
        flash('Транзакция не найдена.', 'danger')
        return redirect(url_for('dashboard', user_id=user_id, logged_in=logged_in))
    
    flash('Ваш платеж успешно обработан! Средства будут зачислены после подтверждения в сети блокчейн.', 'success')
    return redirect(url_for('dashboard', user_id=user_id, logged_in=logged_in))

@app.route('/payment/cancel')
def payment_cancel():
    """
    Страница отмены оплаты
    """
    transaction_id = request.args.get('order_id')
    
    # Получаем данные авторизации из URL-параметров или cookies
    user_id = request.cookies.get('user_id') or request.args.get('user_id')
    logged_in = request.cookies.get('logged_in') or request.args.get('logged_in')
    
    if transaction_id:
        # Проверяем транзакцию
        transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
        if transaction:
            # Обновляем статус транзакции
            transaction.status = 'cancelled'
            db.session.commit()
    
    flash('Платеж был отменен. Вы можете попробовать снова в любое время.', 'warning')
    return redirect(url_for('dashboard', user_id=user_id, logged_in=logged_in))

# =====================================================================
# Административные маршруты
# =====================================================================

@app.route('/secure-admin', methods=['GET', 'POST'])
def secure_admin_login():
    """Секретная страница для входа в админ-панель"""
    import hashlib
    import logging
    from flask import make_response
    from flask_wtf import FlaskForm
    from wtforms import StringField, PasswordField, SubmitField
    from wtforms.validators import DataRequired
    
    # Создаем форму для входа с CSRF защитой
    class SecureAdminForm(FlaskForm):
        username = StringField('Имя пользователя', validators=[DataRequired()])
        password = PasswordField('Пароль', validators=[DataRequired()])
        submit = SubmitField('Войти')
    
    form = SecureAdminForm()
    
    # Если пользователь уже вошел как админ, перенаправляем на админ-панель
    if request.cookies.get('user_id') and request.cookies.get('logged_in') == 'true' and request.cookies.get('is_admin') == 'true':
        return redirect(url_for('admin_dashboard'))
    
    # Данные для входа админа теперь берем из базы данных
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        logging.debug(f"Admin login attempt with username: {username}")
        
        # Находим пользователя-администратора
        admin_user = User.query.filter_by(username='system_admin').first()
        
        # Если админ не существует, создаем его с защищенным паролем
        if not admin_user and username == "admin":
            admin_user = User(
                username='system_admin',
                email='admin@system.local',
                is_admin=True
            )
            # Используем безопасный пароль по умолчанию
            admin_user.set_password("nr5u@m9#zbUf23wd")
            db.session.add(admin_user)
            db.session.commit()
            logging.debug("Created system admin user with secure password")
        
        # Проверяем учетные данные, поддерживая как старое, так и новое имя пользователя
        if (admin_user and 
            ((username == "admin" or username == "system_admin") and 
             admin_user.check_password(password))):
            logging.debug("Admin login successful")
            
            # Установка cookies через редирект
            return redirect(url_for('set_cookies', 
                                   user_id=admin_user.id,
                                   username=admin_user.username,
                                   is_admin='true'))
        else:
            logging.debug("Admin login failed: Invalid credentials")
            flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('admin/login.html', form=form)

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Административная панель - главная страница"""
    import logging, traceback
    
    # Настройка дополнительного логирования
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Инициализируем переменные по умолчанию
    user_count = 0
    transaction_count = 0
    total_invested = 0
    pending_count = 0
    recent_transactions = []
    messages = []
    unread_count = 0
    
    try:
        # Логируем начало выполнения функции и состояние запроса
        logger.debug("Запуск admin_dashboard")
        logger.debug(f"Request path: {request.path}")
        logger.debug(f"Request method: {request.method}")
        logger.debug(f"Request cookies: {request.cookies}")
        
        # Проверяем основные модели и соединение с базой данных
        logger.debug("Проверка соединения с базой данных")
        user_model_exists = User.__tablename__ in db.metadata.tables
        transaction_model_exists = Transaction.__tablename__ in db.metadata.tables
        contact_message_model_exists = ContactMessage.__tablename__ in db.metadata.tables
        
        logger.debug(f"Модели в базе данных: User={user_model_exists}, Transaction={transaction_model_exists}, ContactMessage={contact_message_model_exists}")
        
        # Получаем статистику для админ-панели
        logger.debug("Получение статистики пользователей")
        user_count = User.query.count()
        logger.debug(f"Пользователей в базе: {user_count}")
        
        logger.debug("Получение статистики транзакций")
        transaction_count = Transaction.query.count()
        logger.debug(f"Транзакций в базе: {transaction_count}")
        
        logger.debug("Получение суммы инвестиций")
        total_invested = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.status == 'completed').scalar() or 0
        logger.debug(f"Сумма инвестиций: {total_invested}")
        
        logger.debug("Получение количества ожидающих платежей")
        pending_count = Transaction.query.filter_by(status='payment_awaiting').count()
        logger.debug(f"Ожидающих платежей: {pending_count}")
        
        # Получение последних транзакций для быстрого доступа
        logger.debug("Получение последних транзакций")
        recent_transactions = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
        logger.debug(f"Получено {len(recent_transactions)} транзакций")
        
        # Получение сообщений от пользователей
        logger.debug("Получение сообщений пользователей")
        messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(5).all()
        logger.debug(f"Получено {len(messages)} сообщений")
        unread_count = ContactMessage.query.filter_by(is_read=False).count()
        logger.debug(f"Непрочитанных сообщений: {unread_count}")
        
        logger.debug("Все данные успешно загружены")
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Ошибка в admin_dashboard: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        flash('Произошла ошибка при загрузке данных. Пожалуйста, попробуйте позже.', 'danger')
    
    logger.debug("Подготовка к рендерингу шаблона")
    
    try:
        return render_template('admin/dashboard.html', 
                              title='Админ-панель',
                              user_count=user_count,
                              transaction_count=transaction_count,
                              total_invested=total_invested,
                              pending_count=pending_count,
                              recent_transactions=recent_transactions,
                              messages=messages,
                              unread_count=unread_count,
                              User=User)  # Добавляем модель User в контекст шаблона
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Ошибка при рендеринге шаблона: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        return "Ошибка при рендеринге страницы. Пожалуйста, обратитесь к администратору."

@app.route('/admin/users')
@admin_required
def admin_users():
    """Административная панель - управление пользователями"""
    
    # Получаем список всех пользователей
    users = User.query.order_by(User.registered_on.desc()).all()
    
    return render_template('admin/users.html', 
                          title='Управление пользователями',
                          users=users)

@app.route('/admin/user/<int:user_id>')
@admin_required
def admin_user_details(user_id):
    """Административная панель - детальная информация о пользователе"""
    import logging
    logger = logging.getLogger(__name__)
    
    # Получаем пользователя
    user = User.query.get_or_404(user_id)
    
    # Получаем обычные транзакции пользователя
    regular_transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.desc()).all()
    
    # Получаем TON-транзакции пользователя
    ton_transactions = TonDeposit.query.filter_by(user_id=user.id).order_by(TonDeposit.created_at.desc()).all()
    
    # Создаем объединенный список всех транзакций
    all_transactions = []
    
    # Преобразуем обычные транзакции в единый формат
    for tx in regular_transactions:
        # Определяем тип срока для отображения
        term_value = None
        term_unit = 'months'  # По умолчанию для обычных транзакций - месяцы
        
        if tx.term_months:
            if tx.term_months < 1 and tx.term_months > 0:  # Вероятно, это недели или дни
                # Пробуем определить, недели это или дни
                if tx.term_months >= 0.25:  # Примерно 1 неделя (0.25 месяца)
                    term_value = tx.term_months * 4  # Преобразуем в недели
                    term_unit = 'weeks'
                else:
                    # Это, вероятно, минуты (для тестовых транзакций админа)
                    term_value = tx.term_months * 30 * 24 * 60  # Преобразуем в минуты
                    term_unit = 'minutes'
            elif tx.term_months >= 12:  # Год или более
                term_value = tx.term_months / 12  # Преобразуем в годы
                term_unit = 'years'
            else:
                # Обычный случай - месяцы
                term_value = tx.term_months
                term_unit = 'months'
        
        # Рассчитываем дату выплаты в зависимости от типа срока
        payout_date = None
        if tx.term_months:
            if term_unit == 'minutes':
                payout_date = tx.created_at + timedelta(minutes=term_value)
            elif term_unit == 'weeks':
                payout_date = tx.created_at + timedelta(weeks=term_value)
            elif term_unit == 'years':
                payout_date = tx.created_at + timedelta(days=term_value * 365)
            else:  # months (default)
                payout_date = tx.created_at + timedelta(days=tx.term_months * 30)
        
        all_transactions.append({
            'type': 'regular',
            'transaction_id': tx.transaction_id,
            'amount': tx.amount,
            'status': tx.status,
            'created_at': tx.created_at,
            'term_months': tx.term_months,
            'term_value': term_value,
            'term_unit': term_unit,
            'expected_profit': tx.expected_profit,
            'payout_date': payout_date,
            'source': 'nowpayments',
            'original': tx
        })
    
    # Преобразуем TON-транзакции в тот же формат
    for tx in ton_transactions:
        # Добавляем логирование для отладки
        app.logger.debug(f"Обработка TON-транзакции: ID={tx.id}, MEMO={tx.memo}, term_days={tx.term_days}")
        
        # Рассчитываем срок в месяцах на основе term_days
        term_months = None
        term_value = None  # Числовое значение срока (количество недель/месяцев/лет)
        term_unit = None   # Единица измерения срока (неделя/месяц/год)
        
        if tx.term_days:
            # Пробуем конвертировать term_days в число, если это еще не число
            term_days = float(tx.term_days) if isinstance(tx.term_days, (str, int, float)) else 0
            
            # Определяем тип срока на основе значения term_days
            if term_days < 1:  # Минуты (доли дня)
                # Для минут преобразуем в доли месяца
                term_months = term_days / 30
                # Для отображения в минутах
                term_value = term_days * 24 * 60  # дни в минуты
                term_unit = 'minutes'
                app.logger.debug(f"TON-транзакция {tx.id}: Минуты, term_months={term_months}, term_value={term_value}")
            elif term_days % 7 == 0 and term_days <= 28:  # Недели (кратно 7 дням до 28)
                # Для недель преобразуем в месяцы
                term_months = term_days / 7 / 4.3  # Примерно (недели в месяцы)
                # Для отображения в неделях
                term_value = term_days / 7  # дни в недели
                term_unit = 'weeks'
                app.logger.debug(f"TON-транзакция {tx.id}: Недели, term_months={term_months}, term_value={term_value}")
            elif term_days >= 365:  # Годы (365+ дней)
                # Для лет преобразуем в месяцы
                term_months = term_days / 30
                # Для отображения в годах
                term_value = term_days / 365  # дни в годы
                term_unit = 'years'
                app.logger.debug(f"TON-транзакция {tx.id}: Годы, term_months={term_months}, term_value={term_value}")
            else:  # Месяцы и другие периоды
                # По умолчанию считаем, что это месяцы
                term_months = term_days / 30
                # Для отображения в месяцах
                term_value = term_days / 30  # дни в месяцы
                term_unit = 'months'
                app.logger.debug(f"TON-транзакция {tx.id}: Месяцы, term_months={term_months}, term_value={term_value}")
        else:
            app.logger.debug(f"TON-транзакция {tx.id}: Нет данных о сроке (term_days is None)")
        
        # Рассчитываем дату выплаты (дата создания + срок в днях)
        try:
            # Преобразуем term_days в число, если необходимо
            term_days_float = float(tx.term_days) if tx.term_days else 0
            payout_date = tx.created_at + timedelta(days=term_days_float) if term_days_float > 0 else None
            app.logger.debug(f"TON-транзакция {tx.id}: Дата выплаты={payout_date}")
        except (ValueError, TypeError) as e:
            app.logger.error(f"Ошибка при расчете даты выплаты для TON-транзакции {tx.id}: {str(e)}")
            payout_date = None
        
        all_transactions.append({
            'type': 'ton',
            'transaction_id': tx.memo,  # Используем MEMO как ID транзакции
            'amount': tx.amount,
            'status': tx.status,
            'created_at': tx.created_at,
            'term_months': term_months,
            'term_value': term_value,   # Числовое значение срока
            'term_unit': term_unit,     # Единица измерения срока (weeks, months, years)
            'expected_profit': tx.expected_profit,
            'payout_date': payout_date,
            'source': 'ton',
            'original': tx
        })
    
    # Сортируем все транзакции по дате создания (сначала новые)
    all_transactions.sort(key=lambda x: x['created_at'], reverse=True)
    
    logger.debug(f"Найдено {len(regular_transactions)} обычных и {len(ton_transactions)} TON-транзакций для пользователя {user.id}")
    
    # Получаем IP-логи пользователя, отсортированные по времени (новые в начале)
    ip_logs = UserIPLog.query.filter_by(user_id=user.id).order_by(UserIPLog.timestamp.desc()).all()
    logger.debug(f"Найдено {len(ip_logs)} IP-логов для пользователя {user.id}")
    
    return render_template('admin/user_details.html', 
                          title=f'Пользователь {user.username}',
                          user=user,
                          transactions=all_transactions,
                          ip_logs=ip_logs,
                          total_balance=user.get_total_balance(),
                          expected_profit=user.get_expected_profit())

@app.route('/admin/user/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def admin_toggle_admin_status(user_id):
    """Изменение статуса администратора для пользователя"""
    
    # Получаем пользователя
    user = User.query.get_or_404(user_id)
    
    # Не позволяем снять админ-права у себя
    if int(request.cookies.get('user_id')) == user.id:
        flash('Вы не можете снять права администратора с самого себя.', 'danger')
        return redirect(url_for('admin_user_details', user_id=user.id))
    
    # Изменяем статус администратора
    if user.is_admin:
        user.demote_from_admin()
        flash(f'Права администратора сняты у пользователя {user.username}.', 'success')
    else:
        user.promote_to_admin()
        flash(f'Пользователь {user.username} назначен администратором.', 'success')
    
    db.session.commit()
    return redirect(url_for('admin_user_details', user_id=user.id))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
@csrf.exempt
def admin_delete_user(user_id):
    """Удаление пользователя со всеми связанными данными"""
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info(f"Запрос на удаление пользователя с ID: {user_id}")
    
    # Получаем пользователя
    user = User.query.get_or_404(user_id)
    
    # Защита от удаления себя
    current_user_id = int(request.cookies.get('user_id'))
    if current_user_id == user.id:
        flash('Вы не можете удалить свою учетную запись.', 'danger')
        return redirect(url_for('admin_user_details', user_id=user.id))
    
    # Запоминаем имя пользователя для сообщения
    username = user.username
    
    try:
        # Удаляем все связанные с пользователем данные
        
        # 1. Удаляем IP-логи
        ip_logs_count = UserIPLog.query.filter_by(user_id=user.id).delete()
        logger.info(f"Удалено {ip_logs_count} IP-логов пользователя {username}")
        
        # 2. Удаляем запросы на вывод средств
        withdrawals_count = WithdrawalRequest.query.filter_by(user_id=user.id).delete()
        logger.info(f"Удалено {withdrawals_count} запросов на вывод средств пользователя {username}")
        
        # 3. Удаляем TON-депозиты
        ton_deposits_count = TonDeposit.query.filter_by(user_id=user.id).delete()
        logger.info(f"Удалено {ton_deposits_count} TON-депозитов пользователя {username}")
        
        # 4. Удаляем обычные транзакции
        transactions_count = Transaction.query.filter_by(user_id=user.id).delete()
        logger.info(f"Удалено {transactions_count} обычных транзакций пользователя {username}")
        
        # 5. Ищем сообщения от пользователя по email (т.к. в таблице ContactMessage нет поля user_id)
        # Используем email как связующий элемент
        messages_count = ContactMessage.query.filter_by(email=user.email).delete()
        logger.info(f"Удалено {messages_count} сообщений с email {user.email}")
        
        # 6. Наконец, удаляем самого пользователя
        db.session.delete(user)
        
        # Применяем изменения
        db.session.commit()
        
        # Записываем в лог и уведомляем о успешном удалении
        logger.info(f"Пользователь {username} (ID: {user_id}) успешно удален")
        flash(f'Пользователь {username} успешно удален со всеми связанными данными.', 'success')
        
        # Добавляем уведомление администраторам
        admin_notification = AdminNotification(
            title='Удаление пользователя',
            content=f'Администратор удалил пользователя {username} (ID: {user_id}).',
            notification_type='user_deleted',
            is_read=False
        )
        db.session.add(admin_notification)
        db.session.commit()
        
    except Exception as e:
        # В случае ошибки откатываем изменения и уведомляем
        db.session.rollback()
        logger.error(f"Ошибка при удалении пользователя {username}: {str(e)}")
        flash(f'Произошла ошибка при удалении пользователя: {str(e)}', 'danger')
    
    # Перенаправляем на список пользователей
    return redirect(url_for('admin_users'))

@app.route('/admin/transactions')
@admin_required
def admin_transactions():
    """Административная панель - управление транзакциями"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Получаем список всех транзакций
        transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
        
        # Получаем список всех TON-транзакций
        ton_deposits = TonDeposit.query.order_by(TonDeposit.created_at.desc()).all()
        
        # Логируем количество полученных транзакций
        logger.debug(f"Получено {len(transactions)} обычных транзакций и {len(ton_deposits)} TON транзакций")
        
        # Создаем объединенный список транзакций
        all_transactions = []
        
        # Добавляем обычные транзакции в список
        for tx in transactions:
            all_transactions.append({
                'type': 'regular',
                'data': tx,
                'created_at': tx.created_at,
                'id': tx.id,
                'transaction_id': tx.transaction_id,
                'user_id': tx.user_id,
                'amount': tx.amount,
                'status': tx.status,
                'source': 'nowpayments'
            })
        
        # Добавляем TON-транзакции в список
        for tx in ton_deposits:
            all_transactions.append({
                'type': 'ton',
                'data': tx,
                'created_at': tx.created_at,
                'id': tx.id,
                'transaction_id': tx.memo if tx.memo else f"TON{tx.id}",
                'user_id': tx.user_id,
                'amount': tx.amount,
                'status': tx.status,
                'source': 'ton'
            })
        
        # Сортируем объединенный список по времени создания (сначала новые)
        all_transactions.sort(key=lambda x: x['created_at'], reverse=True)
        
        return render_template('admin/transactions.html', 
                              title='Управление транзакциями',
                              transactions=all_transactions,
                              User=User)
    except Exception as e:
        logger.error(f"Ошибка в admin_transactions: {str(e)}")
        flash('Произошла ошибка при загрузке транзакций. Пожалуйста, попробуйте позже.', 'danger')
        return render_template('admin/transactions.html', 
                              title='Управление транзакциями',
                              transactions=[],
                              User=User)

@app.route('/admin/transaction/<transaction_id>')
@admin_required
def admin_transaction_details(transaction_id):
    """Административная панель - детальная информация о транзакции"""
    
    # Получаем транзакцию
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    
    # Получаем пользователя
    user = User.query.get(transaction.user_id)
    
    return render_template('admin/transaction_details.html', 
                          title=f'Транзакция {transaction.transaction_id}',
                          transaction=transaction,
                          user=user)

# Оставляем старый маршрут для совместимости
@app.route('/admin/transaction/<transaction_id>/update-status', methods=['POST'])
@admin_required
@csrf.exempt
def admin_update_transaction_status(transaction_id):
    """Обновление статуса транзакции (для обратной совместимости)"""
    # Определяем тип транзакции (обычная или TON)
    transaction_type = request.form.get('type', 'regular')
    
    # Если это TON-транзакция, перенаправляем на новый обработчик
    if transaction_type == 'ton' and request.form.get('db_id'):
        return admin_update_ton_transaction_status(request.form.get('db_id'))
    
    # Получаем новый статус
    new_status = request.form.get('status')
    valid_statuses = ['pending', 'payment_awaiting', 'completed', 'failed', 'cancelled', 'archived']
    
    if new_status not in valid_statuses:
        return jsonify({
            'success': False,
            'message': 'Некорректный статус транзакции.'
        }), 400
        
    # Для обычных транзакций (NOWPayments)
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    
    # Обновляем статус
    transaction.status = new_status
    
    # Если статус "completed", то обновляем дату завершения
    if new_status == 'completed' and not transaction.payment_completed_at:
        transaction.payment_completed_at = datetime.utcnow()
    
    db.session.commit()
    app.logger.info(f"Администратор обновил статус транзакции {transaction_id} на {new_status}")
    
    # Проверяем тип запроса (AJAX или обычный)
    is_ajax_request = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.best == 'application/json'
    
    if is_ajax_request:
        return jsonify({
            'success': True,
            'transaction_id': transaction_id,
            'status': new_status,
            'message': f'Статус транзакции обновлен на "{new_status}".'
        })
    else:
        flash(f'Статус транзакции изменен на "{new_status}".', 'success')
        return redirect(url_for('admin_transaction_details', transaction_id=transaction.transaction_id))


# Новый маршрут для просмотра всех TON-транзакций
@app.route('/admin/ton-transactions')
@admin_required
def admin_ton_transactions():
    """Отдельная страница для работы только с TON-транзакциями"""
    
    # Получаем все TON-транзакции, отсортированные по дате создания (новые в начале)
    transactions = TonDeposit.query.order_by(TonDeposit.created_at.desc()).all()
    
    # Получаем информацию о пользователях
    user_ids = [tx.user_id for tx in transactions]
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    
    # Создаем словарь с информацией о пользователях для быстрого доступа
    user_dict = {user.id: {'username': user.username, 'email': user.email} for user in users}
    
    app.logger.info(f"Администратор открыл страницу TON-транзакций. Найдено {len(transactions)} записей.")
    
    return render_template('admin/ton_transactions.html', 
                          title='TON транзакции',
                          transactions=transactions,
                          user_dict=user_dict)

# Новый маршрут для просмотра TON-транзакций в упрощенном режиме с формами
@app.route('/admin/ton-transactions-buttons')
@admin_required
def admin_ton_transactions_buttons():
    """Упрощенная страница для работы с TON-транзакциями через формы"""
    
    # Получаем все TON-транзакции, отсортированные по дате создания (новые в начале)
    transactions = TonDeposit.query.order_by(TonDeposit.created_at.desc()).all()
    
    # Получаем информацию о пользователях
    user_ids = [tx.user_id for tx in transactions]
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    
    # Создаем словарь с информацией о пользователях для быстрого доступа
    user_dict = {user.id: {'username': user.username, 'email': user.email} for user in users}
    
    app.logger.info(f"Администратор открыл УПРОЩЕННУЮ страницу TON-транзакций. Найдено {len(transactions)} записей.")
    
    return render_template('admin/ton_transaction_buttons.html', 
                          title='Управление TON транзакциями (Упрощенный режим)',
                          transactions=transactions,
                          user_dict=user_dict)

# Новый маршрут для обновления статуса через AJAX
@app.route('/admin/ton-transaction/<int:db_id>/update-status', methods=['POST'])
@admin_required
@csrf.exempt
def admin_update_ton_transaction_status(db_id):
    """
    Обновление статуса TON-транзакции через AJAX
    Принимает и возвращает JSON
    """
    """
    Обновление статуса TON-транзакции напрямую по числовому ID из базы данных
    Это полностью переработанная версия, которая работает максимально просто
    """
    import logging, traceback
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    logger.debug(f"=== НАЧИНАЕМ ОБНОВЛЕНИЕ СТАТУСА TON-ТРАНЗАКЦИИ ===")
    logger.debug(f"ID транзакции: {db_id}")
    logger.debug(f"Метод запроса: {request.method}")
    logger.debug(f"Данные формы: {request.form}")
    
    try:
        # Получаем новый статус
        new_status = request.form.get('status')
        logger.debug(f"Получен новый статус: {new_status}")
        
        valid_statuses = ['pending', 'payment_awaiting', 'completed', 'failed', 'cancelled', 'archived']
        
        if new_status not in valid_statuses:
            error_msg = f'Некорректный статус транзакции: {new_status}'
            logger.error(error_msg)
            return jsonify({
                'success': False,
                'message': error_msg
            }), 400
        
        logger.debug(f"Поиск транзакции по ID: {db_id}")
        # Находим TON-транзакцию напрямую по числовому ID
        ton_deposit = TonDeposit.query.get(db_id)
        
        # Проверяем, найдена ли транзакция
        if not ton_deposit:
            error_msg = f'TON-транзакция с ID {db_id} не найдена.'
            logger.error(error_msg)
            return jsonify({
                'success': False,
                'message': error_msg
            }), 404
            
        logger.debug(f"Транзакция найдена: ID={ton_deposit.id}, MEMO={ton_deposit.memo}, статус={ton_deposit.status}")
        
        # Сохраняем старый статус для лога
        old_status = ton_deposit.status
        
        # Обновляем статус TON-транзакции
        ton_deposit.status = new_status
        
        # Устанавливаем время подтверждения для завершенных транзакций
        if new_status == 'completed' and not ton_deposit.payment_confirmed_at:
            ton_deposit.payment_confirmed_at = datetime.utcnow()
        
        # Сохраняем изменения
        db.session.commit()
        
        # Отправляем уведомление пользователю об изменении статуса транзакции
        try:
            from telegram_notification import notify_ton_deposit_status_change
            
            logger.debug(f"Отправка уведомления пользователю об изменении статуса транзакции ID={db_id}")
            
            notify_result = notify_ton_deposit_status_change(
                user_id=ton_deposit.user_id,
                amount=ton_deposit.amount,
                memo=ton_deposit.memo,
                transaction_id=str(ton_deposit.id),
                new_status=new_status
            )
            
            logger.info(f"Результат отправки уведомления пользователю: {notify_result}")
        except Exception as notify_error:
            logger.error(f"Ошибка при отправке уведомления пользователю: {str(notify_error)}")
            # Ошибка уведомления не должна влиять на основной процесс
        
        # Логируем изменение
        app.logger.info(f"Администратор обновил статус TON-транзакции ID={db_id}, MEMO={ton_deposit.memo} с {old_status} на {new_status}")
        
        # Возвращаем JSON-ответ с обновленными данными
        return jsonify({
            'success': True,
            'id': db_id,
            'memo': ton_deposit.memo,
            'old_status': old_status,
            'new_status': new_status,
            'updated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'message': f'Статус TON-транзакции обновлен на "{new_status}".'
        })
        
    except Exception as e:
        app.logger.error(f"Ошибка при обновлении статуса TON-транзакции: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        
        return jsonify({
            'success': False,
            'message': f'Произошла ошибка: {str(e)}'
        }), 500

# Новый маршрут для прямого обновления статуса через форму
@app.route('/admin/ton-transaction/<int:db_id>/update-status-direct', methods=['POST'])
@admin_required
def admin_update_ton_transaction_status_direct(db_id):
    """
    Обновление статуса TON-транзакции через форму с редиректом
    Используется для кнопок на странице ton_transaction_buttons.html
    """
    try:
        # Получаем новый статус
        new_status = request.form.get('status')
        valid_statuses = ['pending', 'payment_awaiting', 'completed', 'failed', 'cancelled', 'archived']
        
        if new_status not in valid_statuses:
            flash(f'Некорректный статус транзакции: {new_status}', 'danger')
            return redirect(url_for('admin_ton_transactions_buttons'))
        
        # Находим TON-транзакцию напрямую по числовому ID
        ton_deposit = TonDeposit.query.get(db_id)
        
        # Проверяем, найдена ли транзакция
        if not ton_deposit:
            flash(f'TON-транзакция с ID {db_id} не найдена.', 'danger')
            return redirect(url_for('admin_ton_transactions_buttons'))
        
        # Сохраняем старый статус для лога
        old_status = ton_deposit.status
        
        # Обновляем статус TON-транзакции
        ton_deposit.status = new_status
        
        # Устанавливаем время подтверждения для завершенных транзакций
        if new_status == 'completed' and not ton_deposit.payment_confirmed_at:
            ton_deposit.payment_confirmed_at = datetime.utcnow()
        
        # Сохраняем изменения
        db.session.commit()
        
        # Отправляем уведомление пользователю об изменении статуса транзакции
        try:
            from telegram_notification import notify_ton_deposit_status_change
            
            app.logger.debug(f"Отправка уведомления пользователю об изменении статуса транзакции ID={db_id}")
            
            notify_result = notify_ton_deposit_status_change(
                user_id=ton_deposit.user_id,
                amount=ton_deposit.amount,
                memo=ton_deposit.memo,
                transaction_id=str(ton_deposit.id),
                new_status=new_status
            )
            
            app.logger.info(f"Результат отправки уведомления пользователю: {notify_result}")
        except Exception as notify_error:
            app.logger.error(f"Ошибка при отправке уведомления пользователю: {str(notify_error)}")
            # Ошибка уведомления не должна влиять на основной процесс
        
        # Логируем изменение
        app.logger.info(f"Администратор обновил статус TON-транзакции ID={db_id}, MEMO={ton_deposit.memo} с {old_status} на {new_status} (прямая форма)")
        
        # Показываем сообщение пользователю
        status_names = {
            'completed': 'Завершена',
            'payment_awaiting': 'Ожидает оплаты',
            'failed': 'Ошибка',
            'cancelled': 'Отменена',
            'pending': 'В обработке',
            'archived': 'Архивирована'
        }
        flash(f'Статус транзакции изменен на "{status_names.get(new_status, new_status)}".', 'success')
        
        # Перенаправляем пользователя обратно на страницу
        return redirect(url_for('admin_ton_transactions_buttons'))
        
    except Exception as e:
        app.logger.error(f"Ошибка при обновлении статуса TON-транзакции: {str(e)}")
        flash(f'Произошла ошибка: {str(e)}', 'danger')
        return redirect(url_for('admin_ton_transactions_buttons'))

@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    """Административная панель - управление уведомлениями"""
    import logging, traceback
    
    # Настройка дополнительного логирования
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Инициализируем переменные по умолчанию
    notifications = []
    unread_count = 0
    user_dict = {}
    
    try:
        # Логируем начало выполнения функции
        logger.debug("Запуск admin_notifications")
        
        # Получаем все уведомления, отсортированные по дате (сначала новые)
        logger.debug("Получение уведомлений из базы данных")
        notifications = AdminNotification.query.order_by(AdminNotification.created_at.desc()).all()
        logger.debug(f"Получено {len(notifications)} уведомлений")
        
        # Подсчитываем количество непрочитанных уведомлений
        logger.debug("Подсчет непрочитанных уведомлений")
        unread_count = AdminNotification.query.filter_by(is_read=False).count()
        logger.debug(f"Непрочитанных уведомлений: {unread_count}")
        
        # Получаем данные о пользователях для отображения
        user_ids = [n.related_user_id for n in notifications if n.related_user_id is not None]
        users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
        
        # Создаем словарь для быстрого доступа к пользователям
        user_dict = {user.id: {'username': user.username, 'email': user.email} for user in users}
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Ошибка в admin_notifications: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        flash('Произошла ошибка при загрузке уведомлений. Пожалуйста, попробуйте позже.', 'danger')
    
    app.logger.info(f"Администратор открыл страницу уведомлений. Найдено {len(notifications)} уведомлений, из них {unread_count} непрочитанных.")
    
    return render_template('admin/notifications.html', 
                          title='Уведомления системы',
                          notifications=notifications,
                          unread_count=unread_count,
                          user_dict=user_dict)
                          
@app.route('/admin/notification/<int:notification_id>/mark-read', methods=['POST'])
@admin_required
def admin_mark_notification_read(notification_id):
    """Отметить уведомление как прочитанное"""
    import logging
    
    try:
        # Находим уведомление
        notification = AdminNotification.query.get_or_404(notification_id)
        
        # Отмечаем как прочитанное
        notification.is_read = True
        db.session.commit()
        
        app.logger.info(f"Администратор отметил уведомление ID={notification_id} как прочитанное")
        flash('Уведомление отмечено как прочитанное', 'success')
    except Exception as e:
        app.logger.error(f"Ошибка при отметке уведомления как прочитанного: {str(e)}")
        flash('Произошла ошибка при обновлении статуса уведомления', 'danger')
    
    # Возвращаемся на страницу уведомлений
    return redirect(url_for('admin_notifications'))

@app.route('/admin/notifications/mark-all-read', methods=['POST'])
@admin_required
def admin_mark_all_notifications_read():
    """Отметить все уведомления как прочитанные"""
    import logging
    
    try:
        # Обновляем все непрочитанные уведомления
        unread_count = AdminNotification.query.filter_by(is_read=False).update({'is_read': True})
        db.session.commit()
        
        app.logger.info(f"Администратор отметил все ({unread_count}) уведомления как прочитанные")
        flash(f'Все ({unread_count}) уведомления отмечены как прочитанные', 'success')
    except Exception as e:
        app.logger.error(f"Ошибка при отметке всех уведомлений как прочитанных: {str(e)}")
        flash('Произошла ошибка при обновлении статусов уведомлений', 'danger')
    
    # Возвращаемся на страницу уведомлений
    return redirect(url_for('admin_notifications'))

@app.route('/admin/notifications/delete-all-read', methods=['POST'])
@admin_required
def admin_delete_read_notifications():
    """Удалить все прочитанные уведомления"""
    import logging
    
    try:
        # Удаляем все прочитанные уведомления
        deleted_count = AdminNotification.query.filter_by(is_read=True).delete()
        db.session.commit()
        
        app.logger.info(f"Администратор удалил все прочитанные уведомления ({deleted_count} шт.)")
        flash(f'Удалено {deleted_count} прочитанных уведомлений', 'success')
    except Exception as e:
        app.logger.error(f"Ошибка при удалении прочитанных уведомлений: {str(e)}")
        flash('Произошла ошибка при удалении уведомлений', 'danger')
    
    # Возвращаемся на страницу уведомлений
    return redirect(url_for('admin_notifications'))

@app.route('/admin/messages')
@admin_required
def admin_messages():
    """Административная панель - управление сообщениями от пользователей"""
    import logging, traceback
    
    # Настройка дополнительного логирования
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    # Инициализируем переменные по умолчанию
    messages = []
    unread_count = 0
    
    try:
        # Логируем начало выполнения функции
        logger.debug("Запуск admin_messages")
        
        # Получаем все сообщения, отсортированные по дате (сначала новые)
        logger.debug("Получение сообщений из базы данных")
        messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
        logger.debug(f"Получено {len(messages)} сообщений")
        
        # Подсчитываем количество непрочитанных сообщений
        logger.debug("Подсчет непрочитанных сообщений")
        unread_count = ContactMessage.query.filter_by(is_read=False).count()
        logger.debug(f"Непрочитанных сообщений: {unread_count}")
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Ошибка в admin_messages: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        flash('Произошла ошибка при загрузке сообщений. Пожалуйста, попробуйте позже.', 'danger')
    
    logger.debug("Подготовка к рендерингу шаблона messages")
    
    try:
        return render_template('admin/messages.html', 
                              title='Управление сообщениями', 
                              messages=messages,
                              unread_count=unread_count)
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Ошибка при рендеринге шаблона messages: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        return "Ошибка при рендеринге страницы сообщений. Пожалуйста, обратитесь к администратору."

@app.route('/admin/message/<int:message_id>')
@admin_required
def admin_message_details(message_id):
    """Административная панель - детальная информация о сообщении"""
    # Получаем сообщение по ID
    message = ContactMessage.query.get_or_404(message_id)
    
    # Помечаем сообщение как прочитанное, если оно ещё не прочитано
    if not message.is_read:
        message.is_read = True
        db.session.commit()
    
    return render_template('admin/message_details.html', 
                          title='Просмотр сообщения', 
                          message=message)

@app.route('/admin/message/toggle_read/<int:message_id>')
@admin_required
def admin_toggle_message_read(message_id):
    """Изменение статуса сообщения (прочитано/непрочитано)"""
    # Получаем сообщение по ID
    message = ContactMessage.query.get_or_404(message_id)
    
    # Меняем статус сообщения на противоположный
    message.is_read = not message.is_read
    db.session.commit()
    
    flash(f'Сообщение отмечено как {"прочитанное" if message.is_read else "непрочитанное"}', 'success')
    return redirect(url_for('admin_message_details', message_id=message.id))

@app.route('/admin/message/delete/<int:message_id>')
@admin_required
def admin_delete_message(message_id):
    """Удаление сообщения"""
    # Получаем сообщение по ID
    message = ContactMessage.query.get_or_404(message_id)
    
    # Удаляем сообщение
    db.session.delete(message)
    db.session.commit()
    
    flash('Сообщение удалено', 'success')
    return redirect(url_for('admin_messages'))

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def admin_change_password():
    """
    Страница для изменения пароля администратора
    Отдельный от пользовательского маршрута для усиления безопасности
    """
    import logging
    
    # Получаем пользователя из базы данных
    user_id = request.cookies.get('user_id')
    user = User.query.get(int(user_id))
    
    if not user or not user.is_admin:
        flash('Доступ запрещен. Эта страница только для администраторов.', 'danger')
        return redirect(url_for('index'))
    
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Проверяем текущий пароль
        if not user.check_password(form.current_password.data):
            logging.warning(f"Admin password change failed: current password mismatch for user_id={user.id}")
            flash('Неверный текущий пароль. Пожалуйста, попробуйте снова.', 'danger')
            return render_template('admin/change_password.html', title='Изменение пароля администратора', form=form)
        
        # Устанавливаем новый пароль с усиленным хешированием
        user.set_password(form.new_password.data)
        db.session.commit()
        
        # Безопасное логирование
        logging.info(f"Admin password changed successfully for user_id={user.id}")
        
        # Добавляем уведомление для администраторов о смене пароля
        notification = AdminNotification(
            title="Смена пароля администратора",
            content=f"Пароль администратора {user.username} был изменен с IP: {utils.get_client_ip()}",
            admin_id=user.id
        )
        db.session.add(notification)
        db.session.commit()
        
        flash('Пароль администратора успешно изменен!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/change_password.html', title='Изменение пароля администратора', form=form)
