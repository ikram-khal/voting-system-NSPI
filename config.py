import os

# Telegram Bot Token (от @BotFather)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin Telegram ID (секретарь учёного совета)
# Узнать свой ID: написать боту @userinfobot в Telegram
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Путь к папке данных
DATA_DIR = os.environ.get("DATA_DIR", "data")

# Порт (Koyeb задаёт автоматически)
PORT = int(os.environ.get("PORT", "8080"))

# Koyeb автоматически даёт переменную KOYEB_PUBLIC_DOMAIN
# Например: my-bot-abc123.koyeb.app
KOYEB_DOMAIN = os.environ.get("KOYEB_PUBLIC_DOMAIN", "")

# Автоопределение режима
IS_PRODUCTION = bool(KOYEB_DOMAIN)
WEBHOOK_URL = f"https://{KOYEB_DOMAIN}" if KOYEB_DOMAIN else ""
WEBAPP_URL = f"https://{KOYEB_DOMAIN}/webapp" if KOYEB_DOMAIN else ""
