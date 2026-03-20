"""
handlers_voter.py — Даўыс бериўшилер.
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
        text = f"👋 *{member['name']}*\n\n🗳 /vote — даўыс бериў\nℹ️ /status — статус"
        if uid == ADMIN_ID:
            text += "\n🔧 /admin — басқарыў"
        await update.message.reply_text(text, parse_mode="Markdown")
        awaiting_pin.pop(uid, None)
        return

    if uid == ADMIN_ID:
        await update.message.reply_text(
            "🏛 *Даўыс бериў системасы*\n\n"
            "👋 Сиз — хаткер (админ).\n🔧 /admin — басқарыў\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Даўыс бериў ушын PIN киргизиң:",
            parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "🏛 *Даўыс бериў системасы*\n\nPIN кодыңызды киргизиң:", parse_mode="Markdown")
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
            await update.message.reply_text("Дизимнен өтиў ушын /start басың")
        return

    pin = update.message.text.strip()
    awaiting_pin.pop(uid, None)

    m = db.get_member_by_pin(pin)
    if not m:
        await update.message.reply_text("❌ PIN табылмады. /start")
        return
    if m["telegram_id"] and m["telegram_id"] != uid:
        await update.message.reply_text("❌ Бул PIN басқа аккаунтқа байланған. Хаткерге хабарласың.")
        return

    name = db.bind_telegram_id(pin, uid)
    if name:
        text = f"✅ *{name}* — дизимнен өтти!\n\n🗳 /vote — даўыс бериў"
        if uid == ADMIN_ID:
            text += "\n🔧 /admin — басқарыў"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Қәте. /start")


async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    member = db.get_member_by_telegram_id(uid)
    if not member:
        await update.message.reply_text("❌ /start — дизимнен өтиң")
        return

    active = db.get_active_questions_for(member["pin"])
    if not active:
        await update.message.reply_text("📭 Актив даўыс бериў жоқ.")
        return

    for item in active:
        q = item["question"]
        kb = [[
            InlineKeyboardButton("✅ Жақлап", callback_data=f"v:{item['meeting_id']}:{q['id']}:for"),
            InlineKeyboardButton("❌ Қарсы", callback_data=f"v:{item['meeting_id']}:{q['id']}:against"),
            InlineKeyboardButton("⬜ Тийкарсыз", callback_data=f"v:{item['meeting_id']}:{q['id']}:abstain"),
        ]]
        await update.message.reply_text(
            f"🗳 *Мәжилис №{item['protocol_number']}*\n📅 {item['meeting_date']}\n\n📝 *{q['text']}*",
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
    labels = {"for": "✅ Жақлап", "against": "❌ Қарсы", "abstain": "⬜ Тийкарсыз"}

    if result == "ok":
        await query.edit_message_text(f"{query.message.text}\n\n📨 Даўысыңыз: {labels[vote]}")

        active = db.get_active_questions_for(member["pin"])
        if active:
            nxt = active[0]
            nq = nxt["question"]
            kb = [[
                InlineKeyboardButton("✅ Жақлап", callback_data=f"v:{nxt['meeting_id']}:{nq['id']}:for"),
                InlineKeyboardButton("❌ Қарсы", callback_data=f"v:{nxt['meeting_id']}:{nq['id']}:against"),
                InlineKeyboardButton("⬜ Тийкарсыз", callback_data=f"v:{nxt['meeting_id']}:{nq['id']}:abstain"),
            ]]
            await context.bot.send_message(chat_id=uid,
                text=f"🗳 Кейинги масала:\n\n📝 *{nq['text']}*",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=uid, text="✅ Барлық масалаларға даўыс бердиңиз. Рахмет!")

    elif result == "already_voted":
        await query.edit_message_text(f"{query.message.text}\n\n⚠️ Сиз даўыс бергенсиз.")
    elif result == "not_attendee":
        await query.edit_message_text("❌ Сиз қатнасыўшылар дизиминде жоқсыз.")
    elif result == "not_active":
        await query.edit_message_text("⏹ Даўыс бериў тамамланған.")
    else:
        await query.edit_message_text("❌ Қәте.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    member = db.get_member_by_telegram_id(uid)
    if not member:
        await update.message.reply_text("❌ /start")
        return
    active = db.get_active_questions_for(member["pin"])
    await update.message.reply_text(
        f"👤 *{member['name']}*\n🔑 PIN: `{member['pin']}`\n📝 Жуўап берилмеген: {len(active)}",
        parse_mode="Markdown")
