"""Notice-board lists: two printable HTML files made from the finished plan (standard library only).

  * course-wise: "Which room do I go to?"  For every exam session: a small table (paper x room) and then, for
                 every paper, its roll numbers in order with room, row and seat.
  * room-wise:   "Who sits in this room?"  For every exam session and every room: a picture of the room (like the
                 app's seating plan) and the roll numbers in order with paper, row and seat. Rooms are listed
                 ground floor first, one block after the other.

One A4 page (or more, when the list is long) per session. Every list is a real table with column headings, so
nobody has to guess what "R3 S5" means. Roll numbers only; names appear only if show_names=True.
The colours are fixed light colours on purpose, so the print looks the same whatever theme the app uses.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Dict, Iterable, List

from .models import ExamData, SessionPlan, natural_key

TITLE = "SDSF End Semester Examination"
PROVISIONAL_NOTE = ("PROVISIONAL room: the room layout has not been checked against the real room yet, "
                    "so seats may change.")
HOW_TO_READ = ("How to read the seat: Row 1 is the row nearest the board. Seat 1 is the seat on the far left as you "
               "face the board (walking lanes are counted too, so the numbers match the plan on the screen).")
SPLIT_AFTER = 14            # a list longer than this is printed as two tables side by side

CSS = """
@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; color: #111; background: #fff; margin: 0; font-size: 11pt; }
.session { padding: 4mm 6mm; break-after: page; page-break-after: always; }
.session:last-child { break-after: auto; page-break-after: auto; }
h1 { font-size: 19pt; margin: 0; }
.head { border-bottom: 3px solid #222; padding-bottom: 6px; margin-bottom: 8px; }
.when { font-size: 15pt; font-weight: bold; margin-top: 4px; }
.how { font-size: 9.5pt; color: #333; margin: 0 0 8px; }
h2 { font-size: 13pt; margin: 14px 0 3px; padding: 4px 8px; background: #e8e8e8; break-after: avoid; page-break-after: avoid; }
h2 small { font-weight: normal; font-size: 10.5pt; }
h3 { font-size: 11pt; margin: 12px 0 3px; break-after: avoid; page-break-after: avoid; }
.sub { margin: 2px 0 4px; font-size: 10pt; color: #333; break-after: avoid; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #999; padding: 2px 6px; text-align: left; font-size: 10.5pt; }
th { background: #f2f2f2; font-size: 9.5pt; }
td.n, th.n { text-align: center; }
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
.pair { display: flex; gap: 8mm; align-items: flex-start; }
.pair > table { flex: 1; }
.roll { font-weight: bold; }
.dim { color: #555; }
.tag { border: 1px solid #000; padding: 0 4px; font-size: 8.5pt; font-weight: bold; }
.glance td, .glance th { text-align: center; }
.glance td:first-child, .glance th:first-child { text-align: left; }
.glance tr.total td { font-weight: bold; background: #f2f2f2; }
.map { margin: 6px 0 4px; break-inside: avoid; page-break-inside: avoid; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.board { margin: 0 0 4px var(--rn); text-align: center; font-size: 8pt; font-weight: bold; color: #555; letter-spacing: .12em;
         border-top: 3px solid #7a4a00; padding-top: 2px; }
.grid { display: grid; gap: 1.2mm; width: max-content; }
.cn, .rn { font-size: 7.5pt; color: #555; display: flex; align-items: center; justify-content: center; }
.seat { height: 11mm; border-radius: 2mm; border: 1px solid; display: flex; flex-direction: column; align-items: center;
        justify-content: center; line-height: 1.15; overflow: hidden; }
.seat b { font-size: 7pt; } .seat span { font-size: 6pt; }
.seat.cc { background: hsl(var(--h) 42% 88%); border-color: hsl(var(--h) 55% 58%); color: hsl(var(--h) 80% 20%); }
.seat.blocked { background: repeating-linear-gradient(45deg, #ddd, #ddd 1.2mm, #fff 1.2mm, #fff 2.4mm); border-color: #bbb; }
.seat.empty { border: 1.5px dashed #999; background: #fff; }
.legend { display: flex; flex-wrap: wrap; gap: 2mm 4mm; margin: 4px 0 2px; font-size: 9pt; break-after: avoid; page-break-after: avoid; }
.legend i { display: inline-block; width: 4mm; height: 4mm; border-radius: 1mm; border: 1px solid; vertical-align: -0.8mm; margin-right: 1.5mm; }
.legend i.blocked { background: repeating-linear-gradient(45deg, #ddd, #ddd 1mm, #fff 1mm, #fff 2mm); border-color: #bbb; }
.legend i.empty { border: 1.5px dashed #999; }
.note { margin-top: 12px; font-size: 9.5pt; color: #333; }
.empty { color: #a00; font-weight: bold; }
"""


def _seated(plan: SessionPlan):
    """Every seated student of one session: (room, row, seat, student), one tuple each."""
    out = []
    for rp in plan.room_plans:
        room = rp.room
        for r in range(room.rows):
            for c in range(room.cols):
                st = room.seat(r, c).student
                if st is not None:
                    out.append((room, r + 1, c + 1, st))
    return out


def _rooms_in_order(plan: SessionPlan) -> list:
    """The rooms used in a session, ground floor first, one block after the other."""
    rooms = [rp.room for rp in plan.room_plans]
    return sorted(rooms, key=lambda r: (r.floor, r.block, natural_key(r.room_id)))


def _where(room) -> str:
    return escape(room.zone_label) if room.zone_label else ""


def _prov_tag(room) -> str:
    return ' <span class="tag">PROVISIONAL</span>' if room.provisional else ""


def _page(plan: SessionPlan, body: List[str], rooms: list) -> str:
    s = plan.session
    parts = [f'<section class="session"><div class="head"><h1>{escape(TITLE)}</h1>',
             f'<div class="when">{escape(s.date)} &nbsp;|&nbsp; {escape(s.slot)}</div></div>',
             f'<p class="how">{escape(HOW_TO_READ)}</p>']
    parts += body
    if any(r.provisional for r in rooms):
        parts.append(f'<div class="note">{escape(PROVISIONAL_NOTE)}</div>')
    parts.append("</section>")
    return "\n".join(parts)


def _document(title: str, pages: List[str]) -> str:
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
            f'<style>{CSS}</style></head><body>\n' + "\n".join(pages) + "\n</body></html>")


def _no_plan(plan: SessionPlan) -> str:
    return f'<p class="empty">No seating for this session{": " + escape(plan.error) if plan.error else ""}.</p>'


def _colour(course: str, data: ExamData) -> str:
    """The same colour the app gives a paper: its position in the sorted list of all papers picks the hue."""
    codes = sorted(data.course_names)
    i = max(0, codes.index(course)) if course in codes else 0
    return f"--h:{(i * 137.5 + 205) % 360:.1f}"


def _legend(plan: SessionPlan, seated: list, data: ExamData) -> str:
    counts: Dict[str, int] = {}
    for _room, _row, _seat, st in seated:
        counts[st.course] = counts.get(st.course, 0) + 1
    order = list(plan.session.courses) + sorted(set(counts) - set(plan.session.courses))
    chips = "".join(f'<span><i class="seat cc" style="{_colour(c, data)}"></i>{escape(c)}'
                    f'{" " + escape(data.course_names[c]) if data.course_names.get(c) else ""} ({counts.get(c, 0)})</span>'
                    for c in order)
    return (f'<div class="legend">{chips}<span><i class="blocked"></i>No seat</span>'
            f'<span><i class="empty"></i>Empty seat</span></div>')


def _room_map(room, data: ExamData) -> str:
    """The seating picture of one room, drawn like the app's room card: the board at the top, one box per seat with
    the roll number and the paper, hatched boxes for walking lanes and dashed boxes for empty seats."""
    col_mm = min(17.0, 168.0 / (room.cols + 0.7))
    rn = 6.0
    cells = ['<span></span>'] + [f'<span class="cn">{c}</span>' for c in range(1, room.cols + 1)]
    for r in range(room.rows):
        cells.append(f'<span class="rn">{r + 1}</span>')
        for c in range(room.cols):
            seat = room.seat(r, c)
            if seat.blocked:
                cells.append('<div class="seat blocked"></div>')
            elif seat.student is None:
                cells.append('<div class="seat empty"></div>')
            else:
                st = seat.student
                cells.append(f'<div class="seat cc" style="{_colour(st.course, data)}"><b>{escape(st.roll_no)}</b>'
                             f'<span>{escape(st.course)}</span></div>')
    return (f'<div class="map" style="--rn:{rn}mm"><div class="board">FRONT OF ROOM (row 1)</div>'
            f'<div class="grid" style="grid-template-columns:{rn}mm repeat({room.cols},{col_mm:.1f}mm)">'
            + "".join(cells) + '</div></div>')


def _rooms_today(rooms: list, counts: Dict[str, int]) -> str:
    """Small key at the top of every page: where each room is and how many students sit in it."""
    rows = "".join(f'<tr><td><b>{escape(r.room_id)}</b>{_prov_tag(r)}</td><td>{_where(r)}</td>'
                   f'<td class="n">{counts.get(r.room_id, 0)}</td></tr>' for r in rooms)
    return (f'<h3>Rooms used in this session</h3><table><thead><tr><th>Room</th><th>Where</th>'
            f'<th class="n">Students</th></tr></thead><tbody>{rows}</tbody></table>')


def _roll_tables(items: list, columns: list, show_names: bool) -> str:
    """items: [(student, cells...)] sorted by roll number. columns: heading of every cell after the roll number.
    A long list is cut into two tables side by side (read the left one first, then the right one)."""
    head = ["Roll no"] + (["Name"] if show_names else []) + columns

    def table(chunk: list) -> str:
        th = "".join(('<th class="n">' if h in ("Row", "Seat") else "<th>") + escape(h) + "</th>" for h in head)
        trs = []
        for st, *cells in chunk:
            tds = [f'<td class="roll">{escape(st.roll_no)}</td>']
            if show_names:
                tds.append(f'<td class="dim">{escape(st.name)}</td>')
            for h, cell in zip(columns, cells):
                tds.append(f'<td class="n">{cell}</td>' if h in ("Row", "Seat") else f"<td>{cell}</td>")
            trs.append("<tr>" + "".join(tds) + "</tr>")
        return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"

    if len(items) <= SPLIT_AFTER:
        return table(items)
    half = (len(items) + 1) // 2
    return f'<div class="pair">{table(items[:half])}{table(items[half:])}</div>'


def render_course_list(plans: Iterable[SessionPlan], data: ExamData, show_names: bool = False) -> str:
    """Course-wise list: per session a paper x room table, then per paper: roll number -> room, row, seat."""
    pages = []
    for plan in plans:
        seated = _seated(plan)
        rooms = _rooms_in_order(plan)
        room_counts: Dict[str, int] = {}
        by_course: Dict[str, list] = {}
        for room, row, seat, st in seated:
            by_course.setdefault(st.course, []).append((room, row, seat, st))
            room_counts[room.room_id] = room_counts.get(room.room_id, 0) + 1
        order = list(plan.session.courses) + sorted(set(by_course) - set(plan.session.courses))
        body: List[str] = []
        if rooms:
            body.append(_rooms_today(rooms, room_counts))
            head = "".join(f'<th>{escape(r.room_id)}</th>' for r in rooms)
            lines = []
            for course in order:
                mine = by_course.get(course, [])
                cells = "".join(f'<td>{sum(1 for it in mine if it[0] is r) or "-"}</td>' for r in rooms)
                lines.append(f'<tr><td>{escape(course)} <span class="dim">{escape(data.course_names.get(course, ""))}</span>'
                             f'</td>{cells}<td><b>{len(mine)}</b></td></tr>')
            total = "".join(f'<td>{room_counts.get(r.room_id, 0)}</td>' for r in rooms)
            body.append(f'<h3>At a glance: how many students of each paper are in each room</h3>'
                        f'<table class="glance"><thead><tr><th>Paper</th>{head}<th>Total</th></tr></thead><tbody>'
                        f'{"".join(lines)}<tr class="total"><td>All papers</td>{total}<td>{len(seated)}</td></tr></tbody></table>')
        if rooms:
            body.append("<h3>Seating maps (the same pictures you see in the app)</h3>")
            body.append(_legend(plan, seated, data))
            for room in rooms:
                body.append(f'<p class="sub"><b>{escape(room.room_id)}</b>{_prov_tag(room)}'
                            f'{" &mdash; " + _where(room) if _where(room) else ""}</p>')
                body.append(_room_map(room, data))
        for course in order:
            mine = sorted(by_course.get(course, []), key=lambda it: natural_key(it[3].roll_no))
            cname = data.course_names.get(course, "")
            title = escape(course) + (f" &ndash; {escape(cname)}" if cname else "")
            body.append(f"<h2>{title} <small>({len(mine)} students)</small></h2>")
            if mine:
                items = [(st, f"<b>{escape(room.room_id)}</b>", row, seat) for room, row, seat, st in mine]
                body.append(_roll_tables(items, ["Room", "Row", "Seat"], show_names))
        if not plan.room_plans:
            body.append(_no_plan(plan))
        pages.append(_page(plan, body, rooms))
    return _document(f"{TITLE} - course-wise list", pages)


def render_room_list(plans: Iterable[SessionPlan], data: ExamData, show_names: bool = False) -> str:
    """Room-wise list: per session, per room (ground floor first): roll number -> paper, row, seat."""
    pages = []
    for plan in plans:
        seated = _seated(plan)
        rooms = _rooms_in_order(plan)
        body: List[str] = []
        if rooms:
            body.append(_legend(plan, seated, data))
        for room in rooms:
            mine = sorted((it for it in seated if it[0] is room), key=lambda it: natural_key(it[3].roll_no))
            papers: Dict[str, int] = {}
            for _room, _row, _seat, st in mine:
                papers[st.course] = papers.get(st.course, 0) + 1
            body.append(f"<h2>Room {escape(room.room_id)}{_prov_tag(room)} <small>({len(mine)} students)</small></h2>")
            where = _where(room)
            mix = " &nbsp;&middot;&nbsp; ".join(f"{escape(c)}: {n}" for c, n in sorted(papers.items()))
            body.append(f'<p class="sub">{where + " &mdash; " if where else ""}Papers in this room: {mix}</p>')
            body.append(_room_map(room, data))
            items = [(st, escape(st.course), row, seat) for _room, row, seat, st in mine]
            body.append(_roll_tables(items, ["Paper", "Row", "Seat"], show_names))
        if not plan.room_plans:
            body.append(_no_plan(plan))
        pages.append(_page(plan, body, rooms))
    return _document(f"{TITLE} - room-wise list", pages)


def export_course_list(plans, data: ExamData, path, show_names: bool = False) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_course_list(plans, data, show_names), encoding="utf-8")


def export_room_list(plans, data: ExamData, path, show_names: bool = False) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_room_list(plans, data, show_names), encoding="utf-8")
