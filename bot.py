"""
bot.py — Илмий Кенгаш: бот для тайного голосования.

Koyeb: BOT_TOKEN + ADMIN_ID
Локально: python bot.py (polling)
"""

import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from config import BOT_TOKEN, BASE_URL, PORT, IS_PRODUCTION
from handlers_voter import cmd_start, cmd_vote, cmd_status, handle_vote_callback, handle_text
from handlers_admin import cmd_admin, cmd_sample, handle_document, handle_admin_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sample", cmd_sample))
    app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("/admin — меню")))

    # Голосование (callback v:...)
    app.add_handler(CallbackQueryHandler(handle_vote_callback, pattern=r"^v:"))

    # Админ-кнопки (callback menu:, mem:, mtg:, att:, ses:, q:)
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^(menu|mem|mtg|att|ses|q):"))

    # Файл от админа
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Текст (PIN или админ-ввод)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def run_production():
    application = build_app()
    await application.initialize()
    await application.start()

    webhook_url = f"{BASE_URL}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"✅ Webhook: {webhook_url}")

    # Установить команды для кнопки Меню
    from telegram import BotCommand, BotCommandScopeChat
    try:
        # Для админа — обе команды
        await application.bot.set_my_commands(
            commands=[
                BotCommand("admin", "🔧 Управление"),
                BotCommand("vote", "🗳 Голосование"),
            ],
            scope=BotCommandScopeChat(chat_id=ADMIN_ID)
        )
        # Для остальных — только голосование
        await application.bot.set_my_commands(
            commands=[
                BotCommand("vote", "🗳 Голосование"),
            ]
        )
        logger.info("✅ Команды меню установлены")
    except Exception as e:
        logger.warning(f"⚠️ Команды: {e}")

    aio_app = web.Application()

    async def handle_webhook(request):
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
        return web.Response(text="ok")

    async def handle_health(request):
        return web.Response(text="OK")

    aio_app.router.add_post("/webhook", handle_webhook)
    aio_app.router.add_get("/", handle_health)

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🚀 Порт {PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await application.stop()
        await application.shutdown()
        await runner.cleanup()


def run_local():
    app = build_app()
    logger.info("🔧 Polling")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    if IS_PRODUCTION:
        asyncio.run(run_production())
    else:
        run_local()
