"""
handlers_admin.py — Обработчики команд для админа/секретаря.

Админ управляет через Mini Web App (основной интерфейс),
но также может голосовать как обычный участник через инлайн-кнопки.

Загрузка участников: админ отправляет .xlsx файл с колонками ФИО и PIN.
"""

import json
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from config import ADMIN_ID, WEBAPP_URL, DATA_DIR
import database as db

logger = logging.getLogger(__name__)


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin — открыть панель управления."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return

    keyboard = [[InlineKeyboardButton(
        "📋 Панель управления",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )]]
    await update.message.reply_text(
        "🏛 *Илмий Кенгаш — Панель секретаря*\n\n"
        "Нажмите кнопку ниже для управления заседаниями и голосованием.\n\n"
        "📎 Также можно отправить .xlsx файл со списком участников.\n"
        "📥 /sample — скачать шаблон файла",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ──────────────────────────────────────────────
#  Загрузка участников из Excel-файла
# ──────────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка файла .xlsx от админа — загрузка списка участников."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Загрузка файлов доступна только админу.")
        return

    document = update.message.document
    if not document:
        return

    filename = document.file_name or ""
    if not filename.lower().endswith(".xlsx"):
        await update.message.reply_text(
            "❌ Отправьте файл в формате .xlsx\n"
            "📥 /sample — скачать шаблон"
        )
        return

    # Скачать файл
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "upload_members.xlsx")
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(filepath)

    # Прочитать Excel
    try:
        from openpyxl import load_workbook
        wb = load_workbook(filepath)
        ws = wb.active

        added = 0
        skipped = 0
        errors = []

        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            # Ожидаем: Колонка A = ФИО, Колонка B = PIN
            if not row or len(row) < 2:
                continue

            name = str(row[0]).strip() if row[0] else ""
            pin = str(row[1]).strip() if row[1] else ""

            # Убрать .0 если PIN был числом в Excel
            if pin.endswith(".0"):
                pin = pin[:-2]

            if not name or not pin:
                errors.append(f"Строка {row_num}: пустое ФИО или PIN")
                continue

            if db.add_member(name, pin):
                added += 1
            else:
                skipped += 1

        # Итог
        msg = f"📊 *Результат загрузки:*\n\n"
        msg += f"✅ Добавлено: {added}\n"
        msg += f"⏭ Пропущено (PIN уже есть): {skipped}\n"
        if errors:
            msg += f"⚠️ Ошибки:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                msg += f"\n...и ещё {len(errors)-10}"

        total = len(db.get_members())
        msg += f"\n\n👥 Всего участников в системе: {total}"

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка чтения Excel: {e}")
        await update.message.reply_text(
            f"❌ Ошибка чтения файла: {e}\n\n"
            "Убедитесь, что в файле:\n"
            "• Колонка A — ФИО\n"
            "• Колонка B — PIN\n"
            "• Первая строка — заголовок\n\n"
            "📥 /sample — скачать шаблон"
        )
    finally:
        # Удалить временный файл
        if os.path.exists(filepath):
            os.remove(filepath)


async def send_sample(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /sample — отправить шаблон Excel-файла."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Команда доступна только админу.")
        return

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Участники"

    # Стили
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="0D6E6E", end_color="0D6E6E", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Заголовки
    headers = ["ФИО", "PIN"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # Примеры
    examples = [
        ("Иванов Иван Иванович", "1001"),
        ("Петрова Мария Сергеевна", "1002"),
        ("Каримов Алишер Бахтиёрович", "1003"),
    ]
    for row_num, (name, pin) in enumerate(examples, 2):
        ws.cell(row=row_num, column=1, value=name).border = thin_border
        ws.cell(row=row_num, column=2, value=pin).border = thin_border

    # Ширина колонок
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 15

    # Сохранить и отправить
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, "shablon_uchastniki.xlsx")
    wb.save(filepath)

    with open(filepath, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="shablon_uchastniki.xlsx",
            caption=(
                "📋 *Шаблон для загрузки участников*\n\n"
                "1. Откройте файл в Excel\n"
                "2. Заполните ФИО и PIN (удалите примеры)\n"
                "3. PIN — любой уникальный код (цифры/буквы)\n"
                "4. Сохраните и отправьте этот файл боту\n\n"
                "⚠️ Первая строка (заголовок) — не удалять!"
            ),
            parse_mode="Markdown"
        )

    os.remove(filepath)


# ──────────────────────────────────────────────
#  API для Web App (через web_app_data)
# ──────────────────────────────────────────────

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных из Mini Web App."""
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        data = json.loads(update.effective_message.web_app_data.data)
    except (json.JSONDecodeError, AttributeError):
        await update.effective_message.reply_text("❌ Ошибка данных из Web App.")
        return

    action = data.get("action")

    if action == "add_member":
        await _handle_add_member(update, data)
    elif action == "remove_member":
        await _handle_remove_member(update, data)
    elif action == "create_meeting":
        await _handle_create_meeting(update, data)
    elif action == "set_attendees":
        await _handle_set_attendees(update, data)
    elif action == "add_session":
        await _handle_add_session(update, data)
    elif action == "add_question":
        await _handle_add_question(update, data)
    elif action == "start_voting":
        await _handle_start_voting(update, data, context)
    elif action == "stop_voting":
        await _handle_stop_voting(update, data, context)
    elif action == "get_data":
        await _handle_get_data(update)
    elif action == "delete_meeting":
        db.delete_meeting(data.get("meeting_id"))
        await update.effective_message.reply_text("🗑 Заседание удалено.")
    elif action == "delete_session":
        db.delete_session(data.get("meeting_id"), data.get("session_id"))
        await update.effective_message.reply_text("🗑 Сеанс удалён.")
    elif action == "delete_question":
        db.delete_question(data.get("meeting_id"), data.get("session_id"), data.get("question_id"))
        await update.effective_message.reply_text("🗑 Вопрос удалён.")
    elif action == "generate_report":
        await _handle_generate_report(update, data, context)
    else:
        await update.effective_message.reply_text(f"❓ Неизвестное действие: {action}")


async def _handle_add_member(update, data):
    name = data.get("name", "").strip()
    pin = data.get("pin", "").strip()
    if not name or not pin:
        await update.effective_message.reply_text("❌ Укажите ФИО и PIN.")
        return
    if db.add_member(name, pin):
        await update.effective_message.reply_text(f"✅ Участник добавлен: {name} (PIN: {pin})")
    else:
        await update.effective_message.reply_text(f"❌ PIN {pin} уже занят.")


async def _handle_remove_member(update, data):
    pin = data.get("pin", "").strip()
    db.remove_member(pin)
    await update.effective_message.reply_text(f"✅ Участник с PIN {pin} удалён.")


async def _handle_create_meeting(update, data):
    date_str = data.get("date", "").strip()
    protocol = data.get("protocol_number", "").strip()
    if not date_str or not protocol:
        await update.effective_message.reply_text("❌ Укажите дату и номер протокола.")
        return
    meeting_id = db.create_meeting(date_str, protocol)
    await update.effective_message.reply_text(
        f"✅ Заседание создано\n📅 Дата: {date_str}\n📝 Протокол №{protocol}"
    )


async def _handle_set_attendees(update, data):
    meeting_id = data.get("meeting_id")
    pins = data.get("pins", [])
    db.set_attendees(meeting_id, pins)
    await update.effective_message.reply_text(
        f"✅ Присутствующие обновлены: {len(pins)} чел."
    )


async def _handle_add_session(update, data):
    meeting_id = data.get("meeting_id")
    title = data.get("title", "").strip()
    if not title:
        await update.effective_message.reply_text("❌ Укажите название сеанса.")
        return
    session_id = db.add_session(meeting_id, title)
    if session_id:
        await update.effective_message.reply_text(f"✅ Сеанс добавлен: {title}")
    else:
        await update.effective_message.reply_text("❌ Заседание не найдено.")


async def _handle_add_question(update, data):
    meeting_id = data.get("meeting_id")
    session_id = data.get("session_id")
    text = data.get("text", "").strip()
    if not text:
        await update.effective_message.reply_text("❌ Укажите текст вопроса.")
        return
    q_id = db.add_question(meeting_id, session_id, text)
    if q_id:
        await update.effective_message.reply_text(f"✅ Вопрос добавлен: {text[:50]}...")
    else:
        await update.effective_message.reply_text("❌ Сеанс не найден.")


async def _handle_start_voting(update, data, context):
    """Запустить голосование и уведомить участников."""
    meeting_id = data.get("meeting_id")
    session_id = data.get("session_id")

    meeting = db.get_meeting(meeting_id)
    if not meeting:
        await update.effective_message.reply_text("❌ Заседание не найдено.")
        return

    # Найти сеанс
    session = None
    for s in meeting["sessions"]:
        if s["id"] == session_id:
            session = s
            break
    if not session:
        await update.effective_message.reply_text("❌ Сеанс не найден.")
        return

    if not session["questions"]:
        await update.effective_message.reply_text("❌ В сеансе нет вопросов.")
        return

    db.start_session_voting(meeting_id, session_id)
    db.update_meeting(meeting_id, {"status": "active"})

    # Уведомить всех присутствующих участников
    members = db.get_members()
    attendee_pins = meeting["attendees"]
    notified = 0

    for m in members:
        if m["pin"] in attendee_pins and m["telegram_id"]:
            try:
                first_q = session["questions"][0]
                keyboard = [
                    [
                        InlineKeyboardButton("✅ За", callback_data=f"vote:{meeting_id}:{session_id}:{first_q['id']}:for"),
                        InlineKeyboardButton("❌ Против", callback_data=f"vote:{meeting_id}:{session_id}:{first_q['id']}:against"),
                        InlineKeyboardButton("⬜ Воздерж.", callback_data=f"vote:{meeting_id}:{session_id}:{first_q['id']}:abstain"),
                    ]
                ]
                await context.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=(
                        f"🗳 *Голосование открыто!*\n\n"
                        f"📋 Сеанс: {session['title']}\n"
                        f"📅 Заседание: {meeting['date']}, протокол №{meeting['protocol_number']}\n\n"
                        f"❓ *Вопрос 1 из {len(session['questions'])}:*\n"
                        f"{first_q['text']}"
                    ),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                notified += 1
            except Exception as e:
                logger.warning(f"Не удалось уведомить {m['name']}: {e}")

    await update.effective_message.reply_text(
        f"✅ Голосование запущено!\n"
        f"📋 Сеанс: {session['title']}\n"
        f"📨 Уведомлено: {notified} из {len(attendee_pins)} участников"
    )


async def _handle_stop_voting(update, data, context):
    """Остановить голосование и показать результаты админу."""
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

    # Формируем результаты
    lines = [
        f"📊 *Результаты голосования*\n",
        f"📋 Сеанс: {session['title']}",
        f"📅 {meeting['date']}, протокол №{meeting['protocol_number']}\n",
        f"👥 Присутствовало: {len(meeting['attendees'])} чел.\n"
    ]

    for i, q in enumerate(session["questions"], 1):
        v = q["votes"]
        total = v["for"] + v["against"] + v["abstain"]
        lines.append(f"*Вопрос {i}:* {q['text']}")
        lines.append(f"  ✅ За: {v['for']}  |  ❌ Против: {v['against']}  |  ⬜ Воздерж.: {v['abstain']}")
        lines.append(f"  📊 Всего голосов: {total}")
        if v["for"] > v["against"]:
            lines.append(f"  ✔️ *РЕШЕНИЕ ПРИНЯТО*")
        elif v["for"] < v["against"]:
            lines.append(f"  ✖️ *РЕШЕНИЕ НЕ ПРИНЯТО*")
        else:
            lines.append(f"  ➖ *ГОЛОСА РАВНЫ*")
        lines.append("")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

    # Уведомить участников о завершении
    members = db.get_members()
    for m in members:
        if m["pin"] in meeting["attendees"] and m["telegram_id"]:
            try:
                await context.bot.send_message(
                    chat_id=m["telegram_id"],
                    text=f"🏁 Голосование по сеансу \"{session['title']}\" завершено."
                )
            except Exception:
                pass


async def _handle_get_data(update):
    """Отправить текущие данные в Web App."""
    data = {
        "members": db.get_members(),
        "meetings": db.get_meetings()
    }
    # Убираем telegram_id из ответа для безопасности
    safe_members = []
    for m in data["members"]:
        safe_members.append({
            "name": m["name"],
            "pin": m["pin"],
            "registered": m["telegram_id"] is not None
        })
    data["members"] = safe_members

    await update.effective_message.reply_text(
        json.dumps(data, ensure_ascii=False)
    )


async def _handle_generate_report(update, data, context):
    """Сгенерировать DOCX-отчёт."""
    meeting_id = data.get("meeting_id")
    session_id = data.get("session_id", None)

    from report import generate_report
    filepath = generate_report(meeting_id, session_id)

    if filepath:
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=f,
                filename=filepath.split("/")[-1],
                caption="📄 Отчёт о голосовании для протокола"
            )
    else:
        await update.effective_message.reply_text("❌ Не удалось создать отчёт.")
