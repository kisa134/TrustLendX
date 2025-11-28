import os
import logging
from logging.handlers import RotatingFileHandler
import time

class RequestFormatter(logging.Formatter):
    """Форматтер для логов, добавляющий информацию о запросе"""
    
    def format(self, record):
        """Форматирует запись лога, добавляя информацию о запросе."""
        # Добавляем временную метку
        record.timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Добавляем информацию о запросе, если она есть
        if hasattr(record, 'request'):
            record.remote_addr = record.request.remote_addr
            record.method = record.request.method
            record.path = record.request.path
        else:
            record.remote_addr = '-'
            record.method = '-'
            record.path = '-'
            
        return super().format(record)

def setup_logging(app):
    """
    Настраивает логирование для приложения Flask
    
    Args:
        app: Экземпляр приложения Flask
    """
    # Создаем директорию для логов, если она не существует
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Настройка форматирования
    formatter = RequestFormatter(
        '%(timestamp)s - %(levelname)s - %(remote_addr)s - %(method)s %(path)s - %(message)s'
    )
    
    # Настройка обработчика файла для всех логов
    file_handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=10485760,  # 10 МБ
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Настройка обработчика файла для ошибок
    error_file_handler = RotatingFileHandler(
        'logs/error.log', 
        maxBytes=10485760,  # 10 МБ
        backupCount=10
    )
    error_file_handler.setFormatter(formatter)
    error_file_handler.setLevel(logging.ERROR)
    
    # Настройка консольного вывода
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Настройка логгера приложения
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_file_handler)
    app.logger.addHandler(console_handler)
    
    # Замена стандартного регистратора Werkzeug
    werkzeug_logger = logging.getLogger('werkzeug')
    for handler in werkzeug_logger.handlers:
        werkzeug_logger.removeHandler(handler)
    werkzeug_logger.addHandler(file_handler)
    werkzeug_logger.addHandler(console_handler)
    
    # Логирование запросов и ответов
    @app.before_request
    def log_request():
        """Логирует информацию о входящем запросе"""
        from flask import request
        app.logger.info(f"Запрос: {request.method} {request.path}", extra={'request': request})
    
    @app.after_request
    def log_response(response):
        """Логирует информацию об исходящем ответе"""
        from flask import request
        app.logger.info(f"Ответ: {response.status_code}", extra={'request': request})
        return response
    
    # Логирование ошибок приложения
    @app.errorhandler(Exception)
    def log_exception(e):
        """Логирует необработанные исключения"""
        from flask import request
        import traceback
        app.logger.error(f"Необработанное исключение: {str(e)}\n{traceback.format_exc()}", 
                        extra={'request': request})
        # Передаем исключение дальше, для обработки другими обработчиками
        raise e
        
    app.logger.info("Логирование настроено")
    
    return app.logger