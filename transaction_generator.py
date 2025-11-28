"""
Генератор фейковых транзакций для TrustLendX
Используется для создания и обновления демонстрационных транзакций на главной странице
"""

import random
import threading
import time
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Инициализируем логгер
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Загружаем список имен из файла
def load_names_from_file():
    """Загружает список имен из файла"""
    names_path = os.path.join('static', 'data', 'names.txt')
    try:
        if os.path.exists(names_path):
            with open(names_path, 'r') as file:
                # Читаем имена, убираем пустые строки и пробелы
                names = [line.strip() for line in file.readlines() if line.strip()]
                if names:
                    return names
    except Exception as e:
        logger.error(f"Ошибка при загрузке имен из файла: {e}")
    
    # Если файл не найден или пуст, используем резервный список
    return [
        "Александр", "Алексей", "Анатолий", "Андрей", "Антон", "Иван", "Игорь", "Максим", "Артём", "Сергей",
        "Владимир", "Дмитрий", "Елена", "Анна", "Ольга", "Мария", "Татьяна", "Наталья", "Светлана", "Екатерина"
    ]

# Загружаем имена из файла
USERS = load_names_from_file()

# Больше не используем кэш транзакций, все данные хранятся в базе
# Оставляем пустой список для обратной совместимости
transaction_cache: List[Dict[str, Any]] = []

# Блокировка для потокобезопасного доступа к кэшу
lock = threading.Lock()

# Флаг для отслеживания работы генератора
generator_running = False

def format_number(number: int) -> str:
    """Форматирование числа с разделителями тысяч"""
    return "{:,}".format(number).replace(",", " ")

def generate_amount() -> int:
    """Генерация суммы по правилам вероятности"""
    random_value = random.random() * 100
    if random_value < 40:  # 40%
        return random.randint(100, 1000)  # 100-1000
    elif random_value < 70:  # 30%
        return random.randint(1000, 10000)  # 1000-10000
    elif random_value < 85:  # 15%
        return random.randint(10000, 50000)  # 10000-50000
    elif random_value < 95:  # 10%
        return random.randint(50000, 70000)  # 50000-70000
    elif random_value < 98:  # 3%
        return random.randint(70000, 90000)  # 70000-90000
    else:  # 2%
        return random.randint(90000, 110000)  # 90000-110000

def generate_type() -> str:
    """Генерация типа (80% депозит, 20% вывод)"""
    return "Депозит" if random.random() < 0.8 else "Вывод"

def generate_status(tx_type: str) -> str:
    """Генерация статуса"""
    if tx_type == "Вывод":
        return "Завершено"  # Выводы всегда завершены
    # Для депозитов: 90% завершено, 10% отклонено
    return "Завершено" if random.random() < 0.9 else "Отклонено"

def get_random_interval() -> int:
    """Случайный интервал для создания транзакций (в секундах)"""
    # Используем интервал 4-37 минут (в секундах)
    return random.randint(4 * 60, 37 * 60)

def generate_transaction() -> Dict[str, Any]:
    """Генерация одной транзакции"""
    user = random.choice(USERS)
    tx_type = generate_type()
    status = generate_status(tx_type)
    amount = generate_amount()
    
    # Минимум 100 USDT
    amount = max(100, amount)
    # Максимум для вывода 110000 USDT
    if tx_type == "Вывод":
        amount = min(110000, amount)
        
    # Получаем текущее время и добавляем 3 часа для Московского времени (UTC+3)
    now = datetime.now()
    moscow_time = now + timedelta(hours=3)
    date_str = moscow_time.strftime("%d.%m.%Y %H:%M")
    tx_id = f"TX{random.randint(10000, 99999)}"
    
    return {
        "id": tx_id,
        "user": user,
        "masked_user": f"{user[0]}***{user[-1]}",
        "amount": amount,
        "amount_formatted": f"{format_number(amount)} USDT",
        "type": tx_type,
        "status": status,
        "date": date_str,
        "timestamp": now.timestamp()
    }

def add_transaction() -> None:
    """Добавление транзакции в базу данных"""
    from app import db
    from models import DemoTransaction, Transaction
    
    # Создаем новую транзакцию
    transaction_data = generate_transaction()
    
    with lock:
        # Создаем новую запись в БД
        demo_tx = DemoTransaction(
            transaction_id=transaction_data['id'],
            masked_user=transaction_data['masked_user'],
            amount=transaction_data['amount'],
            amount_formatted=transaction_data['amount_formatted'],
            type=transaction_data['type'],
            status=transaction_data['status'],
            date=transaction_data['date'],
            timestamp=transaction_data['timestamp']
        )
        
        # Добавляем в базу данных
        db.session.add(demo_tx)
        
        # Получаем общее количество транзакций
        transactions_count = DemoTransaction.query.count()
        
        # Если транзакций больше 20, удаляем самые старые, чтобы база не росла бесконечно
        if transactions_count > 20:
            # Находим самые старые транзакции для удаления
            old_transactions = DemoTransaction.query.order_by(
                DemoTransaction.timestamp.asc()
            ).limit(transactions_count - 20).all()
            
            # Удаляем их
            for old_tx in old_transactions:
                db.session.delete(old_tx)
        
        # Вызываем функцию архивации старых транзакций
        archive_old_transactions()
        
        # Сохраняем изменения
        db.session.commit()
    
    # Обновляем кэш API
    global cached_api_response, last_update_time
    cached_api_response = []  # Сбрасываем кэш, чтобы он обновился при следующем запросе
    last_update_time = 0
    
    # Логируем для отладки
    logger.debug(f"Added new transaction: {transaction_data['id']} - {transaction_data['amount_formatted']}")

def transaction_generator() -> None:
    """Фоновый генератор транзакций"""
    global generator_running
    
    # Импортируем в функции, чтобы избежать циклических импортов
    from app import app
    
    logger.info("Starting transaction generator")
    generator_running = True
    
    try:
        while generator_running:
            # Используем контекст приложения для доступа к базе данных
            with app.app_context():
                # Добавляем новую транзакцию
                add_transaction()
                
                # Ждем случайный интервал перед следующей
                interval = get_random_interval()
                logger.debug(f"Next transaction will be generated in {interval} seconds")
            
            # Используем короткие интервалы для возможности быстрой остановки
            for _ in range(interval):
                if not generator_running:
                    break
                time.sleep(1)
    except Exception as e:
        logger.error(f"Error in transaction generator: {e}")
        generator_running = False

def initialize_transactions() -> None:
    """Инициализируем начальные транзакции в базе данных"""
    from app import db
    from models import DemoTransaction
    
    logger.info("Initializing transaction database")
    
    # Если в базе уже есть транзакции, не генерируем заново
    if DemoTransaction.query.count() > 0:
        logger.info(f"Found {DemoTransaction.query.count()} existing transactions in database")
        return
    
    # Генерируем 5 начальных транзакций, если база пуста
    logger.info("Generating initial transactions")
    for _ in range(5):
        transaction_data = generate_transaction()
        
        demo_tx = DemoTransaction(
            transaction_id=transaction_data['id'],
            masked_user=transaction_data['masked_user'],
            amount=transaction_data['amount'],
            amount_formatted=transaction_data['amount_formatted'],
            type=transaction_data['type'],
            status=transaction_data['status'],
            date=transaction_data['date'],
            timestamp=transaction_data['timestamp']
        )
        
        db.session.add(demo_tx)
    
    # Сохраняем изменения
    db.session.commit()
    logger.info(f"Added {DemoTransaction.query.count()} initial transactions to database")

def start_generator() -> None:
    """Запуск генератора транзакций"""
    global generator_running
    
    # Запускаем генератор, если он еще не запущен
    if not generator_running:
        generator_thread = threading.Thread(target=transaction_generator, daemon=True)
        generator_thread.start()
        logger.info("Transaction generator started")

def stop_generator() -> None:
    """Остановка генератора транзакций"""
    global generator_running
    generator_running = False
    logger.info("Transaction generator stopped")

# Время последнего обновления транзакций
last_update_time = 0
# Кэш ответа API
cached_api_response = []

def archive_old_transactions() -> bool:
    """
    Эта функция раньше архивировала старые транзакции, 
    теперь оставлена для обратной совместимости, но ничего не архивирует,
    так как все транзакции должны отображаться в общем потоке
    """
    # Возвращаем False, чтобы показать что никакие изменения не выполнялись
    return False

def get_transactions() -> List[Dict[str, Any]]:
    """Получение списка транзакций из базы данных, включая реальные транзакции пользователей"""
    from models import DemoTransaction, Transaction, User, TonDeposit
    from app import db
    global last_update_time, cached_api_response
    current_time = time.time()
    
    # Если с последнего обновления прошло более 1 секунды, обновляем кэш (для более быстрого обновления реальных транзакций)
    if current_time - last_update_time > 1:
        # Архивируем старые транзакции при каждом запросе к API
        archive_old_transactions()
        
        # Получаем транзакции из базы данных
        transactions = []
        
        # Получаем фейковые демо-транзакции из базы данных
        demo_transactions = DemoTransaction.query.order_by(DemoTransaction.timestamp.desc()).all()
        
        # Получаем все реальные транзакции со статусом 'completed' или 'archived'
        # Это позволит им корректно перемешиваться в потоке с демо-транзакциями
        real_transactions = Transaction.query.filter(
            (Transaction.status == 'completed') | (Transaction.status == 'archived')
        ).order_by(Transaction.created_at.desc()).all()  # Показываем все реальные транзакции
        
        # Получаем все TON-транзакции со статусом 'completed'
        ton_transactions = TonDeposit.query.filter_by(status='completed').order_by(
            TonDeposit.payment_confirmed_at.desc()
        ).all()
        
        # Создаем список всех транзакций (демо + реальные + ton) для последующего преобразования
        all_transactions = []
        
        # Добавляем демо-транзакции в общий список с меткой
        for tx in demo_transactions:
            all_transactions.append({
                'type': 'demo',
                'tx': tx,
                'timestamp': tx.timestamp
            })
        
        # Добавляем реальные транзакции в общий список с меткой
        for tx in real_transactions:
            all_transactions.append({
                'type': 'real',
                'tx': tx,
                'timestamp': tx.created_at.timestamp()
            })
            
        # Добавляем TON-транзакции в общий список с меткой
        for tx in ton_transactions:
            if tx.payment_confirmed_at:  # Проверяем, что у транзакции есть дата подтверждения
                all_transactions.append({
                    'type': 'ton',
                    'tx': tx,
                    'timestamp': tx.payment_confirmed_at.timestamp()
                })
        
        # Сортируем все транзакции по timestamp (сначала новые)
        all_transactions.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Преобразуем отсортированные транзакции в формат API
        for item in all_transactions:
            if item['type'] == 'demo':
                # Преобразуем демо-транзакцию
                tx = item['tx']
                transactions.append({
                    'id': tx.transaction_id,
                    'masked_user': tx.masked_user,
                    'amount': tx.amount,
                    'amount_formatted': tx.amount_formatted,
                    'type': tx.type,
                    'status': tx.status,
                    'date': tx.date,
                    'timestamp': tx.timestamp,
                    'is_real': False  # Флаг, указывающий что это фейковая транзакция
                })
            elif item['type'] == 'real':
                try:
                    # Преобразуем реальную транзакцию
                    tx = item['tx']
                    
                    # Получаем пользователя для маскирования имени
                    user = User.query.get(tx.user_id)
                    if not user:
                        continue
                        
                    # Маскируем имя пользователя (первая и последняя буква)
                    username = user.username
                    masked_username = f"{username[0]}***{username[-1]}" if len(username) > 2 else f"{username[0]}***"
                    
                    # Определяем тип транзакции (для реальных транзакций всегда "Депозит")
                    tx_type = "Депозит"
                    
                    # Получаем московское время для отображения
                    moscow_time = tx.created_at + timedelta(hours=3)
                    date_str = moscow_time.strftime("%d.%m.%Y %H:%M")
                    
                    # Форматируем сумму
                    amount_formatted = f"{format_number(int(tx.amount))} USDT"
                    
                    # Преобразуем ID реальной транзакции в формат демо-транзакций (TX + 5 цифр)
                    # Берем первые 5 символов ID и преобразуем их в число, затем форматируем как TX + 5 цифр
                    short_id = ''.join(c for c in tx.transaction_id[:8] if c.isalnum())
                    numeric_id = int(hash(short_id) % 90000) + 10000  # Получаем число от 10000 до 99999
                    formatted_tx_id = f"TX{numeric_id}"
                    
                    transactions.append({
                        'id': formatted_tx_id,  # Используем единый формат ID для всех транзакций
                        'masked_user': masked_username,
                        'amount': tx.amount,
                        'amount_formatted': amount_formatted,
                        'type': tx_type,
                        'status': 'Завершено',  # для главной страницы всегда "Завершено"
                        'date': date_str,
                        'timestamp': item['timestamp'],
                        'is_real': True  # Флаг, указывающий что это реальная транзакция
                    })
                except Exception as e:
                    logger.error(f"Ошибка при обработке транзакции: {str(e)}")
            
            elif item['type'] == 'ton':
                try:
                    # Преобразуем TON-транзакцию
                    tx = item['tx']
                    
                    # Получаем пользователя для маскирования имени
                    user = User.query.get(tx.user_id)
                    if not user:
                        continue
                        
                    # Маскируем имя пользователя (первая и последняя буква)
                    username = user.username
                    masked_username = f"{username[0]}***{username[-1]}" if len(username) > 2 else f"{username[0]}***"
                    
                    # Определяем тип транзакции (для TON тоже используем обычный Депозит)
                    tx_type = "Депозит"
                    
                    # Получаем московское время для отображения
                    if tx.payment_confirmed_at:
                        moscow_time = tx.payment_confirmed_at + timedelta(hours=3)
                        date_str = moscow_time.strftime("%d.%m.%Y %H:%M")
                    else:
                        # Если дата подтверждения отсутствует (что странно для статуса completed), используем дату создания
                        moscow_time = tx.created_at + timedelta(hours=3)
                        date_str = moscow_time.strftime("%d.%m.%Y %H:%M")
                    
                    # Форматируем сумму
                    amount_formatted = f"{format_number(int(tx.amount))} USDT"
                    
                    # Генерируем ID транзакции
                    if tx.tx_hash:
                        # Если есть хеш транзакции, используем его
                        if tx.tx_hash.startswith('test') or tx.tx_hash.startswith('abc'):
                            # Тестовая транзакция
                            tx_id = f"TX{int(time.time()) % 100000:05d}"
                        else:
                            # Реальная TON транзакция (используем тот же формат TX#### как у обычных транзакций)
                            tx_id = f"TX{abs(hash(tx.tx_hash)) % 90000 + 10000}"
                    else:
                        # Иначе используем MEMO
                        tx_id = f"TX{abs(hash(tx.memo)) % 90000 + 10000}"
                    
                    transactions.append({
                        'id': tx_id,
                        'masked_user': masked_username,
                        'amount': tx.amount,
                        'amount_formatted': amount_formatted,
                        'type': tx_type,
                        'status': 'Завершено',
                        'date': date_str,
                        'timestamp': item['timestamp'],
                        'is_real': True  # Все депозиты должны выглядеть одинаково, не указываем сеть
                    })
                except Exception as e:
                    logger.error(f"Ошибка при обработке TON транзакции: {str(e)}")
        
        # Сортируем все транзакции по timestamp (сначала новые)
        transactions.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Ограничиваем список 7 последними транзакциями, чтобы они не занимали слишком много места на экране
        transactions = transactions[:7]
        
        # Обновляем кэш
        with lock:
            cached_api_response = transactions
            last_update_time = current_time
            
    return cached_api_response

def get_deposit_stats() -> Dict[str, Any]:
    """Получение статистики по депозитам и выводам из базы данных, включая реальные транзакции пользователей"""
    from models import DemoTransaction, Transaction, TonDeposit
    from app import db
    
    # Базовая сумма "предыдущих" инвестиций (375000 USDT)
    base_total_deposits = 375000
    total_deposits = base_total_deposits
    total_withdrawals = 0
    deposits_count = 25  # Базовый счетчик количества депозитов
    withdrawals_count = 0
    
    try:
        # Получаем данные демо-транзакций из базы данных
        demo_transactions = DemoTransaction.query.all()
        
        # Считаем статистику по демо-транзакциям
        for tx in demo_transactions:
            if tx.status != "Завершено":
                continue
                
            if tx.type == "Депозит":
                total_deposits += tx.amount
                deposits_count += 1
            elif tx.type == "Вывод":
                total_withdrawals += tx.amount
                withdrawals_count += 1
        
        # Получаем ВСЕ реальные транзакции пользователей - и завершенные, и архивированные
        # чтобы счетчик учитывал абсолютно все транзакции
        real_transactions = Transaction.query.filter(
            (Transaction.status == 'completed') | (Transaction.status == 'archived')
        ).all()
        
        # Добавляем статистику по реальным транзакциям
        for tx in real_transactions:
            # Для реальных транзакций все считаем как депозиты (в будущем можно добавить поле для различения типов)
            total_deposits += tx.amount
            deposits_count += 1
            
        # Получаем ВСЕ завершенные TON-транзакции
        ton_transactions = TonDeposit.query.filter_by(status='completed').all()
        
        # Добавляем статистику по TON-транзакциям
        for tx in ton_transactions:
            total_deposits += tx.amount
            deposits_count += 1
            
    except Exception as e:
        logger.error(f"Ошибка при расчете статистики депозитов: {str(e)}")
    
    return {
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "deposits_count": deposits_count,
        "withdrawals_count": withdrawals_count,
        "total_deposits_formatted": format_number(int(total_deposits)) + " USDT",
        "total_withdrawals_formatted": format_number(int(total_withdrawals)) + " USDT"
    }