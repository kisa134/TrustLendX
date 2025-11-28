import os
import json
import time
import logging
import requests
from typing import Dict, List, Optional, Any, Union

class TonClient:
    """
    Клиент для работы с сетью TON через Toncenter API
    Предназначен для отслеживания входящих транзакций на указанный кошелек
    """
    API_BASE_URL = "https://toncenter.com/api/v2"
    
    def __init__(self, api_key: str = None, wallet_address: str = None):
        """
        Инициализация клиента TON
        
        Args:
            api_key: API ключ от Toncenter
            wallet_address: Адрес кошелька для мониторинга
        """
        self.api_key = api_key or os.environ.get("TON_API_KEY", "")
        self.wallet_address = wallet_address or os.environ.get("TON_WALLET_ADDRESS", "")
        self.logger = logging.getLogger("ton_client")
        
        # Проверяем наличие ключа API и адреса кошелька
        if not self.api_key:
            self.logger.warning("API ключ Toncenter не указан")
        if not self.wallet_address:
            self.logger.warning("Адрес кошелька TON не указан")
            
    def _make_request(self, endpoint: str, method: str = "GET", params: Dict = None) -> Dict:
        """
        Выполняет запрос к Toncenter API
        
        Args:
            endpoint: Конечная точка API
            method: HTTP метод (GET, POST)
            params: Параметры запроса
            
        Returns:
            Dict: Результат запроса
        """
        url = f"{self.API_BASE_URL}/{endpoint}"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=params)
            else:
                raise ValueError(f"Неподдерживаемый HTTP метод: {method}")
                
            response.raise_for_status()  # Вызовет исключение для ошибок HTTP
            data = response.json()
            
            if data.get("ok") == False:
                error_message = data.get("error", "Неизвестная ошибка")
                self.logger.error(f"Ошибка API: {error_message}")
                return {"success": False, "error": error_message}
                
            return {"success": True, "result": data.get("result")}
            
        except requests.RequestException as e:
            self.logger.error(f"Ошибка запроса: {str(e)}")
            return {"success": False, "error": str(e)}
            
    def get_wallet_info(self) -> Dict:
        """
        Получает информацию о кошельке
        
        Returns:
            Dict: Информация о кошельке
        """
        return self._make_request("getAddressInformation", params={"address": self.wallet_address})
        
    def get_transactions(self, limit: int = 100) -> Dict:
        """
        Получает последние транзакции кошелька
        
        Args:
            limit: Максимальное количество транзакций
            
        Returns:
            Dict: Список транзакций
        """
        return self._make_request("getTransactions", params={
            "address": self.wallet_address,
            "limit": limit
        })
        
    def check_incoming_payment(self, memo: str, expected_amount: Optional[float] = None) -> Dict:
        """
        Проверяет входящий платеж с указанным MEMO (комментарием)
        
        Args:
            memo: Комментарий к платежу (MEMO)
            expected_amount: Ожидаемая сумма (опционально)
            
        Returns:
            Dict: Информация о найденной транзакции или ошибка
        """
        self.logger.info(f"Проверка платежа с MEMO: {memo}, ожидаемая сумма: {expected_amount}")
        
        # Логирование проверки платежа
        self.logger.info(f"Начинаем проверку платежа с MEMO: {memo} через TonCenter API")
            
        try:
            # Получаем последние транзакции
            tx_result = self.get_transactions(limit=200)  # Увеличиваем лимит до 200 транзакций
            if not tx_result.get("success"):
                self.logger.error(f"Ошибка получения транзакций: {tx_result.get('error', 'Неизвестная ошибка')}")
                
                # Логируем ошибку получения транзакций
                self.logger.error("Не удалось получить транзакции от TonCenter API. Требуется ручная проверка.")
                
                return tx_result
                
            transactions = tx_result.get("result", [])
            self.logger.info(f"Получено {len(transactions)} транзакций для проверки")
            
            # Ищем транзакцию с нужным MEMO
            for tx in transactions:
                # Проверяем, что это входящая транзакция (in_msg)
                if "in_msg" not in tx or "message" not in tx["in_msg"]:
                    continue
                    
                tx_message = tx["in_msg"]["message"]
                # Проверяем наличие MEMO в сообщении (не обязательно точное соответствие)
                if memo in tx_message:
                    # Конвертируем из наноТОН в ТОН (1 TON = 1e9 nanoTON)
                    amount = int(tx["in_msg"]["value"]) / 1e9
                    self.logger.info(f"Найдена транзакция с MEMO: {memo}, сумма: {amount}")
                    
                    # Если ожидаемая сумма указана, проверяем её с допуском 0.01 USDT
                    if expected_amount and abs(amount - expected_amount) > 0.01:
                        self.logger.warning(f"Неправильная сумма: ожидалось {expected_amount} USDT, получено {amount} USDT")
                        return {
                            "success": False, 
                            "error": f"Неправильная сумма: ожидалось {expected_amount} USDT, получено {amount} USDT"
                        }
                    
                    return {
                        "success": True,
                        "transaction": {
                            "hash": tx.get("transaction_id", {}).get("hash", ""),
                            "lt": tx.get("transaction_id", {}).get("lt", ""),
                            "amount": amount,
                            "memo": memo,
                            "message": tx_message,  # Добавляем полное сообщение для отладки
                            "timestamp": tx.get("utime", 0)
                        }
                    }
        except Exception as e:
            self.logger.error(f"Ошибка при проверке платежа: {str(e)}")
            
            # Логируем ошибку и рекомендуем ручную проверку
            self.logger.error(f"Ошибка API при проверке платежа с MEMO {memo}. Требуется ручная проверка в админ-панели.")
                
            return {"success": False, "error": str(e)}
            
        self.logger.warning(f"Транзакция с MEMO {memo} не найдена среди {len(transactions)} последних транзакций")
        return {"success": False, "error": "Транзакция не найдена"}
        
    def check_balance(self) -> Dict:
        """
        Проверяет баланс кошелька
        
        Returns:
            Dict: Баланс кошелька в TON
        """
        info = self.get_wallet_info()
        if not info.get("success"):
            return info
            
        balance_nano = int(info.get("result", {}).get("balance", 0))
        balance_ton = balance_nano / 1e9
        
        return {
            "success": True,
            "balance": balance_ton
        }