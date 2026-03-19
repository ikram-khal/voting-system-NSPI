"""
report.py — Генерация DOCX-отчёта о результатах голосования.

Отчёт содержит:
  - Дату и номер протокола заседания
  - Количество присутствующих
  - Результаты каждого сеанса и вопроса
"""

import os
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import database as db
from config import DATA_DIR


def generate_report(meeting_id, session_id=None):
    """Сгенерировать DOCX-отчёт.

    Args:
        meeting_id: ID заседания
        session_id: ID конкретного сеанса (None = все сеансы)

    Returns:
        Путь к файлу или None при ошибке.
    """
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        return None

    members = db.get_members()
    member_map = {m["pin"]: m["name"] for m in members}

    doc = Document()

    # Стиль документа
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Times New Roman"
    font.size = Pt(12)

    # Заголовок
    title = doc.add_heading("РЕЗУЛЬТАТЫ ТАЙНОГО ГОЛОСОВАНИЯ", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Информация о заседании
    doc.add_paragraph("")
    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.LEFT
    info.add_run(f"Дата заседания: ").bold = True
    info.add_run(f"{meeting['date']}\n")
    info.add_run(f"Протокол №: ").bold = True
    info.add_run(f"{meeting['protocol_number']}\n")
    info.add_run(f"Присутствовало: ").bold = True
    info.add_run(f"{len(meeting['attendees'])} членов учёного совета\n")

    # Список присутствующих
    doc.add_heading("Присутствующие:", level=2)
    attendee_names = []
    for pin in meeting["attendees"]:
        name = member_map.get(pin, f"PIN: {pin}")
        attendee_names.append(name)

    for i, name in enumerate(sorted(attendee_names), 1):
        doc.add_paragraph(f"{i}. {name}", style="List Number")

    doc.add_paragraph("")

    # Определить, какие сеансы включать
    sessions = meeting["sessions"]
    if session_id:
        sessions = [s for s in sessions if s["id"] == session_id]

    # Результаты по каждому сеансу
    for sess in sessions:
        doc.add_heading(f"Сеанс: {sess['title']}", level=2)

        for i, q in enumerate(sess["questions"], 1):
            v = q["votes"]
            total = v["for"] + v["against"] + v["abstain"]

            # Вопрос
            q_para = doc.add_paragraph()
            q_para.add_run(f"Вопрос {i}: ").bold = True
            q_para.add_run(q["text"])

            # Таблица результатов
            table = doc.add_table(rows=2, cols=4)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER

            # Заголовки
            headers = ["", "За", "Против", "Воздержался"]
            for j, header in enumerate(headers):
                cell = table.rows[0].cells[j]
                cell.text = header
                for paragraph in cell.paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in paragraph.runs:
                        run.bold = True

            # Данные
            row = table.rows[1]
            row.cells[0].text = "Количество голосов"
            row.cells[1].text = str(v["for"])
            row.cells[2].text = str(v["against"])
            row.cells[3].text = str(v["abstain"])
            for j in range(4):
                for paragraph in row.cells[j].paragraphs:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # Итог
            result_para = doc.add_paragraph()
            result_para.add_run(f"Всего голосов: {total} из {len(meeting['attendees'])}").italic = True
            result_para.add_run("\n")
            if v["for"] > v["against"]:
                result_para.add_run("РЕШЕНИЕ: ПРИНЯТО").bold = True
            elif v["for"] < v["against"]:
                result_para.add_run("РЕШЕНИЕ: НЕ ПРИНЯТО").bold = True
            else:
                result_para.add_run("РЕШЕНИЕ: ГОЛОСА РАВНЫ").bold = True

            doc.add_paragraph("")

    # Подписи
    doc.add_paragraph("")
    doc.add_paragraph("")
    sign = doc.add_paragraph()
    sign.add_run("Секретарь учёного совета: ").bold = True
    sign.add_run("_" * 30)
    doc.add_paragraph("")
    sign2 = doc.add_paragraph()
    sign2.add_run("Председатель учёного совета: ").bold = True
    sign2.add_run("_" * 30)

    # Сохранить
    os.makedirs(DATA_DIR, exist_ok=True)
    safe_date = meeting["date"].replace(".", "-").replace("/", "-")
    filename = f"report_{meeting['protocol_number']}_{safe_date}.docx"
    filepath = os.path.join(DATA_DIR, filename)
    doc.save(filepath)

    return filepath
