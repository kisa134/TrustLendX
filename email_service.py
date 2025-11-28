import os
import logging
from datetime import datetime
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from flask import current_app, render_template

logger = logging.getLogger(__name__)

# Настройки Brevo API
API_KEY = os.environ.get('BREVO_API_KEY')
SENDER_EMAIL = 'verific@trustlendx.com'
SENDER_NAME = 'TrustLendX'

# Настройки для отслеживания
TRACK_OPENS = True  # Отслеживание открытий писем
TRACK_CLICKS = True  # Отслеживание кликов по ссылкам в письмах

# Настройки для улучшения доставляемости
USE_DKIM = True  # Использовать DKIM подпись (должна быть настроена в DNS)
USE_SPF = True   # Использовать SPF проверку (должна быть настроена в DNS)

# Вывод информации о настройках при запуске модуля
logger.info(f"Email сервис инициализирован. Используется Brevo API.")
logger.info(f"Отправитель: {SENDER_NAME} <{SENDER_EMAIL}>")
logger.info(f"Отслеживание: открытия={TRACK_OPENS}, клики={TRACK_CLICKS}")
logger.info(f"Защита от спама: DKIM={USE_DKIM}, SPF={USE_SPF}")

def send_email(to_email, subject, html_content, text_content=None):
    """
    Отправляет электронное письмо через Brevo API.
    
    Args:
        to_email (str): Email получателя
        subject (str): Тема письма
        html_content (str): HTML содержимое письма
        text_content (str, optional): Текстовое содержимое письма (для клиентов без поддержки HTML)
        
    Returns:
        bool: True если письмо отправлено успешно, иначе False
    """
    if not API_KEY:
        logger.error("BREVO_API_KEY не настроен в переменных окружения")
        return False
        
    try:
        # Конфигурация API
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = API_KEY
        
        # Создаем экземпляр API
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        
        # Создаем отправителя
        sender = sib_api_v3_sdk.SendSmtpEmailSender(name=SENDER_NAME, email=SENDER_EMAIL)
        
        # Создаем получателя
        recipient = {"email": to_email}
        
        # Подготавливаем содержимое
        email_content = {"subject": subject, "html_content": html_content}
        
        # Если есть текстовая версия, добавляем её
        if text_content:
            email_content["plain_content"] = text_content
        
        # Создаем и отправляем email со стандартными настройками
        # Примечание: отслеживание открытий и кликов в Brevo настраивается
        # в панели управления, а не через API
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[recipient],
            sender=sender,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            headers={"X-TrustLendX-Verification": "true"}
        )
        
        # Логируем попытку отправки
        logger.debug(f"Попытка отправки письма через API на {to_email}, тема: {subject}")
        
        # Отправляем письмо
        response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"Письмо успешно отправлено на {to_email}. Message ID: {response.message_id}")
        return True
        
    except ApiException as e:
        logger.error(f"Ошибка Brevo API при отправке письма: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке письма: {str(e)}")
        return False

def send_verification_email(user):
    """
    Отправляет письмо с подтверждением email при регистрации.
    
    Args:
        user: Объект пользователя
        
    Returns:
        bool: True если письмо отправлено успешно, иначе False
    """
    # Генерируем токен для подтверждения
    token = user.generate_email_verification_token()
    
    # Получаем URL для подтверждения
    verification_url = user.get_email_verification_url()
    
    # Формируем тему письма
    subject = "Подтверждение регистрации - TrustLendX"
    
    # Подготавливаем текст письма
    text_content = f"""
    Здравствуйте, {user.username}!
    
    Благодарим Вас за регистрацию на платформе TrustLendX.
    
    Для завершения регистрации и подтверждения вашего email, пожалуйста, перейдите по следующей ссылке:
    {verification_url}
    
    Если Вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.
    
    С уважением,
    Команда TrustLendX
    """
    
    # Подготавливаем HTML версию письма с улучшенным дизайном
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Подтверждение регистрации - TrustLendX</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
            body {{ 
                font-family: 'Roboto', Arial, sans-serif; 
                line-height: 1.6; 
                color: #333; 
                background-color: #f9f9f9;
                margin: 0;
                padding: 0;
            }}
            .container {{ 
                max-width: 600px; 
                margin: 0 auto; 
                padding: 20px;
                background-color: #ffffff;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            }}
            .header {{
                background-color: #1a2b4e;
                padding: 20px;
                text-align: center;
                border-radius: 8px 8px 0 0;
            }}
            .logo {{ 
                text-align: center; 
                margin-bottom: 5px;
                color: #ffffff;
            }}
            .logo h1 {{
                margin: 0;
                font-size: 28px;
                font-weight: 500;
            }}
            .content {{
                padding: 20px 30px;
            }}
            .button {{ 
                display: inline-block; 
                padding: 12px 24px; 
                background-color: #007bff; 
                color: white !important; 
                text-decoration: none; 
                border-radius: 4px; 
                margin: 20px 0;
                font-weight: 500;
                transition: background-color 0.2s ease;
            }}
            .button:hover {{
                background-color: #0056b3;
            }}
            .footer {{ 
                margin-top: 30px; 
                padding-top: 20px;
                font-size: 13px; 
                color: #777; 
                text-align: center;
                border-top: 1px solid #eeeeee;
            }}
            .link {{
                color: #007bff;
                text-decoration: none;
            }}
            .small-text {{
                font-size: 12px;
                color: #999;
            }}
            @media only screen and (max-width: 600px) {{
                .container {{
                    width: 100%;
                    border-radius: 0;
                }}
                .header {{
                    border-radius: 0;
                }}
                .content {{
                    padding: 15px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">
                    <h1>TrustLendX</h1>
                </div>
            </div>
            <div class="content">
                <p>Здравствуйте, <strong>{user.username}</strong>!</p>
                <p>Благодарим Вас за регистрацию на платформе TrustLendX.</p>
                <p>Для завершения регистрации и подтверждения вашего email, пожалуйста, нажмите на кнопку ниже:</p>
                <p style="text-align: center;">
                    <a href="{verification_url}" class="button">Подтвердить Email</a>
                </p>
                <p>Или перейдите по следующей ссылке:</p>
                <p><a href="{verification_url}" class="link">{verification_url}</a></p>
                <p>Если Вы не регистрировались на нашем сайте, просто проигнорируйте это письмо.</p>
                
                <div class="footer">
                    <p>С уважением,<br><strong>Команда TrustLendX</strong></p>
                    <p class="small-text">© {datetime.now().year} TrustLendX. Все права защищены.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Отправляем письмо
    return send_email(user.email, subject, html_content, text_content)