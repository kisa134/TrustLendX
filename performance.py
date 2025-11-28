import time
from functools import wraps
from flask import request, current_app

# Словарь для хранения статистики запросов
request_stats = {
    'total_requests': 0,
    'slow_requests': 0,
    'routes': {}
}

def setup_performance_monitoring(app):
    """
    Настраивает мониторинг производительности
    
    Args:
        app: Экземпляр приложения Flask
    """
    
    @app.before_request
    def start_timer():
        """Измеряет время начала запроса"""
        request.start_time = time.time()
    
    @app.after_request
    def log_request_info(response):
        """Логирует информацию о времени выполнения запроса"""
        # Если таймер не был установлен, ничего не делаем
        if not hasattr(request, 'start_time'):
            return response
            
        # Считаем время выполнения
        duration = time.time() - request.start_time
        
        # Обновляем статистику
        global request_stats
        request_stats['total_requests'] += 1
        
        # Обрабатываем медленные запросы (более 500мс)
        if duration > 0.5:
            request_stats['slow_requests'] += 1
            app.logger.warning(
                f"Медленный запрос: {request.method} {request.path} выполнен за {duration:.2f}с"
            )
        
        # Обновляем статистику по маршруту
        route = request.endpoint if request.endpoint else request.path
        if route not in request_stats['routes']:
            request_stats['routes'][route] = {
                'count': 0,
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0
            }
        
        route_stats = request_stats['routes'][route]
        route_stats['count'] += 1
        route_stats['total_time'] += duration
        route_stats['min_time'] = min(route_stats['min_time'], duration)
        route_stats['max_time'] = max(route_stats['max_time'], duration)
        
        # Добавляем заголовок время выполнения запроса (для отладки)
        if app.debug:
            response.headers['X-Request-Time'] = f"{duration:.2f}s"
        
        return response
    
    # Добавляем маршрут для статистики (для администраторов)
    @app.route('/admin/performance', methods=['GET'])
    def performance_stats():
        """Возвращает статистику производительности"""
        from flask import jsonify, render_template
        
        # Проверяем, является ли пользователь администратором
        if not getattr(request, 'is_admin', False):
            return render_template('errors/403.html'), 403
        
        # Обрабатываем запрос API
        if request.headers.get('Accept') == 'application/json':
            return jsonify(request_stats)
        
        # Визуальное представление статистики
        # В более полной реализации здесь будет шаблон с графиками
        routes_stats = []
        for route, stats in request_stats['routes'].items():
            if stats['count'] > 0:
                avg_time = stats['total_time'] / stats['count']
                routes_stats.append({
                    'route': route,
                    'count': stats['count'],
                    'avg_time': f"{avg_time:.2f}s",
                    'min_time': f"{stats['min_time']:.2f}s",
                    'max_time': f"{stats['max_time']:.2f}s"
                })
        
        return render_template(
            'admin/performance.html',
            total_requests=request_stats['total_requests'],
            slow_requests=request_stats['slow_requests'],
            routes=sorted(routes_stats, key=lambda x: x['count'], reverse=True)
        )
    
    # Добавляем эндпоинт для сброса статистики
    @app.route('/admin/performance/reset', methods=['POST'])
    def reset_performance_stats():
        """Сбрасывает статистику производительности"""
        from flask import jsonify, redirect, url_for
        
        # Проверяем, является ли пользователь администратором
        if not getattr(request, 'is_admin', False):
            return render_template('errors/403.html'), 403
        
        global request_stats
        request_stats = {
            'total_requests': 0,
            'slow_requests': 0,
            'routes': {}
        }
        
        # Обрабатываем запрос API
        if request.headers.get('Accept') == 'application/json':
            return jsonify({'success': True, 'message': 'Статистика сброшена'})
        
        return redirect(url_for('performance_stats'))
    
    # Создаем шаблон папки для администраторов, если её нет
    import os
    if not os.path.exists('templates/admin'):
        os.makedirs('templates/admin')
    
    return app

def cache_control(max_age=3600, private=False, no_store=False, must_revalidate=False):
    """
    Декоратор для установки заголовков кэширования
    
    Args:
        max_age: максимальное время кэширования в секундах
        private: кэшировать только на стороне клиента
        no_store: запретить кэширование
        must_revalidate: требовать проверки актуальности контента
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            response = view_func(*args, **kwargs)
            
            # 🔒 Security fix: Проверяем, что ответ имеет атрибут headers
            # Это может быть кортеж (код, содержимое), если используется jsonify с кодом
            if isinstance(response, tuple) and len(response) >= 2:
                # Обрабатываем случай, когда response = jsonify(...), 401
                # Первый элемент должен быть Response-объектом
                resp_obj, status_code = response[0], response[1]
                if hasattr(resp_obj, 'headers'):
                    # Устанавливаем заголовки кэширования в объект ответа
                    if no_store:
                        resp_obj.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                        resp_obj.headers['Pragma'] = 'no-cache'
                        resp_obj.headers['Expires'] = '0'
                    else:
                        directives = []
                        if private:
                            directives.append('private')
                        else:
                            directives.append('public')
                        
                        if must_revalidate:
                            directives.append('must-revalidate')
                        
                        directives.append(f'max-age={max_age}')
                        
                        resp_obj.headers['Cache-Control'] = ', '.join(directives)
                # Оставляем ответ как есть
                return response
            
            # Обычный случай - ответ является объектом Response
            if hasattr(response, 'headers'):
                if no_store:
                    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                    response.headers['Pragma'] = 'no-cache'
                    response.headers['Expires'] = '0'
                else:
                    directives = []
                    if private:
                        directives.append('private')
                    else:
                        directives.append('public')
                    
                    if must_revalidate:
                        directives.append('must-revalidate')
                    
                    directives.append(f'max-age={max_age}')
                    
                    response.headers['Cache-Control'] = ', '.join(directives)
            
            return response
        return wrapped
    return decorator