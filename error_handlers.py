import logging
import traceback
from flask import render_template, request, jsonify
from werkzeug.exceptions import HTTPException

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def register_error_handlers(app):
    """
    Регистрирует обработчики ошибок для приложения Flask
    """
    
    @app.errorhandler(404)
    def page_not_found(e):
        """Обработчик ошибки 404 - страница не найдена"""
        logger.warning(f"404 Error: {request.path} - {request.remote_addr}")
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        """Обработчик ошибки 500 - внутренняя ошибка сервера"""
        error_tb = traceback.format_exc()
        logger.error(f"500 Error: {request.path}\n{error_tb}")
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(e):
        """Обработчик ошибки 403 - доступ запрещен"""
        logger.warning(f"403 Error: {request.path} - {request.remote_addr}")
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(400)
    def bad_request(e):
        """Обработчик ошибки 400 - плохой запрос"""
        logger.warning(f"400 Error: {request.path} - {request.remote_addr}")
        return render_template('errors/400.html'), 400

    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        """Обработчик всех необработанных исключений"""
        error_tb = traceback.format_exc()
        logger.error(f"Unhandled Exception: {request.path}\n{error_tb}")
        
        # Проверяем, является ли запрос AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'error': True,
                'message': 'Внутренняя ошибка сервера',
                'details': str(e) if app.debug else None
            }), 500
        
        return render_template('errors/500.html'), 500
    
    # Обработка всех HTTPException
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        logger.warning(f"HTTP Exception {e.code}: {request.path} - {request.remote_addr}")
        
        # Проверяем, является ли запрос AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'error': True,
                'message': e.description,
                'status_code': e.code
            }), e.code
        
        # Для 404 и общих ошибок используем специальные шаблоны
        if e.code == 404:
            return render_template('errors/404.html'), 404
        elif e.code >= 500:
            return render_template('errors/500.html'), e.code
        else:
            return render_template('errors/generic.html', error=e), e.code