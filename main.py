import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

from app import app

# Импортируем модули для поддержки всех функций
import logging
import error_handlers 
import logger
import performance
import transaction_generator
import aml_settings_route  # Импортируем маршрут настроек AML
# Импорт NOWPayments удален в связи с переходом полностью на TON
from ton_deposit_routes import ton_bp  # Импортируем Blueprint для TON
from withdrawal_routes import withdrawal_routes  # Импортируем Blueprint для запросов на вывод средств
# Blueprint для реферальной системы уже зарегистрирован в app.py

# Регистрируем blueprints
app.register_blueprint(ton_bp)
app.register_blueprint(withdrawal_routes)

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger(__name__).info("Запуск приложения TrustLendX")
    
    # Получаем порт из переменных окружения (для деплоя на облачных платформах)
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    # Запускаем приложение
    app.run(host="0.0.0.0", port=port, debug=debug)
