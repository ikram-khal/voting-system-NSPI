"""
handlers_voter.py — Обработчики для участников (голосующих).

Участники взаимодействуют с ботом через:
  - /start → регистрация по PIN
  - /vote  → проверить доступные голосования
  - inline-кнопки → голосование За / Против / Воздержался
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
import database as db

logger = logging.getLogger(__name__)

# Состояния для регистрации
WAITING_PIN = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — приветствие и проверка регистрации."""
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)

    if member:
        await update.message.reply_text(
            f"👋 Добро пожаловать, *{member['name']}*!\n\n"
            f"Вы зарегистрированы в системе голосования Илмий Кенгаш.\n\n"
            f"📝 /vote — проверить доступные голосования\n"
            f"ℹ️ /status — ваш статус",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🏛 *Илмий Кенгаш — Система голосования*\n\n"
            "Для регистрации введите ваш уникальный PIN-код, "
            "который вам выдал секретарь учёного совета.\n\n"
            "Введите PIN:",
            parse_mode="Markdown"
        )
        return WAITING_PIN

    return ConversationHandler.END


async def receive_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение PIN для регистрации."""
    pin = update.message.text.strip()
    user_id = update.effective_user.id

    # Проверить, не привязан ли уже этот PIN к другому аккаунту
    existing = db.get_member_by_pin(pin)
    if not existing:
        await update.message.reply_text(
            "❌ PIN не найден. Проверьте правильность и попробуйте снова.\n"
            "Введите PIN:"
        )
        return WAITING_PIN

    if existing["telegram_id"] is not None and existing["telegram_id"] != user_id:
        await update.message.reply_text(
            "❌ Этот PIN уже привязан к другому аккаунту.\n"
            "Обратитесь к секретарю учёного совета."
        )
        return ConversationHandler.END

    name = db.bind_telegram_id(pin, user_id)
    if name:
        await update.message.reply_text(
            f"✅ Регистрация успешна!\n\n"
            f"👤 {name}\n\n"
            f"Теперь вы будете получать уведомления о голосованиях.\n"
            f"📝 /vote — проверить доступные голосования",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Ошибка регистрации. Попробуйте позже.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена регистрации."""
    await update.message.reply_text("Отменено. Используйте /start для повторной попытки.")
    return ConversationHandler.END


async def vote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /vote — показать доступные голосования."""
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)

    if not member:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы. Используйте /start для регистрации."
        )
        return

    active = db.get_active_voting(member["pin"])

    if not active:
        await update.message.reply_text(
            "📭 Нет активных голосований.\n"
            "Вы получите уведомление, когда начнётся голосование."
        )
        return

    for voting in active:
        for q in voting["questions"]:
            keyboard = [
                [
                    InlineKeyboardButton("✅ За", callback_data=f"vote:{voting['meeting_id']}:{voting['session_id']}:{q['id']}:for"),
                    InlineKeyboardButton("❌ Против", callback_data=f"vote:{voting['meeting_id']}:{voting['session_id']}:{q['id']}:against"),
                    InlineKeyboardButton("⬜ Воздерж.", callback_data=f"vote:{voting['meeting_id']}:{voting['session_id']}:{q['id']}:abstain"),
                ]
            ]
            await update.message.reply_text(
                f"🗳 *{voting['session_title']}*\n"
                f"📅 {voting['meeting_date']}, протокол №{voting['protocol_number']}\n\n"
                f"❓ {q['text']}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )


async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопки голосования."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    member = db.get_member_by_telegram_id(user_id)

    if not member:
        await query.edit_message_text("❌ Вы не зарегистрированы.")
        return

    # Формат: vote:meeting_id:session_id:question_id:vote_type
    parts = query.data.split(":")
    if len(parts) != 5 or parts[0] != "vote":
        return

    _, meeting_id, session_id, question_id, vote_type = parts

    if vote_type not in ("for", "against", "abstain"):
        return

    result = db.cast_vote(meeting_id, session_id, question_id, member["pin"], vote_type)

    vote_labels = {"for": "✅ За", "against": "❌ Против", "abstain": "⬜ Воздержался"}

    if result == "ok":
        await query.edit_message_text(
            f"{query.message.text}\n\n"
            f"📨 Ваш голос принят: {vote_labels[vote_type]}",
        )

        # Проверить, есть ли ещё вопросы в этом сеансе
        active = db.get_active_voting(member["pin"])
        current_session = None
        for v in active:
            if v["session_id"] == session_id:
                current_session = v
                break

        if current_session and current_session["questions"]:
            next_q = current_session["questions"][0]
            keyboard = [
                [
                    InlineKeyboardButton("✅ За", callback_data=f"vote:{meeting_id}:{session_id}:{next_q['id']}:for"),
                    InlineKeyboardButton("❌ Против", callback_data=f"vote:{meeting_id}:{session_id}:{next_q['id']}:against"),
                    InlineKeyboardButton("⬜ Воздерж.", callback_data=f"vote:{meeting_id}:{session_id}:{next_q['id']}:abstain"),
                ]
            ]
            q_index = len(current_session["questions"])
            meeting = db.get_meeting(meeting_id)
            session = None
            for s in meeting["sessions"]:
                if s["id"] == session_id:
                    session = s
                    break
            total_q = len(session["questions"]) if session else "?"

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🗳 *{current_session['session_title']}*\n\n"
                    f"❓ *Следующий вопрос:*\n"
                    f"{next_q['text']}"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Вы проголосовали по всем вопросам этого сеанса. Спасибо!"
            )

    elif result == "already_voted":
        await query.edit_message_text(
            f"{query.message.text}\n\n⚠️ Вы уже голосовали по этому вопросу."
        )
    elif result == "not_attendee":
        await query.edit_message_text(
            "❌ Вы не отмечены как присутствующий на этом заседании."
        )
    elif result == "session_not_active":
        await query.edit_message_text(
            "⏹ Голосование по этому сеансу уже завершено."
        )
    else:
        await query.edit_message_text("❌ Ошибка. Попробуйте позже.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status — статус участника."""
    user_id = update.effective_user.id
    member = db.get_member_by_telegram_id(user_id)

    if not member:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы. Используйте /start"
        )
        return

    active = db.get_active_voting(member["pin"])
    active_count = sum(len(v["questions"]) for v in active)

    await update.message.reply_text(
        f"👤 *{member['name']}*\n"
        f"🔑 PIN: {member['pin']}\n"
        f"📝 Неотвеченных вопросов: {active_count}",
        parse_mode="Markdown"
    )


def get_registration_handler():
    """Создать ConversationHandler для регистрации."""
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_pin)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
