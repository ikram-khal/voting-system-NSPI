"""
handlers_voter.py — Обработчики для голосующих.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID
import database as db

logger = logging.getLogger(__name__)

# Ожидание PIN: {user_id: True}
awaiting_pin = {}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_adm = (user_id == ADMIN_ID)
    member = db.get_member_by_telegram_id(user_id)

    if member:
        text = (
            f"👋 Добро пожаловать, *{member['name']}*!\n\n"
            f"📝 /vote — голосовать\n"
            f"ℹ️ /status — статус"
        )
        if is_adm:
            text += "\n\n🔧 /admin — панель управления"
        await update.message.reply_text(text, parse_mode="Markdown")
        awaiting_pin.pop(user_id, None)
        return

    if is_adm:
        await update.message.reply_text(
            "🏛 *Илмий Кенгаш*\n\n"
            "👋 Вы — *секретарь (админ)*.\n"
            "🔧 /admin — панель управления\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Чтобы голосовать — введите ваш PIN:",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏛 *Илмий Кенгаш — Голосование*\n\n"
            "Введите ваш PIN-код:",
            parse_mode="Markdown"
        )
    awaiting_pin[user_id] = True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текстовые сообщения — PIN или админ-ввод."""
    user_id = update.effective_user.id

    # Сначала проверить админский ввод
    if user_id == ADMIN_ID:
        from handlers_admin import handle_admin_text
        handled = await handle_admin_text(update, context)
        if handled:
            return

    # Проверить ожидание PIN
    if user_id not in awaiting_pin:
        member = db.get_member_by_telegram_id(user_id)
        if member:
            await update.message.reply_text("📝 /vote — голосовать\nℹ️ /status — статус")
        else:
            await update.message.reply_text("Нажмите /start для регистрации.")
        return

    pin = update.message.text.strip()
    awaiting_pin.pop(user_id, None)

    existing = db.get_member_by_pin(pin)
    if not existing:
        await update.message.reply_text("❌ PIN не найден. /start — попробовать снова.")
        return

    if existing["telegram_id"] and existing["telegram_id"] != user_id:
        await update.message.reply_text("❌ PIN привязан к другому аккаунту. Обратитесь к секретарю.")
        return

    name = db.bind_telegram_id(pin, user_id)
    if name:
        text = f"✅ *{name}* — зарегистрирован!\n\n📝 /vote — голосовать"
        if user_id == ADMIN_ID:
            text += "\n🔧 /admin — панель"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Ошибка. /start")


async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)
    if not member:
        await update.message.reply_text("❌ /start для регистрации")
        return

    active = db.get_active_voting(member["pin"])
    if not active:
        await update.message.reply_text("📭 Нет активных голосований.")
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
                f"📅 {voting['meeting_date']}, №{voting['protocol_number']}\n\n"
                f"❓ {q['text']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )


async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    member = db.get_member_by_telegram_id(user_id)
    if not member:
        await query.edit_message_text("❌ /start для регистрации")
        return

    parts = query.data.split(":")
    if len(parts) != 5 or parts[0] != "v":
        return

    _, meeting_id, session_id, question_id, vote_type = parts

    result = db.cast_vote(meeting_id, session_id, question_id, member["pin"], vote_type)
    labels = {"for": "✅ За", "against": "❌ Против", "abstain": "⬜ Воздержался"}

    if result == "ok":
        await query.edit_message_text(
            f"{query.message.text}\n\n📨 Ваш голос: {labels[vote_type]}"
        )
        # Следующий вопрос
        active = db.get_active_voting(member["pin"])
        for v in active:
            if v["session_id"] == session_id and v["questions"]:
                nq = v["questions"][0]
                keyboard = [[
                    InlineKeyboardButton("✅ За", callback_data=f"v:{meeting_id}:{session_id}:{nq['id']}:for"),
                    InlineKeyboardButton("❌ Против", callback_data=f"v:{meeting_id}:{session_id}:{nq['id']}:against"),
                    InlineKeyboardButton("⬜ Воздерж.", callback_data=f"v:{meeting_id}:{session_id}:{nq['id']}:abstain"),
                ]]
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🗳 *{v['session_title']}*\n\n❓ {nq['text']}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return
        await context.bot.send_message(chat_id=user_id, text="✅ Все вопросы отвечены. Спасибо!")

    elif result == "already_voted":
        await query.edit_message_text(f"{query.message.text}\n\n⚠️ Уже голосовали.")
    elif result == "not_attendee":
        await query.edit_message_text("❌ Вы не в списке присутствующих.")
    elif result == "session_not_active":
        await query.edit_message_text("⏹ Голосование завершено.")
    else:
        await query.edit_message_text("❌ Ошибка.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)
    if not member:
        await update.message.reply_text("❌ /start")
        return
    active = db.get_active_voting(member["pin"])
    count = sum(len(v["questions"]) for v in active)
    await update.message.reply_text(
        f"👤 *{member['name']}*\n🔑 PIN: {member['pin']}\n📝 Неотвеченных: {count}",
        parse_mode="Markdown"
    )
