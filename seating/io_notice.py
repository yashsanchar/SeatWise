"""Notice-board lists: two printable HTML files made from the finished plan (standard library only).

  * course-wise: for every exam session and every course -> roll numbers (sorted) with the room and seat
  * room-wise:   for every exam session and every room   -> roll numbers (sorted) with the seat and course

One A4 page per session (page-break in print CSS). Roll numbers only; names appear only if show_names=True.
The colours are fixed light colours on purpose, so the print looks the same whatever theme the app uses.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import ExamData, SessionPlan, natural_key
from .seat_encoding import FLAG_OCCUPIED, seat_code

TITLE = "SDSF End Semester Examination"
PROVISIONAL_NOTE = ("* = PROVISIONAL room: the room layout has not been checked against the real room yet, "
                    "so seats may change.")

CSS = """
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; margin: 0; font-size: 12pt; }
.session { padding: 4mm 6mm; break-after: page; page-break-after: always; }
.session:last-child { break-after: auto; page-break-after: auto; }
h1 { font-size: 20pt; margin: 0; }
.head { border-bottom: 3px solid #222; padding-bottom: 6px; margin-bottom: 10px; }
.when { font-size: 16pt; font-weight: bold; margin-top: 4px; }
h2 { font-size: 15pt; margin: 14px 0 4px; padding: 4px 8px; background: #e8e8e8; break-after: avoid; }
h2 small { font-weight: normal; font-size: 11pt; }
.list { column-count: 2; column-gap: 10mm; }
.row { display: flex; justify-content: space-between; gap: 6px; padding: 1px 0; white-space: nowrap; border-bottom: 1px solid #ccc; break-inside: avoid; }
.roll { font-weight: bold; }
.code { color: #555; font-size: 10pt; }
.tag { border: 1px solid #000; padding: 0 4px; font-size: 9pt; font-weight: bold; }
.note { margin-top: 12px; font-size: 10pt; color: #333; }
.empty { color: #a00; font-weight: bold; }
"""


def _seated(plan: SessionPlan, data: ExamData):
    """Every seated student of one session: (room, row, seat, seat_code, student), one tuple each."""
    index = {r.room_id: i for i, r in enumerate(data.rooms)}
    out = []
    for rp in plan.room_plans:
        room = rp.room
        for r in range(room.rows):
            for c in range(room.cols):
                st = room.seat(r, c).student
                if st is not None:
                    out.append((room, r + 1, c + 1, seat_code(index.get(room.room_id, 0), r, c, FLAG_OCCUPIED), st))
    return out


def _room_label(room, short: bool = False) -> str:
    """Room name. Provisional rooms get the full PROVISIONAL tag in headings and a '*' inside the long lists."""
    if not room.provisional:
        return escape(room.room_id)
    return escape(room.room_id) + ("*" if short else ' <span class="tag">PROVISIONAL</span>')


def _page(plan: SessionPlan, body: List[str], any_provisional: bool) -> str:
    s = plan.session
    parts = [f'<section class="session"><div class="head"><h1>{escape(TITLE)}</h1>',
             f'<div class="when">{escape(s.date)} &nbsp;|&nbsp; {escape(s.slot)}</div></div>']
    parts += body
    if any_provisional:
        parts.append(f'<div class="note">{escape(PROVISIONAL_NOTE)}</div>')
    parts.append("</section>")
    return "\n".join(parts)


def _document(title: str, pages: List[str]) -> str:
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
            f'<style>{CSS}</style></head><body>\n' + "\n".join(pages) + "\n</body></html>")


def _name(student, show_names: bool) -> str:
    return f' <span class="code">{escape(student.name)}</span>' if show_names else ""


def render_course_list(plans: Iterable[SessionPlan], data: ExamData, show_names: bool = False) -> str:
    """Course-wise list: per session, per course: roll number -> room and seat (sorted by roll number)."""
    pages = []
    for plan in plans:
        seated = _seated(plan, data)
        by_course: Dict[str, list] = {}
        for item in seated:
            by_course.setdefault(item[4].course, []).append(item)
        order = list(plan.session.courses) + sorted(set(by_course) - set(plan.session.courses))
        body = []
        for course in order:
            items = sorted(by_course.get(course, []), key=lambda it: natural_key(it[4].roll_no))
            cname = data.course_names.get(course, "")
            title = escape(course) + (f" &ndash; {escape(cname)}" if cname else "")
            body.append(f"<h2>{title} <small>({len(items)} students)</small></h2>")
            body.append('<div class="list">')
            for room, row, seat, code, st in items:
                body.append(f'<div class="row"><span><span class="roll">{escape(st.roll_no)}</span>'
                            f'{_name(st, show_names)}</span><span>{_room_label(room, True)} '
                            f'<span class="code">R{row} S{seat}</span></span></div>')
            body.append("</div>")
        if not plan.room_plans:
            body.append(f'<p class="empty">No seating for this session{": " + escape(plan.error) if plan.error else ""}.</p>')
        pages.append(_page(plan, body, any(it[0].provisional for it in seated)))
    return _document(f"{TITLE} - course-wise list", pages)


def render_room_list(plans: Iterable[SessionPlan], data: ExamData, show_names: bool = False) -> str:
    """Room-wise list: per session, per room: roll number -> course and seat (sorted by roll number)."""
    pages = []
    for plan in plans:
        seated = _seated(plan, data)
        body = []
        for rp in plan.room_plans:
            items = sorted((it for it in seated if it[0] is rp.room), key=lambda it: natural_key(it[4].roll_no))
            body.append(f"<h2>Room {_room_label(rp.room)} <small>({len(items)} students)</small></h2>")
            body.append('<div class="list">')
            for room, row, seat, code, st in items:
                body.append(f'<div class="row"><span><span class="roll">{escape(st.roll_no)}</span>'
                            f'{_name(st, show_names)}</span><span>{escape(st.course)} '
                            f'<span class="code">R{row} S{seat}</span></span></div>')
            body.append("</div>")
        if not plan.room_plans:
            body.append(f'<p class="empty">No seating for this session{": " + escape(plan.error) if plan.error else ""}.</p>')
        pages.append(_page(plan, body, any(rp.room.provisional for rp in plan.room_plans)))
    return _document(f"{TITLE} - room-wise list", pages)


def export_course_list(plans, data: ExamData, path, show_names: bool = False) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_course_list(plans, data, show_names), encoding="utf-8")


def export_room_list(plans, data: ExamData, path, show_names: bool = False) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_room_list(plans, data, show_names), encoding="utf-8")
