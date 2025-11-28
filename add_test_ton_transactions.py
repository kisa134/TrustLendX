#!/usr/bin/env python3
"""
Скрипт для добавления тестовых TON-транзакций в базу данных.
Используется только в целях разработки и тестирования.
"""

import os
import random
import string
from datetime import datetime, timedelta
from app import app, db
from models import TonDeposit, User
import sys

def generate_memo(length=12):
    """Генерирует случайную строку MEMO"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def main():
    with app.app_context():
        print("Checking existing users...")
        
        # Убедимся, что у нас есть хотя бы один пользователь
        user_count = User.query.count()
        if user_count == 0:
            print("No users found. Creating a test user...")
            from werkzeug.security import generate_password_hash
            test_user = User(
                username="test_user",
                email="test@example.com",
                password_hash=generate_password_hash("password"),
                is_admin=True
            )
            db.session.add(test_user)
            db.session.commit()
            user_ids = [test_user.id]
        else:
            print(f"Found {user_count} users")
            users = User.query.all()
            user_ids = [user.id for user in users]
        
        # Проверяем количество существующих TON-транзакций
        existing_ton_count = TonDeposit.query.count()
        print(f"Found {existing_ton_count} existing TON transactions")
        
        # Если транзакций меньше 5, добавляем новые
        num_to_add = max(0, 5 - existing_ton_count)
        if num_to_add > 0:
            print(f"Adding {num_to_add} test TON transactions...")
            
            statuses = ['pending', 'payment_awaiting', 'completed', 'failed']
            
            for i in range(num_to_add):
                # Получаем случайного пользователя
                user_id = random.choice(user_ids)
                
                # Генерируем случайные данные
                amount = round(random.uniform(10, 2000), 2)
                status = random.choice(statuses)
                created_at = datetime.utcnow() - timedelta(days=random.randint(0, 30))
                memo = generate_memo()
                
                # Создаем запись в базе данных
                ton_deposit = TonDeposit(
                    user_id=user_id,
                    amount=amount,
                    memo=memo,
                    status=status,
                    created_at=created_at
                )
                
                # Если статус "completed", добавляем дату подтверждения
                if status == 'completed':
                    ton_deposit.payment_confirmed_at = created_at + timedelta(hours=random.randint(1, 24))
                
                db.session.add(ton_deposit)
                
                print(f"Added transaction: {memo} - {amount} USDT - {status}")
            
            # Сохраняем изменения
            db.session.commit()
            print("Done!")
        else:
            print("No new transactions needed to be added.")

if __name__ == "__main__":
    main()