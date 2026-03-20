"""
bot.py — Универсальный бот для илмий семинар / илмий кенгаш.
"""

import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from config import BOT_TOKEN, BASE_URL, PORT, IS_PRODUCTION, ADMIN_ID
from handlers_voter import cmd_start, cmd_vote, cmd_status, handle_vote_callback, handle_text
from handlers_admin import cmd_admin, cmd_sample, handle_document, handle_admin_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("vote", cmd_vote))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sample", cmd_sample))

    app.add_handler(CallbackQueryHandler(handle_vote_callback, pattern=r"^v:"))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^(m|mem|mtg|att|qst|q):"))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def run_production():
    application = build_app()
    await application.initialize()
    await application.start()

    await application.bot.set_webhook(url=f"{BASE_URL}/webhook")
    logger.info(f"✅ Webhook: {BASE_URL}/webhook")

    # Команды меню
    from telegram import BotCommand, BotCommandScopeChat
    try:
        await application.bot.set_my_commands([
            BotCommand("admin", "🔧 Басқарыў"),
            BotCommand("vote", "🗳 Даўыс бериў"),
        ], scope=BotCommandScopeChat(chat_id=ADMIN_ID))

        await application.bot.set_my_commands([
            BotCommand("vote", "🗳 Даўыс бериў"),
        ])
        logger.info("✅ Меню установлено")
    except Exception as e:
        logger.warning(f"⚠️ Меню: {e}")

    aio_app = web.Application()

    async def wh(request):
        try:
            data = await request.json()
            await application.process_update(Update.de_json(data, application.bot))
        except Exception as e:
            logger.error(f"WH: {e}")
        return web.Response(text="ok")

    aio_app.router.add_post("/webhook", wh)
    aio_app.router.add_get("/", lambda r: web.Response(text="OK"))

    runner = web.AppRunner(aio_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info(f"🚀 Порт {PORT}")

    try:
        await asyncio.Event().wait()
    finally:
        await application.stop()
        await application.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    if IS_PRODUCTION:
        asyncio.run(run_production())
    else:
        build_app().run_polling(drop_pending_updates=True)
