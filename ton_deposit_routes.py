import os
import json
import time
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, current_app, session, flash
from flask_login import login_required, current_user

from app import db
from models import User, TonDeposit, AdminNotification
from ton_payment_service import ton_payment_service
from ton_client import TonClient
from telegram_notification import notify_new_ton_deposit, notify_ton_deposit_status_change

# Настройки TON
TON_WALLET_ADDRESS = os.environ.get('TON_WALLET_ADDRESS')
TON_API_KEY = os.environ.get('TON_API_KEY')

# Создаем Blueprint
ton_bp = Blueprint('ton', __name__, url_prefix='/ton')

# Настройка логирования
logger = logging.getLogger(__name__)

@ton_bp.route('/create-deposit', methods=['POST'])
def create_ton_deposit():
    """
    Маршрут для создания нового депозита через TON
    """
    try:
        # Проверяем авторизацию (как в маршруте dashboard)
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        
        # Проверяем авторизацию
        if not user_id or logged_in != 'true':
            flash('Пожалуйста, войдите в систему для доступа к этой функции.', 'warning')
            return redirect(url_for('login'))
        
        # Получаем пользователя из базы данных
        user = User.query.get(int(user_id))
        
        if not user:
            flash('Пользователь не найден.', 'danger')
            return redirect(url_for('login'))
            
        # Получаем IP-адрес пользователя и информацию о User-Agent
        from utils import log_user_ip
        client_ip = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        # Логируем IP-адрес при создании депозита
        log_user_ip(user.id, client_ip, 'deposit_ton', user_agent)
            
        # Получаем данные из запроса
        data = request.form or request.get_json()
        
        # Валидация данных
        amount = float(data.get('amount', 0))
        term_type = data.get('term_type', 'months')
        term_value = int(data.get('term_value', 0))
        
        # Проверяем минимальную сумму (5 USDT для тестового режима, 10 USDT для обычного)
        min_amount = 5 if term_type == 'minutes' else 10
        if amount < min_amount:
            flash(f'Минимальная сумма депозита - {min_amount} USDT', 'danger')
            return redirect(url_for('dashboard'))
            
        # Проверяем тип срока и значение
        if term_type not in ['minutes', 'weeks', 'months']:
            flash('Выберите корректный тип срока (минуты, недели или месяцы)', 'danger')
            return redirect(url_for('dashboard'))
            
        # Проверяем, имеет ли пользователь права администратора для тестового режима
        if term_type == 'minutes' and not user.is_admin:
            flash('Тестовый режим доступен только для администраторов', 'danger')
            return redirect(url_for('dashboard'))
            
        # Проверяем значение срока
        if term_value <= 0:
            flash('Укажите корректное значение срока', 'danger')
            return redirect(url_for('dashboard'))
            
        # Валидируем максимальные значения
        if term_type == 'minutes' and term_value != 5:
            flash('Для тестового режима доступно только значение 5 минут', 'danger')
            return redirect(url_for('dashboard'))
        elif term_type == 'weeks' and term_value > 4:
            flash('Максимальный срок для недель - 4 недели', 'danger')
            return redirect(url_for('dashboard'))
        elif term_type == 'months' and term_value > 12:
            flash('Максимальный срок для месяцев - 12 месяцев', 'danger')
            return redirect(url_for('dashboard'))
            
        # Конвертируем срок в дни
        term_days = 0
        if term_type == 'minutes':
            # Конвертируем минуты в доли дня (для тестирования)
            term_days = term_value / (24 * 60)  # минуты в доли дня
        elif term_type == 'weeks':
            term_days = term_value * 7
        elif term_type == 'months':
            term_days = term_value * 30
        
        # Создаем депозит через сервис
        result = ton_payment_service.create_deposit(
            user_id=user.id,
            amount=amount,
            term_days=term_days
        )
        
        if result.get('success'):
            # Успех - перенаправляем на страницу оплаты
            deposit_info = result.get('deposit', {})
            deposit_id = deposit_info.get('id')
            
            # Не отправляем уведомление в Telegram при создании депозита
            # Уведомление будет отправлено только при нажатии кнопки "Я оплатил"
            print(f"DEBUG: Депозит создан с ID {deposit_id}, уведомление будет отправлено при нажатии 'Я оплатил'")
            deposit = TonDeposit.query.get(deposit_id)  # Получаем депозит для дальнейшей обработки
                # Ошибка уведомления не должна влиять на основной процесс
            
            # Редирект на страницу оплаты
            return redirect(url_for('ton.payment_page', deposit_id=deposit_id))
        else:
            # Ошибка
            error_message = result.get('error', 'Неизвестная ошибка')
            flash(f'Ошибка при создании депозита: {error_message}', 'danger')
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        logger.error(f"Ошибка создания TON депозита: {str(e)}")
        flash(f'Произошла ошибка: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
        
@ton_bp.route('/payment/<int:deposit_id>', methods=['GET'])
def payment_page(deposit_id):
    """
    Страница оплаты депозита через TON
    """
    try:
        # Проверяем авторизацию (как в маршруте dashboard)
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        
        # Проверяем авторизацию
        if not user_id or logged_in != 'true':
            flash('Пожалуйста, войдите в систему для доступа к этой функции.', 'warning')
            return redirect(url_for('login'))
        
        # Получаем пользователя из базы данных
        user = User.query.get(int(user_id))
        
        if not user:
            flash('Пользователь не найден.', 'danger')
            return redirect(url_for('login'))
            
        # Получаем депозит
        deposit = TonDeposit.query.get(deposit_id)
        
        # Проверяем что депозит существует и принадлежит данному пользователю
        if not deposit or deposit.user_id != user.id:
            flash('Депозит не найден', 'danger')
            return redirect(url_for('dashboard'))
            
        # Получаем данные для отображения
        payment_data = {
            'id': deposit.id,
            'amount': deposit.amount,
            'memo': deposit.memo,
            'wallet_address': TON_WALLET_ADDRESS,
            'qr_code_url': deposit.qr_code_url,
            'term_days': deposit.term_days,
            'expected_profit': deposit.expected_profit,
            'status': deposit.status
        }
        
        # Если депозит уже оплачен, показываем информацию
        if deposit.status == 'completed':
            payment_data['payment_confirmed_at'] = deposit.payment_confirmed_at
            payment_data['tx_hash'] = deposit.tx_hash
            
        # Рендерим шаблон
        return render_template('ton_payment.html', payment=payment_data)
        
    except Exception as e:
        logger.error(f"Ошибка отображения страницы оплаты: {str(e)}")
        flash(f'Произошла ошибка: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))
        
@ton_bp.route('/check-payment/<int:deposit_id>', methods=['GET'])
def check_payment(deposit_id):
    """
    API маршрут для проверки статуса платежа и создания уведомлений для администраторов
    
    Обновлено:
    - Более гибкая авторизационная логика, особенно для AJAX-запросов
    - Добавлено создание уведомлений для администраторов при нажатии "Я оплатил"
    """
    
    # Расширяем логирование
    logger.info(f"Запрос на проверку платежа для депозита ID: {deposit_id}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    try:
        # Информация для отладки
        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        content_type = request.headers.get('Content-Type')
        accept = request.headers.get('Accept')
        
        # Улучшенное логирование параметров
        logger.info(f"Все аргументы запроса: {dict(request.args)}")
        show_loading_raw = request.args.get('show_loading', 'false')
        show_loading = show_loading_raw.lower() == 'true'
        
        logger.info(f"Тип запроса: XHR={is_xhr}, Content-Type={content_type}, Accept={accept}")
        logger.info(f"Параметр show_loading: raw='{show_loading_raw}', обработанный={show_loading}")
        
        # Получаем депозит (сначала без проверки владельца - это ключевое изменение)
        deposit = TonDeposit.query.get(deposit_id)
        
        if not deposit:
            logger.warning(f"Депозит с ID {deposit_id} не найден в базе данных")
            return jsonify({'success': False, 'error': 'Депозит не найден'})
            
        logger.info(f"Депозит найден: {deposit.id}, пользователь: {deposit.user_id}, статус: {deposit.status}")
        
        # Проверяем параметр show_loading из запроса и создаем уведомление если нужно
        # Улучшенная логика обработки параметра
        create_notification = False
        
        # Явно проверяем наличие параметра show_loading=true
        if 'show_loading' in request.args and request.args.get('show_loading').lower() == 'true':
            logger.info("Параметр show_loading=true обнаружен в запросе")
            create_notification = True
        elif show_loading:
            logger.info("Параметр show_loading установлен в True через обработчик")
            create_notification = True
        
        # Если нужно создать уведомление и депозит не завершен/не отменен
        if create_notification and deposit.status not in ['completed', 'failed']:
            logger.info("Создаём уведомление для администратора")
            
            # Получаем информацию о пользователе
            user = User.query.get(deposit.user_id)
            user_info = f"{user.username} (ID: {user.id})" if user else f"Пользователь ID: {deposit.user_id}"
            
            # Создаем текст уведомления
            notification_text = f"Пользователь {user_info} сообщает об оплате депозита #{deposit.id} на сумму {deposit.amount} USDT (MEMO: {deposit.memo})"
            
            try:
                # Проверяем, не существует ли уже такое уведомление для этого депозита
                existing_notification = AdminNotification.query.filter_by(
                    notification_type="payment",
                    related_transaction_id=deposit.id,
                    transaction_type="ton",
                    is_read=False
                ).first()
                
                # Если уведомления еще нет, создаем новое
                if not existing_notification:
                    logger.info(f"Создаем новое уведомление для админа о платеже депозита ID: {deposit.id}")
                    notification = AdminNotification(
                        title="Новый платеж TON",
                        message=notification_text,
                        notification_type="payment",
                        related_transaction_id=deposit.id,
                        transaction_type="ton",
                        related_user_id=deposit.user_id,
                        created_at=datetime.utcnow(),
                        is_read=False
                    )
                    db.session.add(notification)
                    db.session.commit()
                    logger.info(f"Уведомление создано: ID {notification.id}")
                else:
                    logger.info(f"Уведомление о платеже депозита ID: {deposit.id} уже существует")
            except Exception as notification_error:
                # Не даем ошибке при создании уведомления остановить выполнение запроса
                logger.error(f"Ошибка при создании уведомления: {str(notification_error)}")
                logger.error(traceback.format_exc())
        
        # Для AJAX-запросов и запросов на конкретные депозиты,
        # мы проверяем только наличие депозита и не требуем полной авторизации
        # Это изменение позволяет работать кнопке "Я оплатил"
        
        # Получаем текущий статус депозита перед проверкой
        current_status = deposit.status
        logger.info(f"Текущий статус депозита ID {deposit_id}: {current_status}")
        
        # Проверяем статус платежа
        result = ton_payment_service.check_deposit_payment(deposit_id)
        logger.info(f"Результат проверки: {result}")
        
        # Если статус изменился, отправляем уведомление в Telegram
        if result.get('success') and result.get('deposit', {}).get('status') != current_status:
            new_status = result.get('deposit', {}).get('status')
            logger.info(f"Статус депозита ID {deposit_id} изменился: {current_status} -> {new_status}")
            
            try:
                # Получаем обновленные данные о депозите
                updated_deposit = TonDeposit.query.get(deposit_id)
                
                # Отправляем уведомление в Telegram об изменении статуса
                notify_result = notify_ton_deposit_status_change(
                    user_id=updated_deposit.user_id,
                    amount=updated_deposit.amount,
                    memo=updated_deposit.memo,
                    transaction_id=str(updated_deposit.id),
                    new_status=new_status
                )
                
                logger.info(f"Результат отправки уведомления об изменении статуса: {notify_result}")
            except Exception as notify_error:
                logger.error(f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}")
                # Ошибка уведомления не должна влиять на основной процесс
        
        return jsonify(result)
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Ошибка проверки платежа: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        return jsonify({'success': False, 'error': str(e)})
        
@ton_bp.route('/deposits', methods=['GET'])
def user_deposits():
    """
    API маршрут для получения списка депозитов пользователя
    """
    try:
        # Проверяем авторизацию (как в маршруте dashboard)
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        
        # Проверяем авторизацию
        if not user_id or logged_in != 'true':
            return jsonify({'success': False, 'error': 'Требуется авторизация'})
        
        # Получаем пользователя из базы данных
        user = User.query.get(int(user_id))
        
        if not user:
            return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
        result = ton_payment_service.get_user_deposits(user.id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Ошибка получения депозитов пользователя: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
        
@ton_bp.route('/check-all-pending', methods=['GET'])
def check_all_pending():
    """
    Маршрут для проверки всех ожидающих платежей
    Примечание: в реальном приложении этот маршрут должен быть защищен и доступен 
    только администраторам или через cron-задачу
    """
    try:
        # Проверяем авторизацию (как в маршруте dashboard)
        user_id = request.cookies.get('user_id')
        logged_in = request.cookies.get('logged_in')
        
        # Проверяем авторизацию и права администратора
        is_admin = False
        is_local = request.remote_addr in ['127.0.0.1', '::1']
        
        # Если это локальный запрос - разрешаем (для cron-задач)
        if not is_local and (not user_id or logged_in != 'true'):
            return jsonify({'success': False, 'error': 'Требуется авторизация'}), 403
        
        # Если запрос от пользователя, проверяем права администратора
        if not is_local:
            user = User.query.get(int(user_id))
            if not user:
                return jsonify({'success': False, 'error': 'Пользователь не найден'}), 403
            is_admin = user.is_admin
        
        # Проверяем доступ
        if not (is_admin or is_local):
            return jsonify({'success': False, 'error': 'Доступ запрещен'}), 403
            
        # Получаем список всех ожидающих депозитов и их текущие статусы
        pending_deposits = TonDeposit.query.filter(TonDeposit.status.in_(['pending', 'payment_awaiting'])).all()
        deposits_status_map = {d.id: d.status for d in pending_deposits}
        
        # Проверяем все ожидающие платежи
        result = ton_payment_service.check_all_pending_deposits()
        
        # Обрабатываем успешный результат и отправляем уведомления при необходимости
        if result.get('success'):
            # Для каждого обновленного депозита проверяем изменение статуса
            for updated_deposit_info in result.get('deposits', []):
                deposit_id = updated_deposit_info.get('id')
                new_status = updated_deposit_info.get('status')
                
                # Если статус изменился, отправляем уведомление
                if deposit_id in deposits_status_map and deposits_status_map[deposit_id] != new_status:
                    old_status = deposits_status_map[deposit_id]
                    logger.info(f"Найдено изменение статуса депозита ID {deposit_id}: {old_status} -> {new_status}")
                    
                    try:
                        # Получаем актуальные данные о депозите
                        deposit = TonDeposit.query.get(deposit_id)
                        
                        # Проверяем токены Telegram
                        token_debug = os.environ.get('TELEGRAM_TOKEN')
                        token_debug = token_debug[:4] + "..." + token_debug[-4:] if token_debug else "None"
                        chat_id_debug = os.environ.get('TELEGRAM_CHAT_ID')
                        chat_id_debug = chat_id_debug[:2] + "..." + chat_id_debug[-2:] if chat_id_debug else "None"
                        logger.info(f"Используемые токены для отправки уведомлений: TELEGRAM_TOKEN={token_debug}, TELEGRAM_CHAT_ID={chat_id_debug}")
                        
                        # Отправляем уведомление в Telegram об изменении статуса
                        notify_result = notify_ton_deposit_status_change(
                            user_id=deposit.user_id,
                            amount=deposit.amount,
                            memo=deposit.memo,
                            transaction_id=str(deposit.id),
                            new_status=new_status
                        )
                        
                        if notify_result:
                            logger.info(f"Уведомление об изменении статуса успешно отправлено в Telegram для депозита #{deposit.id}")
                        else:
                            logger.error(f"Ошибка при отправке уведомления об изменении статуса в Telegram для депозита #{deposit.id}")
                        
                        logger.info(f"Результат отправки уведомления об изменении статуса: {notify_result}")
                    except Exception as notify_error:
                        logger.error(f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}")
                        # Ошибка уведомления не должна влиять на основной процесс
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Ошибка проверки ожидающих платежей: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
        
@ton_bp.route('/notify-payment/<int:deposit_id>', methods=['POST'])
def notify_payment(deposit_id):
    """
    Маршрут для обработки нажатия кнопки "Я оплатил" - форма POST
    Создает уведомление для администратора и перенаправляет на страницу платежа
    """
    logger.info(f"Получен POST-запрос для уведомления о платеже депозита ID: {deposit_id}")
    
    try:
        # Получаем депозит
        deposit = TonDeposit.query.get(deposit_id)
        
        if not deposit:
            logger.warning(f"Депозит с ID {deposit_id} не найден")
            flash("Депозит не найден", "danger")
            return redirect(url_for('dashboard'))
            
        # Проверяем, что депозит не завершен и не отменен
        if deposit.status in ['completed', 'failed']:
            logger.info(f"Депозит {deposit_id} уже имеет статус {deposit.status}")
            flash("Этот депозит уже обработан", "info")
            return redirect(url_for('ton.payment_page', deposit_id=deposit_id))
            
        # Получаем информацию о пользователе
        user = User.query.get(deposit.user_id)
        user_info = f"{user.username} (ID: {user.id})" if user else f"Пользователь ID: {deposit.user_id}"
        
        # Создаем текст уведомления
        notification_text = f"Пользователь {user_info} сообщает об оплате депозита #{deposit.id} на сумму {deposit.amount} USDT (MEMO: {deposit.memo})"
        
        # Проверяем, не существует ли уже такое уведомление для этого депозита
        existing_notification = AdminNotification.query.filter_by(
            notification_type="payment",
            related_transaction_id=deposit.id,
            transaction_type="ton",
            is_read=False
        ).first()
        
        # Если уведомления еще нет, создаем новое
        if not existing_notification:
            logger.info(f"Создаем новое уведомление для админа о платеже депозита ID: {deposit.id}")
            notification = AdminNotification(
                title="Новый платеж TON",
                message=notification_text,
                notification_type="payment",
                related_transaction_id=deposit.id,
                transaction_type="ton",
                related_user_id=deposit.user_id,
                created_at=datetime.utcnow(),
                is_read=False
            )
            db.session.add(notification)
            db.session.commit()
            logger.info(f"Уведомление создано: ID {notification.id}")
            
            # Отправляем уведомление в Telegram
            try:
                logger.info(f"Отправка уведомления в Telegram для депозита #{deposit.id}: пользователь {deposit.user_id}, сумма {deposit.amount}, MEMO {deposit.memo}")
                
                # Проверяем, что все параметры не None
                if deposit.user_id is None or deposit.amount is None or deposit.memo is None:
                    logger.error(f"Некорректные данные для отправки уведомления: user_id={deposit.user_id}, amount={deposit.amount}, memo={deposit.memo}")
                
                # Выводим информацию о токенах (с маскировкой)
                token_debug = os.environ.get('TELEGRAM_TOKEN')
                token_debug = token_debug[:4] + "..." + token_debug[-4:] if token_debug else "None"
                chat_id_debug = os.environ.get('TELEGRAM_CHAT_ID')
                chat_id_debug = chat_id_debug[:2] + "..." + chat_id_debug[-2:] if chat_id_debug else "None"
                logger.info(f"Используемые токены: TELEGRAM_TOKEN={token_debug}, TELEGRAM_CHAT_ID={chat_id_debug}")
                
                # Вызываем функцию отправки уведомления
                notify_result = notify_new_ton_deposit(
                    user_id=deposit.user_id,
                    amount=deposit.amount,
                    memo=deposit.memo,
                    transaction_id=str(deposit.id)
                )
                
                logger.info(f"Результат отправки уведомления в Telegram: {notify_result}")
                if notify_result:
                    logger.info(f"Уведомление успешно отправлено в Telegram для депозита #{deposit.id}")
                else:
                    logger.error(f"Ошибка при отправке уведомления в Telegram для депозита #{deposit.id}: результат=False")
            except Exception as e:
                logger.error(f"Исключение при отправке уведомления в Telegram: {str(e)}")
                logger.error(f"Детали ошибки: {traceback.format_exc()}")
                
            flash("Ваше уведомление об оплате отправлено администратору", "success")
        else:
            logger.info(f"Уведомление о платеже депозита ID: {deposit.id} уже существует")
            flash("Администратор уже получил уведомление о вашем платеже", "info")
        
        # Получаем текущий статус депозита перед проверкой
        current_status = deposit.status
        logger.info(f"Текущий статус депозита ID {deposit_id} перед проверкой: {current_status}")
        
        # Проверяем статус платежа после создания уведомления
        result = ton_payment_service.check_deposit_payment(deposit_id)
        logger.info(f"Результат проверки после нажатия кнопки 'Я оплатил': {result}")
        
        # Если статус изменился, отправляем дополнительное уведомление
        if result.get('success') and result.get('deposit', {}).get('status') != current_status:
            new_status = result.get('deposit', {}).get('status')
            logger.info(f"Статус депозита ID {deposit_id} изменился: {current_status} -> {new_status}")
            
            try:
                # Получаем обновленные данные о депозите
                updated_deposit = TonDeposit.query.get(deposit_id)
                
                # Отправляем уведомление в Telegram об изменении статуса
                notify_result = notify_ton_deposit_status_change(
                    user_id=updated_deposit.user_id,
                    amount=updated_deposit.amount,
                    memo=updated_deposit.memo,
                    transaction_id=str(updated_deposit.id),
                    new_status=new_status
                )
                
                logger.info(f"Результат отправки уведомления об изменении статуса: {notify_result}")
            except Exception as notify_error:
                logger.error(f"Ошибка при отправке уведомления в Telegram: {str(notify_error)}")
                # Ошибка уведомления не должна влиять на основной процесс
        
        # Перенаправляем на страницу платежа
        return redirect(url_for('ton.payment_page', deposit_id=deposit_id))
        
    except Exception as e:
        logger.error(f"Ошибка при создании уведомления: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        flash("Произошла ошибка при отправке уведомления", "danger")
        return redirect(url_for('ton.payment_page', deposit_id=deposit_id))


@ton_bp.route('/deposit-info/<int:deposit_id>', methods=['GET'])
def deposit_info(deposit_id):
    """
    Публичный API маршрут для получения информации о депозите
    Используется для тестирования и отладки
    """
    try:
        # Получаем депозит
        deposit = TonDeposit.query.get(deposit_id)
        
        # Проверяем что депозит существует
        if not deposit:
            return jsonify({'success': False, 'error': 'Депозит не найден'}), 404
            
        # Возвращаем информацию о депозите
        return jsonify({
            'success': True,
            'deposit': {
                'id': deposit.id,
                'status': deposit.status,
                'amount': deposit.amount,
                'memo': deposit.memo,
                'payment_confirmed_at': deposit.payment_confirmed_at.isoformat() if deposit.payment_confirmed_at else None,
                'created_at': deposit.created_at.isoformat(),
                'term_days': deposit.term_days,
                'tx_hash': deposit.tx_hash
            }
        })
            
    except Exception as e:
        logger.error(f"Ошибка получения информации о депозите: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})