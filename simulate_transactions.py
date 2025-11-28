"""
Скрипт для симуляции реальных транзакций в системе.
Создаёт TON депозит и запрос на вывод для проверки отправки уведомлений.
"""
from app import app, db
from datetime import datetime
from models import TonDeposit, User, WithdrawalRequest
import random
import string
import json
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_random_string(length=10):
    """Генерирует случайную строку указанной длины"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def simulate_ton_deposit():
    """Создаёт TON депозит и вызывает события для отправки уведомления"""
    with app.app_context():
        # Проверяем наличие хотя бы одного пользователя в системе
        user = User.query.first()
        if not user:
            logger.error("Не найдено пользователей в системе для создания тестового депозита")
            return False
        
        # Создаём тестовый депозит с правильными параметрами
        # TonDeposit принимает только user_id, amount и term_days
        deposit = TonDeposit(
            user_id=user.id,
            amount=100.0,
            term_days=30
        )
        
        db.session.add(deposit)
        db.session.commit()
        
        # Получаем ID созданного депозита и memo
        deposit_id = deposit.id
        # Memo генерируется автоматически в конструкторе TonDeposit
        logger.info(f"Создан тестовый TON депозит с ID: {deposit_id}, MEMO: {deposit.memo}")
        
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from ton_deposit_routes import create_ton_deposit
            from telegram_notification import notify_new_ton_deposit
            
            # Вызываем функцию отправки уведомления напрямую
            result = notify_new_ton_deposit(
                user_id=user.id,
                amount=deposit.amount,
                memo=deposit.memo,
                transaction_id=str(deposit_id)
            )
            
            logger.info(f"Результат отправки уведомления о TON депозите: {result}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о TON депозите: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

def simulate_withdrawal_request():
    """Создаёт запрос на вывод средств и вызывает события для отправки уведомления"""
    with app.app_context():
        # Проверяем наличие хотя бы одного пользователя в системе
        user = User.query.first()
        if not user:
            logger.error("Не найдено пользователей в системе для создания тестового запроса на вывод")
            return False
        
        # Создаём тестовый запрос на вывод
        withdrawal = WithdrawalRequest(
            user_id=user.id,
            amount=150.0,
            wallet_address='EQWithdraw12345abcdefghijklmnopqrstuvwxyz',
            memo='Тестовый запрос на вывод',
            status='pending',
            request_date=datetime.utcnow()
        )
        
        db.session.add(withdrawal)
        db.session.commit()
        
        # Получаем ID созданного запроса
        withdrawal_id = withdrawal.id
        logger.info(f"Создан тестовый запрос на вывод с ID: {withdrawal_id}")
        
        try:
            # Импортируем здесь чтобы избежать циклических импортов
            from telegram_notification import notify_withdrawal_request
            
            # Вызываем функцию отправки уведомления напрямую
            result = notify_withdrawal_request(
                user_id=user.id,
                username=user.username,
                amount=withdrawal.amount,
                wallet_address=withdrawal.wallet_address,
                request_id=str(withdrawal_id)
            )
            
            logger.info(f"Результат отправки уведомления о запросе на вывод: {result}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о запросе на вывод: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

if __name__ == "__main__":
    print("=== Симуляция создания TON депозита и запроса на вывод ===")
    
    # Вызываем функции симуляции
    print("\n--- Создание TON депозита ---")
    deposit_result = simulate_ton_deposit()
    print(f"Результат: {'Успешно' if deposit_result else 'Ошибка'}")
    
    print("\n--- Создание запроса на вывод ---")
    withdrawal_result = simulate_withdrawal_request()
    print(f"Результат: {'Успешно' if withdrawal_result else 'Ошибка'}")
    
    print("\n=== Симуляция завершена ===")
    print("Проверьте, были ли отправлены уведомления в Telegram.")