# 🚀 Инструкция по деплою TrustLendX

## Быстрый старт на Render.com (5 минут)

### Шаг 1: Регистрация на Render

1. Перейдите на https://render.com
2. Нажмите "Get Started" → "Sign Up"
3. Войдите через GitHub аккаунт

### Шаг 2: Создание Web Service

1. В дашборде нажмите **"New +"** → **"Web Service"**
2. Нажмите **"Connect a repository"**
3. Найдите и выберите `kisa134/TrustLendX`
4. Нажмите **"Connect"**

### Шаг 3: Настройка сервиса

Render автоматически обнаружит настройки из `render.yaml`, но проверьте:

- **Name**: `trustlendx` (или любое другое)
- **Region**: `Frankfurt (EU Central)` или ближайший к вам
- **Branch**: `master`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn --bind 0.0.0.0:$PORT main:app`
- **Instance Type**: `Free` (для теста)

### Шаг 4: Добавление переменных окружения

В разделе **Environment Variables** добавьте:

```bash
# Обязательные переменные
DATABASE_URL=postgresql://user:password@host:5432/dbname
SECRET_KEY=your-secret-key-here-generate-random-string

# TON Blockchain
TON_API_KEY=your_ton_api_key
TON_WALLET_ADDRESS=your_ton_wallet_address

# Telegram
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# NOWPayments
NOWPAYMENTS_API_KEY=your_nowpayments_api_key

# Flask
FLASK_ENV=production
FLASK_DEBUG=0
```

### Шаг 5: Создание базы данных PostgreSQL

1. В Render нажмите **"New +"** → **"PostgreSQL"**
2. **Name**: `trustlendx-db`
3. **Database**: `trustlendx`
4. **User**: `trustlendx_user`
5. **Region**: тот же, что и для Web Service
6. **Plan**: `Free`
7. Нажмите **"Create Database"**

### Шаг 6: Подключение БД к приложению

1. Откройте созданную БД
2. Скопируйте **Internal Database URL** (начинается с `postgres://`)
3. Вернитесь в Web Service → Environment → Добавьте:
   - Key: `DATABASE_URL`
   - Value: скопированный URL

### Шаг 7: Деплой!

1. Нажмите **"Create Web Service"**
2. Render начнёт сборку (займёт 3-5 минут)
3. После успешного деплоя вы получите URL типа:
   `https://trustlendx.onrender.com`

### Шаг 8: Инициализация БД

После первого деплоя нужно создать таблицы:

1. В Render откройте **Shell** (во вкладке Web Service)
2. Выполните команды:

```bash
python3 << EOF
from app import app, db
with app.app_context():
    db.create_all()
print("✅ Database tables created!")
EOF
```

---

## 🔧 Альтернативные варианты

### Railway.app (ещё проще)

1. https://railway.app → Login with GitHub
2. New Project → Deploy from GitHub repo
3. Выберите `TrustLendX`
4. Add PostgreSQL plugin
5. Добавьте переменные окружения
6. Deploy автоматически!

URL будет типа: `https://trustlendx.up.railway.app`

### Fly.io (Docker)

```bash
# Установите Fly CLI
curl -L https://fly.io/install.sh | sh  # Linux/Mac
# или скачайте с https://fly.io/docs/hands-on/install-flyctl/

# Залогиньтесь
fly auth login

# Инициализация
fly launch --name trustlendx

# Добавьте БД PostgreSQL
fly postgres create --name trustlendx-db

# Подключите БД к приложению
fly postgres attach --app trustlendx trustlendx-db

# Добавьте переменные
fly secrets set \
  TON_API_KEY=your_key \
  TELEGRAM_TOKEN=your_token \
  SECRET_KEY=$(openssl rand -hex 32)

# Деплой
fly deploy
```

URL будет: `https://trustlendx.fly.dev`

---

## 📊 Мониторинг и логи

### Render
- Логи: Dashboard → Web Service → Logs
- Метрики: Dashboard → Metrics
- Shell: Dashboard → Shell (для отладки)

### Railway
- Логи: Project → Deployments → View Logs
- Метрики: Project → Metrics

### Fly.io
```bash
fly logs              # Просмотр логов
fly status            # Статус приложения
fly ssh console       # SSH доступ
```

---

## ⚠️ Важные моменты

### 1. Переменные окружения
**Никогда не коммитьте файл `.env` в Git!** Он уже в `.gitignore`.

### 2. SECRET_KEY
Генерируйте случайный ключ:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. База данных
- На бесплатном плане Render БД удаляется через 90 дней неактивности
- Railway даёт 500 MB бесплатно
- Fly.io - 3 GB бесплатно

### 4. HTTPS
Все платформы автоматически дают бесплатный SSL сертификат!

### 5. Домен
Можно подключить свой домен:
- Render: Settings → Custom Domain
- Railway: Settings → Domains
- Fly.io: `fly certs add yourdomain.com`

---

## 🐛 Типичные проблемы

### Ошибка: "Application failed to start"
1. Проверьте логи
2. Убедитесь, что все зависимости в `requirements.txt`
3. Проверьте `DATABASE_URL`

### Ошибка: "Port already in use"
В `main.py` должно быть:
```python
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
```

### База данных не инициализирована
Выполните в Shell:
```python
from app import app, db
with app.app_context():
    db.create_all()
```

---

## 📞 Поддержка

- Render: https://render.com/docs
- Railway: https://docs.railway.app
- Fly.io: https://fly.io/docs

**Удачи с деплоем! 🚀**
