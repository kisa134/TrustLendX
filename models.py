import os
import pyotp
import base64
import time
import json
import logging
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask import request, url_for
from app import db, login_manager

@login_manager.user_loader
def load_user(user_id):
    import logging
    logging.debug(f"Loading user with ID: {user_id}")
    if user_id is None:
        return None
    user = User.query.get(int(user_id))
    logging.debug(f"User loaded: {user}")
    return user

class ReferralSettings(db.Model):
    """
    Модель для хранения настроек реферальной системы
    Связана с системой администрирования реферальной программы
    """
    id = db.Column(db.Integer, primary_key=True)
    min_deposit_amount = db.Column(db.Float, default=100.0)  # Минимальная сумма депозита для учета реферала (USDT)
    referral_percentage = db.Column(db.Float, default=20.0)  # Процент вознаграждения (%)
    active = db.Column(db.Boolean, default=True)  # Активна ли реферальная программа
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Дата последнего обновления
    updated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Кто последним обновил настройки
    description = db.Column(db.Text, nullable=True)  # Описание изменений
    
    # Получение текущих настроек
    @classmethod
    def get_current(cls):
        """Возвращает текущие настройки или создает значения по умолчанию"""
        settings = cls.query.order_by(cls.id.desc()).first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings

class ReferralPayment(db.Model):
    """
    Модель для отслеживания выплат рефералам
    Каждая запись представляет выплату рефоводу за прибыль реферала
    """
    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # ID рефовода
    referral_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # ID реферала
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=True)  # Связанная транзакция
    amount = db.Column(db.Float, nullable=False)  # Сумма выплаты (USDT)
    referral_profit = db.Column(db.Float, nullable=False)  # Прибыль реферала (USDT)
    percentage = db.Column(db.Float, nullable=False)  # Использованный процент
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Дата создания записи
    paid_at = db.Column(db.DateTime, nullable=True)  # Дата фактической выплаты
    status = db.Column(db.String(20), default='pending')  # Статус: pending, paid, canceled
    notes = db.Column(db.Text, nullable=True)  # Примечания
    
    # Связи для быстрого доступа
    referrer = db.relationship('User', foreign_keys=[referrer_id], backref='referral_payments_received')
    referral = db.relationship('User', foreign_keys=[referral_id], backref='referral_payments_generated')
    transaction = db.relationship('Transaction', backref='referral_payments')
    
    @property
    def is_paid(self):
        """Проверяет, была ли выплата совершена"""
        return self.status == 'paid' and self.paid_at is not None

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    registered_on = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)  # Флаг для определения администратора
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    ton_deposits = db.relationship('TonDeposit', backref='user', lazy=True)  # Связь с TON депозитами
    
    # Поля для реферальной системы
    referral_code = db.Column(db.String(10), unique=True, nullable=True)  # Уникальный код пользователя
    referred_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # ID пригласившего пользователя
    referrals = db.relationship('User', backref=db.backref('referred_by', remote_side=[id]), lazy='dynamic')  # Список приглашенных
    referral_earnings = db.Column(db.Float, default=0.0)  # Общий заработок от рефералов
    
    # Поля для верификации email
    email_verified = db.Column(db.Boolean, default=False)  # Статус верификации email
    email_verification_token = db.Column(db.String(100), nullable=True)  # Токен для верификации email
    email_verification_token_expires = db.Column(db.DateTime, nullable=True)  # Срок действия токена
    
    def generate_email_verification_token(self, expires_in=86400):
        """
        Генерирует токен для подтверждения email.
        
        Args:
            expires_in: Срок действия токена в секундах (по умолчанию 24 часа)
            
        Returns:
            str: Сгенерированный токен
        """
        token = secrets.token_urlsafe(64)
        self.email_verification_token = token
        self.email_verification_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        db.session.commit()
        return token
        
    def verify_email(self, token):
        """
        Проверяет токен подтверждения email и устанавливает email как подтвержденный.
        
        Args:
            token: Токен для проверки
            
        Returns:
            bool: True если токен верный и email подтвержден, иначе False
        """
        if not token or token != self.email_verification_token:
            return False
            
        if self.email_verification_token_expires is None or self.email_verification_token_expires < datetime.utcnow():
            return False
            
        self.email_verified = True
        self.email_verification_token = None
        self.email_verification_token_expires = None
        return True
        
    def get_email_verification_url(self, _external=True):
        """
        Получает URL для подтверждения email.
        
        Args:
            _external: Создать абсолютный URL
            
        Returns:
            str: URL для подтверждения email
        """
        if not self.email_verification_token:
            return None
            
        return url_for('verify_email', token=self.email_verification_token, _external=_external)
    
    # Поля для двухфакторной аутентификации
    otp_secret = db.Column(db.String(32), nullable=True)
    otp_enabled = db.Column(db.Boolean, default=False)
    otp_verified = db.Column(db.Boolean, default=False)
    last_otp_used = db.Column(db.String(6), nullable=True)  # Для предотвращения повторного использования
    auth_attempts = db.Column(db.Integer, default=0)  # Для контроля попыток входа
    last_auth_attempt = db.Column(db.DateTime, nullable=True)  # Для временной блокировки
    
    def set_password(self, password):
        """
        Устанавливает хеш пароля для пользователя.
        Метод использует werkzeug.security.generate_password_hash с pbkdf2 алгоритмом,
        который включает соль и 260000 итераций хеширования.
        
        Args:
            password: Пароль в открытом виде (не сохраняется в системе)
        """
        # Метод pbkdf2:sha256 по умолчанию, соль генерируется автоматически
        # Увеличено число итераций для большей безопасности
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:260000')
        
    def check_password(self, password):
        """
        Проверяет пароль в открытом виде с хешем пароля пользователя.
        
        Args:
            password: Пароль в открытом виде для проверки
            
        Returns:
            bool: True если пароль верный, иначе False
        """
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def get_total_balance(self):
        """Calculate total active balance across all user's deposits minus withdrawals"""
        # Считаем как традиционные депозиты, так и TON депозиты
        active_transactions = [t for t in self.transactions if t.status == 'completed']
        active_ton_deposits = [t for t in self.ton_deposits if t.status == 'completed']
        
        normal_balance = sum(t.amount for t in active_transactions)
        ton_balance = sum(t.amount for t in active_ton_deposits)
        
        # Вычитаем выведенные средства
        total_withdrawn = self.get_total_withdrawn()
        
        # Возвращаем фактический баланс
        return max(0, (normal_balance + ton_balance) - total_withdrawn)
        
    def get_expected_profit(self):
        """Calculate expected profit across all active deposits based on actual current balance"""
        # Получаем фактический остаток на счете
        total_balance = self.get_total_balance()
        
        # Если баланс равен нулю, прибыль невозможна
        if total_balance <= 0:
            return 0.0
            
        # Считаем сумму всех активных вкладов
        active_transactions = [t for t in self.transactions if t.status == 'completed']
        active_ton_deposits = [t for t in self.ton_deposits if t.status == 'completed']
        
        original_sum = sum(t.amount for t in active_transactions) + sum(t.amount for t in active_ton_deposits)
        
        # Считаем всю прибыль от действующих вкладов
        normal_profits = sum(t.expected_profit for t in active_transactions if t.expected_profit)
        ton_profits = sum(t.expected_profit for t in active_ton_deposits if t.expected_profit)
        total_profits = normal_profits + ton_profits
        
        # Если не было вывода средств, возвращаем полную прибыль
        total_withdrawn = self.get_total_withdrawn()
        if total_withdrawn <= 0 or original_sum == 0:
            return total_profits
            
        # Пропорционально уменьшаем прибыль в соответствии с текущим балансом
        # Формула: (фактический_баланс / изначальная_сумма_вкладов) * полная_прибыль
        adjusted_profit = (total_balance / original_sum) * total_profits
        
        return round(adjusted_profit, 2)
        
    def get_completed_withdrawals(self):
        """Получить все завершенные запросы на вывод средств"""
        return [w for w in self.withdrawal_requests if w.status == 'completed']
        
    def get_total_withdrawn(self):
        """Получить общую сумму выведенных средств"""
        completed_withdrawals = self.get_completed_withdrawals()
        return sum(w.amount for w in completed_withdrawals)
        
    def decrease_balance(self, amount):
        """Уменьшает баланс пользователя на указанную сумму
        
        Используется при выводе средств после подтверждения админом.
        Проверяет наличие достаточного количества средств, а затем
        фактически уменьшает суммы активных депозитов пользователя,
        начиная с самых новых.
        
        Returns:
            bool: True если баланс успешно уменьшен, False если недостаточно средств
        """
        if amount <= 0:
            return False
            
        current_balance = self.get_total_balance()
        if current_balance < amount:
            return False
        
        # Фактическое уменьшение баланса активных депозитов
        remaining_amount = amount
        
        # Сначала уменьшаем TON депозиты, начиная с самых новых
        active_ton_deposits = [t for t in self.ton_deposits if t.status == 'completed']
        active_ton_deposits.sort(key=lambda t: t.created_at, reverse=True)  # Сортировка от новых к старым
        
        for deposit in active_ton_deposits:
            if remaining_amount <= 0:
                break
                
            if deposit.amount <= remaining_amount:
                # Используем весь депозит
                remaining_amount -= deposit.amount
                deposit.status = 'withdrawn'
                deposit.withdrawal_date = datetime.utcnow()
            else:
                # Используем часть депозита
                deposit.amount -= remaining_amount
                # Пересчитываем ожидаемую прибыль для депозита с новой суммой
                deposit.calculate_expected_profit()
                remaining_amount = 0
        
        # Если остался неиспользованный остаток, уменьшаем обычные транзакции
        if remaining_amount > 0:
            active_transactions = [t for t in self.transactions if t.status == 'completed']
            active_transactions.sort(key=lambda t: t.date, reverse=True)  # Сортировка от новых к старым
            
            for transaction in active_transactions:
                if remaining_amount <= 0:
                    break
                    
                if transaction.amount <= remaining_amount:
                    # Используем всю транзакцию
                    remaining_amount -= transaction.amount
                    transaction.status = 'withdrawn'
                    transaction.withdrawal_date = datetime.utcnow()
                else:
                    # Используем часть транзакции
                    transaction.amount -= remaining_amount
                    # Пересчитываем ожидаемую прибыль для транзакции с новой суммой
                    transaction.calculate_expected_profit()
                    remaining_amount = 0
        
        # В этой точке баланс должен быть уменьшен на полную сумму
        return True
    
    def promote_to_admin(self):
        """Назначить пользователя администратором"""
        self.is_admin = True
        
    def demote_from_admin(self):
        """Убрать права администратора"""
        self.is_admin = False
    
    # Методы для двухфакторной аутентификации
    def generate_otp_secret(self):
        """Генерирует секретный ключ для 2FA"""
        if not self.otp_secret:
            self.otp_secret = base64.b32encode(os.urandom(15)).decode('utf-8')
        return self.otp_secret
    
    def get_otp_uri(self):
        """Получает URI для QR-кода 2FA"""
        service_name = "TrustLendX"
        return pyotp.totp.TOTP(self.otp_secret).provisioning_uri(
            name=self.email, 
            issuer_name=service_name
        )
    
    def verify_otp(self, otp_code):
        """Проверяет OTP-код"""
        if not self.otp_enabled or not self.otp_secret:
            return True
        
        if otp_code == self.last_otp_used:
            return False  # Предотвращение повторного использования
        
        totp = pyotp.TOTP(self.otp_secret)
        valid = totp.verify(otp_code)
        
        if valid:
            self.last_otp_used = otp_code
            self.auth_attempts = 0  # Сброс счетчика при успешной аутентификации
        
        return valid
    
    def enable_otp(self):
        """Включает 2FA"""
        if not self.otp_secret:
            self.generate_otp_secret()
        self.otp_enabled = True
    
    def disable_otp(self):
        """Отключает 2FA"""
        self.otp_enabled = False
    
    def is_account_locked(self):
        """Проверяет, заблокирован ли аккаунт из-за множественных попыток входа"""
        if self.auth_attempts >= 5 and self.last_auth_attempt:
            # Если прошло меньше 15 минут с последней попытки и их было >= 5
            time_diff = (datetime.utcnow() - self.last_auth_attempt).total_seconds()
            if time_diff < 900:  # 15 минут = 900 секунд
                return True
        return False
    
    def increment_auth_attempts(self):
        """Увеличивает счетчик попыток входа"""
        self.auth_attempts += 1
        self.last_auth_attempt = datetime.utcnow()
        

        
    def __repr__(self):
        return f'<User {self.username}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(64), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, payment_awaiting, completed, failed, expired
    deposit_start_date = db.Column(db.DateTime, default=datetime.utcnow)
    deposit_end_date = db.Column(db.DateTime)
    term_months = db.Column(db.Integer)
    expected_profit = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Поля для интеграции с платежным шлюзом
    payment_id = db.Column(db.String(64))  # ID платежа в системе NOWPayments
    payment_url = db.Column(db.String(255))  # Ссылка для оплаты
    payment_currency = db.Column(db.String(10), default='BTC')  # Валюта платежа
    payment_amount = db.Column(db.Float)  # Сумма в криптовалюте
    payment_status = db.Column(db.String(20))  # Статус платежа в системе NOWPayments
    payment_completed_at = db.Column(db.DateTime)  # Дата завершения платежа
    
    def calculate_expected_profit(self):
        """Calculate expected profit based on amount and term"""
        from utils import calculate_profit_for_term
        
        if self.amount <= 0:
            self.expected_profit = 0
            return 0
        
        # Проверяем специальный случай для тестового 5-минутного депозита админа
        if self.term_months is not None and self.term_months < 0.1 and self.deposit_end_date:
            # Проверяем, что разница между датами составляет примерно 5 минут
            time_diff_minutes = (self.deposit_end_date - self.deposit_start_date).total_seconds() / 60
            
            if 4.5 <= time_diff_minutes <= 5.5:  # Примерно 5 минут с погрешностью
                # Используем 5-минутный тестовый режим
                self.expected_profit = calculate_profit_for_term(self.amount, term_minutes=5)
                return self.expected_profit
                
        if self.term_months <= 0:
            self.expected_profit = 0
            return 0
            
        # Используем общую функцию для расчета прибыли по месяцам
        self.expected_profit = calculate_profit_for_term(self.amount, term_months=self.term_months)
        return self.expected_profit
    
    def __repr__(self):
        return f'<Transaction {self.transaction_id}>'
        
class TonDeposit(db.Model):
    """Модель депозита с использованием TON и MEMO"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # Сумма депозита в USDT
    memo = db.Column(db.String(64), unique=True, nullable=False)  # Уникальный MEMO для идентификации платежа
    status = db.Column(db.String(20), default='pending')  # pending, payment_awaiting, completed, failed, expired
    deposit_start_date = db.Column(db.DateTime, default=datetime.utcnow)  # Дата создания депозита
    deposit_end_date = db.Column(db.DateTime)  # Дата окончания инвестиционного срока
    term_days = db.Column(db.Integer)  # Срок инвестирования в днях
    expected_profit = db.Column(db.Float)  # Ожидаемая прибыль
    tx_hash = db.Column(db.String(128))  # Хеш транзакции в блокчейне TON
    payment_confirmed_at = db.Column(db.DateTime)  # Время подтверждения платежа
    qr_code_url = db.Column(db.String(255))  # URL изображения QR-кода для оплаты
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __init__(self, user_id, amount, term_days):
        """
        Инициализация нового депозита
        
        Args:
            user_id: ID пользователя
            amount: Сумма депозита в USDT
            term_days: Срок инвестирования в днях (или доли дня для минут)
        """
        self.user_id = user_id
        self.amount = float(amount)
        self.term_days = float(term_days)  # Используем float для поддержки минут
        self.memo = f"INV_{user_id}_{int(time.time())}"  # Формат: INV_USERID_TIMESTAMP
        self.status = "pending"
        self.deposit_start_date = datetime.utcnow()
        
        # Обрабатываем специальный тестовый случай для минут
        if term_days < 0.01:  # Меньше 1/100 дня ~ менее 15 минут 
            minutes = int(term_days * 24 * 60)  # Преобразуем дни в минуты
            self.deposit_end_date = self.deposit_start_date + timedelta(minutes=minutes)
        else:
            # Обычный случай для дней, недель, месяцев
            self.deposit_end_date = self.deposit_start_date + timedelta(days=term_days)
            
        self.calculate_expected_profit()
    
    def calculate_expected_profit(self):
        """Рассчитывает ожидаемую прибыль на основе суммы и срока"""
        from utils import calculate_profit_for_term
        
        # Преобразуем к числовым типам для безопасности
        amount = float(self.amount)
        term_days = float(self.term_days)  # Используем float для поддержки дробных дней (минуты)
        
        if amount <= 0 or term_days <= 0:
            self.expected_profit = 0.0
            return 0.0
        
        # Проверяем, является ли это тестовым 5-минутным вкладом
        if term_days < 0.01:  # Очень малое значение дней (минуты)
            term_minutes = int(term_days * 24 * 60)  # Конвертируем дни в минуты
            self.expected_profit = float(calculate_profit_for_term(amount, term_minutes=term_minutes))
        # Определяем тип срока на основе количества дней    
        elif term_days <= 28:  # 4 недели максимум (4 * 7 = 28 дней)
            # Если срок до 28 дней включительно, считаем как недели
            term_weeks = int(term_days // 7)
            if term_days % 7 > 0:  # Если есть остаток, округляем вверх
                term_weeks += 1
            
            # Ограничиваем максимум 4 недели
            term_weeks = min(term_weeks, 4)
            
            # Используем недельные ставки
            self.expected_profit = float(calculate_profit_for_term(amount, term_weeks=term_weeks))
        else:
            # Если срок более 28 дней, считаем как месяцы
            term_months = term_days / 30.0
            
            # Используем месячные ставки со сложным процентом
            self.expected_profit = float(calculate_profit_for_term(amount, term_months=term_months))
            
        return self.expected_profit
    
    def to_dict(self):
        """Преобразует модель в словарь для API"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "memo": self.memo,
            "status": self.status,
            "deposit_start_date": self.deposit_start_date.isoformat() if self.deposit_start_date else None,
            "deposit_end_date": self.deposit_end_date.isoformat() if self.deposit_end_date else None,
            "term_days": self.term_days,
            "expected_profit": self.expected_profit,
            "tx_hash": self.tx_hash,
            "payment_confirmed_at": self.payment_confirmed_at.isoformat() if self.payment_confirmed_at else None,
            "qr_code_url": self.qr_code_url,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<TonDeposit {self.memo}>'


class UserIPLog(db.Model):
    """Модель для хранения IP-адресов пользователей"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # IPv6 может быть до 45 символов
    user_agent = db.Column(db.String(512), nullable=True)  # User-Agent браузера
    activity_type = db.Column(db.String(50), nullable=False)  # Тип активности: login, register, deposit, withdraw, etc.
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # Дата и время записи
    
    # Связь с моделью User
    user = db.relationship('User', backref=db.backref('ip_logs', lazy=True))
    
    def __repr__(self):
        return f'<UserIPLog {self.ip_address} - {self.activity_type}>'


class DemoTransaction(db.Model):
    """Модель для хранения демонстрационных транзакций на главной странице"""
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(64), unique=True)
    masked_user = db.Column(db.String(64))  # Маскированное имя пользователя
    amount = db.Column(db.Float, nullable=False)  # Сумма транзакции
    amount_formatted = db.Column(db.String(64))  # Отформатированная сумма для отображения
    type = db.Column(db.String(20))  # Тип: Депозит или Вывод
    status = db.Column(db.String(20))  # Статус: Завершено или Отклонено
    date = db.Column(db.String(30))  # Дата в формате строки для отображения
    timestamp = db.Column(db.Float)  # Временная метка для сортировки
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Время создания записи
    
    def __repr__(self):
        return f'<DemoTransaction {self.transaction_id} - {self.amount_formatted}>'

class ContactMessage(db.Model):
    """Модель для хранения сообщений от пользователей через форму обратной связи"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<ContactMessage {self.id} - {self.subject}>'


class WithdrawalRequest(db.Model):
    """Модель для запросов на вывод средств"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # Сумма вывода в USDT
    wallet_address = db.Column(db.String(150), nullable=False)  # Адрес кошелька для вывода
    network = db.Column(db.String(20), default="TON")  # Сеть для вывода
    memo = db.Column(db.Text, nullable=True)  # Комментарий пользователя к выводу
    status = db.Column(db.String(20), default="pending")  # pending, approved, completed, rejected
    admin_comment = db.Column(db.Text, nullable=True)  # Комментарий администратора
    tx_hash = db.Column(db.String(128), nullable=True)  # Хеш транзакции вывода
    request_date = db.Column(db.DateTime, default=datetime.utcnow)  # Дата запроса
    processed_date = db.Column(db.DateTime, nullable=True)  # Дата обработки запроса
    
    # Связь с пользователем
    user = db.relationship('User', backref='withdrawal_requests', lazy=True)
    
    def __repr__(self):
        return f'<WithdrawalRequest {self.id} - {self.amount} USDT>'
    
    def to_dict(self):
        """Преобразует модель в словарь для API"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "wallet_address": self.wallet_address,
            "network": self.network,
            "memo": self.memo,
            "status": self.status,
            "admin_comment": self.admin_comment,
            "tx_hash": self.tx_hash,
            "request_date": self.request_date.isoformat() if self.request_date else None,
            "processed_date": self.processed_date.isoformat() if self.processed_date else None,
            "username": self.user.username if self.user else "Unknown"
        }

class AdminNotification(db.Model):
    """Модель для уведомлений администраторам"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(20), default="info")  # info, payment, warning, error
    related_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    related_transaction_id = db.Column(db.Integer, nullable=True)  # ID транзакции (обычной или TON)
    transaction_type = db.Column(db.String(10), nullable=True)  # "ton" или "regular"
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь с пользователем (опциональная)
    related_user = db.relationship('User', backref='notifications', lazy=True, foreign_keys=[related_user_id])
    
    def __repr__(self):
        return f'<AdminNotification {self.id} - {self.title}>'
    
    def to_dict(self):
        """Преобразует модель в словарь для API"""
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "notification_type": self.notification_type,
            "related_user_id": self.related_user_id,
            "related_transaction_id": self.related_transaction_id,
            "transaction_type": self.transaction_type,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class ProxySettings(db.Model):
    """Модель для хранения настроек прокси-серверов для внешних API"""
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(50), nullable=False, unique=True)  # getblock или nowpayments
    host = db.Column(db.String(255))
    port = db.Column(db.Integer)
    username = db.Column(db.String(100))
    password = db.Column(db.String(100))
    enabled = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProxySettings {self.service_name}>'
        
    def get_proxy_url(self):
        """Возвращает URL для настройки прокси в формате для requests"""
        if not self.enabled or not self.host:
            return None
            
        auth = ""
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
            
        return f"http://{auth}{self.host}:{self.port}"
        
    def get_proxies_dict(self):
        """Возвращает словарь с настройками прокси для requests"""
        proxy_url = self.get_proxy_url()
        if not proxy_url:
            return None
            
        return {
            "http": proxy_url,
            "https": proxy_url
        }
