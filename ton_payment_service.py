import os
import json
import time
import uuid
import base64
import logging
import io
import qrcode
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

from flask import current_app, session
from werkzeug.utils import secure_filename

from models import db, TonDeposit, User
from ton_client import TonClient
from telegram_notification import notify_new_ton_deposit, notify_ton_deposit_status_change

# Настройки TON
TON_WALLET_ADDRESS = os.environ.get('TON_WALLET_ADDRESS')
TON_API_KEY = os.environ.get('TON_API_KEY')

logger = logging.getLogger(__name__)

class TonPaymentService:
    """
    Сервис для обработки платежей через TON с использованием MEMO
    """
    
    def __init__(self, ton_client: Optional[TonClient] = None):
        """
        Инициализация сервиса платежей
        
        Args:
            ton_client: Клиент для работы с TON API (опционально)
        """
        if ton_client:
            self.ton_client = ton_client
        else:
            self.ton_client = TonClient(
                api_key=TON_API_KEY,
                wallet_address=TON_WALLET_ADDRESS
            )
            
        self.logger = logging.getLogger("ton_payment_service")
        
    def create_deposit(self, user_id: int, amount: float, term_days: Union[int, float]) -> Dict[str, Any]:
        """
        Создает новый депозит с использованием TON
        
        Args:
            user_id: ID пользователя
            amount: Сумма депозита в USDT
            term_days: Срок инвестирования в днях
            
        Returns:
            Dict: Информация о созданном депозите
        """
        try:
            # Проверяем существование пользователя
            user = User.query.get(user_id)
            if not user:
                return {"success": False, "error": "Пользователь не найден"}
                
            # Валидация суммы и срока
            if amount <= 0:
                return {"success": False, "error": "Сумма должна быть больше нуля"}
                
            if term_days <= 0:
                return {"success": False, "error": "Срок должен быть больше нуля"}
                
            # Создаем новый депозит
            deposit = TonDeposit(
                user_id=user_id,
                amount=amount,
                term_days=term_days
            )
            
            # Генерируем QR-код для оплаты
            qr_image = self.generate_payment_qr(deposit.memo, amount)
            
            # Сохраняем QR-код в статические файлы
            qr_filename = f"payment_qr_{deposit.memo}.png"
            static_path = os.path.join(current_app.static_folder, "payment_qr")
            
            # Создаем директорию, если её нет
            os.makedirs(static_path, exist_ok=True)
            
            # Полный путь к файлу
            qr_filepath = os.path.join(static_path, qr_filename)
            qr_image.save(qr_filepath)
            
            # URL для QR-кода
            qr_url = f"/static/payment_qr/{qr_filename}"
            deposit.qr_code_url = qr_url
            
            # Устанавливаем статус
            deposit.status = "payment_awaiting"
            
            # Сохраняем в базу данных
            db.session.add(deposit)
            db.session.commit()
            
            # Примечание: уведомление в Telegram будет отправлено только после нажатия пользователем кнопки "Я оплатил"
            
            return {
                "success": True,
                "deposit": {
                    "id": deposit.id,
                    "memo": deposit.memo,
                    "amount": deposit.amount,
                    "term_days": deposit.term_days,
                    "expected_profit": deposit.expected_profit,
                    "wallet_address": TON_WALLET_ADDRESS,
                    "qr_code_url": qr_url
                }
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании депозита: {str(e)}")
            db.session.rollback()
            return {"success": False, "error": str(e)}
            
    def check_deposit_payment(self, deposit_id: int) -> Dict[str, Any]:
        """
        Проверяет статус оплаты депозита
        
        Args:
            deposit_id: ID депозита
            
        Returns:
            Dict: Информация о статусе платежа
        """
        try:
            deposit = TonDeposit.query.get(deposit_id)
            if not deposit:
                return {"success": False, "error": "Депозит не найден"}
                
            # Если депозит уже оплачен, возвращаем информацию о нем
            if deposit.status == "completed":
                return {"success": True, "status": "completed", "deposit": deposit.to_dict()}
                
            # Проверяем платеж через API
            payment_info = self.ton_client.check_incoming_payment(
                memo=deposit.memo,
                expected_amount=deposit.amount
            )
            
            if payment_info.get("success"):
                # Платеж найден
                transaction = payment_info.get("transaction", {})
                
                # Сохраняем старый статус для уведомления
                old_status = deposit.status
                
                # Обновляем депозит
                deposit.status = "completed"
                deposit.tx_hash = transaction.get("hash")
                deposit.payment_confirmed_at = datetime.utcnow()
                
                # Сохраняем изменения
                db.session.commit()
                
                # Отправляем уведомление в Telegram об изменении статуса платежа
                try:
                    notify_ton_deposit_status_change(
                        user_id=deposit.user_id,
                        amount=deposit.amount,
                        memo=deposit.memo,
                        transaction_id=str(deposit.id),
                        new_status="completed"
                    )
                    self.logger.info(f"Отправлено уведомление в Telegram об изменении статуса депозита #{deposit.id}")
                except Exception as e:
                    self.logger.error(f"Ошибка при отправке уведомления в Telegram: {str(e)}")
                
                return {
                    "success": True,
                    "status": "completed",
                    "deposit": deposit.to_dict(),
                    "transaction": transaction
                }
            else:
                # Платеж не найден
                return {
                    "success": True,
                    "status": "payment_awaiting",
                    "deposit": deposit.to_dict(),
                    "message": "Платеж еще не получен или не обработан"
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка при проверке платежа: {str(e)}")
            return {"success": False, "error": str(e)}
            
    def check_all_pending_deposits(self) -> Dict[str, Any]:
        """
        Проверяет все ожидающие платежи
        
        Returns:
            Dict: Информация о проверенных депозитах
        """
        try:
            # Проверяем депозиты как в статусе "payment_awaiting", так и "pending"
            pending_deposits = TonDeposit.query.filter(
                TonDeposit.status.in_(["payment_awaiting", "pending"])
            ).all()
            
            self.logger.info(f"Проверка {len(pending_deposits)} ожидающих платежей")
            
            if not pending_deposits:
                return {"success": True, "message": "Нет ожидающих платежей", "updated": 0}
                
            updated_count = 0
            
            for deposit in pending_deposits:
                # Сначала обновляем статус до "payment_awaiting", если он "pending"
                if deposit.status == "pending":
                    deposit.status = "payment_awaiting"
                    db.session.commit()
                
                # Логируем проверку конкретного депозита
                self.logger.info(f"Проверка платежа для депозита #{deposit.id} (memo: {deposit.memo}, сумма: {deposit.amount})")
                
                # Проверяем входящий платёж
                payment_info = self.ton_client.check_incoming_payment(
                    memo=deposit.memo,
                    expected_amount=deposit.amount
                )
                
                if payment_info.get("success"):
                    # Платеж найден
                    transaction = payment_info.get("transaction", {})
                    self.logger.info(f"Платеж найден: {transaction}")
                    
                    # Сохраняем старый статус для уведомления
                    old_status = deposit.status
                    
                    # Обновляем депозит
                    deposit.status = "completed"
                    deposit.tx_hash = transaction.get("hash")
                    deposit.payment_confirmed_at = datetime.utcnow()
                    
                    updated_count += 1
                    self.logger.info(f"Платеж подтвержден для депозита #{deposit.id} (memo: {deposit.memo})")
                    
                    # Сохраняем изменения сразу после подтверждения каждого платежа
                    db.session.commit()
                    
                    # Отправляем уведомление в Telegram об изменении статуса платежа
                    try:
                        notify_ton_deposit_status_change(
                            user_id=deposit.user_id,
                            amount=deposit.amount,
                            memo=deposit.memo,
                            transaction_id=str(deposit.id),
                            new_status="completed"
                        )
                        self.logger.info(f"Отправлено уведомление в Telegram об изменении статуса депозита #{deposit.id}")
                    except Exception as e:
                        self.logger.error(f"Ошибка при отправке уведомления в Telegram: {str(e)}")
                else:
                    error = payment_info.get("error", "Неизвестная ошибка")
                    self.logger.warning(f"Платеж не найден для депозита #{deposit.id}: {error}")
                    
            return {
                "success": True,
                "message": f"Проверено {len(pending_deposits)} депозитов, обновлено {updated_count}",
                "updated": updated_count,
                "deposits": [d.id for d in pending_deposits]
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при проверке ожидающих платежей: {str(e)}")
            db.session.rollback()
            return {"success": False, "error": str(e)}
            
    def get_user_deposits(self, user_id: int) -> Dict[str, Any]:
        """
        Получает все депозиты пользователя через TON
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict: Список депозитов пользователя
        """
        try:
            deposits = TonDeposit.query.filter_by(user_id=user_id).order_by(TonDeposit.created_at.desc()).all()
            
            return {
                "success": True,
                "deposits": [deposit.to_dict() for deposit in deposits]
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении депозитов пользователя: {str(e)}")
            return {"success": False, "error": str(e)}
            
    @staticmethod
    def generate_payment_qr(memo: str, amount: float) -> Any:
        """
        Генерирует QR-код для оплаты через Tonkeeper
        
        Args:
            memo: MEMO для платежа
            amount: Сумма платежа в USDT
            
        Returns:
            PIL.Image: Изображение QR-кода
        """
        # Создаем ссылку для оплаты через Tonkeeper
        # Форматируем сумму в наноТОН (1 TON = 1e9 наноТОН)
        # Но так как мы работаем с USDT, просто передаем сумму как есть (в USDT)
        payment_link = f"ton://transfer/{TON_WALLET_ADDRESS}?amount={amount}&text={memo}"
        
        # Создаем QR-код
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(payment_link)
        qr.make(fit=True)
        
        # Создаем изображение
        img = qr.make_image(fill_color="black", back_color="white")
        
        return img

# Глобальный экземпляр сервиса
ton_payment_service = TonPaymentService()