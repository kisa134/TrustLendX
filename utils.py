import html
import re
import string
import random
import logging
from datetime import datetime
from markupsafe import Markup

def calculate_profit_for_term(amount, term_months=None, term_weeks=None, term_minutes=None):
    """
    Calculate expected profit based on investment amount and term
    
    Args:
        amount (float): The investment amount
        term_months (int, optional): The investment term in months
        term_weeks (int, optional): The investment term in weeks (used for terms less than 1 month)
        term_minutes (int, optional): The investment term in minutes (used for admin testing)
        
    Returns:
        float: The calculated profit
    """
    if amount <= 0:
        return 0
    
    # Проверяем, что указан хотя бы один тип срока
    if term_months is None and term_weeks is None and term_minutes is None:
        return 0
    
    # Специальный тестовый режим для администраторов - 5 минут с 10% прибылью
    if term_minutes is not None:
        if term_minutes == 5:
            return amount * 0.10  # 10% прибыль для 5-минутного тестового депозита
        else:
            # Для других значений минут (если такие будут) используем мизерную прибыль
            return amount * 0.001
    
    # Для недельных сроков используем фиксированные проценты (не сложный процент)
    if term_weeks is not None and term_months is None:
        if term_weeks == 1:
            return amount * 0.012  # 1 неделя - 1.2%
        elif term_weeks == 2:
            return amount * 0.0241  # 2 недели - 2.41%
        elif term_weeks == 3:
            return amount * 0.0364  # 3 недели - 3.64%
        elif term_weeks == 4:
            return amount * 0.0488  # 4 недели - 4.88%
        elif term_weeks > 4:
            # Если больше 4 недель, считаем как 1 месяц
            term_months = 1
    
    # Расчет по сложному проценту для месячных сроков
    if term_months is not None:
        # Ограничиваем максимальный срок до 30 месяцев согласно таблице
        if term_months > 30:
            term_months = 30
        
        # Один месяц - 5% (фиксированный процент)
        if term_months == 1:
            return amount * 0.05
        
        # Для сроков более 1 месяца используем сложный процент (5% ежемесячно)
        total_amount = amount
        monthly_rate = 0.05  # 5% в месяц
        
        for _ in range(term_months):
            total_amount += total_amount * monthly_rate
        
        return total_amount - amount
        
    return 0

def sanitize_input(text):
    """
    Санитизирует пользовательский ввод для предотвращения XSS атак
    
    Args:
        text (str): Текст для санитизации
        
    Returns:
        str: Безопасный текст
    """
    if not text:
        return ""
        
    # Экранируем HTML-теги и специальные символы
    escaped_text = html.escape(str(text))
    
    return escaped_text

def sanitize_username(username):
    """
    Санитизирует имя пользователя для предотвращения XSS атак и обеспечения валидного формата
    
    Args:
        username (str): Имя пользователя для санитизации
        
    Returns:
        str: Безопасное имя пользователя
    """
    if not username:
        return ""
        
    # Удаляем все символы, кроме букв, цифр, подчеркиваний и дефисов
    sanitized = re.sub(r'[^\w\-]', '', str(username))
    
    return sanitized

def generate_referral_code(length=8):
    """
    Генерирует уникальный реферальный код.
    
    Args:
        length (int): Длина кода, по умолчанию 8 символов
        
    Returns:
        str: Уникальный реферальный код
    """
    # Используем только буквы верхнего регистра и цифры для лучшей читаемости
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def get_referral_url(referral_code, request_base_url=''):
    """
    Создает полную реферальную ссылку на основе кода.
    
    Args:
        referral_code (str): Реферальный код пользователя
        request_base_url (str): Базовый URL сайта (если указан)
        
    Returns:
        str: Полная реферальная ссылка
    """
    if not referral_code:
        return ''
    
    # Если указан базовый URL, используем его, иначе используем относительный путь
    base = request_base_url.rstrip('/') if request_base_url else ''
    return f"{base}/ref?code={referral_code}"


def calculate_referral_earnings(amount, expected_profit):
    """
    Рассчитывает реферальное вознаграждение (20% от прибыли).
    
    Args:
        amount (float): Сумма инвестиции
        expected_profit (float): Ожидаемая прибыль от инвестиции
        
    Returns:
        float: Сумма реферального вознаграждения
    """
    if not expected_profit or expected_profit <= 0:
        return 0.0
    
    return expected_profit * 0.2  # 20% от прибыли


def safe_format(value):
    """
    Безопасное форматирование для вывода в шаблонах
    Возвращает Markup объект, который Jinja2 не будет экранировать повторно
    
    Args:
        value (str): Значение для форматирования
        
    Returns:
        Markup: Безопасный для вывода объект
    """
    if not value:
        return Markup("")
        
    # Сначала экранируем текст, затем оборачиваем в Markup для предотвращения повторного экранирования
    escaped = html.escape(str(value))
    
    # Преобразуем URL в кликабельные ссылки (только если это http/https)
    escaped = re.sub(
        r'(https?://[^\s<>"]+)', 
        r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>', 
        escaped
    )
    
    # Преобразуем переносы строк в <br>
    escaped = escaped.replace('\n', '<br>')
    
    return Markup(escaped)


def check_payment_statuses(user):
    """
    Проверяет статусы открытых платежей пользователя и обновляет их
    
    Функция была заменена на проверку статусов TON-транзакций, 
    которая реализована в ton_deposit_routes.py через TonClient.
    
    Args:
        user (User): пользователь
        
    Returns:
        int: количество обновленных транзакций (всегда 0, т.к. функция устарела)
    """
    import logging
    
    # Функционал NOWPayments удален, возвращаем 0
    logging.debug(f"check_payment_statuses вызвана для пользователя {user.id if user else 'None'}, "
                 f"но функция устарела и не используется")
    return 0


def check_admin_test_transactions(user):
    """
    Проверяет и автоматически завершает 5-минутные тестовые транзакции для администраторов
    
    Args:
        user (User): пользователь-администратор
        
    Returns:
        int: количество обновленных транзакций
    """
    if not user or not user.is_admin:
        return 0
        
    from datetime import datetime
    from models import Transaction
    from app import db
    import logging
    
    try:
        # Ищем только 5-минутные тестовые транзакции (term_months < 0.1) со статусом payment_awaiting
        test_transactions = Transaction.query.filter(
            Transaction.user_id == user.id,
            Transaction.status == 'payment_awaiting',
            Transaction.term_months < 0.1
        ).all()
        
        now = datetime.utcnow()
        updated_count = 0
        
        for tx in test_transactions:
            # Проверяем, есть ли все нужные данные
            if not (tx.deposit_end_date and tx.deposit_start_date and tx.term_months is not None):
                continue
                
            # Все отобранные транзакции имеют term_months < 0.1, можно сразу переходить к проверке времени
            # Вычисляем время между началом и концом депозита в минутах
            time_diff_minutes = (tx.deposit_end_date - tx.deposit_start_date).total_seconds() / 60
            
            # Если это 5-минутная транзакция и она уже должна была завершиться
            if 4.5 <= time_diff_minutes <= 5.5 and now >= tx.deposit_end_date:
                logging.info(f"Auto-completing test 5-minute transaction {tx.transaction_id} for admin user {user.id}")
                
                # Автоматически завершаем тестовую транзакцию
                tx.status = 'completed'
                tx.payment_status = 'confirmed'
                tx.payment_completed_at = now
                updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            logging.info(f"Auto-completed {updated_count} test transactions for admin user {user.id}")
            
        return updated_count
            
    except Exception as e:
        logging.error(f"Error auto-completing test transactions: {str(e)}")
        return 0


def get_client_ip():
    """
    Получает реальный IP-адрес клиента с учетом прокси-серверов и заголовков X-Forwarded-For
    Использует ProxyFix middleware и Flask request.access_route для Replit
    
    Returns:
        str: IP-адрес клиента
    """
    from flask import request
    import logging
    
    # Используем access_route - список IP-адресов от конечного пользователя до сервера
    # Это правильный способ получения IP-адреса при использовании ProxyFix
    if request.access_route and len(request.access_route) > 0:
        ip = request.access_route[0]
        logging.debug(f"IP from access_route: {ip}")
        return ip
    
    # Проверяем заголовки, которые могут содержать реальный IP
    # X-Forwarded-For: используется большинством прокси-серверов
    if request.headers.get('X-Forwarded-For'):
        # Первый IP в цепочке обычно является реальным IP клиента
        ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        logging.debug(f"IP from X-Forwarded-For: {ip}")
        return ip
    
    # CF-Connecting-IP: используется Cloudflare
    if request.headers.get('CF-Connecting-IP'):
        ip = request.headers.get('CF-Connecting-IP')
        logging.debug(f"IP from CF-Connecting-IP: {ip}")
        return ip
    
    # True-Client-IP: альтернативный заголовок
    if request.headers.get('True-Client-IP'):
        ip = request.headers.get('True-Client-IP')
        logging.debug(f"IP from True-Client-IP: {ip}")
        return ip
    
    # X-Real-IP: используется NGINX
    if request.headers.get('X-Real-IP'):
        ip = request.headers.get('X-Real-IP')
        logging.debug(f"IP from X-Real-IP: {ip}")
        return ip
    
    # Если ни один из заголовков не найден, возвращаем стандартный remote_addr
    # Но это часто дает IP прокси-сервера, а не клиента
    logging.debug(f"Fallback to remote_addr: {request.remote_addr}")
    return request.remote_addr

def log_user_ip(user_id, ip_address, activity_type, user_agent=None):
    """
    Логирует IP-адрес пользователя при различных действиях на сайте
    
    Args:
        user_id (int): ID пользователя
        ip_address (str): IP-адрес пользователя
        activity_type (str): Тип активности (login, register, deposit, withdraw, etc.)
        user_agent (str, optional): User-Agent браузера пользователя
        
    Returns:
        bool: True если запись успешно создана, False в случае ошибки
    """
    try:
        from models import UserIPLog
        from app import db
        import logging
        
        if not user_id or not ip_address or not activity_type:
            logging.warning(f"Invalid parameters for log_user_ip: user_id={user_id}, ip={ip_address}, type={activity_type}")
            return False
        
        # Создаем новую запись в логе
        ip_log = UserIPLog(
            user_id=user_id,
            ip_address=ip_address,
            activity_type=activity_type,
            user_agent=user_agent
        )
        
        db.session.add(ip_log)
        db.session.commit()
        
        logging.debug(f"IP log created: User {user_id}, IP {ip_address}, Type {activity_type}")
        return True
        
    except Exception as e:
        logging.error(f"Error logging user IP: {str(e)}")
        # Если произошла ошибка, откатываем сессию
        try:
            from app import db
            db.session.rollback()
        except:
            pass
        return False
