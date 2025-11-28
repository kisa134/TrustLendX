import os
import sys
from app import app, db
from models import User
from utils import generate_referral_code
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_codes_for_all_users():
    """Генерирует и сохраняет реферальные коды для всех пользователей, у которых их еще нет"""
    with app.app_context():
        users = User.query.all()
        updated_count = 0
        
        for user in users:
            if not user.referral_code:
                # Генерируем уникальный код
                while True:
                    new_code = generate_referral_code()
                    # Проверяем, что код еще не используется
                    existing = User.query.filter_by(referral_code=new_code).first()
                    if not existing:
                        break
                
                user.referral_code = new_code
                updated_count += 1
        
        if updated_count > 0:
            try:
                db.session.commit()
                logger.info(f"Успешно создано {updated_count} новых реферальных кодов")
            except Exception as e:
                db.session.rollback()
                logger.error(f"Ошибка при сохранении реферальных кодов: {e}")
                return False
        else:
            logger.info("Все пользователи уже имеют реферальные коды")
        
        return True

if __name__ == "__main__":
    logger.info("Начинаем генерацию реферальных кодов...")
    success = generate_codes_for_all_users()
    
    if success:
        logger.info("Генерация реферальных кодов завершена успешно")
        sys.exit(0)
    else:
        logger.error("Ошибка при генерации реферальных кодов")
        sys.exit(1)