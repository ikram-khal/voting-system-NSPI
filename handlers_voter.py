"""
handlers_voter.py — Голосующие участники.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID
import database as db

logger = logging.getLogger(__name__)
awaiting_pin = {}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    member = db.get_member_by_telegram_id(uid)

    if member:
        text = f"👋 *{member['name']}*\n\n🗳 /vote — голосовать\nℹ️ /status — статус"
        if uid == ADMIN_ID:
            text += "\n🔧 /admin — управление"
        await update.message.reply_text(text, parse_mode="Markdown")
        awaiting_pin.pop(uid, None)
        return

    if uid == ADMIN_ID:
        await update.message.reply_text(
            "🏛 *Илмий семинар / Илмий кенгаш*\n\n"
            "👋 Вы — секретарь.\n🔧 /admin — управление\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Для голосования введите PIN:",
            parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "🏛 *Система голосования*\n\nВведите ваш PIN-код:", parse_mode="Markdown")
    awaiting_pin[uid] = True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid == ADMIN_ID:
        from handlers_admin import handle_admin_text
        if await handle_admin_text(update, context):
            return

    if uid not in awaiting_pin:
        member = db.get_member_by_telegram_id(uid)
        if member:
            await update.message.reply_text("🗳 /vote · ℹ️ /status")
        else:
            await update.message.reply_text("/start для регистрации")
        return

    pin = update.message.text.strip()
    awaiting_pin.pop(uid, None)

    m = db.get_member_by_pin(pin)
    if not m:
        await update.message.reply_text("❌ PIN не найден. /start")
        return
    if m["telegram_id"] and m["telegram_id"] != uid:
        await update.message.reply_text("❌ PIN привязан к другому. Обратитесь к секретарю.")
        return

    name = db.bind_telegram_id(pin, uid)
    if name:
        text = f"✅ *{name}* зарегистрирован!\n\n🗳 /vote — голосовать"
        if uid == ADMIN_ID:
            text += "\n🔧 /admin — управление"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Ошибка. /start")


async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    member = db.get_member_by_telegram_id(uid)
    if not member:
        await update.message.reply_text("❌ /start")
        return

    active = db.get_active_questions_for(member["pin"])
    if not active:
        await update.message.reply_text("📭 Нет активных голосований.")
        return

    for item in active:
        q = item["question"]
        label = db.type_label(item["meeting_type"])
        kb = [[
            InlineKeyboardButton("✅ За", callback_data=f"v:{item['meeting_id']}:{q['id']}:for"),
            InlineKeyboardButton("❌ Против", callback_data=f"v:{item['meeting_id']}:{q['id']}:against"),
            InlineKeyboardButton("⬜ Воздерж.", callback_data=f"v:{item['meeting_id']}:{q['id']}:abstain"),
        ]]
        await update.message.reply_text(
            f"🗳 *{label}* №{item['protocol_number']}\n📅 {item['meeting_date']}\n\n❓ *{q['text']}*",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def handle_vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    member = db.get_member_by_telegram_id(uid)
    if not member:
        await query.edit_message_text("❌ /start")
        return

    parts = query.data.split(":")
    if len(parts) != 4 or parts[0] != "v":
        return
    _, mid, qid, vote = parts

    result = db.cast_vote(mid, qid, member["pin"], vote)
    labels = {"for": "✅ За", "against": "❌ Против", "abstain": "⬜ Воздержался"}

    if result == "ok":
        await query.edit_message_text(f"{query.message.text}\n\n📨 Голос: {labels[vote]}")

        # Следующий вопрос?
        active = db.get_active_questions_for(member["pin"])
        if active:
            nxt = active[0]
            nq = nxt["question"]
            kb = [[
                InlineKeyboardButton("✅ За", callback_data=f"v:{nxt['meeting_id']}:{nq['id']}:for"),
                InlineKeyboardButton("❌ Против", callback_data=f"v:{nxt['meeting_id']}:{nq['id']}:against"),
                InlineKeyboardButton("⬜ Воздерж.", callback_data=f"v:{nxt['meeting_id']}:{nq['id']}:abstain"),
            ]]
            await context.bot.send_message(chat_id=uid,
                text=f"🗳 Следующий вопрос:\n\n❓ *{nq['text']}*",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=uid, text="✅ Все вопросы отвечены. Спасибо!")

    elif result == "already_voted":
        await query.edit_message_text(f"{query.message.text}\n\n⚠️ Уже голосовали.")
    elif result == "not_attendee":
        await query.edit_message_text("❌ Вы не в списке присутствующих.")
    elif result == "not_active":
        await query.edit_message_text("⏹ Голосование завершено.")
    else:
        await query.edit_message_text("❌ Ошибка.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    member = db.get_member_by_telegram_id(uid)
    if not member:
        await update.message.reply_text("❌ /start")
        return
    active = db.get_active_questions_for(member["pin"])
    await update.message.reply_text(
        f"👤 *{member['name']}*\n🔑 PIN: `{member['pin']}`\n📝 Неотвеченных: {len(active)}",
        parse_mode="Markdown")
