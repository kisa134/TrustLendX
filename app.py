import os
import logging
from datetime import timedelta
from flask import Flask, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# Настройка логирования с более детальным форматом
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Create SQLAlchemy base class
class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy
db = SQLAlchemy(model_class=Base)

# Initialize CSRF protection
csrf = CSRFProtect()

# Create Flask application
app = Flask(__name__)

# Добавляем ProxyFix для корректной обработки IP за прокси (Replit)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# 🔒 Security fix: Инициализация rate limiter для защиты от брутфорс-атак
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

# CSRF исключения только для API webhook маршрутов
csrf_exempt_routes = [
    '/admin/transaction/<transaction_id>/update-status',
    '/webhooks/payment-notification'
]

# Импортируем модули для мониторинга и обработки ошибок
from error_handlers import register_error_handlers
from logger import setup_logging
from performance import setup_performance_monitoring, cache_control

# 🔒 Security fix: Улучшенная политика безопасности контента (CSP)
csp = {
    'default-src': [
        '\'self\'',
        'https://cdn.replit.com',
        'https://cdnjs.cloudflare.com',
        'https://fonts.googleapis.com',
        'https://fonts.gstatic.com',
        'https://cdn.jsdelivr.net',
    ],
    'img-src': [
        '\'self\'',
        'data:',
        'https://cdn.replit.com',
        'https://*.replit.app',  # Для поддержки Replit деплоя
    ],
    'style-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        'https://cdn.replit.com',
        'https://fonts.googleapis.com',
        'https://cdnjs.cloudflare.com',
        'https://cdn.jsdelivr.net',
    ],
    'script-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        '\'unsafe-eval\'',
        'https://cdn.jsdelivr.net',
        'https://cdnjs.cloudflare.com',
        'https://*.replit.app',  # Для поддержки Replit деплоя
    ],
    'font-src': [
        '\'self\'',
        'https://fonts.gstatic.com',
        'https://cdnjs.cloudflare.com',
    ],
    'connect-src': [
        '\'self\'',
        'https://*.replit.app',  # Для поддержки AJAX запросов в Replit деплое
    ],
    'frame-ancestors': [
        '\'self\'',
    ],
    'base-uri': [
        '\'self\'',
    ],
    'form-action': [
        '\'self\'',
    ],
}

# 🔒 Security fix: Инициализируем Talisman для усиленных HTTP-заголовков безопасности
talisman = Talisman(
    app,
    content_security_policy=csp,
    content_security_policy_nonce_in=['script-src'],
    content_security_policy_report_only=False,
    content_security_policy_report_uri=None,
    force_https=False,  # Будет включено в продакшене
    session_cookie_secure=False,  # Будет включено в продакшене
    session_cookie_http_only=True,
    feature_policy={
        'geolocation': '\'none\'',
        'microphone': '\'none\'',
        'camera': '\'none\'',
        'payment': '\'none\'',
        'usb': '\'none\'',
        'accelerometer': '\'none\'',
        'ambient-light-sensor': '\'none\'',
        'autoplay': '\'none\'',
        'battery': '\'none\'',
        'display-capture': '\'none\'',
        'document-domain': '\'none\'',
        'encrypted-media': '\'none\'',
        'execution-while-not-rendered': '\'none\'',
        'execution-while-out-of-viewport': '\'none\'',
        'fullscreen': '\'none\'',
        'gyroscope': '\'none\'',
        'magnetometer': '\'none\'',
        'midi': '\'none\'',
        'navigation-override': '\'none\'',
        'picture-in-picture': '\'none\'',
        'publickey-credentials-get': '\'none\'',
        'screen-wake-lock': '\'none\'',
        'sync-xhr': '\'none\'',
        'xr-spatial-tracking': '\'none\'',
    },
    referrer_policy='strict-origin-when-cross-origin',
    # 🔒 Security fix: Усиленные заголовки безопасности
    x_xss_protection='1; mode=block',  # Включаем встроенную защиту от XSS в браузерах 
    x_content_type_options='nosniff',  # Запрещаем браузеру угадывать тип контента
    frame_options='SAMEORIGIN',  # Запрещаем встраивание сайта во фреймы на других доменах
    strict_transport_security=True,  # Включаем HSTS
    strict_transport_security_preload=True,  # Включаем HSTS preload
    strict_transport_security_max_age=31536000,  # HSTS действителен 1 год
    strict_transport_security_include_subdomains=True,  # HSTS для всех поддоменов
)

# 🔒 Security fix: Обновленные настройки приложения с усиленной безопасностью
# Используем ключ сессии из Replit Secrets
app.secret_key = os.environ.get("SESSION_SECRET")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# 🔒 Security fix: Усиленные настройки CSRF защиты
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = 1800  # Уменьшено время жизни CSRF токена до 30 минут
app.config["WTF_CSRF_SSL_STRICT"] = True  # Строгая проверка SSL для CSRF
app.config["WTF_CSRF_METHODS"] = ['POST', 'PUT', 'PATCH', 'DELETE']  # Явно указываем методы для CSRF защиты

# 🔒 Security fix: Улучшенные настройки сессий с повышенной безопасностью
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)  # Уменьшено время жизни сессии до 2 часов
app.config["SESSION_COOKIE_SECURE"] = False  # В продакшене должно быть True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_NAME"] = "investor_session"
app.config["SESSION_COOKIE_DOMAIN"] = None
app.config["SESSION_COOKIE_PATH"] = "/"
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"  # 🔒 Security fix: Изменено с Lax на Strict для лучшей защиты

# 🔒 Security fix: Дополнительные настройки безопасности
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # Лимит размера запроса (16MB)

# Initialize SQLAlchemy with the app
db.init_app(app)

# Функция для проверки, нужно ли исключить маршрут из CSRF-защиты
def csrf_exempt_check(view_func):
    # Проверяем, является ли запрос AJAX-запросом (с заголовком X-Requested-With)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        logging.debug("Отключение CSRF для AJAX запроса")
        return True
    
    # Проверяем по пути
    for route in csrf_exempt_routes:
        if request.path.startswith(route.split('<')[0]):
            logging.debug(f"Отключение CSRF для маршрута {request.path}")
            return True
    
    return False

# Указываем конкретные маршруты, для которых не будет CSRF-защиты
for route in csrf_exempt_routes:
    csrf.exempt(route)

# Initialize CSRF protection with the app
csrf.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Create database tables
with app.app_context():
    # Import models to ensure they are registered with SQLAlchemy
    from models import User, Transaction, ProxySettings
    db.create_all()
    
    # Инициализируем записи настроек прокси, если они еще не существуют
    # GetBlock API прокси
    getblock_proxy = ProxySettings.query.filter_by(service_name='getblock').first()
    if not getblock_proxy:
        getblock_proxy = ProxySettings(
            service_name='getblock',
            enabled=False,
            host='',
            port=0
        )
        db.session.add(getblock_proxy)
        
    # NOWPayments API прокси
    nowpayments_proxy = ProxySettings.query.filter_by(service_name='nowpayments').first()
    if not nowpayments_proxy:
        nowpayments_proxy = ProxySettings(
            service_name='nowpayments',
            enabled=False,
            host='',
            port=0
        )
        db.session.add(nowpayments_proxy)
        
    db.session.commit()

# Регистрируем обработчики ошибок
register_error_handlers(app)

# Настраиваем логирование
setup_logging(app)

# Настраиваем мониторинг производительности
setup_performance_monitoring(app)

# Import routes after app and extensions have been created
from routes import *

# Запускаем генератор транзакций при первом запросе
transaction_initialized = False

@app.before_request
def initialize_transactions():
    global transaction_initialized
    
    # Инициализируем только один раз
    if not transaction_initialized:
        import transaction_generator
        transaction_generator.initialize_transactions()
        transaction_generator.start_generator()
        transaction_initialized = True

# Добавляем CSS для мобильной адаптации
@app.context_processor
def inject_mobile_css():
    return {
        'mobile_css': True  # Флаг для включения мобильного CSS в базовый шаблон
    }

# 🔒 Security fix: Добавляем фильтр nl2br для безопасного преобразования переносов строки в HTML тег <br>
@app.template_filter('nl2br')
def nl2br(value):
    if not value:
        return ''
    from markupsafe import Markup, escape
    
    # Первым делом экранируем HTML теги, чтобы предотвратить XSS-атаки
    escaped_value = escape(value)
    
    # Затем безопасно заменяем переносы строк на <br>
    result = escaped_value.replace('\n', '<br>').replace('\r\n', '<br>')
    
    return Markup(result)

# Импортируем blueprint для реферальной системы в админ-панели
try:
    from referral_admin_routes import referral_admin
    app.register_blueprint(referral_admin)
except ImportError as e:
    logging.error(f"Не удалось импортировать referral_admin: {e}")
    pass
