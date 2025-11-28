"""
Скрипт для принудительного выхода администратора из системы
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Получаем DATABASE_URL из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("Ошибка: Отсутствует переменная окружения DATABASE_URL")
    sys.exit(1)

# Создаем подключение к базе данных
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Удаляем все сессии для администратора
    sql = text("DELETE FROM flask_session WHERE user_id = (SELECT id FROM \"user\" WHERE username = 'system_admin')")
    session.execute(sql)
    session.commit()
    print("Все сессии администратора успешно удалены")
    
except Exception as e:
    session.rollback()
    print(f"Ошибка при удалении сессий: {str(e)}")
finally:
    session.close()
