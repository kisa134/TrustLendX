"""
Модуль для отправки уведомлений в Telegram
Использует прямые HTTP-запросы к Telegram Bot API для максимальной совместимости

Основные функции:
- Отправка тестового уведомления
- Отправка уведомления о новом TON депозите
- Отправка уведомления об изменении статуса TON депозита

Примечание: Для отладки добавлена опция USE_MOCK_MODE, которая позволяет
имитировать отправку уведомлений без реального подключения к Telegram API.
"""
import os
import logging
import requests
import traceback
import json
import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Получаем токен и chat_id из переменных окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
TELEGRAM_API_URL = "https://api.telegram.org/bot"

# Флаг для имитации отправки уведомлений (без реального подключения к Telegram API)
USE_MOCK_MODE = False  # Установлено в False для реальной отправки уведомлений

# Путь к файлу для сохранения уведомлений в режиме имитации
MOCK_NOTIFICATIONS_FILE = "telegram_notifications.json"

def save_mock_notification(message: str) -> bool:
    """
    Сохраняет имитационное уведомление в файл вместо отправки в Telegram
    
    Args:
        message: Текст сообщения
        
    Returns:
        bool: True если сообщение успешно сохранено, False в противном случае
    """
    try:
        # Подготовка данных для сохранения
        notification_data = {
            "timestamp": str(datetime.datetime.now()),
            "message": message
        }
        
        # Загружаем существующие уведомления
        existing_data = []
        try:
            if os.path.exists(MOCK_NOTIFICATIONS_FILE):
                with open(MOCK_NOTIFICATIONS_FILE, 'r') as file:
                    existing_data = json.load(file)
        except Exception as e:
            logger.warning(f"Не удалось загрузить существующие уведомления: {str(e)}")
            
        # Добавляем новое уведомление
        existing_data.append(notification_data)
        
        # Сохраняем обновленные данные
        with open(MOCK_NOTIFICATIONS_FILE, 'w') as file:
            json.dump(existing_data, file, indent=2)
            
        logger.info(f"Имитационное уведомление сохранено в {MOCK_NOTIFICATIONS_FILE}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении имитационного уведомления: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def send_notification(message: str) -> bool:
    """
    Отправляет уведомление в Telegram используя прямые HTTP-запросы
    
    Args:
        message: Текст сообщения
        
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    # Дополнительное логирование для отладки
    print(f"DEBUG: Отправка уведомления в Telegram: {message[:50]}...")
    logger.info(f"DEBUG: Отправка уведомления в Telegram: {message[:50]}...")
    
    # Используем режим имитации, если включен
    if USE_MOCK_MODE:
        logger.info("Используется режим имитации для отправки уведомлений")
        print("DEBUG: Используется режим имитации для отправки уведомлений")
        return save_mock_notification(message)
    
    # Проверяем наличие необходимых переменных окружения
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        error_msg = "Не указаны переменные окружения TELEGRAM_TOKEN или TELEGRAM_CHAT_ID"
        logger.error(error_msg)
        print(f"DEBUG ERROR: {error_msg}")
        return False
        
    try:
        # Отладочная информация о токенах (маскированная)
        token_debug = TELEGRAM_TOKEN[:4] + "..." + TELEGRAM_TOKEN[-4:] if TELEGRAM_TOKEN else "None"
        chat_id_debug = TELEGRAM_CHAT_ID[:2] + "..." + TELEGRAM_CHAT_ID[-2:] if TELEGRAM_CHAT_ID else "None"
        print(f"DEBUG: Использую токен: {token_debug}, chat_id: {chat_id_debug}")
        logger.info(f"DEBUG: Использую токен: {token_debug}, chat_id: {chat_id_debug}")
        
        url = f"{TELEGRAM_API_URL}{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        # Отладка запроса
        print(f"DEBUG: Отправка POST запроса на URL: {url}")
        logger.info(f"DEBUG: Отправка POST запроса на URL: {url}")
        
        # Устанавливаем таймаут для избежания зависаний
        response = requests.post(url, data=data, timeout=5)
        
        # Логируем ответ для отладки
        response_debug = f"Ответ от Telegram API: {response.status_code}, тело: {response.text[:100]}..."
        logger.info(response_debug)
        print(f"DEBUG: {response_debug}")
        
        # Проверяем статус ответа
        response.raise_for_status()
        
        success_msg = f"Уведомление успешно отправлено в Telegram, статус: {response.status_code}"
        logger.info(success_msg)
        print(f"DEBUG SUCCESS: {success_msg}")
        return True
    except requests.RequestException as e:
        error_msg = f"Ошибка HTTP при отправке уведомления в Telegram: {str(e)}"
        logger.error(error_msg)
        print(f"DEBUG ERROR: {error_msg}")
        return False
    except Exception as e:
        error_msg = f"Необработанная ошибка при отправке уведомления в Telegram: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        print(f"DEBUG ERROR: {error_msg}")
        print(f"DEBUG TRACEBACK: {traceback.format_exc()}")
        return False

def test_notification() -> bool:
    """
    Отправляет тестовое уведомление в Telegram
    
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    test_message = "<b>Тестовое уведомление</b>\n\n"
    test_message += "Это тестовое уведомление от системы TrustLendX."
    
    return send_notification(test_message)

def notify_new_ton_deposit(user_id: int, amount: float, memo: str, transaction_id: str) -> bool:
    """
    Отправляет уведомление о новом TON депозите в Telegram
    
    Args:
        user_id: ID пользователя
        amount: Сумма депозита
        memo: MEMO для платежа
        transaction_id: ID транзакции
        
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    notification_message = "<b>🔔 Новый TON депозит</b>\n\n"
    notification_message += f"<b>Пользователь:</b> ID {user_id}\n"
    notification_message += f"<b>Сумма:</b> {amount} USDT\n"
    notification_message += f"<b>MEMO:</b> <code>{memo}</code>\n"
    notification_message += f"<b>ID транзакции:</b> {transaction_id}\n"
    notification_message += f"<b>Статус:</b> Ожидание оплаты\n\n"
    notification_message += "Пользователь нажал кнопку 'Я оплатил'."
    
    return send_notification(notification_message)

def notify_ton_deposit_status_change(user_id: int, amount: float, memo: str, 
                                   transaction_id: str, new_status: str) -> bool:
    """
    Отправляет уведомление об изменении статуса TON депозита в Telegram
    
    Args:
        user_id: ID пользователя
        amount: Сумма депозита
        memo: MEMO для платежа
        transaction_id: ID транзакции
        new_status: Новый статус транзакции
        
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    # Преобразуем статус для отображения
    status_map = {
        "pending": "⏳ Ожидание оплаты",
        "payment_awaiting": "⏳ Ожидание оплаты",
        "completed": "✅ Завершена",
        "failed": "❌ Ошибка"
    }
    
    status_display = status_map.get(new_status, new_status)
    
    notification_message = "<b>🔄 Изменение статуса TON депозита</b>\n\n"
    notification_message += f"<b>Пользователь:</b> ID {user_id}\n"
    notification_message += f"<b>Сумма:</b> {amount} USDT\n"
    notification_message += f"<b>MEMO:</b> <code>{memo}</code>\n"
    notification_message += f"<b>ID транзакции:</b> {transaction_id}\n"
    notification_message += f"<b>Новый статус:</b> {status_display}"
    
    return send_notification(notification_message)

def notify_withdrawal_request(user_id: int, username: str, amount: float, wallet_address: str, 
                             request_id: str) -> bool:
    """
    Отправляет уведомление о новом запросе на вывод средств в Telegram
    
    Args:
        user_id: ID пользователя
        username: Имя пользователя
        amount: Сумма вывода
        wallet_address: Адрес кошелька для вывода
        request_id: ID запроса на вывод
        
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    # Безопасная обработка параметров
    safe_username = username or "Неизвестный пользователь"
    safe_wallet = wallet_address or "Не указан"
    safe_amount = float(amount) if amount is not None else 0.0
    
    notification_message = "<b>💸 Новый запрос на вывод средств</b>\n\n"
    notification_message += f"<b>Пользователь:</b> {safe_username} (ID: {user_id})\n"
    notification_message += f"<b>Сумма:</b> {safe_amount} USDT\n"
    notification_message += f"<b>Адрес кошелька:</b> <code>{safe_wallet}</code>\n"
    notification_message += f"<b>ID запроса:</b> {request_id}\n"
    notification_message += f"<b>Статус:</b> Ожидает подтверждения"
    
    return send_notification(notification_message)

def notify_withdrawal_status_change(user_id: int, username: str, amount: float, wallet_address: str, 
                                   request_id: str, new_status: str, tx_hash: Optional[str] = None) -> bool:
    """
    Отправляет уведомление об изменении статуса запроса на вывод средств в Telegram
    
    Args:
        user_id: ID пользователя
        username: Имя пользователя
        amount: Сумма вывода
        wallet_address: Адрес кошелька для вывода
        request_id: ID запроса на вывод
        new_status: Новый статус запроса
        tx_hash: Хеш транзакции (опционально)
        
    Returns:
        bool: True если сообщение успешно отправлено, False в противном случае
    """
    # Безопасная обработка параметров
    safe_username = username or "Неизвестный пользователь"
    safe_wallet = wallet_address or "Не указан"
    safe_amount = float(amount) if amount is not None else 0.0
    safe_status = new_status or "unknown"
    safe_tx_hash = tx_hash or "Не указан"
    
    status_map = {
        "pending": "Ожидает подтверждения",
        "approved": "Подтвержден администратором",
        "completed": "Завершен",
        "rejected": "Отклонен"
    }
    
    status_text = status_map.get(safe_status, safe_status)
    
    notification_message = "<b>🔄 Изменение статуса запроса на вывод</b>\n\n"
    notification_message += f"<b>Пользователь:</b> {safe_username} (ID: {user_id})\n"
    notification_message += f"<b>Сумма:</b> {safe_amount} USDT\n"
    notification_message += f"<b>Адрес кошелька:</b> <code>{safe_wallet}</code>\n"
    notification_message += f"<b>ID запроса:</b> {request_id}\n"
    notification_message += f"<b>Статус:</b> {status_text}"
    
    if safe_tx_hash != "Не указан" and safe_status == "completed":
        notification_message += f"\n<b>Хеш транзакции:</b> <code>{safe_tx_hash}</code>"
    
    return send_notification(notification_message)