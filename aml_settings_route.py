import os
import logging
import traceback
import functools
from flask import render_template, request, redirect, url_for, flash
from app import app, csrf
from getblock_client import GetBlockClient

# Заглушка для current_user - через cookie
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
        
    def is_admin(self):
        return request.cookies.get('is_admin') == 'true'

# Создаем объект для заглушки
current_user = CurrentUser()

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
        from models import User
        user = User.query.get(int(user_id))
        if not user or not user.is_admin:
            logging.debug(f"Admin auth failed for {f.__name__}")
            flash('У вас нет прав администратора для доступа к этой странице.', 'danger')
            return redirect(url_for('index'))
        
        logging.debug(f"Admin auth successful for user_id={user_id}")
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/aml-settings', methods=['GET', 'POST'])
@admin_required
def admin_aml_settings():
    """Административная панель - настройки AML проверки"""
    # Настройка дополнительного логирования
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    
    try:
        # Логируем начало выполнения функции
        logger.debug("Запуск admin_aml_settings")
        
        if request.method == 'POST':
            # Обновление настроек AML
            proxy_enabled = request.form.get('proxy_enabled') == 'on'
            proxy_host = request.form.get('proxy_host', '')
            proxy_port = request.form.get('proxy_port', '')
            proxy_user = request.form.get('proxy_user', '')
            proxy_pass = request.form.get('proxy_pass', '')
            api_token = request.form.get('api_token', '')
            
            # Сохраняем настройки в переменные окружения (временно, для текущей сессии)
            os.environ['GETBLOCK_PROXY_ENABLED'] = 'true' if proxy_enabled else 'false'
            if proxy_host:
                os.environ['GETBLOCK_PROXY_HOST'] = proxy_host
            if proxy_port:
                os.environ['GETBLOCK_PROXY_PORT'] = proxy_port
            if proxy_user:
                os.environ['GETBLOCK_PROXY_USER'] = proxy_user
            if proxy_pass:
                os.environ['GETBLOCK_PROXY_PASS'] = proxy_pass
            if api_token:
                os.environ['GETBLOCK_API_TOKEN'] = api_token
            
            flash('Настройки AML успешно обновлены.', 'success')
            
            # Проверяем соединение, если был включен прокси
            if proxy_enabled and proxy_host and proxy_port:
                client = GetBlockClient()
                test_result = client.test_proxy_connection()
                
                if test_result.get('success'):
                    flash(f'Соединение через прокси успешно установлено. IP адрес: {test_result.get("current_ip")}', 'success')
                else:
                    flash(f'Ошибка соединения через прокси: {test_result.get("error", "неизвестная ошибка")}', 'danger')
                    if test_result.get('cloudflare_blocked'):
                        flash('Cloudflare блокирует доступ к API. Попробуйте использовать другой IP адрес.', 'warning')
        
        # Получаем текущие настройки
        proxy_enabled = os.environ.get('GETBLOCK_PROXY_ENABLED', 'false').lower() == 'true'
        proxy_host = os.environ.get('GETBLOCK_PROXY_HOST', '')
        proxy_port = os.environ.get('GETBLOCK_PROXY_PORT', '')
        proxy_user = os.environ.get('GETBLOCK_PROXY_USER', '')
        proxy_pass = os.environ.get('GETBLOCK_PROXY_PASS', '')
        api_token = os.environ.get('GETBLOCK_API_TOKEN', '')
        
        # Тестируем текущее подключение
        client = GetBlockClient()
        connection_status = client.test_proxy_connection()
        
        return render_template(
            'admin/aml_settings.html',
            title='Настройки AML проверки',
            proxy_enabled=proxy_enabled,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_user=proxy_user,
            proxy_pass=proxy_pass,
            api_token=api_token,
            connection_status=connection_status
        )
    
    except Exception as e:
        # Логируем ошибку
        logger.error(f"Ошибка в admin_aml_settings: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Сообщаем пользователю об ошибке
        flash(f'Произошла ошибка: {str(e)}', 'danger')
        
        # Возвращаем шаблон с минимальными данными
        return render_template(
            'admin/aml_settings.html',
            title='Настройки AML проверки',
            proxy_enabled=False,
            proxy_host='',
            proxy_port='',
            proxy_user='',
            proxy_pass='',
            api_token='',
            connection_status={'success': False, 'error': str(e)}
        )