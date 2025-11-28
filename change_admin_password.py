"""
Скрипт для изменения пароля администратора напрямую в базе данных.
Используется для исправления проблемы с невозможностью изменить пароль
через интерфейс.
"""
import os
import sys
from werkzeug.security import generate_password_hash
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

# Новый пароль
NEW_PASSWORD = "nr5u@m9#zbUf23wd"

try:
    # Обновляем пароль администратора напрямую
    # Используем более безопасный алгоритм хеширования с повышенным числом итераций
    password_hash = generate_password_hash(NEW_PASSWORD, method='pbkdf2:sha256:260000')
    
    # Выполняем обновление с использованием text() для SQL-запроса
    sql = text("UPDATE \"user\" SET password_hash = :password_hash WHERE username = 'system_admin'")
    result = session.execute(sql, {"password_hash": password_hash})
    
    # Подтверждаем изменения
    session.commit()
    
    print(f"Пароль успешно изменен для пользователя 'system_admin'")
    
except Exception as e:
    session.rollback()
    print(f"Ошибка при изменении пароля: {str(e)}")
finally:
    session.close()