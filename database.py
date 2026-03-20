"""
database.py — JSON-хранилище.

Заседание содержит вопросы напрямую (без сеансов).
Каждый вопрос запускается/останавливается отдельно.
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
        _write("members.json", [m for m in members if m["pin"] != pin])


def bind_telegram_id(pin, telegram_id):
    with _lock:
        members = get_members()
        for m in members:
            if m["pin"] == pin:
                m["telegram_id"] = telegram_id
                _write("members.json", members)
                return m["name"]
        return None


def get_member_by_telegram_id(tid):
    for m in get_members():
        if m["telegram_id"] == tid:
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


def create_meeting(meeting_type, date_str, protocol_number):
    """meeting_type: 'seminar' или 'council'"""
    with _lock:
        meetings = get_meetings()
        mid = f"m{int(datetime.now().timestamp())}"
        meetings.append({
            "id": mid,
            "type": meeting_type,
            "date": date_str,
            "protocol_number": protocol_number,
            "attendees": [],
            "questions": [],
            "status": "active"
        })
        _write("meetings.json", meetings)
        return mid


def get_meeting(mid):
    for mt in get_meetings():
        if mt["id"] == mid:
            return mt
    return None


def update_meeting(mid, updates):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                mt.update(updates)
                break
        _write("meetings.json", meetings)


def delete_meeting(mid):
    with _lock:
        _write("meetings.json", [m for m in get_meetings() if m["id"] != mid])


def toggle_attendee(mid, pin):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                if pin in mt["attendees"]:
                    mt["attendees"].remove(pin)
                    _write("meetings.json", meetings)
                    return False
                else:
                    mt["attendees"].append(pin)
                    _write("meetings.json", meetings)
                    return True
    return False


def set_all_attendees(mid):
    with _lock:
        meetings = get_meetings()
        members = get_members()
        for mt in meetings:
            if mt["id"] == mid:
                mt["attendees"] = [m["pin"] for m in members]
                _write("meetings.json", meetings)
                return len(mt["attendees"])
    return 0


# ── ВОПРОСЫ ──

def add_question(mid, text):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                qid = f"q{int(datetime.now().timestamp())}{len(mt['questions'])}"
                mt["questions"].append({
                    "id": qid,
                    "text": text,
                    "status": "draft",
                    "votes": {"for": 0, "against": 0, "abstain": 0},
                    "voted_pins": []
                })
                _write("meetings.json", meetings)
                return qid
    return None


def get_question(mid, qid):
    mt = get_meeting(mid)
    if mt:
        for q in mt["questions"]:
            if q["id"] == qid:
                return q
    return None


def delete_question(mid, qid):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                mt["questions"] = [q for q in mt["questions"] if q["id"] != qid]
                _write("meetings.json", meetings)


def start_question_voting(mid, qid):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                for q in mt["questions"]:
                    if q["id"] == qid:
                        q["status"] = "voting"
                        _write("meetings.json", meetings)
                        return True
    return False


def stop_question_voting(mid, qid):
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                for q in mt["questions"]:
                    if q["id"] == qid:
                        q["status"] = "closed"
                        _write("meetings.json", meetings)
                        return True
    return False


def cast_vote(mid, qid, pin, vote):
    """vote: 'for' | 'against' | 'abstain'"""
    with _lock:
        meetings = get_meetings()
        for mt in meetings:
            if mt["id"] == mid:
                if pin not in mt["attendees"]:
                    return "not_attendee"
                for q in mt["questions"]:
                    if q["id"] == qid:
                        if q["status"] != "voting":
                            return "not_active"
                        if pin in q["voted_pins"]:
                            return "already_voted"
                        q["votes"][vote] += 1
                        q["voted_pins"].append(pin)
                        _write("meetings.json", meetings)
                        return "ok"
    return "not_found"


def get_active_questions_for(pin):
    """Все открытые вопросы для участника."""
    result = []
    for mt in get_meetings():
        if pin not in mt.get("attendees", []):
            continue
        for q in mt["questions"]:
            if q["status"] == "voting" and pin not in q["voted_pins"]:
                result.append({
                    "meeting_id": mt["id"],
                    "meeting_type": mt["type"],
                    "meeting_date": mt["date"],
                    "protocol_number": mt["protocol_number"],
                    "question": q
                })
    return result


# Названия типов
TYPE_LABELS = {
    "seminar": "Илмий семинар",
    "council": "Илмий кенгаш"
}


def type_label(meeting_type):
    return TYPE_LABELS.get(meeting_type, meeting_type)
