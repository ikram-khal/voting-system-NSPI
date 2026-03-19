"""
report.py — Генерация DOCX-отчёта.
"""

import os
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
import database as db
from config import DATA_DIR


def generate_report(meeting_id, session_id=None):
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        return None

    member_map = {m["pin"]: m["name"] for m in db.get_members()}
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    title = doc.add_heading("РЕЗУЛЬТАТЫ ТАЙНОГО ГОЛОСОВАНИЯ", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph("")
    info = doc.add_paragraph()
    run = info.add_run(f"Дата заседания: ")
    run.bold = True
    info.add_run(f"{meeting['date']}\n")
    run = info.add_run(f"Протокол №: ")
    run.bold = True
    info.add_run(f"{meeting['protocol_number']}\n")
    run = info.add_run(f"Присутствовало: ")
    run.bold = True
    info.add_run(f"{len(meeting['attendees'])} членов учёного совета")

    doc.add_heading("Присутствующие:", level=2)
    names = sorted(member_map.get(p, p) for p in meeting["attendees"])
    for i, name in enumerate(names, 1):
        doc.add_paragraph(f"{i}. {name}", style="List Number")

    sessions = meeting["sessions"]
    if session_id:
        sessions = [s for s in sessions if s["id"] == session_id]

    for sess in sessions:
        doc.add_heading(f"Сеанс: {sess['title']}", level=2)

        for i, q in enumerate(sess["questions"], 1):
            v = q["votes"]
            total = v["for"] + v["against"] + v["abstain"]

            p = doc.add_paragraph()
            p.add_run(f"Вопрос {i}: ").bold = True
            p.add_run(q["text"])

            table = doc.add_table(rows=2, cols=4)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER

            for j, h in enumerate(["", "За", "Против", "Воздержался"]):
                cell = table.rows[0].cells[j]
                cell.text = h
                for par in cell.paragraphs:
                    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for r in par.runs:
                        r.bold = True

            row = table.rows[1]
            row.cells[0].text = "Голосов"
            row.cells[1].text = str(v["for"])
            row.cells[2].text = str(v["against"])
            row.cells[3].text = str(v["abstain"])
            for j in range(4):
                for par in row.cells[j].paragraphs:
                    par.alignment = WD_ALIGN_PARAGRAPH.CENTER

            rp = doc.add_paragraph()
            rp.add_run(f"Всего: {total} из {len(meeting['attendees'])}").italic = True
            rp.add_run("\n")
            if v["for"] > v["against"]:
                rp.add_run("РЕШЕНИЕ: ПРИНЯТО").bold = True
            elif v["for"] < v["against"]:
                rp.add_run("РЕШЕНИЕ: НЕ ПРИНЯТО").bold = True
            else:
                rp.add_run("РЕШЕНИЕ: ГОЛОСА РАВНЫ").bold = True
            doc.add_paragraph("")

    doc.add_paragraph("")
    doc.add_paragraph("")
    s1 = doc.add_paragraph()
    s1.add_run("Секретарь учёного совета: ").bold = True
    s1.add_run("_" * 30)
    s2 = doc.add_paragraph()
    s2.add_run("Председатель учёного совета: ").bold = True
    s2.add_run("_" * 30)

    os.makedirs(DATA_DIR, exist_ok=True)
    safe_date = meeting["date"].replace(".", "-").replace("/", "-")
    filename = f"report_{meeting['protocol_number']}_{safe_date}.docx"
    filepath = os.path.join(DATA_DIR, filename)
    doc.save(filepath)
    return filepath
