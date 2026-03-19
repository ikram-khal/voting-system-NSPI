"""
database.py — JSON-хранилище данных.
Файлы: data/members.json, data/meetings.json
"""

import json
import os
import threading
from datetime import datetime
from config import DATA_DIR

_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _read(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(filename, data):
    _ensure_dir()
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── УЧАСТНИКИ ──

def get_members():
    return _read("members.json") or []


def save_members(members):
    with _lock:
        _write("members.json", members)


def add_member(name, pin):
    with _lock:
        members = get_members()
        if any(m["pin"] == pin for m in members):
            return False
        members.append({"name": name, "pin": pin, "telegram_id": None})
        _write("members.json", members)
        return True


def remove_member(pin):
    with _lock:
        members = get_members()
        members = [m for m in members if m["pin"] != pin]
        _write("members.json", members)


def bind_telegram_id(pin, telegram_id):
    with _lock:
        members = get_members()
        for m in members:
            if m["pin"] == pin:
                m["telegram_id"] = telegram_id
                _write("members.json", members)
                return m["name"]
        return None


def get_member_by_telegram_id(telegram_id):
    for m in get_members():
        if m["telegram_id"] == telegram_id:
            return m
    return None


def get_member_by_pin(pin):
    for m in get_members():
        if m["pin"] == pin:
            return m
    return None


# ── ЗАСЕДАНИЯ ──

def get_meetings():
    return _read("meetings.json") or []


def save_meetings(meetings):
    with _lock:
        _write("meetings.json", meetings)


def create_meeting(date_str, protocol_number):
    with _lock:
        meetings = get_meetings()
        meeting_id = f"m_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        meetings.append({
            "id": meeting_id,
            "date": date_str,
            "protocol_number": protocol_number,
            "created_at": datetime.now().isoformat(),
            "attendees": [],
            "sessions": [],
            "status": "draft"
        })
        _write("meetings.json", meetings)
        return meeting_id


def get_meeting(meeting_id):
    for mt in get_meetings():
        if mt["id"] == meeting_id:
            return mt
    return None


def update_meeting(meeting_id, updates):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                mt.update(updates)
                break
        _write("meetings.json", meetings)


def set_attendees(meeting_id, pin_list):
    update_meeting(meeting_id, {"attendees": pin_list})


def add_session(meeting_id, title):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                session_id = f"s_{len(mt['sessions'])+1}_{int(datetime.now().timestamp())}"
                mt["sessions"].append({
                    "id": session_id,
                    "title": title,
                    "questions": [],
                    "status": "draft"
                })
                _write("meetings.json", meetings)
                return session_id
    return None


def add_question(meeting_id, session_id, question_text):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                for sess in mt["sessions"]:
                    if sess["id"] == session_id:
                        q_id = f"q_{len(sess['questions'])+1}_{int(datetime.now().timestamp())}"
                        sess["questions"].append({
                            "id": q_id,
                            "text": question_text,
                            "votes": {"for": 0, "against": 0, "abstain": 0},
                            "voted_pins": []
                        })
                        _write("meetings.json", meetings)
                        return q_id
    return None


def start_session_voting(meeting_id, session_id):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                for sess in mt["sessions"]:
                    if sess["id"] == session_id:
                        sess["status"] = "voting"
                        mt["status"] = "active"
                        _write("meetings.json", meetings)
                        return True
    return False


def close_session_voting(meeting_id, session_id):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                for sess in mt["sessions"]:
                    if sess["id"] == session_id:
                        sess["status"] = "closed"
                        _write("meetings.json", meetings)
                        return True
    return False


def cast_vote(meeting_id, session_id, question_id, pin, vote):
    """Записать анонимный голос. Возвращает статус."""
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                if pin not in mt["attendees"]:
                    return "not_attendee"
                for sess in mt["sessions"]:
                    if sess["id"] == session_id:
                        if sess["status"] != "voting":
                            return "session_not_active"
                        for q in sess["questions"]:
                            if q["id"] == question_id:
                                if pin in q["voted_pins"]:
                                    return "already_voted"
                                q["votes"][vote] += 1
                                q["voted_pins"].append(pin)
                                _write("meetings.json", meetings)
                                return "ok"
    return "not_found"


def get_active_voting(pin):
    """Найти неотвеченные вопросы для участника."""
    result = []
    for mt in get_meetings():
        if pin not in mt.get("attendees", []):
            continue
        for sess in mt["sessions"]:
            if sess["status"] == "voting":
                unanswered = [q for q in sess["questions"] if pin not in q["voted_pins"]]
                if unanswered:
                    result.append({
                        "meeting_id": mt["id"],
                        "meeting_date": mt["date"],
                        "protocol_number": mt["protocol_number"],
                        "session_id": sess["id"],
                        "session_title": sess["title"],
                        "questions": unanswered,
                        "total_questions": len(sess["questions"])
                    })
    return result


def delete_meeting(meeting_id):
    with _lock:
        meetings = [m for m in get_meetings() if m["id"] != meeting_id]
        _write("meetings.json", meetings)


def delete_session(meeting_id, session_id):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                mt["sessions"] = [s for s in mt["sessions"] if s["id"] != session_id]
                _write("meetings.json", meetings)
                return True
    return False


def delete_question(meeting_id, session_id, question_id):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == meeting_id:
                for sess in mt["sessions"]:
                    if sess["id"] == session_id:
                        sess["questions"] = [q for q in sess["questions"] if q["id"] != question_id]
                        _write("meetings.json", meetings)
                        return True
    return False
