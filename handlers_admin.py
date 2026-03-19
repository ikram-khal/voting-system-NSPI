"""
handlers_admin.py — Обработчики для админа/секретаря.

Панель управления открывается через inline-кнопку (WebApp).
Загрузка участников — через .xlsx файл.
"""

import json
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from config import ADMIN_ID, WEBAPP_URL, DATA_DIR
import database as db

logger = logging.getLogger(__name__)


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin — панель управления."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав администратора.")
        return

    if not WEBAPP_URL:
        await update.message.reply_text(
            "🏛 *Илмий Кенгаш — Панель секретаря*\n\n"
            "⚠️ WebApp недоступна в локальном режиме.\n"
            "На Koyeb панель откроется автоматически.\n\n"
            "📎 Пока можно отправить .xlsx файл для загрузки участников.\n"
            "📥 /sample — скачать шаблон",
            parse_mode="Markdown"
        )
        return

    keyboard = [[InlineKeyboardButton(
        "📋 Открыть панель управления",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )]]
    await update.message.reply_text(
        "🏛 *Илмий Кенгаш — Панель секретаря*\n\n"
        "Нажмите кнопку ниже ⬇️",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ── Загрузка Excel ──

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загрузка .xlsx со списком участников."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Загрузка доступна только админу.")
        return

    document = update.message.document
    if not document:
        return

    filename = document.file_name or ""
    if not filename.lower().endswith(".xlsx"):
        await update.message.reply_text(
            "❌ Нужен файл .xlsx\n📥 /sample — скачать шаблон"
        )
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "upload_members.xlsx")
    tg_file = await context.bot.get_file(document.file_id)
    await tg_file.download_to_drive(filepath)

    try:
        from openpyxl import load_workbook
        wb = load_workbook(filepath)
        ws = wb.active

        added = 0
        skipped = 0
        errors = []

        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 2:
                continue
            name = str(row[0]).strip() if row[0] else ""
            pin = str(row[1]).strip() if row[1] else ""
            if pin.endswith(".0"):
                pin = pin[:-2]
            if not name or not pin:
                errors.append(f"Строка {row_num}: пустое ФИО или PIN")
                continue
            if db.add_member(name, pin):
                added += 1
            else:
                skipped += 1

        msg = f"📊 *Результат загрузки:*\n\n"
        msg += f"✅ Добавлено: {added}\n"
        msg += f"⏭ Пропущено (PIN занят): {skipped}\n"
        if errors:
            msg += f"⚠️ Ошибки:\n" + "\n".join(errors[:5])
        msg += f"\n\n👥 Всего в системе: {len(db.get_members())}"
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка Excel: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {e}\n\n"
            "Формат: колонка A = ФИО, B = PIN\n"
            "📥 /sample — скачать шаблон"
        )
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


async def cmd_sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /sample — шаблон Excel."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Только для админа.")
        return

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Участники"

    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0D6E6E", end_color="0D6E6E", fill_type="solid")
    border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin")
    )

    for col, header in enumerate(["ФИО", "PIN"], 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border

    examples = [
        ("Иванов Иван Иванович", "1001"),
        ("Петрова Мария Сергеевна", "1002"),
        ("Каримов Алишер Бахтиёрович", "1003"),
    ]
    for r, (name, pin) in enumerate(examples, 2):
        ws.cell(row=r, column=1, value=name).border = border
        ws.cell(row=r, column=2, value=pin).border = border

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 15

    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "shablon.xlsx")
    wb.save(filepath)

    with open(filepath, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="shablon_uchastniki.xlsx",
            caption=(
                "📋 *Шаблон для загрузки*\n\n"
                "1. Заполните ФИО и PIN\n"
                "2. Удалите примеры\n"
                "3. Отправьте файл боту\n\n"
                "⚠️ Первую строку (заголовок) не удалять!"
            ),
            parse_mode="Markdown"
        )
    os.remove(filepath)


# ── Данные из Web App ──

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных из Mini Web App."""
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        data = json.loads(update.effective_message.web_app_data.data)
    except (json.JSONDecodeError, AttributeError):
        await update.effective_message.reply_text("❌ Ошибка данных.")
        return

    action = data.get("action")
    handlers = {
        "add_member": _wa_add_member,
        "remove_member": _wa_remove_member,
        "create_meeting": _wa_create_meeting,
        "set_attendees": _wa_set_attendees,
        "add_session": _wa_add_session,
        "add_question": _wa_add_question,
        "start_voting": _wa_start_voting,
        "stop_voting": _wa_stop_voting,
        "delete_meeting": _wa_delete_meeting,
        "delete_session": _wa_delete_session,
        "delete_question": _wa_delete_question,
        "generate_report": _wa_generate_report,
    }

    handler = handlers.get(action)
    if handler:
        await handler(update, data, context)
    else:
        await update.effective_message.reply_text(f"❓ Неизвестное: {action}")


async def _wa_add_member(update, data, context):
    name = data.get("name", "").strip()
    pin = data.get("pin", "").strip()
    if not name or not pin:
        await update.effective_message.reply_text("❌ Укажите ФИО и PIN.")
        return
    if db.add_member(name, pin):
        await update.effective_message.reply_text(f"✅ {name} (PIN: {pin})")
    else:
        await update.effective_message.reply_text(f"❌ PIN {pin} занят.")


async def _wa_remove_member(update, data, context):
    db.remove_member(data.get("pin", ""))
    await update.effective_message.reply_text("✅ Участник удалён.")


async def _wa_create_meeting(update, data, context):
    date_str = data.get("date", "").strip()
    protocol = data.get("protocol_number", "").strip()
    if not date_str or not protocol:
        await update.effective_message.reply_text("❌ Дата и номер протокола.")
        return
    db.create_meeting(date_str, protocol)
    await update.effective_message.reply_text(f"✅ Заседание: {date_str}, №{protocol}")


async def _wa_set_attendees(update, data, context):
    db.set_attendees(data.get("meeting_id"), data.get("pins", []))
    await update.effective_message.reply_text(f"✅ Присутствующие: {len(data.get('pins', []))} чел.")


async def _wa_add_session(update, data, context):
    title = data.get("title", "").strip()
    if not title:
        await update.effective_message.reply_text("❌ Название сеанса.")
        return
    sid = db.add_session(data.get("meeting_id"), title)
    await update.effective_message.reply_text(f"✅ Сеанс: {title}")


async def _wa_add_question(update, data, context):
    text = data.get("text", "").strip()
    if not text:
        await update.effective_message.reply_text("❌ Текст вопроса.")
        return
    db.add_question(data.get("meeting_id"), data.get("session_id"), text)
    await update.effective_message.reply_text(f"✅ Вопрос добавлен")


async def _wa_start_voting(update, data, context):
    meeting_id = data.get("meeting_id")
    session_id = data.get("session_id")
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        await update.effective_message.reply_text("❌ Заседание не найдено.")
        return

    session = None
    for s in meeting["sessions"]:
        if s["id"] == session_id:
            session = s
            break
    if not session or not session["questions"]:
        await update.effective_message.reply_text("❌ Нет вопросов в сеансе.")
        return

    db.start_session_voting(meeting_id, session_id)

    # Уведомить участников
    members = db.get_members()
    notified = 0
    first_q = session["questions"][0]

    for m in members:
        if m["pin"] in meeting["attendees"] and m["telegram_id"]:
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
                        f"📋 {session['title']}\n"
                        f"📅 {meeting['date']}, протокол №{meeting['protocol_number']}\n\n"
                        f"❓ *Вопрос 1 из {len(session['questions'])}:*\n"
                        f"{first_q['text']}"
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                notified += 1
            except Exception as e:
                logger.warning(f"Не уведомлён {m['name']}: {e}")

    await update.effective_message.reply_text(
        f"✅ Голосование запущено!\n📋 {session['title']}\n📨 Уведомлено: {notified}"
    )


async def _wa_stop_voting(update, data, context):
    meeting_id = data.get("meeting_id")
    session_id = data.get("session_id")
    db.close_session_voting(meeting_id, session_id)

    meeting = db.get_meeting(meeting_id)
    session = None
    for s in meeting["sessions"]:
        if s["id"] == session_id:
            session = s
            break
    if not session:
        await update.effective_message.reply_text("❌ Сеанс не найден.")
        return

    lines = [
        f"📊 *Результаты: {session['title']}*",
        f"📅 {meeting['date']}, протокол №{meeting['protocol_number']}",
        f"👥 Присутствовало: {len(meeting['attendees'])}\n"
    ]
    for i, q in enumerate(session["questions"], 1):
        v = q["votes"]
        total = v["for"] + v["against"] + v["abstain"]
        verdict = "✔️ ПРИНЯТО" if v["for"] > v["against"] else "✖️ НЕ ПРИНЯТО" if v["for"] < v["against"] else "➖ РАВНЫ"
        lines.append(f"*{i}. {q['text']}*")
        lines.append(f"   ✅ {v['for']}  ❌ {v['against']}  ⬜ {v['abstain']}  (всего: {total})")
        lines.append(f"   {verdict}\n")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

    # Уведомить участников
    for m in db.get_members():
        if m["pin"] in meeting["attendees"] and m["telegram_id"]:
            try:
                await context.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=f"🏁 Голосование \"{session['title']}\" завершено."
                )
            except Exception:
                pass


async def _wa_delete_meeting(update, data, context):
    db.delete_meeting(data.get("meeting_id"))
    await update.effective_message.reply_text("🗑 Заседание удалено.")


async def _wa_delete_session(update, data, context):
    db.delete_session(data.get("meeting_id"), data.get("session_id"))
    await update.effective_message.reply_text("🗑 Сеанс удалён.")


async def _wa_delete_question(update, data, context):
    db.delete_question(data.get("meeting_id"), data.get("session_id"), data.get("question_id"))
    await update.effective_message.reply_text("🗑 Вопрос удалён.")


async def _wa_generate_report(update, data, context):
    from report import generate_report
    filepath = generate_report(data.get("meeting_id"), data.get("session_id"))
    if filepath:
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename=filepath.split("/")[-1],
                caption="📄 Отчёт для протокола"
            )
    else:
        await update.effective_message.reply_text("❌ Ошибка создания отчёта.")
