"""
bot.py — Главный файл бота Илмий Кенгаш.

Запуск:
  python bot.py

Режимы:
  - Локально: polling (автоматически, если нет KOYEB_PUBLIC_DOMAIN)
  - Koyeb: webhook + встроенный веб-сервер для Mini Web App

На Koyeb нужны только 2 переменные окружения:
  BOT_TOKEN  — токен от @BotFather
  ADMIN_ID   — ваш Telegram ID

Всё остальное определяется автоматически.
"""

import os
import json
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from config import BOT_TOKEN, WEBHOOK_URL, WEBAPP_URL, PORT, IS_PRODUCTION
from handlers_voter import (
    get_registration_handler, vote_command,
    status_command, handle_vote_callback
)
from handlers_admin import admin_panel, handle_webapp_data, handle_document, send_sample

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")


def build_app():
    """Создать и настроить Telegram Application."""
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрация (ConversationHandler: /start → PIN)
    application.add_handler(get_registration_handler())

    # Команды
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("vote", vote_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("sample", send_sample))

    # Inline-кнопки голосования
    application.add_handler(CallbackQueryHandler(handle_vote_callback, pattern=r"^vote:"))

    # Загрузка Excel-файла с участниками
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Данные из Mini Web App
    application.add_handler(MessageHandler(
        filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data
    ))

    return application


async def run_production():
    """Продакшн: aiohttp-сервер с webhook + webapp + health."""
    application = build_app()

    # Инициализация бота
    await application.initialize()
    await application.start()

    # Установка webhook
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")
    logger.info(f"🌐 WebApp доступна: {WEBAPP_URL}")

    # aiohttp маршруты
    aio_app = web.Application()

    # POST /webhook — принимает обновления от Telegram
    async def handle_webhook(request):
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="ok")

    # GET /webapp — отдаёт Mini Web App
    async def handle_webapp(request):
        filepath = os.path.join(WEBAPP_DIR, "index.html")
        if os.path.exists(filepath):
            return web.FileResponse(filepath)
        return web.Response(text="Webapp not found", status=404)

    # GET / — health check для Koyeb
    async def handle_health(request):
        return web.Response(text="OK")

    # GET /api/data — API для Web App (получить данные)
    async def handle_api_data(request):
        import database as db
        members = db.get_members()
        safe_members = [{
            "name": m["name"],
            "pin": m["pin"],
            "registered": m["telegram_id"] is not None
        } for m in members]

        return web.json_response({
            "members": safe_members,
            "meetings": db.get_meetings()
        })

    aio_app.router.add_post("/webhook", handle_webhook)
    aio_app.router.add_get("/webapp", handle_webapp)
    aio_app.router.add_get("/", handle_health)
    aio_app.router.add_get("/api/data", handle_api_data)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🚀 Сервер запущен на порту {PORT}")

    # Держим сервер работающим
    try:
        await asyncio.Event().wait()
    finally:
        await application.stop()
        await application.shutdown()
        await runner.cleanup()


def run_local():
    """Локальный режим: polling."""
    application = build_app()
    logger.info("🔧 Локальный режим (polling)")
    logger.info("   Mini Web App недоступна (нужен HTTPS на Koyeb)")
    logger.info("   Бот работает — можно тестировать команды")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    if IS_PRODUCTION:
        asyncio.run(run_production())
    else:
        run_local()
