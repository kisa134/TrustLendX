import json
import csv
import io
from datetime import datetime, timedelta
import pytz
from flask import Blueprint, render_template, jsonify, request, Response, abort, current_app
from flask_login import current_user
from models import User, Transaction, ReferralSettings, ReferralPayment, db
from aml_settings_route import admin_required
from sqlalchemy import desc, func, and_, or_, select
from sqlalchemy.sql.expression import extract
import logging

# Определяем московский часовой пояс
moscow_tz = pytz.timezone('Europe/Moscow')

# Создаем Blueprint для маршрутов администрирования реферальной системы
referral_admin = Blueprint('referral_admin', __name__)

@referral_admin.route('/admin/referrals')
@admin_required
def admin_referrals():
    """Страница администрирования реферальной системы"""
    
    # Получаем текущие настройки реферальной системы
    settings = ReferralSettings.get_current()
    
    # Общая статистика
    total_referrals = db.session.query(func.count(User.id)).filter(User.referred_by_id != None).scalar() or 0
    
    # Активные рефералы (хотя бы один депозит ≥ min_deposit_amount)
    min_deposit = settings.min_deposit_amount
    active_referrals_subquery = db.session.query(User.id).filter(
        User.referred_by_id != None  # Только пользователи, пришедшие по реферальной ссылке
    ).join(
        Transaction, 
        and_(
            Transaction.user_id == User.id,
            Transaction.status == 'completed',
            Transaction.amount >= min_deposit
        )
    ).distinct().subquery()
    
    active_referrals = db.session.query(func.count()).filter(User.id.in_(active_referrals_subquery)).scalar() or 0
    
    # Общий оборот рефералов
    total_turnover = db.session.query(func.sum(Transaction.amount)).join(
        User, 
        and_(
            User.id == Transaction.user_id,
            User.referred_by_id != None,
            Transaction.status == 'completed'
        )
    ).scalar() or 0
    
    # Выплачено рефоводам
    total_paid = db.session.query(func.sum(ReferralPayment.amount)).filter(
        ReferralPayment.status == 'paid'
    ).scalar() or 0
    
    # Статистика по топ рефоводам
    # Создаем алиасы для таблицы User
    Referrer = db.aliased(User)
    Referral = db.aliased(User)
    
    # Используем select() для явного определения левой стороны соединения
    stmt = select(
        Referrer.id,
        Referrer.username,
        Referrer.email,
        func.count(Referral.id).label('referral_count')
    ).select_from(Referrer).join(
        Referral, 
        Referral.referred_by_id == Referrer.id
    ).group_by(
        Referrer.id,
        Referrer.username,
        Referrer.email
    ).order_by(
        desc('referral_count')
    ).limit(10)
    
    top_referrers = db.session.execute(stmt).all()
    
    # Передаем данные в шаблон
    return render_template(
        'admin/referrals.html',
        title='Управление реферальной системой',
        settings=settings,
        total_referrals=total_referrals,
        active_referrals=active_referrals,
        total_turnover=total_turnover,
        total_paid=total_paid,
        top_referrers=top_referrers,
        active_percentage=round(active_referrals / total_referrals * 100 if total_referrals else 0, 1)
    )

@referral_admin.route('/api/admin/referrals/data')
@admin_required
def get_referrals_data():
    """API для получения данных о рефералах с пагинацией и фильтрацией"""
    # Логируем параметры запроса для отладки
    logging.debug(f"get_referrals_data request query params: {request.args}")
    logging.debug(f"get_referrals_data request cookies: {request.cookies}")
    
    # Проверяем параметры админа из URL (для AJAX-запросов с JavaScript)
    user_id = request.args.get('user_id')
    is_admin = request.args.get('is_admin')
    logged_in = request.args.get('logged_in')
    
    logging.debug(f"get_referrals_data params from URL: user_id={user_id}, is_admin={is_admin}, logged_in={logged_in}")
    
    # Параметры пагинации и фильтрации
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    referrer_id = request.args.get('referrer_id', type=int)
    
    # Базовый запрос с использованием select() для явного указания левой стороны соединения
    # Создаем алиас для таблицы User для рефоводов
    Referrer = db.aliased(User)
    
    # Создаем базовый запрос с select_from
    query = select(
        User.id.label('referral_id'),
        User.username.label('referral_username'),
        User.email.label('referral_email'),
        User.registered_on.label('registration_date'),
        User.referred_by_id,
        User.referral_code,
        Referrer.username.label('referrer_username'),
        Referrer.email.label('referrer_email')
    ).select_from(User).filter(
        User.referred_by_id != None  # Только пользователи, пришедшие по реферальной ссылке
    ).join(
        Referrer, 
        Referrer.id == User.referred_by_id
    )
    
    # Применяем фильтры
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(search_term),
                User.email.ilike(search_term),
                User.username.ilike(search_term),
                User.email.ilike(search_term)
            )
        )
    
    if referrer_id:
        query = query.filter(User.referred_by_id == referrer_id)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(User.registered_on >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Добавляем день, чтобы включить весь выбранный день
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(User.registered_on <= date_to_obj)
        except ValueError:
            pass
    
    if status == 'active':
        # Активные рефералы - имеют хотя бы один депозит ≥ min_deposit_amount
        settings = ReferralSettings.get_current()
        min_deposit = settings.min_deposit_amount
        
        active_referrals_subquery = db.session.query(User.id).join(
            Transaction, 
            and_(
                Transaction.user_id == User.id,
                Transaction.status == 'completed',
                Transaction.amount >= min_deposit
            )
        ).distinct().subquery()
        
        query = query.filter(User.id.in_(active_referrals_subquery))
    elif status == 'pending':
        # Неактивные рефералы - не имеют депозитов ≥ min_deposit_amount
        settings = ReferralSettings.get_current()
        min_deposit = settings.min_deposit_amount
        
        active_referrals_subquery = db.session.query(User.id).join(
            Transaction, 
            and_(
                Transaction.user_id == User.id,
                Transaction.status == 'completed',
                Transaction.amount >= min_deposit
            )
        ).distinct().subquery()
        
        query = query.filter(~User.id.in_(active_referrals_subquery))
    
    # Добавляем сортировку
    query = query.order_by(desc(User.registered_on))
    
    # Создаем подзапрос для подсчета
    subquery = query.subquery()
    count_stmt = select(func.count()).select_from(subquery)
    total = db.session.execute(count_stmt).scalar() or 0
    
    # Применяем пагинацию
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    # Выполняем запрос
    referrals = db.session.execute(query).all()
    
    # Формируем результат
    result = []
    for row in referrals:
        # Получаем сумму депозитов реферала
        total_deposits = db.session.query(func.sum(Transaction.amount)).filter(
            Transaction.user_id == row.referral_id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Получаем прибыль реферала
        total_profit = db.session.query(func.sum(Transaction.expected_profit)).filter(
            Transaction.user_id == row.referral_id,
            Transaction.status == 'completed'
        ).scalar() or 0
        
        # Получаем выплаты рефоводу
        referrer_earnings = db.session.query(func.sum(ReferralPayment.amount)).filter(
            ReferralPayment.referral_id == row.referral_id,
            ReferralPayment.referrer_id == row.referred_by_id
        ).scalar() or 0
        
        # Получаем статус реферала (активный или ожидающий)
        settings = ReferralSettings.get_current()
        min_deposit = settings.min_deposit_amount
        
        has_min_deposit = db.session.query(Transaction).filter(
            Transaction.user_id == row.referral_id,
            Transaction.status == 'completed',
            Transaction.amount >= min_deposit
        ).first() is not None
        
        status = 'active' if has_min_deposit else 'pending'
        
        # Преобразуем UTC время регистрации в московское время
        moscow_registration_date = row.registration_date.replace(tzinfo=pytz.UTC).astimezone(moscow_tz)
        
        result.append({
            'id': row.referral_id,
            'referral_username': row.referral_username,
            'referral_email': row.referral_email,
            'registration_date': moscow_registration_date.strftime('%Y-%m-%d %H:%M'),
            'referrer_id': row.referred_by_id,
            'referrer_username': row.referrer_username,
            'referrer_email': row.referrer_email,
            'total_deposits': total_deposits,
            'total_profit': total_profit,
            'referrer_earnings': referrer_earnings,
            'status': status
        })
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'data': result
    })

@referral_admin.route('/api/admin/referrals/settings', methods=['GET', 'POST'])
@admin_required
def referral_settings():
    """API для получения и обновления настроек реферальной системы"""
    # Логируем вызов API
    logging.debug(f"referral_settings API call from user: {current_user.id} ({current_user.username}), method: {request.method}")
    
    if request.method == 'GET':
        settings = ReferralSettings.get_current()
        return jsonify({
            'id': settings.id,
            'min_deposit_amount': settings.min_deposit_amount,
            'referral_percentage': settings.referral_percentage,
            'active': settings.active,
            'updated_at': settings.updated_at.strftime('%Y-%m-%d %H:%M:%S') if settings.updated_at else None
        })
    
    elif request.method == 'POST':
        settings = ReferralSettings.get_current()
        
        # Получаем данные из запроса
        data = request.get_json()
        
        if 'min_deposit_amount' in data:
            try:
                min_deposit = float(data['min_deposit_amount'])
                if min_deposit < 0:
                    return jsonify({'error': 'Минимальная сумма депозита не может быть отрицательной'}), 400
                settings.min_deposit_amount = min_deposit
            except (ValueError, TypeError):
                return jsonify({'error': 'Неверный формат минимальной суммы депозита'}), 400
        
        if 'referral_percentage' in data:
            try:
                percentage = float(data['referral_percentage'])
                if percentage < 0 or percentage > 100:
                    return jsonify({'error': 'Процент должен быть в диапазоне от 0 до 100'}), 400
                settings.referral_percentage = percentage
            except (ValueError, TypeError):
                return jsonify({'error': 'Неверный формат процента'}), 400
        
        if 'active' in data:
            settings.active = bool(data['active'])
        
        if 'description' in data:
            settings.description = data['description']
        
        # Сохраняем, кто внес изменения
        settings.updated_by_id = current_user.id
        settings.updated_at = datetime.utcnow()
        
        # Сохраняем изменения
        db.session.commit()
        
        # Логируем изменения
        current_app.logger.info(
            f"Настройки реферальной системы обновлены пользователем {current_user.username} (ID: {current_user.id}): "
            f"min_deposit={settings.min_deposit_amount}, percentage={settings.referral_percentage}, "
            f"active={settings.active}"
        )
        
        return jsonify({
            'id': settings.id,
            'min_deposit_amount': settings.min_deposit_amount,
            'referral_percentage': settings.referral_percentage,
            'active': settings.active,
            'updated_at': settings.updated_at.strftime('%Y-%m-%d %H:%M:%S') if settings.updated_at else None,
            'message': 'Настройки успешно обновлены'
        })

@referral_admin.route('/api/admin/referrals/payments')
@admin_required
def get_referral_payments():
    """API для получения данных о выплатах рефералам с пагинацией и фильтрацией"""
    # Логируем вызов API
    logging.debug(f"get_referral_payments request from user: {current_user.id} ({current_user.username}), query params: {request.args}")
    
    # Параметры пагинации и фильтрации
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    referrer_id = request.args.get('referrer_id', type=int)
    
    # Базовый запрос с использованием select() для улучшенной совместимости с SQLAlchemy 2.0
    query = select(ReferralPayment)
    
    # Применяем фильтры
    if search:
        search_term = f"%{search}%"
        # Создаем алиасы для User, чтобы избежать неоднозначности
        ReferrerUser = db.aliased(User)
        ReferralUser = db.aliased(User)
        
        # Два отдельных join для реферера и реферала
        query = (
            query.join(ReferrerUser, ReferralPayment.referrer_id == ReferrerUser.id)
            .join(ReferralUser, ReferralPayment.referral_id == ReferralUser.id)
            .where(
                or_(
                    ReferrerUser.username.ilike(search_term),
                    ReferrerUser.email.ilike(search_term),
                    ReferralUser.username.ilike(search_term),
                    ReferralUser.email.ilike(search_term)
                )
            )
        )
    
    if status:
        query = query.where(ReferralPayment.status == status)
    
    if referrer_id:
        query = query.where(ReferralPayment.referrer_id == referrer_id)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.where(ReferralPayment.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Добавляем день, чтобы включить весь выбранный день
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.where(ReferralPayment.created_at <= date_to_obj)
        except ValueError:
            pass
    
    # Добавляем сортировку
    query = query.order_by(desc(ReferralPayment.created_at))
    
    # Создаем запрос для подсчета общего количества
    count_query = select(func.count()).select_from(query.subquery())
    total = db.session.execute(count_query).scalar() or 0
    
    # Применяем пагинацию
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    # Выполняем запрос
    payments = db.session.execute(query).scalars().all()
    
    # Формируем результат
    result = []
    for payment in payments:
        # Получаем данные о рефоводе и реферале с использованием SQLAlchemy 2.0 синтаксиса
        stmt_referrer = select(User).where(User.id == payment.referrer_id)
        stmt_referral = select(User).where(User.id == payment.referral_id)
        
        referrer = db.session.execute(stmt_referrer).scalar_one_or_none()
        referral = db.session.execute(stmt_referral).scalar_one_or_none()
        
        # Преобразуем UTC время в московское время
        moscow_created_at = payment.created_at.replace(tzinfo=pytz.UTC).astimezone(moscow_tz)
        moscow_paid_at = payment.paid_at.replace(tzinfo=pytz.UTC).astimezone(moscow_tz) if payment.paid_at else None
        
        result.append({
            'id': payment.id,
            'referrer_id': payment.referrer_id,
            'referrer_username': referrer.username if referrer else 'Unknown',
            'referrer_email': referrer.email if referrer else 'Unknown',
            'referral_id': payment.referral_id,
            'referral_username': referral.username if referral else 'Unknown',
            'referral_email': referral.email if referral else 'Unknown',
            'amount': payment.amount,
            'referral_profit': payment.referral_profit,
            'percentage': payment.percentage,
            'created_at': moscow_created_at.strftime('%Y-%m-%d %H:%M'),
            'paid_at': moscow_paid_at.strftime('%Y-%m-%d %H:%M') if moscow_paid_at else None,
            'status': payment.status,
            'notes': payment.notes
        })
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'data': result
    })

@referral_admin.route('/api/admin/referrals/payments/<int:payment_id>', methods=['POST'])
@admin_required
def update_referral_payment(payment_id):
    """API для обновления статуса выплаты реферального вознаграждения"""
    
    # Получаем выплату по ID с использованием улучшенного синтаксиса SQLAlchemy 2.0
    stmt = select(ReferralPayment).where(ReferralPayment.id == payment_id)
    payment = db.session.execute(stmt).scalar_one_or_none()
    if not payment:
        return jsonify({'error': 'Выплата не найдена'}), 404
    
    # Получаем данные из запроса
    data = request.get_json()
    
    if 'status' in data:
        status = data['status']
        if status not in ['pending', 'paid', 'canceled']:
            return jsonify({'error': 'Неверный статус'}), 400
        
        old_status = payment.status
        payment.status = status
        
        # Если статус изменен на "оплачено", устанавливаем дату выплаты
        if status == 'paid' and old_status != 'paid':
            payment.paid_at = datetime.utcnow()
            
            # Обновляем статистику рефовода с использованием SQLAlchemy 2.0 синтаксиса
            stmt_referrer = select(User).where(User.id == payment.referrer_id)
            referrer = db.session.execute(stmt_referrer).scalar_one_or_none()
            if referrer:
                referrer.referral_earnings += payment.amount
        
        # Если статус был "оплачено", а теперь отменен, корректируем статистику
        elif old_status == 'paid' and status != 'paid':
            # Отменяем выплату с использованием SQLAlchemy 2.0 синтаксиса
            stmt_referrer = select(User).where(User.id == payment.referrer_id)
            referrer = db.session.execute(stmt_referrer).scalar_one_or_none()
            if referrer and referrer.referral_earnings >= payment.amount:
                referrer.referral_earnings -= payment.amount
            
            payment.paid_at = None
    
    if 'notes' in data:
        payment.notes = data['notes']
    
    # Сохраняем изменения
    db.session.commit()
    
    # Логируем изменения
    current_app.logger.info(
        f"Статус выплаты реферального вознаграждения ID={payment_id} обновлен пользователем {current_user.username} "
        f"(ID: {current_user.id}): status={payment.status}, notes='{payment.notes}'"
    )
    
    return jsonify({
        'id': payment.id,
        'status': payment.status,
        'paid_at': payment.paid_at.strftime('%Y-%m-%d %H:%M') if payment.paid_at else None,
        'notes': payment.notes,
        'message': 'Статус выплаты успешно обновлен'
    })

@referral_admin.route('/api/admin/referrals/create-payment', methods=['POST'])
@admin_required
def create_manual_payment():
    """API для создания ручной выплаты реферального вознаграждения"""
    
    # Получаем данные из запроса
    data = request.get_json()
    
    # Проверяем обязательные поля
    required_fields = ['referrer_id', 'referral_id', 'amount', 'referral_profit']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Отсутствует обязательное поле: {field}'}), 400
    
    try:
        # Проверяем существование пользователей с использованием синтаксиса SQLAlchemy 2.0
        stmt_referrer = select(User).where(User.id == data['referrer_id'])
        stmt_referral = select(User).where(User.id == data['referral_id'])
        
        referrer = db.session.execute(stmt_referrer).scalar_one_or_none()
        referral = db.session.execute(stmt_referral).scalar_one_or_none()
        
        if not referrer:
            return jsonify({'error': 'Рефовод не найден'}), 404
        
        if not referral:
            return jsonify({'error': 'Реферал не найден'}), 404
        
        # Проверяем, что реферал действительно привел рефовод
        if referral.referred_by_id != referrer.id:
            return jsonify({'error': 'Указанный пользователь не является рефералом данного рефовода'}), 400
        
        # Получаем настройки реферальной системы
        settings = ReferralSettings.get_current()
        
        # Создаем новую выплату
        payment = ReferralPayment(
            referrer_id=referrer.id,
            referral_id=referral.id,
            amount=float(data['amount']),
            referral_profit=float(data['referral_profit']),
            percentage=settings.referral_percentage,  # Используем текущий процент из настроек
            status='pending',
            notes=data.get('notes', 'Создано вручную администратором')
        )
        
        # Если статус указан как "paid", помечаем выплату как оплаченную
        if data.get('status') == 'paid':
            payment.status = 'paid'
            payment.paid_at = datetime.utcnow()
            
            # Обновляем статистику рефовода
            referrer.referral_earnings += payment.amount
        
        # Сохраняем в базу
        db.session.add(payment)
        db.session.commit()
        
        # Логируем создание
        current_app.logger.info(
            f"Создана ручная выплата реферального вознаграждения ID={payment.id} пользователем {current_user.username} "
            f"(ID: {current_user.id}): referrer={referrer.username}, referral={referral.username}, "
            f"amount={payment.amount}, status={payment.status}"
        )
        
        return jsonify({
            'id': payment.id,
            'referrer_id': payment.referrer_id,
            'referral_id': payment.referral_id,
            'amount': payment.amount,
            'referral_profit': payment.referral_profit,
            'percentage': payment.percentage,
            'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M'),
            'status': payment.status,
            'message': 'Выплата успешно создана'
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Ошибка при создании выплаты: {str(e)}")
        return jsonify({'error': f'Ошибка при создании выплаты: {str(e)}'}), 500

@referral_admin.route('/api/admin/referrals/remove-referral', methods=['POST'])
@admin_required
def remove_referral():
    """API для удаления реферальной связи между пользователями"""
    
    # Получаем данные из запроса
    data = request.get_json()
    
    if 'referral_id' not in data:
        return jsonify({'error': 'Отсутствует ID реферала'}), 400
    
    try:
        # Получаем реферала с использованием SQLAlchemy 2.0 синтаксиса
        stmt_referral = select(User).where(User.id == data['referral_id'])
        referral = db.session.execute(stmt_referral).scalar_one_or_none()
        
        if not referral:
            return jsonify({'error': 'Реферал не найден'}), 404
        
        # Получаем рефовода с использованием SQLAlchemy 2.0 синтаксиса
        referrer = None
        referrer_id = None
        
        if referral.referred_by_id:
            stmt_referrer = select(User).where(User.id == referral.referred_by_id)
            referrer = db.session.execute(stmt_referrer).scalar_one_or_none()
            referrer_id = referral.referred_by_id
        
        # Удаляем связь
        old_referred_by_id = referral.referred_by_id
        referral.referred_by_id = None
        
        # Сохраняем изменения
        db.session.commit()
        
        # Логируем удаление связи
        current_app.logger.info(
            f"Удалена реферальная связь пользователем {current_user.username} (ID: {current_user.id}): "
            f"реферал {referral.username} (ID: {referral.id}) больше не привязан к рефоводу "
            f"ID: {old_referred_by_id}"
        )
        
        return jsonify({
            'referral_id': referral.id,
            'referrer_id': referrer_id,
            'message': f'Реферальная связь успешно удалена. {referral.username} больше не является рефералом.'
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Ошибка при удалении реферальной связи: {str(e)}")
        return jsonify({'error': f'Ошибка при удалении реферальной связи: {str(e)}'}), 500

@referral_admin.route('/api/admin/referrals/analytics')
@admin_required
def referral_analytics():
    """API для получения аналитических данных по реферальной программе"""
    # Логируем вызов API
    logging.debug(f"referral_analytics API call from user: {current_user.id} ({current_user.username})")
    
    try:
        # Получаем период анализа
        period = request.args.get('period', 'month')
        
        # Текущая дата
        today = datetime.utcnow().date()
        
        if period == 'week':
            # Статистика за последние 7 дней
            start_date = today - timedelta(days=7)
            date_format = '%Y-%m-%d'
            date_extract = func.date(User.registered_on)
        elif period == 'month':
            # Статистика за последние 30 дней
            start_date = today - timedelta(days=30)
            date_format = '%Y-%m-%d'
            date_extract = func.date(User.registered_on)
        elif period == 'year':
            # Статистика по месяцам за год
            start_date = datetime(today.year - 1, today.month, 1).date()
            date_format = '%Y-%m'
            date_extract = func.date_format(User.registered_on, '%Y-%m')
        else:
            return jsonify({'error': 'Неверный период'}), 400
        
        # Количество новых рефералов по дням/месяцам
        referrals_per_period = db.session.query(
            date_extract.label('period'),
            func.count(User.id).label('count')
        ).filter(
            User.referred_by_id != None,
            User.registered_on >= start_date
        ).group_by(
            'period'
        ).order_by(
            'period'
        ).all()
        
        # Преобразуем результаты в формат для графика
        referrals_data = [
            {
                'period': str(row.period),
                'count': row.count
            }
            for row in referrals_per_period
        ]
        
        # Активация рефералов (первый депозит ≥ min_deposit_amount) по дням/месяцам
        settings = ReferralSettings.get_current()
        min_deposit = settings.min_deposit_amount
        
        activations_per_period = db.session.query(
            func.date_format(Transaction.created_at, date_format).label('period'),
            func.count(Transaction.id).label('count')
        ).join(
            User, 
            and_(
                User.id == Transaction.user_id,
                User.referred_by_id != None
            )
        ).filter(
            Transaction.status == 'completed',
            Transaction.amount >= min_deposit,
            Transaction.created_at >= start_date
        ).group_by(
            'period'
        ).order_by(
            'period'
        ).all()
        
        # Преобразуем результаты в формат для графика
        activations_data = [
            {
                'period': str(row.period),
                'count': row.count
            }
            for row in activations_per_period
        ]
        
        # Топ-10 рефоводов по количеству активных рефералов
        top_referrers = db.session.query(
            User.id,
            User.username,
            func.count(Transaction.id).label('active_referrals')
        ).join(
            User, 
            User.referred_by_id == User.id
        ).join(
            Transaction,
            and_(
                Transaction.user_id == User.id,
                Transaction.status == 'completed',
                Transaction.amount >= min_deposit
            )
        ).group_by(
            User.id
        ).order_by(
            desc('active_referrals')
        ).limit(10).all()
        
        # Преобразуем результаты в формат для графика
        top_referrers_data = [
            {
                'id': row.id,
                'username': row.username,
                'active_referrals': row.active_referrals
            }
            for row in top_referrers
        ]
        
        # Общие суммы и конверсии
        total_referrals = db.session.query(func.count(User.id)).filter(User.referred_by_id != None).scalar() or 0
        
        active_referrals_count = db.session.query(func.count(User.id)).join(
            Transaction, 
            and_(
                Transaction.user_id == User.id,
                Transaction.status == 'completed',
                Transaction.amount >= min_deposit
            )
        ).filter(
            User.referred_by_id != None
        ).scalar() or 0
        
        conversion_rate = round(active_referrals_count / total_referrals * 100 if total_referrals else 0, 2)
        
        # Возвращаем аналитические данные
        return jsonify({
            'period': period,
            'referrals_per_period': referrals_data,
            'activations_per_period': activations_data,
            'top_referrers': top_referrers_data,
            'total_referrals': total_referrals,
            'active_referrals': active_referrals_count,
            'conversion_rate': conversion_rate
        })
    
    except Exception as e:
        current_app.logger.error(f"Ошибка при получении аналитики: {str(e)}")
        return jsonify({'error': f'Ошибка при получении аналитики: {str(e)}'}), 500

@referral_admin.route('/api/admin/referrals/export', methods=['GET'])
@admin_required
def export_referrals():
    """API для экспорта данных о рефералах в CSV"""
    # Логируем вызов API
    logging.debug(f"export_referrals API call from user: {current_user.id} ({current_user.username})")
    
    try:
        # Параметры фильтрации
        export_type = request.args.get('type', 'referrals')  # referrals, payments
        
        if export_type == 'referrals':
            # Экспорт списка рефералов
            query = db.session.query(
                User.id.label('referral_id'),
                User.username.label('referral_username'),
                User.email.label('referral_email'),
                User.registered_on.label('registration_date'),
                User.referred_by_id,
                User.referral_code
            ).filter(
                User.referred_by_id != None
            )
            
            # Присоединяем данные о рефоводе
            # Создаем алиас для таблицы User для рефоводов
            Referrer = db.aliased(User)
            
            query = query.add_columns(
                Referrer.username.label('referrer_username'),
                Referrer.email.label('referrer_email')
            ).join(
                Referrer, 
                Referrer.id == User.referred_by_id
            )
            
            # Выполняем запрос
            referrals = query.all()
            
            # Создаем CSV-файл в памяти
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Заголовок CSV
            writer.writerow([
                'ID', 'Username', 'Email', 'Registration Date',
                'Referrer ID', 'Referrer Username', 'Referrer Email',
                'Referral Code', 'Total Deposits', 'Status'
            ])
            
            # Добавляем данные
            for row in referrals:
                # Получаем сумму депозитов реферала
                total_deposits = db.session.query(func.sum(Transaction.amount)).filter(
                    Transaction.user_id == row.referral_id,
                    Transaction.status == 'completed'
                ).scalar() or 0
                
                # Получаем статус реферала (активный или ожидающий)
                settings = ReferralSettings.get_current()
                min_deposit = settings.min_deposit_amount
                
                has_min_deposit = db.session.query(Transaction).filter(
                    Transaction.user_id == row.referral_id,
                    Transaction.status == 'completed',
                    Transaction.amount >= min_deposit
                ).first() is not None
                
                status = 'active' if has_min_deposit else 'pending'
                
                writer.writerow([
                    row.referral_id,
                    row.referral_username,
                    row.referral_email,
                    row.registration_date.strftime('%Y-%m-%d %H:%M'),
                    row.referred_by_id,
                    row.referrer_username,
                    row.referrer_email,
                    row.referral_code,
                    total_deposits,
                    status
                ])
            
            # Создаем HTTP-ответ с CSV-файлом
            output.seek(0)
            return Response(
                output,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=referrals_export.csv'}
            )
        
        elif export_type == 'payments':
            # Экспорт выплат рефералам
            payments = ReferralPayment.query.all()
            
            # Создаем CSV-файл в памяти
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Заголовок CSV
            writer.writerow([
                'ID', 'Referrer ID', 'Referrer Username', 'Referrer Email',
                'Referral ID', 'Referral Username', 'Referral Email',
                'Amount', 'Referral Profit', 'Percentage',
                'Created At', 'Paid At', 'Status', 'Notes'
            ])
            
            # Добавляем данные
            for payment in payments:
                # Получаем данные о рефоводе и реферале
                referrer = User.query.get(payment.referrer_id)
                referral = User.query.get(payment.referral_id)
                
                writer.writerow([
                    payment.id,
                    payment.referrer_id,
                    referrer.username if referrer else 'Unknown',
                    referrer.email if referrer else 'Unknown',
                    payment.referral_id,
                    referral.username if referral else 'Unknown',
                    referral.email if referral else 'Unknown',
                    payment.amount,
                    payment.referral_profit,
                    payment.percentage,
                    payment.created_at.strftime('%Y-%m-%d %H:%M'),
                    payment.paid_at.strftime('%Y-%m-%d %H:%M') if payment.paid_at else '',
                    payment.status,
                    payment.notes or ''
                ])
            
            # Создаем HTTP-ответ с CSV-файлом
            output.seek(0)
            return Response(
                output,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=referral_payments_export.csv'}
            )
        
        else:
            return jsonify({'error': 'Неверный тип экспорта'}), 400
    
    except Exception as e:
        current_app.logger.error(f"Ошибка при экспорте данных: {str(e)}")
        return jsonify({'error': f'Ошибка при экспорте данных: {str(e)}'}), 500