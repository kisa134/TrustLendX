"""
Модуль для обработки запросов на вывод средств с поддержкой Telegram-уведомлений
"""
import logging
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db, limiter
from models import User, WithdrawalRequest, AdminNotification
from routes import admin_required, login_required, CurrentUser
from telegram_notification import notify_withdrawal_request, notify_withdrawal_status_change

# Экземпляр текущего пользователя для совместимости с кодом
current_user = CurrentUser()

# Создаем Blueprint
withdrawal_routes = Blueprint('withdrawal_routes', __name__)

@withdrawal_routes.route('/create-withdrawal-request', methods=['POST'])
@login_required
# 🔒 Security fix: Ограничение частоты запросов на вывод средств (максимум 5 в час, 20 в день)
@limiter.limit("5 per hour; 20 per day")
def create_withdrawal_request():
    """Обработка запроса на вывод средств из личного кабинета"""
    from forms import WithdrawalForm
    
    user = User.query.get(current_user.id)
    
    if not user:
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('dashboard'))
        
    # Логируем IP-адрес пользователя при создании запроса на вывод средств
    from utils import log_user_ip
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent')
    log_user_ip(user.id, client_ip, 'withdraw', user_agent)
    
    # Создаем форму и проверяем валидацию
    form = WithdrawalForm()
    
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Ошибка в поле {field}: {error}", "danger")
        return redirect(url_for('dashboard'))
    
    try:
        # Получаем данные из формы после валидации
        amount = form.amount.data
        wallet_address = form.wallet_address.data
        memo = form.memo.data
        
        # Дополнительная проверка на достаточность средств (это не может быть в форме, так как зависит от баланса пользователя)
        total_balance = user.get_total_balance()
        if amount > total_balance:
            flash(f'Недостаточно средств. Доступно: {total_balance} USDT', 'warning')
            return redirect(url_for('dashboard'))
        
        # Создание запроса на вывод
        withdrawal_request = WithdrawalRequest(
            user_id=user.id,
            amount=amount,
            wallet_address=wallet_address,
            network='TON',
            memo=memo,
            status='pending'
        )
        
        db.session.add(withdrawal_request)
        
        # Создание уведомления для администратора
        notification = AdminNotification(
            title='Новый запрос на вывод',
            message=f'Пользователь {user.username} запросил вывод {amount} USDT',
            notification_type='payment',
            related_user_id=user.id,
            is_read=False
        )
        
        db.session.add(notification)
        db.session.commit()
        
        # Отправляем уведомление в Telegram о новом запросе на вывод
        try:
            print(f"DEBUG: Отправка уведомления о запросе на вывод: user_id={user.id}, username={user.username}, amount={amount}, wallet_address={wallet_address}")
            
            # Проверяем, что все параметры имеют корректные значения
            safe_username = user.username or "Неизвестный пользователь"
            safe_wallet = wallet_address or "Не указан"
            
            notify_result = notify_withdrawal_request(
                user_id=user.id,
                username=safe_username,
                amount=float(amount),  # Обеспечиваем, что сумма - float
                wallet_address=safe_wallet,
                request_id=str(withdrawal_request.id)
            )
            print(f"DEBUG: Результат отправки уведомления о запросе на вывод: {notify_result}")
            logging.info(f"Результат отправки уведомления о запросе на вывод: {notify_result}")
        except Exception as notify_error:
            error_msg = f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}"
            print(f"DEBUG ERROR: {error_msg}")
            logging.error(error_msg)
            import traceback
            print(f"DEBUG TRACEBACK: {traceback.format_exc()}")
            # Ошибка уведомления не должна влиять на основной процесс
        
        flash('Запрос на вывод успешно создан и будет обработан в течение 24 часов', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при создании запроса: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@withdrawal_routes.route('/admin/withdrawal-requests')
@login_required
@admin_required
def admin_withdrawal_requests():
    """Страница управления запросами на вывод средств"""
    # Получаем все запросы на вывод средств (сортировка: сначала новые)
    requests = WithdrawalRequest.query.order_by(WithdrawalRequest.request_date.desc()).all()
    
    return render_template('admin/withdrawal_requests.html', 
                           requests=requests, 
                           title='Запросы на вывод')

@withdrawal_routes.route('/admin/withdrawal-requests/<int:request_id>')
@login_required
@admin_required
def admin_withdrawal_request_details(request_id):
    """Страница с деталями запроса на вывод средств"""
    # Получаем запрос по ID
    withdrawal_request = WithdrawalRequest.query.get_or_404(request_id)
    
    return render_template('admin/withdrawal_request_details.html', 
                           request=withdrawal_request, 
                           title=f'Запрос на вывод #{request_id}')

@withdrawal_routes.route('/admin/withdrawal-requests/<int:request_id>/update', methods=['POST'])
@login_required
@admin_required
def admin_update_withdrawal_status(request_id):
    """Обновление статуса запроса на вывод средств"""
    withdrawal_request = WithdrawalRequest.query.get_or_404(request_id)
    
    action = request.form.get('action')
    admin_comment = request.form.get('admin_comment', '')
    tx_hash = request.form.get('tx_hash', '')
    
    withdrawal_request.admin_comment = admin_comment
    
    message = ''  # Инициализируем переменную сообщения
    
    if action == 'approve':
        withdrawal_request.status = 'approved'
        withdrawal_request.processed_date = datetime.utcnow()
        message = f'Запрос на вывод #{request_id} одобрен'
    elif action == 'reject':
        withdrawal_request.status = 'rejected'
        withdrawal_request.processed_date = datetime.utcnow()
        message = f'Запрос на вывод #{request_id} отклонен'
    elif action == 'complete':
        # Проверяем достаточно ли средств у пользователя и уменьшаем его баланс
        user = withdrawal_request.user
        if not user.decrease_balance(withdrawal_request.amount):
            flash(f'Недостаточно средств на балансе пользователя {user.username}', 'danger')
            return redirect(url_for('withdrawal_routes.admin_withdrawal_request_details', request_id=request_id))
            
        withdrawal_request.status = 'completed'
        withdrawal_request.tx_hash = tx_hash
        withdrawal_request.processed_date = datetime.utcnow()
        message = f'Запрос на вывод #{request_id} выполнен. Баланс пользователя уменьшен на {withdrawal_request.amount} USDT'
    
    # Создание уведомления для администратора
    notification = AdminNotification(
        title=f'Статус запроса на вывод #{request_id} обновлен',
        message=message,
        notification_type='info',
        related_user_id=withdrawal_request.user_id,
        is_read=False
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Отправляем уведомление пользователю через Telegram
    try:
        print(f"DEBUG: Отправка уведомления об изменении статуса запроса на вывод: user_id={withdrawal_request.user_id}, username={withdrawal_request.user.username}, amount={withdrawal_request.amount}")
        
        from telegram_notification import notify_withdrawal_status_change
        
        # Безопасные значения для предотвращения ошибок
        safe_username = withdrawal_request.user.username or "Неизвестный пользователь"
        safe_wallet = withdrawal_request.wallet_address or "Не указан"
        
        notify_result = notify_withdrawal_status_change(
            user_id=withdrawal_request.user_id,
            username=safe_username,
            amount=float(withdrawal_request.amount),
            wallet_address=safe_wallet,
            request_id=str(withdrawal_request.id),
            new_status=withdrawal_request.status,
            tx_hash=withdrawal_request.tx_hash or ""
        )
        
        print(f"DEBUG: Результат отправки уведомления об изменении статуса: {notify_result}")
        import logging
        logging.info(f"Результат отправки уведомления об изменении статуса запроса на вывод: {notify_result}")
    except Exception as notify_error:
        error_msg = f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}"
        print(f"DEBUG ERROR: {error_msg}")
        import logging
        logging.error(error_msg)
        import traceback
        print(f"DEBUG TRACEBACK: {traceback.format_exc()}")
        # Ошибка уведомления не должна влиять на основной процесс
    
    flash(message, 'success')
    return redirect(url_for('withdrawal_routes.admin_withdrawal_request_details', request_id=request_id))

@withdrawal_routes.route('/admin/withdrawal-requests/<int:request_id>/approve')
@login_required
@admin_required
def admin_approve_withdrawal(request_id):
    """Быстрое одобрение запроса на вывод"""
    withdrawal_request = WithdrawalRequest.query.get_or_404(request_id)
    
    withdrawal_request.status = 'approved'
    withdrawal_request.processed_date = datetime.utcnow()
    
    # Создание уведомления для администратора
    notification = AdminNotification(
        title=f'Запрос на вывод #{request_id} одобрен',
        message=f'Запрос на вывод #{request_id} от пользователя {withdrawal_request.user.username} на сумму {withdrawal_request.amount} USDT одобрен',
        notification_type='info',
        related_user_id=withdrawal_request.user_id,
        is_read=False
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Отправляем уведомление пользователю через Telegram
    try:
        from telegram_notification import notify_withdrawal_status_change
        
        # Безопасные значения для предотвращения ошибок
        safe_username = withdrawal_request.user.username or "Неизвестный пользователь"
        safe_wallet = withdrawal_request.wallet_address or "Не указан"
        
        notify_result = notify_withdrawal_status_change(
            user_id=withdrawal_request.user_id,
            username=safe_username,
            amount=float(withdrawal_request.amount),
            wallet_address=safe_wallet,
            request_id=str(withdrawal_request.id),
            new_status='approved',
            tx_hash=withdrawal_request.tx_hash or ""
        )
        
        import logging
        logging.info(f"Результат отправки уведомления об одобрении запроса на вывод: {notify_result}")
    except Exception as notify_error:
        import logging
        logging.error(f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}")
        # Ошибка уведомления не должна влиять на основной процесс
    
    flash(f'Запрос на вывод #{request_id} успешно одобрен', 'success')
    return redirect(url_for('withdrawal_routes.admin_withdrawal_requests'))

@withdrawal_routes.route('/admin/withdrawal-requests/<int:request_id>/reject')
@login_required
@admin_required
def admin_reject_withdrawal(request_id):
    """Быстрое отклонение запроса на вывод"""
    withdrawal_request = WithdrawalRequest.query.get_or_404(request_id)
    
    withdrawal_request.status = 'rejected'
    withdrawal_request.processed_date = datetime.utcnow()
    
    # Создание уведомления для администратора
    notification = AdminNotification(
        title=f'Запрос на вывод #{request_id} отклонен',
        message=f'Запрос на вывод #{request_id} от пользователя {withdrawal_request.user.username} на сумму {withdrawal_request.amount} USDT отклонен',
        notification_type='info',
        related_user_id=withdrawal_request.user_id,
        is_read=False
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Отправляем уведомление пользователю через Telegram
    try:
        from telegram_notification import notify_withdrawal_status_change
        
        # Безопасные значения для предотвращения ошибок
        safe_username = withdrawal_request.user.username or "Неизвестный пользователь"
        safe_wallet = withdrawal_request.wallet_address or "Не указан"
        
        notify_result = notify_withdrawal_status_change(
            user_id=withdrawal_request.user_id,
            username=safe_username,
            amount=float(withdrawal_request.amount),
            wallet_address=safe_wallet,
            request_id=str(withdrawal_request.id),
            new_status='rejected',
            tx_hash=withdrawal_request.tx_hash or ""
        )
        
        import logging
        logging.info(f"Результат отправки уведомления об отклонении запроса на вывод: {notify_result}")
    except Exception as notify_error:
        import logging
        logging.error(f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}")
        # Ошибка уведомления не должна влиять на основной процесс
    
    flash(f'Запрос на вывод #{request_id} отклонен', 'success')
    return redirect(url_for('withdrawal_routes.admin_withdrawal_requests'))

@withdrawal_routes.route('/admin/withdrawal-requests/<int:request_id>/complete')
@login_required
@admin_required
def admin_complete_withdrawal(request_id):
    """Быстрое завершение запроса на вывод"""
    withdrawal_request = WithdrawalRequest.query.get_or_404(request_id)
    
    if withdrawal_request.status != 'approved':
        flash('Запрос должен быть одобрен перед завершением', 'warning')
        return redirect(url_for('withdrawal_routes.admin_withdrawal_requests'))
    
    # Проверяем достаточно ли средств у пользователя
    user = withdrawal_request.user
    if not user.decrease_balance(withdrawal_request.amount):
        flash(f'Недостаточно средств на балансе пользователя {user.username}', 'danger')
        return redirect(url_for('withdrawal_routes.admin_withdrawal_requests'))
    
    withdrawal_request.status = 'completed'
    withdrawal_request.processed_date = datetime.utcnow()
    
    # Создание уведомления для администратора
    notification = AdminNotification(
        title=f'Запрос на вывод #{request_id} выполнен',
        message=f'Запрос на вывод #{request_id} от пользователя {withdrawal_request.user.username} на сумму {withdrawal_request.amount} USDT выполнен',
        notification_type='info',
        related_user_id=withdrawal_request.user_id,
        is_read=False
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Отправляем уведомление пользователю через Telegram
    try:
        from telegram_notification import notify_withdrawal_status_change
        
        # Безопасные значения для предотвращения ошибок
        safe_username = withdrawal_request.user.username or "Неизвестный пользователь"
        safe_wallet = withdrawal_request.wallet_address or "Не указан"
        
        notify_result = notify_withdrawal_status_change(
            user_id=withdrawal_request.user_id,
            username=safe_username,
            amount=float(withdrawal_request.amount),
            wallet_address=safe_wallet,
            request_id=str(withdrawal_request.id),
            new_status='completed',
            tx_hash=withdrawal_request.tx_hash or ""
        )
        
        import logging
        logging.info(f"Результат отправки уведомления о завершении запроса на вывод: {notify_result}")
    except Exception as notify_error:
        import logging
        logging.error(f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}")
        # Ошибка уведомления не должна влиять на основной процесс
    
    flash(f'Запрос на вывод #{request_id} отмечен как выполненный. Баланс пользователя уменьшен на {withdrawal_request.amount} USDT', 'success')
    return redirect(url_for('withdrawal_routes.admin_withdrawal_requests'))