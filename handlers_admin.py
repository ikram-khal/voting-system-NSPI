"""
handlers_admin.py — Админ-панель через inline-кнопки.

Навигация:
  /admin → Главное меню
    → 👥 Участники → список, удалить
    → 📋 Заседания → список → открыть заседание
      → 👥 Присутствующие (чекбоксы)
      → 📂 Сеансы → открыть сеанс
        → ❓ Вопросы
        → 🗳 Запуск/Стоп голосования
        → 📊 Результаты
      → 📄 Отчёт
"""

import json
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_ID, DATA_DIR
import database as db

logger = logging.getLogger(__name__)

# Состояния ожидания текстового ввода от админа
# {user_id: {"action": "...", "meeting_id": "...", ...}}
admin_input = {}


def is_admin(user_id):
    return user_id == ADMIN_ID


# ══════════════════════════════════════
#  ГЛАВНОЕ МЕНЮ
# ══════════════════════════════════════

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Нет прав.")
        return
    await show_main_menu(update.effective_chat.id, context)


async def show_main_menu(chat_id, context, message_id=None):
    members = db.get_members()
    meetings = db.get_meetings()
    active = sum(1 for mt in meetings for s in mt["sessions"] if s["status"] == "voting")

    text = (
        "🏛 *Илмий Кенгаш — Панель секретаря*\n\n"
        f"👥 Участников: {len(members)}\n"
        f"📋 Заседаний: {len(meetings)}\n"
        f"🗳 Активных голосований: {active}"
    )
    keyboard = [
        [InlineKeyboardButton("👥 Участники", callback_data="menu:members"),
         InlineKeyboardButton("📋 Заседания", callback_data="menu:meetings")],
        [InlineKeyboardButton("📎 Загрузить xlsx", callback_data="menu:upload"),
         InlineKeyboardButton("📥 Шаблон xlsx", callback_data="menu:sample")],
    ]

    if message_id:
        await context.bot.edit_message_text(
            text=text, chat_id=chat_id, message_id=message_id,
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )


# ══════════════════════════════════════
#  УЧАСТНИКИ
# ══════════════════════════════════════

async def show_members(chat_id, context, message_id):
    members = db.get_members()

    if not members:
        text = "👥 *Участники*\n\nСписок пуст. Загрузите .xlsx или добавьте вручную."
    else:
        lines = ["👥 *Участники*\n"]
        for i, m in enumerate(members, 1):
            status = "✅" if m["telegram_id"] else "⏳"
            lines.append(f"{i}. {m['name']} ({m['pin']}) {status}")
        lines.append(f"\n✅ = в боте, ⏳ = не зарегистрирован")
        text = "\n".join(lines)

    keyboard = [
        [InlineKeyboardButton("➕ Добавить вручную", callback_data="mem:add")],
    ]
    # Кнопки удаления (по 2 в ряд)
    row = []
    for m in members:
        row.append(InlineKeyboardButton(f"❌ {m['name'][:15]}", callback_data=f"mem:del:{m['pin']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="menu:main")])

    await context.bot.edit_message_text(
        text=text, chat_id=chat_id, message_id=message_id,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# ══════════════════════════════════════
#  ЗАСЕДАНИЯ (список)
# ══════════════════════════════════════

async def show_meetings(chat_id, context, message_id):
    meetings = db.get_meetings()

    if not meetings:
        text = "📋 *Заседания*\n\nНет заседаний."
    else:
        lines = ["📋 *Заседания*\n"]
        for mt in meetings:
            status = {"draft": "📝", "active": "🟢", "closed": "🔴"}.get(mt["status"], "📝")
            lines.append(f"{status} Протокол №{mt['protocol_number']} — {mt['date']}")
            lines.append(f"   Сеансов: {len(mt['sessions'])}, Присутств.: {len(mt['attendees'])}")
        text = "\n".join(lines)

    keyboard = [
        [InlineKeyboardButton("➕ Новое заседание", callback_data="mtg:create")],
    ]
    for mt in meetings:
        keyboard.append([InlineKeyboardButton(
            f"📋 №{mt['protocol_number']} ({mt['date']})",
            callback_data=f"mtg:open:{mt['id']}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="menu:main")])

    await context.bot.edit_message_text(
        text=text, chat_id=chat_id, message_id=message_id,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# ══════════════════════════════════════
#  ЗАСЕДАНИЕ (детали)
# ══════════════════════════════════════

async def show_meeting_detail(chat_id, context, message_id, meeting_id):
    mt = db.get_meeting(meeting_id)
    if not mt:
        return

    members = db.get_members()
    text = (
        f"📋 *Протокол №{mt['protocol_number']}*\n"
        f"📅 {mt['date']}\n"
        f"👥 Присутствующих: {len(mt['attendees'])} из {len(members)}\n"
        f"📂 Сеансов: {len(mt['sessions'])}"
    )

    keyboard = [
        [InlineKeyboardButton(f"👥 Присутствующие ({len(mt['attendees'])})", callback_data=f"att:{meeting_id}:0")],
        [InlineKeyboardButton("📂 Сеансы", callback_data=f"ses:list:{meeting_id}"),
         InlineKeyboardButton("➕ Сеанс", callback_data=f"ses:add:{meeting_id}")],
        [InlineKeyboardButton("📄 Отчёт (DOCX)", callback_data=f"mtg:report:{meeting_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"mtg:del:{meeting_id}"),
         InlineKeyboardButton("◀️ Назад", callback_data="menu:meetings")],
    ]

    await context.bot.edit_message_text(
        text=text, chat_id=chat_id, message_id=message_id,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# ══════════════════════════════════════
#  ПРИСУТСТВУЮЩИЕ (с пагинацией)
# ══════════════════════════════════════

async def show_attendees(chat_id, context, message_id, meeting_id, page=0):
    mt = db.get_meeting(meeting_id)
    if not mt:
        return
    members = db.get_members()
    per_page = 8
    total_pages = max(1, (len(members) + per_page - 1) // per_page)
    page = min(page, total_pages - 1)
    start = page * per_page
    page_members = members[start:start + per_page]

    text = (
        f"👥 *Присутствующие — Протокол №{mt['protocol_number']}*\n"
        f"Отмечено: {len(mt['attendees'])} из {len(members)}\n"
        f"Стр. {page+1}/{total_pages}\n\n"
        f"Нажмите на имя чтобы отметить/убрать:"
    )

    keyboard = []
    for m in page_members:
        check = "✅" if m["pin"] in mt["attendees"] else "⬜"
        keyboard.append([InlineKeyboardButton(
            f"{check} {m['name']}",
            callback_data=f"att:toggle:{meeting_id}:{m['pin']}:{page}"
        )])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"att:{meeting_id}:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"Все ✅", callback_data=f"att:all:{meeting_id}:{page}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"att:{meeting_id}:{page+1}"))
    keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("◀️ К заседанию", callback_data=f"mtg:open:{meeting_id}")])

    await context.bot.edit_message_text(
        text=text, chat_id=chat_id, message_id=message_id,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# ══════════════════════════════════════
#  СЕАНСЫ
# ══════════════════════════════════════

async def show_sessions(chat_id, context, message_id, meeting_id):
    mt = db.get_meeting(meeting_id)
    if not mt:
        return

    if not mt["sessions"]:
        text = f"📂 *Сеансы — Протокол №{mt['protocol_number']}*\n\nНет сеансов."
    else:
        lines = [f"📂 *Сеансы — Протокол №{mt['protocol_number']}*\n"]
        for s in mt["sessions"]:
            icon = {"draft": "📝", "voting": "🟢", "closed": "🔴"}.get(s["status"], "📝")
            lines.append(f"{icon} {s['title']} ({len(s['questions'])} вопр.)")
        text = "\n".join(lines)

    keyboard = [[InlineKeyboardButton("➕ Новый сеанс", callback_data=f"ses:add:{meeting_id}")]]
    for s in mt["sessions"]:
        icon = {"draft": "📝", "voting": "🟢", "closed": "🔴"}.get(s["status"], "📝")
        keyboard.append([InlineKeyboardButton(
            f"{icon} {s['title'][:30]}",
            callback_data=f"ses:open:{meeting_id}:{s['id']}"
        )])
    keyboard.append([InlineKeyboardButton("◀️ К заседанию", callback_data=f"mtg:open:{meeting_id}")])

    await context.bot.edit_message_text(
        text=text, chat_id=chat_id, message_id=message_id,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# ══════════════════════════════════════
#  СЕАНС (детали)
# ══════════════════════════════════════

async def show_session_detail(chat_id, context, message_id, meeting_id, session_id):
    mt = db.get_meeting(meeting_id)
    sess = db.get_session(meeting_id, session_id)
    if not mt or not sess:
        return

    status_text = {"draft": "📝 Черновик", "voting": "🟢 Голосование", "closed": "🔴 Завершён"}.get(sess["status"], "?")

    lines = [
        f"📂 *{sess['title']}*",
        f"Статус: {status_text}",
        f"Вопросов: {len(sess['questions'])}",
        ""
    ]

    for i, q in enumerate(sess["questions"], 1):
        v = q["votes"]
        total = v["for"] + v["against"] + v["abstain"]
        lines.append(f"*{i}. {q['text']}*")
        if sess["status"] == "closed":
            verdict = "✔️ Принято" if v["for"] > v["against"] else "✖️ Не принято" if v["for"] < v["against"] else "➖ Равны"
            lines.append(f"   ✅{v['for']}  ❌{v['against']}  ⬜{v['abstain']}  ({total} гол.) {verdict}")
        elif sess["status"] == "voting":
            lines.append(f"   Проголосовало: {len(q['voted_pins'])} из {len(mt['attendees'])}")
        lines.append("")

    text = "\n".join(lines) if sess["questions"] else f"📂 *{sess['title']}*\n{status_text}\n\nНет вопросов."

    keyboard = []

    if sess["status"] == "draft":
        keyboard.append([InlineKeyboardButton("❓ Добавить вопрос", callback_data=f"q:add:{meeting_id}:{session_id}")])
        if sess["questions"]:
            keyboard.append([InlineKeyboardButton("🗳 Запустить голосование", callback_data=f"ses:start:{meeting_id}:{session_id}")])
        # Кнопки удаления вопросов
        for q in sess["questions"]:
            keyboard.append([InlineKeyboardButton(
                f"🗑 {q['text'][:25]}...",
                callback_data=f"q:del:{meeting_id}:{session_id}:{q['id']}"
            )])

    elif sess["status"] == "voting":
        keyboard.append([InlineKeyboardButton("⏹ Остановить голосование", callback_data=f"ses:stop:{meeting_id}:{session_id}")])

    elif sess["status"] == "closed":
        keyboard.append([InlineKeyboardButton("📄 Отчёт по сеансу", callback_data=f"ses:report:{meeting_id}:{session_id}")])

    keyboard.append([InlineKeyboardButton("🗑 Удалить сеанс", callback_data=f"ses:del:{meeting_id}:{session_id}")])
    keyboard.append([InlineKeyboardButton("◀️ К сеансам", callback_data=f"ses:list:{meeting_id}")])

    await context.bot.edit_message_text(
        text=text, chat_id=chat_id, message_id=message_id,
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )


# ══════════════════════════════════════
#  CALLBACK HANDLER (роутер)
# ══════════════════════════════════════

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех admin inline-кнопок."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Нет прав", show_alert=True)
        return

    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    msg_id = query.message.message_id

    # ── Главное меню ──
    if data == "menu:main":
        await show_main_menu(chat_id, context, msg_id)

    elif data == "menu:members":
        await show_members(chat_id, context, msg_id)

    elif data == "menu:meetings":
        await show_meetings(chat_id, context, msg_id)

    elif data == "menu:upload":
        admin_input[ADMIN_ID] = {"action": "upload"}
        await context.bot.edit_message_text(
            text="📎 *Загрузка участников*\n\nОтправьте .xlsx файл.\nКолонка A = ФИО, B = PIN\n\n/cancel — отмена",
            chat_id=chat_id, message_id=msg_id, parse_mode="Markdown"
        )

    elif data == "menu:sample":
        await send_sample_file(chat_id, context)

    # ── Участники ──
    elif data == "mem:add":
        admin_input[ADMIN_ID] = {"action": "add_member"}
        await context.bot.edit_message_text(
            text="➕ *Добавить участника*\n\nОтправьте сообщение в формате:\n`ФИО, PIN`\n\nНапример:\n`Иванов Иван Иванович, 1001`\n\n/cancel — отмена",
            chat_id=chat_id, message_id=msg_id, parse_mode="Markdown"
        )

    elif data.startswith("mem:del:"):
        pin = data.split(":")[2]
        member = db.get_member_by_pin(pin)
        name = member["name"] if member else pin
        db.remove_member(pin)
        await query.answer(f"Удалён: {name}", show_alert=True)
        await show_members(chat_id, context, msg_id)

    # ── Заседания ──
    elif data == "mtg:create":
        admin_input[ADMIN_ID] = {"action": "create_meeting"}
        await context.bot.edit_message_text(
            text="➕ *Новое заседание*\n\nОтправьте дату и номер протокола:\n`ДД.ММ.ГГГГ, номер`\n\nНапример:\n`20.03.2026, 5`\n\n/cancel — отмена",
            chat_id=chat_id, message_id=msg_id, parse_mode="Markdown"
        )

    elif data.startswith("mtg:open:"):
        meeting_id = data.split(":")[2]
        await show_meeting_detail(chat_id, context, msg_id, meeting_id)

    elif data.startswith("mtg:del:"):
        meeting_id = data.split(":")[2]
        db.delete_meeting(meeting_id)
        await query.answer("Заседание удалено", show_alert=True)
        await show_meetings(chat_id, context, msg_id)

    elif data.startswith("mtg:report:"):
        meeting_id = data.split(":")[2]
        await generate_and_send_report(chat_id, context, meeting_id)

    # ── Присутствующие ──
    elif data.startswith("att:toggle:"):
        parts = data.split(":")
        meeting_id, pin, page = parts[2], parts[3], int(parts[4])
        db.toggle_attendee(meeting_id, pin)
        await show_attendees(chat_id, context, msg_id, meeting_id, page)

    elif data.startswith("att:all:"):
        parts = data.split(":")
        meeting_id, page = parts[2], int(parts[3])
        all_pins = [m["pin"] for m in db.get_members()]
        db.set_attendees(meeting_id, all_pins)
        await show_attendees(chat_id, context, msg_id, meeting_id, page)

    elif data.startswith("att:"):
        parts = data.split(":")
        meeting_id, page = parts[1], int(parts[2])
        await show_attendees(chat_id, context, msg_id, meeting_id, page)

    # ── Сеансы ──
    elif data.startswith("ses:list:"):
        meeting_id = data.split(":")[2]
        await show_sessions(chat_id, context, msg_id, meeting_id)

    elif data.startswith("ses:add:"):
        meeting_id = data.split(":")[2]
        admin_input[ADMIN_ID] = {"action": "add_session", "meeting_id": meeting_id}
        await context.bot.edit_message_text(
            text="➕ *Новый сеанс*\n\nОтправьте название:\n\nНапример:\n`Защита диссертации Иванова И.И.`\n\n/cancel — отмена",
            chat_id=chat_id, message_id=msg_id, parse_mode="Markdown"
        )

    elif data.startswith("ses:open:"):
        parts = data.split(":")
        meeting_id, session_id = parts[2], parts[3]
        await show_session_detail(chat_id, context, msg_id, meeting_id, session_id)

    elif data.startswith("ses:del:"):
        parts = data.split(":")
        meeting_id, session_id = parts[2], parts[3]
        db.delete_session(meeting_id, session_id)
        await query.answer("Сеанс удалён", show_alert=True)
        await show_sessions(chat_id, context, msg_id, meeting_id)

    elif data.startswith("ses:start:"):
        parts = data.split(":")
        meeting_id, session_id = parts[2], parts[3]
        await start_voting(chat_id, context, msg_id, meeting_id, session_id)

    elif data.startswith("ses:stop:"):
        parts = data.split(":")
        meeting_id, session_id = parts[2], parts[3]
        await stop_voting(chat_id, context, msg_id, meeting_id, session_id)

    elif data.startswith("ses:report:"):
        parts = data.split(":")
        meeting_id, session_id = parts[2], parts[3]
        await generate_and_send_report(chat_id, context, meeting_id, session_id)

    # ── Вопросы ──
    elif data.startswith("q:add:"):
        parts = data.split(":")
        meeting_id, session_id = parts[2], parts[3]
        admin_input[ADMIN_ID] = {"action": "add_question", "meeting_id": meeting_id, "session_id": session_id}
        await context.bot.edit_message_text(
            text="❓ *Добавить вопрос*\n\nОтправьте текст вопроса.\n\nНапример:\n`Утвердить диссертацию Иванова И.И.`\n\n/cancel — отмена",
            chat_id=chat_id, message_id=msg_id, parse_mode="Markdown"
        )

    elif data.startswith("q:del:"):
        parts = data.split(":")
        meeting_id, session_id, question_id = parts[2], parts[3], parts[4]
        db.delete_question(meeting_id, session_id, question_id)
        await query.answer("Вопрос удалён", show_alert=True)
        await show_session_detail(chat_id, context, msg_id, meeting_id, session_id)


# ══════════════════════════════════════
#  ГОЛОСОВАНИЕ
# ══════════════════════════════════════

async def start_voting(chat_id, context, msg_id, meeting_id, session_id):
    mt = db.get_meeting(meeting_id)
    sess = db.get_session(meeting_id, session_id)
    if not mt or not sess:
        return

    if not mt["attendees"]:
        await context.bot.edit_message_text(
            text="❌ Сначала отметьте присутствующих!",
            chat_id=chat_id, message_id=msg_id
        )
        return

    db.start_session_voting(meeting_id, session_id)

    # Уведомить участников
    members = db.get_members()
    notified = 0
    first_q = sess["questions"][0]

    for m in members:
        if m["pin"] in mt["attendees"] and m["telegram_id"]:
            try:
                keyboard = [[
                    InlineKeyboardButton("✅ За", callback_data=f"v:{meeting_id}:{session_id}:{first_q['id']}:for"),
                    InlineKeyboardButton("❌ Против", callback_data=f"v:{meeting_id}:{session_id}:{first_q['id']}:against"),
                    InlineKeyboardButton("⬜ Воздерж.", callback_data=f"v:{meeting_id}:{session_id}:{first_q['id']}:abstain"),
                ]]
                await context.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=(
                        f"🗳 *Голосование открыто!*\n\n"
                        f"📋 {sess['title']}\n"
                        f"📅 {mt['date']}, №{mt['protocol_number']}\n\n"
                        f"❓ *Вопрос 1 из {len(sess['questions'])}:*\n{first_q['text']}"
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                notified += 1
            except Exception as e:
                logger.warning(f"Не уведомлён {m['name']}: {e}")

    await context.bot.edit_message_text(
        text=f"🗳 *Голосование запущено!*\n\n📋 {sess['title']}\n📨 Уведомлено: {notified} из {len(mt['attendees'])}",
        chat_id=chat_id, message_id=msg_id, parse_mode="Markdown"
    )
    # Через секунду показать детали сеанса
    await context.bot.send_message(chat_id=chat_id, text="Обновляю...")
    # Отправить новое сообщение с деталями
    sess = db.get_session(meeting_id, session_id)  # обновить
    msg = await context.bot.send_message(chat_id=chat_id, text="⏳")
    await show_session_detail(chat_id, context, msg.message_id, meeting_id, session_id)


async def stop_voting(chat_id, context, msg_id, meeting_id, session_id):
    db.close_session_voting(meeting_id, session_id)
    mt = db.get_meeting(meeting_id)
    sess = db.get_session(meeting_id, session_id)

    # Уведомить участников
    for m in db.get_members():
        if m["pin"] in mt["attendees"] and m["telegram_id"]:
            try:
                await context.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=f"🏁 Голосование \"{sess['title']}\" завершено."
                )
            except Exception:
                pass

    await show_session_detail(chat_id, context, msg_id, meeting_id, session_id)


# ══════════════════════════════════════
#  ТЕКСТОВЫЙ ВВОД ОТ АДМИНА
# ══════════════════════════════════════

async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений от админа (ввод данных)."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return False  # Не обработано — передать дальше

    state = admin_input.get(user_id)
    if not state:
        return False  # Нет ожидания ввода

    text = update.message.text.strip()

    if text == "/cancel":
        admin_input.pop(user_id, None)
        await update.message.reply_text("Отменено. /admin — меню")
        return True

    action = state["action"]

    if action == "add_member":
        admin_input.pop(user_id, None)
        parts = text.split(",", 1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: `ФИО, PIN`\nПопробуйте /admin", parse_mode="Markdown")
            return True
        name, pin = parts[0].strip(), parts[1].strip()
        if db.add_member(name, pin):
            await update.message.reply_text(f"✅ Добавлен: {name} (PIN: {pin})\n/admin — меню")
        else:
            await update.message.reply_text(f"❌ PIN {pin} занят.\n/admin — меню")

    elif action == "create_meeting":
        admin_input.pop(user_id, None)
        parts = text.split(",", 1)
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: `ДД.ММ.ГГГГ, номер`\n/admin", parse_mode="Markdown")
            return True
        date_str, protocol = parts[0].strip(), parts[1].strip()
        db.create_meeting(date_str, protocol)
        await update.message.reply_text(f"✅ Заседание: {date_str}, №{protocol}\n/admin — меню")

    elif action == "add_session":
        admin_input.pop(user_id, None)
        meeting_id = state["meeting_id"]
        db.add_session(meeting_id, text)
        await update.message.reply_text(f"✅ Сеанс: {text}\n/admin — меню")

    elif action == "add_question":
        admin_input.pop(user_id, None)
        meeting_id = state["meeting_id"]
        session_id = state["session_id"]
        db.add_question(meeting_id, session_id, text)
        await update.message.reply_text(f"✅ Вопрос добавлен\n/admin — меню")

    elif action == "upload":
        admin_input.pop(user_id, None)
        await update.message.reply_text("📎 Отправьте .xlsx *файл* (не текст)\n/admin — меню", parse_mode="Markdown")

    return True


# ══════════════════════════════════════
#  ФАЙЛ XLSX
# ══════════════════════════════════════

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для админа.")
        return

    document = update.message.document
    filename = document.file_name or ""
    if not filename.lower().endswith(".xlsx"):
        await update.message.reply_text("❌ Нужен .xlsx\n📥 /sample — шаблон")
        return

    admin_input.pop(ADMIN_ID, None)  # сбросить состояние

    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "upload.xlsx")
    tg_file = await context.bot.get_file(document.file_id)
    await tg_file.download_to_drive(filepath)

    try:
        from openpyxl import load_workbook
        wb = load_workbook(filepath)
        ws = wb.active
        added, skipped = 0, 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or len(row) < 2:
                continue
            name = str(row[0]).strip() if row[0] else ""
            pin = str(row[1]).strip() if row[1] else ""
            if pin.endswith(".0"):
                pin = pin[:-2]
            if not name or not pin:
                continue
            if db.add_member(name, pin):
                added += 1
            else:
                skipped += 1

        await update.message.reply_text(
            f"📊 *Загрузка:*\n✅ Добавлено: {added}\n⏭ Пропущено: {skipped}\n👥 Всего: {len(db.get_members())}\n\n/admin — меню",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}\n📥 /sample — шаблон")
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


async def cmd_sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await send_sample_file(update.effective_chat.id, context)


async def send_sample_file(chat_id, context):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Участники"

    hf = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    hfill = PatternFill(start_color="0D6E6E", end_color="0D6E6E", fill_type="solid")
    b = Border(left=Side("thin"), right=Side("thin"), top=Side("thin"), bottom=Side("thin"))

    for col, h in enumerate(["ФИО", "PIN"], 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font, c.fill, c.border = hf, hfill, b

    for r, (n, p) in enumerate([
        ("Иванов Иван Иванович", "1001"),
        ("Петрова Мария Сергеевна", "1002"),
        ("Каримов Алишер Бахтиёрович", "1003"),
    ], 2):
        ws.cell(row=r, column=1, value=n).border = b
        ws.cell(row=r, column=2, value=p).border = b

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 15

    os.makedirs(DATA_DIR, exist_ok=True)
    fp = os.path.join(DATA_DIR, "shablon.xlsx")
    wb.save(fp)

    with open(fp, "rb") as f:
        await context.bot.send_document(
            chat_id=chat_id, document=f, filename="shablon_uchastniki.xlsx",
            caption="📋 Заполните и отправьте боту.\nA=ФИО, B=PIN. Строку 1 не удалять."
        )
    os.remove(fp)


# ══════════════════════════════════════
#  ОТЧЁТ
# ══════════════════════════════════════

async def generate_and_send_report(chat_id, context, meeting_id, session_id=None):
    from report import generate_report
    filepath = generate_report(meeting_id, session_id)
    if filepath:
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id, document=f,
                filename=filepath.split("/")[-1],
                caption="📄 Отчёт для протокола"
            )
    else:
        await context.bot.send_message(chat_id=chat_id, text="❌ Ошибка отчёта.")
