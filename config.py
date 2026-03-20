import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DATA_DIR = os.environ.get("DATA_DIR", "data")
PORT = int(os.environ.get("PORT", "8080"))

KOYEB_DOMAIN = os.environ.get("KOYEB_PUBLIC_DOMAIN", "")
IS_PRODUCTION = bool(KOYEB_DOMAIN)
BASE_URL = f"https://{KOYEB_DOMAIN}" if KOYEB_DOMAIN else ""
