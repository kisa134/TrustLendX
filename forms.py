from flask_wtf import FlaskForm
from wtforms import Form, StringField, PasswordField, SubmitField, FloatField, IntegerField, TextAreaField, validators, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, NumberRange
from models import User

class ManualEmailVerificationForm(FlaskForm):
    """
    Форма для ручной верификации email
    Используется в случае проблем с отправкой писем
    """
    email = StringField('Email', validators=[
        DataRequired(), 
        Email(message='Пожалуйста, введите корректный email адрес')
    ])
    verification_code = StringField('Код активации', validators=[
        DataRequired(),
        Length(min=10, max=100, message='Код верификации должен быть от 10 до 100 символов')
    ])
    submit = SubmitField('Подтвердить')

class WithdrawalForm(FlaskForm):
    """
    Форма для запроса на вывод средств
    Правила валидации:
     - Минимальная сумма: 5 USDT
     - Адрес кошелька TON: мин. 10 символов
    """
    amount = FloatField('Сумма для вывода (USDT)', validators=[
        DataRequired(),
        NumberRange(min=5, message='Минимальная сумма для вывода: 5 USDT')
    ])
    wallet_address = StringField('Адрес кошелька TON', validators=[
        DataRequired(),
        Length(min=10, message='Пожалуйста, введите корректный адрес кошелька TON')
    ])
    memo = TextAreaField('Комментарий', validators=[
        Length(max=200, message='Комментарий должен быть не более 200 символов')
    ])
    submit = SubmitField('Отправить запрос')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    otp_code = StringField('Код двухфакторной аутентификации', validators=[Length(min=0, max=6)])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()], 
                       description='После регистрации на указанный email будет отправлено письмо с ссылкой для подтверждения')
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Подтверждение пароля', validators=[DataRequired(), EqualTo('password', message='Пароли должны совпадать')])
    referral_code = StringField('Реферальный код (если есть)', validators=[Length(max=10)])
    submit = SubmitField('Зарегистрироваться')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Это имя пользователя уже занято. Пожалуйста, выберите другое.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Этот email уже зарегистрирован. Пожалуйста, используйте другой.')

class DepositForm(FlaskForm):
    """
    Форма создания нового вклада с обновленными правилами валидации
    Минимальная сумма: USDT - 1, TRX - 5
    Используется NOWPayments API через прокси-сервер
    """
    amount = FloatField('Сумма инвестиции', validators=[DataRequired()])
    term_type = SelectField('Тип срока', choices=[
        ('minutes', 'Минуты (только для админов)'),
        ('weeks', 'Недели'), 
        ('months', 'Месяцы')
    ], default='months')
    term_value = IntegerField('Срок', validators=[
        DataRequired(), 
        NumberRange(min=1, max=52, message='Срок должен быть от 1 до 52 недель или от 1 до 12 месяцев')
    ])
    crypto_currency = SelectField('Валюта оплаты', choices=[
        ('usdtton', 'USDT (TON)'),
        ('trx', 'TRX (Tron)')
    ], default='usdtton')
    submit = SubmitField('Инвестировать')
    
    def validate_term_value(self, term_value):
        """
        Валидация срока в зависимости от выбранного типа (минуты, недели или месяцы)
        """
        if self.term_type.data == 'minutes':
            # Только 5 минут для тестирования доступно для админов
            if term_value.data != 5:
                raise ValidationError('В режиме тестирования допустимо только значение 5 минут')
        elif self.term_type.data == 'weeks' and term_value.data > 4:
            raise ValidationError('Максимальный срок для недель - 4 недели')
        elif self.term_type.data == 'months' and term_value.data > 12:
            raise ValidationError('Максимальный срок для месяцев - 12 месяцев (1 год)')
    
    def validate_amount(self, amount):
        """
        Валидация суммы в зависимости от выбранной криптовалюты
        USDT: минимум 1 USDT
        TRX: минимум 5 TRX эквивалент
        """
        if not amount.data or amount.data <= 0:
            raise ValidationError('Сумма инвестиции должна быть положительным числом')
        
        # Новые правила минимальной суммы: USDT - 1, TRX - 5
        min_amount = 1.0 if self.crypto_currency.data == 'usdtton' else 5.0
        
        if amount.data < min_amount:
            currency_display = "USDT" if self.crypto_currency.data == 'usdtton' else "TRX"
            raise ValidationError(f'Минимальная сумма инвестиции - {min_amount} {currency_display}')

class ContactForm(FlaskForm):
    name = StringField('Имя', validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    subject = StringField('Тема', validators=[DataRequired(), Length(min=5, max=100)])
    message = TextAreaField('Сообщение', validators=[DataRequired(), Length(min=10, max=1000)])
    submit = SubmitField('Отправить сообщение')

class OTPSetupForm(FlaskForm):
    otp_code = StringField('Код подтверждения', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Подтвердить')

class OTPVerifyForm(FlaskForm):
    otp_code = StringField('Код двухфакторной аутентификации', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Подтвердить')
    
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Текущий пароль', validators=[DataRequired()])
    new_password = PasswordField('Новый пароль', validators=[
        DataRequired(), 
        Length(min=6, message='Пароль должен содержать не менее 6 символов')
    ])
    confirm_password = PasswordField('Подтвердите новый пароль', validators=[
        DataRequired(), 
        EqualTo('new_password', message='Пароли должны совпадать')
    ])
    submit = SubmitField('Изменить пароль')
    
class TonDepositForm(FlaskForm):
    """
    Форма создания нового вклада через TON
    Использует Toncenter API для мониторинга транзакций с MEMO
    Предлагает выбор типа срока (недели/месяцы) с соответствующими процентными ставками
    """
    amount = FloatField('Сумма инвестиции (USDT)', validators=[
        DataRequired(),
        NumberRange(min=5, message='Минимальная сумма для инвестиции - 5 USDT')
    ])
    term_type = SelectField('Тип срока', choices=[
        ('weeks', 'Недели'),
        ('months', 'Месяцы')
    ], default='months')
    term_value = IntegerField('Срок', validators=[
        DataRequired(), 
        NumberRange(min=1, max=52, message='Срок должен быть от 1 до 4 недель или от 1 до 12 месяцев')
    ])
    submit = SubmitField('Пополнить депозит')
    
    def validate_amount(self, amount):
        """
        Валидация суммы инвестиции
        Минимальная сумма: 10 USDT
        """
        if amount.data <= 0:
            raise ValidationError('Сумма должна быть положительным числом')
            
    def validate_term_value(self, term_value):
        """
        Валидация срока в зависимости от выбранного типа (недели или месяцы)
        Недели: от 1 до 4 недель
        Месяцы: от 1 до 12 месяцев
        """
        if self.term_type.data == 'weeks' and term_value.data > 4:
            raise ValidationError('Максимальный срок для недель - 4 недели')
        elif self.term_type.data == 'months' and term_value.data > 12:
            raise ValidationError('Максимальный срок для месяцев - 12 месяцев (1 год)')
