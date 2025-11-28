"""
Скрипт для проверки текущего состояния базы данных.
Показывает статистику по депозитам и выводам.
"""
from app import app, db
from models import TonDeposit, WithdrawalRequest

with app.app_context():
    # Количество TON депозитов
    ton_deposits_count = TonDeposit.query.count()
    # Количество запросов на вывод
    withdrawal_count = WithdrawalRequest.query.count()
    
    print(f"\n===== Статистика базы данных =====")
    print(f"TON депозитов: {ton_deposits_count}")
    print(f"Запросов на вывод: {withdrawal_count}")
    
    # Последние 5 TON депозитов
    if ton_deposits_count > 0:
        print("\n----- Последние 5 TON депозитов -----")
        last_deposits = TonDeposit.query.order_by(TonDeposit.id.desc()).limit(5).all()
        for deposit in last_deposits:
            print(f"ID: {deposit.id}, Сумма: {deposit.amount}, Статус: {deposit.status}")
    else:
        print("\nНет TON депозитов в базе данных.")
    
    # Последние 5 запросов на вывод
    if withdrawal_count > 0:
        print("\n----- Последние 5 запросов на вывод -----")
        last_withdrawals = WithdrawalRequest.query.order_by(WithdrawalRequest.id.desc()).limit(5).all()
        for withdrawal in last_withdrawals:
            print(f"ID: {withdrawal.id}, Сумма: {withdrawal.amount}, Статус: {withdrawal.status}")
    else:
        print("\nНет запросов на вывод в базе данных.")