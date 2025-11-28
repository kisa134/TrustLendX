import os
import psycopg2
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем параметры подключения к базе данных
db_params = {
    'dbname': os.getenv('PGDATABASE'),
    'user': os.getenv('PGUSER'),
    'password': os.getenv('PGPASSWORD'),
    'host': os.getenv('PGHOST'),
    'port': os.getenv('PGPORT')
}

try:
    # Устанавливаем соединение с PostgreSQL
    conn = psycopg2.connect(**db_params)
    
    # Создаем курсор для выполнения SQL-запросов
    cursor = conn.cursor()
    
    # SQL-запросы для добавления новых столбцов
    sql_queries = [
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR(100)',
        'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email_verification_token_expires TIMESTAMP'
    ]
    
    # Выполняем запросы
    for query in sql_queries:
        cursor.execute(query)
        print(f"Выполнен запрос: {query}")
    
    # Фиксируем изменения
    conn.commit()
    print("Миграция успешно выполнена!")
    
    # Закрываем курсор и соединение
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Ошибка при выполнении миграции: {e}")