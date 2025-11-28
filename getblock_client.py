import os
import requests
import logging
import json
import time
from typing import Dict, Any, Optional, List

class GetBlockClient:
    """
    Клиент для работы с API GetBlock для проверки криптоадресов на AML/KYC
    """
    BASE_URL = "https://api.getblock.net/v1"
    
    def __init__(self, api_token: str = ""):
        """
        Инициализация клиента
        
        Args:
            api_token: API токен для доступа к GetBlock. Если не указан, берется из переменной окружения.
        """
        self.api_token = api_token or os.environ.get("GETBLOCK_API_TOKEN") or "RqZUtFDqAiPIhUh6GRBvEKNojW90EMyOJCRgfZ5b"
        self.using_proxy = False
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-KEY": self.api_token
        })
        
        # Настройка прокси-сервера (если необходимо)
        proxy_enabled = os.environ.get("GETBLOCK_PROXY_ENABLED", "false").lower() == "true"
        if proxy_enabled:
            proxy_host = os.environ.get("GETBLOCK_PROXY_HOST", "")
            proxy_port = os.environ.get("GETBLOCK_PROXY_PORT", "")
            proxy_user = os.environ.get("GETBLOCK_PROXY_USER", "")
            proxy_pass = os.environ.get("GETBLOCK_PROXY_PASS", "")
            
            if proxy_host and proxy_port:
                proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}" if proxy_user and proxy_pass else f"http://{proxy_host}:{proxy_port}"
                self.session.proxies = {
                    "http": proxy_url,
                    "https": proxy_url
                }
                self.using_proxy = True
                logging.info(f"GetBlock API будет использовать прокси-сервер: {proxy_host}:{proxy_port}")
    
    def ping(self) -> Dict[str, Any]:
        """
        Проверка доступности API
        
        Returns:
            Dict: Ответ от API
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/ping")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Ошибка при проверке доступности API: {e}")
            return {"success": False, "error": str(e)}

    def get_currency_list(self) -> Dict[str, Any]:
        """
        Получение списка поддерживаемых криптовалют
        
        Returns:
            Dict: Список поддерживаемых валют
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/currencylist")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Ошибка при получении списка валют: {e}")
            return {"success": False, "error": str(e)}
    
    def check_address(self, address: str, currency: str) -> Dict[str, Any]:
        """
        Отправка адреса на проверку
        
        Args:
            address: Криптоадрес для проверки
            currency: Валюта адреса (BTC, ETH, TRX и т.д.)
            
        Returns:
            Dict: Результат операции с ID проверки
        """
        try:
            payload = {
                "address": address,
                "currency": currency
            }
            
            logging.debug(f"Отправка запроса на проверку адреса: {address}, валюта: {currency}")
            logging.debug(f"Использование прокси: {self.using_proxy}")
            
            if self.using_proxy:
                logging.debug(f"Прокси-настройки: {self.session.proxies}")
            
            # Дополнительная проверка состояния сессии
            logging.debug(f"Заголовки запроса: {self.session.headers}")
                        
            response = self.session.post(
                f"{self.BASE_URL}/checkaddr",
                data=json.dumps(payload),
                timeout=20  # Увеличиваем таймаут для работы через прокси
            )
            
            logging.debug(f"Статус ответа: {response.status_code}")
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Ошибка при отправке адреса на проверку: {e}")
            # Так как payload определен выше в блоке try, он доступен здесь
            logging.error(f"Детали запроса: адрес={address}, валюта={currency}")
            
            # Пытаемся получить детали ответа сервера, если они есть
            error_details = ""
            response_text = ""
            
            if hasattr(e, 'response') and e.response:
                try:
                    response_text = e.response.text
                    error_details = f"Статус: {e.response.status_code}, Ответ: {response_text}"
                except:
                    error_details = "Не удалось извлечь детали ответа"
            
            return {
                "success": False, 
                "error": str(e),
                "error_details": error_details,
                "response_text": response_text
            }
    
    def get_result(self, check_id: str) -> Dict[str, Any]:
        """
        Получение результатов проверки
        
        Args:
            check_id: ID проверки
            
        Returns:
            Dict: Результаты проверки
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/getresult?id={check_id}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Ошибка при получении результатов проверки: {e}")
            return {"success": False, "error": str(e)}
    
    def find_report(self, address: str, currency: str) -> Dict[str, Any]:
        """
        Поиск отчета о проверке адреса
        
        Args:
            address: Криптоадрес
            currency: Валюта адреса
            
        Returns:
            Dict: Информация о найденных отчетах
        """
        try:
            payload = {
                "address": address,
                "currency": currency
            }
            
            logging.debug(f"Поиск отчетов для адреса: {address}, валюта: {currency}")
            logging.debug(f"Использование прокси: {self.using_proxy}")
            
            response = self.session.post(
                f"{self.BASE_URL}/findreport",
                data=json.dumps(payload),
                timeout=20  # Увеличиваем таймаут для работы через прокси
            )
            
            logging.debug(f"Статус ответа при поиске отчета: {response.status_code}")
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Ошибка при поиске отчета: {e}")
            
            # Пытаемся получить детали ответа сервера, если они есть
            error_details = ""
            response_text = ""
            
            if hasattr(e, 'response') and e.response:
                try:
                    response_text = e.response.text
                    error_details = f"Статус: {e.response.status_code}, Ответ: {response_text}"
                except:
                    error_details = "Не удалось извлечь детали ответа"
            
            return {
                "success": False, 
                "error": str(e),
                "error_details": error_details,
                "response_text": response_text
            }
    
    def get_checks_history(self, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """
        Получение истории проверок
        
        Args:
            page: Номер страницы
            limit: Количество записей на странице
            
        Returns:
            Dict: История проверок
        """
        try:
            response = self.session.get(
                f"{self.BASE_URL}/getcheckshistory?page={page}&limit={limit}"
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Ошибка при получении истории проверок: {e}")
            return {"success": False, "error": str(e)}
    
    def perform_check_and_wait(self, address: str, currency: str, max_attempts: int = 20, 
                            interval: int = 1) -> Dict[str, Any]:
        """
        Выполняет проверку адреса и ждет результата
        
        Args:
            address: Криптоадрес для проверки
            currency: Валюта адреса
            max_attempts: Максимальное количество попыток получения результата
            interval: Интервал между попытками в секундах
            
        Returns:
            Dict: Результаты проверки
        """
        # Сначала ищем существующий отчет
        report = self.find_report(address, currency)
        
        if report.get("success") and report.get("count", 0) > 0:
            # Если отчет уже существует, возвращаем его ID
            check_id = report.get("data", [])[0].get("check_id", "")
            if check_id:
                return self.get_result(check_id)
            return {"success": False, "error": "Не удалось получить ID проверки из отчета"}
        
        # Если отчета нет, выполняем новую проверку
        check_result = self.check_address(address, currency)
        
        if not check_result.get("success"):
            return check_result
        
        check_id = check_result.get("id", "")
        if not check_id:
            return {"success": False, "error": "Не удалось получить ID проверки"}
            
        # Ждем результата
        for attempt in range(max_attempts):
            result = self.get_result(check_id)
            
            if result.get("status") != "pending":
                return result
            
            time.sleep(interval)
        
        return {"success": False, "error": "Время ожидания результата истекло"}
    
    def parse_check_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Парсит результат проверки и возвращает упрощенную структуру данных
        
        Args:
            result: Результат проверки от API
            
        Returns:
            Dict: Упрощенная структура результата проверки
        """
        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Неизвестная ошибка")
            }
        
        data = result.get("data", {})
        
        # Определяем общий риск
        risk_score = data.get("risk_score", 0)
        
        if risk_score < 25:
            risk_level = "low"
            verdict = "Чистый"
            color = "success"
        elif risk_score < 75:
            risk_level = "medium"
            verdict = "Средний риск"
            color = "warning"
        else:
            risk_level = "high"
            verdict = "Высокий риск"
            color = "danger"
        
        # Извлекаем основные риски
        risk_triggers = []
        
        # В API возвращается разная структура для разных проверок, пытаемся обработать все варианты
        if "risk_triggers" in data:
            # Случай, когда риски представлены напрямую
            risk_triggers = data["risk_triggers"]
        elif "services" in data:
            # Случай, когда риски представлены в разделе services
            for service in data["services"]:
                if service.get("risk") and service.get("name"):
                    risk_triggers.append({
                        "name": service["name"],
                        "risk": service["risk"]
                    })
        
        # Формируем рекомендации в зависимости от уровня риска
        recommendations = []
        
        if risk_level == "low":
            recommendations.append("Транзакции с этим адресом безопасны")
        elif risk_level == "medium":
            recommendations.append("Рекомендуется дополнительная проверка перед совершением транзакций")
            recommendations.append("Запросите дополнительную информацию у контрагента")
        else:
            recommendations.append("Высокий риск! Не рекомендуется проводить транзакции с этим адресом")
            recommendations.append("Рекомендуется обратиться в службу безопасности перед любыми операциями")
        
        return {
            "success": True,
            "address": data.get("address", ""),
            "currency": data.get("currency", ""),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "verdict": verdict,
            "color": color,
            "risk_triggers": risk_triggers[:5],  # Ограничиваем список из 5 основных рисков
            "recommendations": recommendations,
            "check_time": data.get("check_time", ""),
            "is_fake": data.get("is_fake", False)
        }
    
    def test_proxy_connection(self) -> Dict[str, Any]:
        """
        Проверяет соединение с GetBlock API через прокси (если настроен)
        
        Returns:
            Dict: Результат проверки соединения
        """
        # Подготовка базового результата
        result = {
            "success": False,
            "using_proxy": self.using_proxy,
            "current_ip": "неизвестен",
            "api_available": False
        }
        
        try:
            # Добавляем информацию о настройках прокси
            if self.using_proxy and hasattr(self, 'session') and hasattr(self.session, 'proxies'):
                proxy_info = {}
                if isinstance(self.session.proxies, dict):
                    # Безопасно копируем прокси-настройки, скрывая пароли
                    for protocol, url in self.session.proxies.items():
                        if url and isinstance(url, str):
                            # Маскируем пароль в URL, если он есть
                            masked_url = url
                            if '@' in url:
                                # Формат: http://user:pass@host:port
                                parts = url.split('@')
                                if len(parts) >= 2:
                                    auth_part = parts[0]
                                    if ':' in auth_part:
                                        user_pass = auth_part.split(':')
                                        if len(user_pass) >= 2:
                                            user = user_pass[0].split('/')[-1]  # Убираем протокол
                                            masked_url = f"{user_pass[0]}:***@{parts[1]}"
                            proxy_info[protocol] = masked_url
                result["proxy_info"] = proxy_info
        except Exception as proxy_error:
            logging.warning(f"Ошибка при получении информации о прокси: {proxy_error}")
        
        # Определение текущего IP
        current_ip = "неизвестен"
        try:
            # Пробуем первый сервис определения IP
            try:
                if self.using_proxy:
                    ip_response = requests.get("https://api.ipify.org?format=json", 
                                            proxies=self.session.proxies if hasattr(self, 'session') else None, 
                                            timeout=5)
                else:
                    ip_response = requests.get("https://api.ipify.org?format=json", timeout=5)
                
                if ip_response.status_code == 200:
                    ip_data = ip_response.json()
                    if ip_data and "ip" in ip_data:
                        current_ip = ip_data["ip"]
            except Exception as ipify_error:
                logging.warning(f"Не удалось определить IP через ipify: {ipify_error}")
                # Пробуем альтернативный сервис
                try:
                    if self.using_proxy:
                        ip_alt_response = requests.get("https://ifconfig.me/ip", 
                                                     proxies=self.session.proxies if hasattr(self, 'session') else None, 
                                                     timeout=5)
                    else:
                        ip_alt_response = requests.get("https://ifconfig.me/ip", timeout=5)
                    
                    if ip_alt_response.status_code == 200:
                        alt_ip = ip_alt_response.text.strip()
                        if alt_ip:  # Проверяем, что получили непустую строку
                            current_ip = alt_ip
                except Exception as alt_ip_error:
                    logging.warning(f"Не удалось определить IP через альтернативный сервис: {alt_ip_error}")
        except Exception as ip_check_error:
            logging.warning(f"Общая ошибка при определении IP: {ip_check_error}")
        
        # Обновляем результат
        result["current_ip"] = current_ip
        
        # Проверка базового соединения без вызова реальных API-методов
        try:
            # Пытаемся выполнить простой пинг без полной проверки API
            success = False
            message = "Соединение не установлено"
            
            # Простая проверка подключения к хосту
            try:
                # В этом блоке мы не используем никаких API-методов, просто проверяем TCP-соединение
                response = requests.head(
                    f"{self.BASE_URL}", 
                    timeout=5,
                    proxies=self.session.proxies if hasattr(self, 'session') else None
                )
                
                success = response.status_code < 500  # Любой ответ, не являющийся серверной ошибкой
                message = f"Соединение установлено, статус: {response.status_code}"
                
                result["api_available"] = success
                result["status_code"] = response.status_code
            except requests.RequestException as req_error:
                message = f"Ошибка соединения: {str(req_error)}"
                result["request_error"] = str(req_error)
            
            # Формируем финальный результат
            result["success"] = success
            result["message"] = message
            
            return result
            
        except Exception as final_error:
            logging.error(f"Критическая ошибка при проверке соединения: {final_error}")
            result["error"] = str(final_error)
            result["message"] = "Критическая ошибка при проверке соединения"
            return result
    
    def get_currency_name(self, currency_code: str) -> str:
        """
        Получает полное название валюты по коду
        
        Args:
            currency_code: Код валюты (BTC, ETH, TRX и т.д.)
            
        Returns:
            str: Полное название валюты
        """
        currency_map = {
            "BTC": "Bitcoin",
            "ETH": "Ethereum",
            "TRX": "Tron",
            "BSC": "Binance Smart Chain",
            "USDT": "Tether",
            "LTC": "Litecoin",
            "XRP": "Ripple",
            "BCH": "Bitcoin Cash",
            "DOGE": "Dogecoin"
        }
        
        return currency_map.get(currency_code.upper(), currency_code)