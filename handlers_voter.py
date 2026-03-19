"""
handlers_voter.py — Обработчики для участников.

БЕЗ ConversationHandler — используем простой словарь состояний.
Это надёжнее и не блокирует бота.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID
import database as db

logger = logging.getLogger(__name__)

# Простое хранение состояний: {user_id: "awaiting_pin"}
user_states = {}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start."""
    user_id = update.effective_user.id
    is_admin = (user_id == ADMIN_ID)
    member = db.get_member_by_telegram_id(user_id)

    if member:
        text = (
            f"👋 Добро пожаловать, *{member['name']}*!\n\n"
            f"📝 /vote — проверить доступные голосования\n"
            f"ℹ️ /status — ваш статус"
        )
        if is_admin:
            text += (
                f"\n\n🔧 *Вы — секретарь (админ)*\n"
                f"📋 /admin — открыть панель управления\n"
                f"📎 Отправьте .xlsx для загрузки участников\n"
                f"📥 /sample — скачать шаблон"
            )
        await update.message.reply_text(text, parse_mode="Markdown")
        # Сбросить состояние
        user_states.pop(user_id, None)
        return

    # Не зарегистрирован
    if is_admin:
        await update.message.reply_text(
            "🏛 *Илмий Кенгаш — Система голосования*\n\n"
            "👋 Вы — *секретарь (админ)*.\n\n"
            "📋 /admin — открыть панель управления\n"
            "📎 Отправьте .xlsx файл со списком участников\n"
            "📥 /sample — скачать шаблон\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Чтобы *самому голосовать*, зарегистрируйтесь.\n"
            "Введите ваш PIN-код:",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏛 *Илмий Кенгаш — Система голосования*\n\n"
            "Для регистрации введите ваш PIN-код, "
            "который вам выдал секретарь.\n\n"
            "Введите PIN:",
            parse_mode="Markdown"
        )

    user_states[user_id] = "awaiting_pin"


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (для ввода PIN)."""
    user_id = update.effective_user.id

    if user_states.get(user_id) != "awaiting_pin":
        # Нет ожидания — игнорируем или подсказываем
        await update.message.reply_text(
            "Используйте команды:\n"
            "📝 /vote — голосовать\n"
            "ℹ️ /status — статус\n"
            "/start — начало"
        )
        return

    pin = update.message.text.strip()

    # Убрать состояние
    user_states.pop(user_id, None)

    existing = db.get_member_by_pin(pin)
    if not existing:
        await update.message.reply_text(
            "❌ PIN не найден. Проверьте и попробуйте /start заново."
        )
        return

    if existing["telegram_id"] is not None and existing["telegram_id"] != user_id:
        await update.message.reply_text(
            "❌ Этот PIN уже привязан к другому аккаунту.\n"
            "Обратитесь к секретарю."
        )
        return

    name = db.bind_telegram_id(pin, user_id)
    if name:
        text = (
            f"✅ Регистрация успешна!\n\n"
            f"👤 *{name}*\n\n"
            f"📝 /vote — голосовать\n"
            f"ℹ️ /status — статус"
        )
        if user_id == ADMIN_ID:
            text += "\n📋 /admin — панель управления"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Ошибка. Попробуйте /start")


async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /vote — показать доступные голосования."""
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)

    if not member:
        await update.message.reply_text("❌ Сначала зарегистрируйтесь: /start")
        return

    active = db.get_active_voting(member["pin"])

    if not active:
        await update.message.reply_text(
            "📭 Нет активных голосований.\n"
            "Вы получите уведомление, когда начнётся."
        )
        return

    for voting in active:
        for q in voting["questions"]:
            keyboard = [[
                InlineKeyboardButton("✅ За", callback_data=f"v:{voting['meeting_id']}:{voting['session_id']}:{q['id']}:for"),
                InlineKeyboardButton("❌ Против", callback_data=f"v:{voting['meeting_id']}:{voting['session_id']}:{q['id']}:against"),
                InlineKeyboardButton("⬜ Воздерж.", callback_data=f"v:{voting['meeting_id']}:{voting['session_id']}:{q['id']}:abstain"),
            ]]
            await update.message.reply_text(
                f"🗳 *{voting['session_title']}*\n"
                f"📅 {voting['meeting_date']}, протокол №{voting['protocol_number']}\n\n"
                f"❓ {q['text']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )


async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки голосования."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    member = db.get_member_by_telegram_id(user_id)
    if not member:
        await query.edit_message_text("❌ Вы не зарегистрированы. /start")
        return

    # Формат: v:meeting_id:session_id:question_id:vote_type
    parts = query.data.split(":")
    if len(parts) != 5 or parts[0] != "v":
        return

    _, meeting_id, session_id, question_id, vote_type = parts

    if vote_type not in ("for", "against", "abstain"):
        return

    result = db.cast_vote(meeting_id, session_id, question_id, member["pin"], vote_type)

    labels = {"for": "✅ За", "against": "❌ Против", "abstain": "⬜ Воздержался"}

    if result == "ok":
        await query.edit_message_text(
            f"{query.message.text}\n\n📨 Ваш голос: {labels[vote_type]}"
        )

        # Показать следующий вопрос
        active = db.get_active_voting(member["pin"])
        for v in active:
            if v["session_id"] == session_id and v["questions"]:
                next_q = v["questions"][0]
                keyboard = [[
                    InlineKeyboardButton("✅ За", callback_data=f"v:{meeting_id}:{session_id}:{next_q['id']}:for"),
                    InlineKeyboardButton("❌ Против", callback_data=f"v:{meeting_id}:{session_id}:{next_q['id']}:against"),
                    InlineKeyboardButton("⬜ Воздерж.", callback_data=f"v:{meeting_id}:{session_id}:{next_q['id']}:abstain"),
                ]]
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🗳 *{v['session_title']}*\n\n❓ {next_q['text']}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return

        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Вы проголосовали по всем вопросам. Спасибо!"
        )

    elif result == "already_voted":
        await query.edit_message_text(f"{query.message.text}\n\n⚠️ Вы уже голосовали.")
    elif result == "not_attendee":
        await query.edit_message_text("❌ Вы не отмечены как присутствующий.")
    elif result == "session_not_active":
        await query.edit_message_text("⏹ Голосование уже завершено.")
    else:
        await query.edit_message_text("❌ Ошибка.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status."""
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)

    if not member:
        await update.message.reply_text("❌ Не зарегистрированы. /start")
        return

    active = db.get_active_voting(member["pin"])
    count = sum(len(v["questions"]) for v in active)

    await update.message.reply_text(
        f"👤 *{member['name']}*\n"
        f"🔑 PIN: {member['pin']}\n"
        f"📝 Неотвеченных вопросов: {count}",
        parse_mode="Markdown"
    )
