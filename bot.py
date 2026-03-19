"""
bot.py — Илмий Кенгаш: бот для тайного голосования.

Koyeb: нужны только BOT_TOKEN и ADMIN_ID.
Локально: polling режим (python bot.py).
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
from config import BOT_TOKEN, BASE_URL, WEBAPP_URL, PORT, IS_PRODUCTION, ADMIN_ID
from handlers_voter import cmd_start, cmd_vote, cmd_status, handle_vote_callback, handle_text
from handlers_admin import cmd_admin, cmd_sample, handle_document, handle_webapp_data

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WEBAPP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")


def build_app():
    """Собрать Telegram Application с хэндлерами."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sample", cmd_sample))

    # Кнопки голосования
    app.add_handler(CallbackQueryHandler(handle_vote_callback, pattern=r"^v:"))

    # Excel-файл от админа
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Данные из Web App
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    # Текстовые сообщения (ввод PIN)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def run_production():
    """Koyeb: webhook + веб-сервер для Mini Web App."""
    application = build_app()

    await application.initialize()
    await application.start()

    # Webhook
    webhook_url = f"{BASE_URL}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook: {webhook_url}")

    # Кнопка Меню для админа
    try:
        from telegram import MenuButtonWebApp, WebAppInfo
        await application.bot.set_chat_menu_button(
            chat_id=ADMIN_ID,
            menu_button=MenuButtonWebApp(
                text="📋 Панель",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        )
        logger.info(f"✅ Кнопка Меню для админа (ID: {ADMIN_ID})")
    except Exception as e:
        logger.warning(f"⚠️ Кнопка Меню: {e}")

    # aiohttp сервер
    aio_app = web.Application()

    async def handle_webhook(request):
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
        return web.Response(text="ok")

    async def handle_webapp(request):
        filepath = os.path.join(WEBAPP_DIR, "index.html")
        if os.path.exists(filepath):
            return web.FileResponse(filepath)
        return web.Response(text="Not found", status=404)

    async def handle_health(request):
        return web.Response(text="OK")

    async def handle_api_data(request):
        import database as db
        members = [{
            "name": m["name"],
            "pin": m["pin"],
            "registered": m["telegram_id"] is not None
        } for m in db.get_members()]
        return web.json_response({
            "members": members,
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
    logger.info(f"🚀 Сервер: порт {PORT}")
    logger.info(f"🌐 WebApp: {WEBAPP_URL}")

    try:
        await asyncio.Event().wait()
    finally:
        await application.stop()
        await application.shutdown()
        await runner.cleanup()


def run_local():
    """Локально: polling."""
    app = build_app()
    logger.info("🔧 Polling режим (локальный)")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    if IS_PRODUCTION:
        asyncio.run(run_production())
    else:
        run_local()
