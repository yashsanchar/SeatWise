"""Built-in starting data: the provisional rooms, the printed timetable, and the plain-dict
forms the room editor and timetable table send back and forth.

A room "spec" is a dict:  {room_id, name, layout, available, provisional, note}
  layout = list of strings, one per row, front row first; "1" = seat, "0" = no seat.
A timetable "row" is a dict:  {date (YYYY-MM-DD), slot, course, course_name, group}
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .errors import DataFormatError
from .io_csv import clean_name, norm_code, parse_layout
from .models import ExamSession, Room

MAX_ROOM_SIDE = 40          # sanity limit for rows / columns in the editor

# --------------------------------------------------------------------------- rooms
# Every room is described as "files" (what people in a classroom call rows): a file runs from the front of the
# room to the back and is a stack of benches. Each file is (seats per bench, number of benches). Files are listed
# left to right and a walking lane (a "no seat" column) is drawn between neighbouring files. A file that has fewer
# benches than the deepest one starts at the front. The grid is then one string of 1/0 per row, front row first.
def _files_layout(*files: tuple) -> List[str]:
    depth = max(benches for _width, benches in files)
    rows = []
    for r in range(depth):
        rows.append("0".join(("1" * width if r < benches else "0" * width) for width, benches in files))
    return rows


_PROVISIONAL = "Provisional: described from memory, to be confirmed by walking into the room. "


def _spec(room_id: str, block: str, layout: List[str], note: str) -> Dict[str, Any]:
    return {"room_id": room_id, "name": f"{room_id} (Block {block})", "layout": layout, "available": True,
            "provisional": True, "note": f"Block {block}. {_PROVISIONAL}{note}"}


DEFAULT_ROOM_SPECS: List[Dict[str, Any]] = [
    _spec("B-002", "B", _files_layout((2, 6), (3, 6), (2, 9)),
          "Left file 6 benches of 2, middle file 6 benches of 3, right file 9 benches of 2, walking lane "
          "between files. Files are drawn starting at the front."),
    _spec("B-003", "B", _files_layout((2, 9), (3, 7), (2, 7)),
          "Left file 9 benches of 2, middle file 7 benches of 3, right file 7 benches of 2, walking lane "
          "between files. Files are drawn starting at the front."),
    _spec("B-004", "B", ["11111111"] * 6,
          "No rows: single chairs and 1-seat benches right next to each other. The real count is not known "
          "(6 x 8 = 48 is a placeholder) and there are pillars at unknown places. Block the pillar cells and "
          "fix the size in the Rooms tab."),
    _spec("A-201", "A", _files_layout((3, 9), (3, 9), (1, 9)),
          "Left file 9 benches of 3, middle file 9 benches of 3, right file 9 single-seat benches, walking "
          "lane between files."),
    _spec("A-202", "A", _files_layout((1, 3), (3, 5), (3, 5)),
          "Left file 3 single-seat benches, middle file 5 benches of 3, right file 5 benches of 3 (described "
          "as 'singular' but seating 3 each, please check), walking lane between files."),
    _spec("A-203", "A", _files_layout((3, 5), (3, 5)),
          "Only 2 files: 5 benches of 3 on the left, 5 benches of 3 on the right, walking lane between."),
    _spec("A-204", "A", _files_layout((3, 8), (3, 8)),
          "Only 2 files: 8 benches of 3 on the left, 8 benches of 3 on the right, walking lane between."),
]


def room_to_spec(room: Room) -> Dict[str, Any]:
    layout = ["".join("0" if (r, c) in room.blocked else "1" for c in range(room.cols)) for r in range(room.rows)]
    return {"room_id": room.room_id, "name": room.name, "layout": layout, "available": room.available,
            "provisional": room.provisional, "note": room.note, "rows": room.rows, "cols": room.cols,
            "capacity": room.capacity}


def room_from_spec(spec: Dict[str, Any], position: int = 0) -> Room:
    """Validate one room from the editor and build the Room. Raises DataFormatError with a plain message."""
    label = f"Room {position}" if position else "Room"
    room_id = clean_name(str(spec.get("room_id", "")))
    if not room_id:
        raise DataFormatError(f"{label}: the room needs a Room ID")
    label = f"Room {room_id}"
    layout = spec.get("layout")
    if not isinstance(layout, Sequence) or isinstance(layout, str) or not layout:
        raise DataFormatError(f"{label}: the layout is empty")
    if not all(isinstance(line, str) for line in layout):
        raise DataFormatError(f"{label}: the layout is not valid")
    if len(layout) > MAX_ROOM_SIDE or max(len(line) for line in layout) > MAX_ROOM_SIDE:
        raise DataFormatError(f"{label}: a room can be at most {MAX_ROOM_SIDE} rows by {MAX_ROOM_SIDE} columns")
    rows, cols, blocked = parse_layout("/".join(line if line else "0" for line in layout), room_id)
    if rows * cols - len(blocked) < 1:
        raise DataFormatError(f"{label}: the room has no seats. Click at least one cell to make it a seat")
    return Room(room_id, rows, cols, blocked, clean_name(str(spec.get("name", ""))) or room_id,
                bool(spec.get("available", True)), bool(spec.get("provisional", False)),
                str(spec.get("note", "")).strip())


def rooms_from_specs(specs: Sequence[Dict[str, Any]]) -> List[Room]:
    if not specs:
        raise DataFormatError("There must be at least one room")
    rooms: List[Room] = []
    ids = set()
    for i, spec in enumerate(specs, start=1):
        room = room_from_spec(spec, i)
        if room.room_id.upper() in ids:
            raise DataFormatError(f"Room ID {room.room_id} is used twice. Each room needs its own ID")
        ids.add(room.room_id.upper())
        rooms.append(room)
    return rooms


def default_rooms() -> List[Room]:
    return rooms_from_specs(DEFAULT_ROOM_SPECS)


# --------------------------------------------------------------------------- timetable
SLOT = "11:00 AM - 2:00 PM"
G_MBA, G_MSC = "MBA BA sem 3", "MSc DSA sem 3"
G_M3, G_M5, G_M7, G_M9 = "M.Tech sem 3", "M.Tech sem 5", "M.Tech sem 7", "M.Tech sem 9"

# (group, [(date, course code, paper name), ...]) - transcribed by hand from the printed timetable (scanned,
# no OCR), paired with the dates by row order. DS5A-623 (printed on 23 Nov for MBA) is not written by this
# batch and M.Tech sem 3 writes only Numerical Methods on DS6A-204, so those are left out.
_PRINTED = [
    (G_MBA, [("2026-11-23", "DS5A-621", "Financial Analytics"), ("2026-11-25", "DS5A-601", "Forecasting Methods"),
             ("2026-11-27", "DS5A-605", "Natural Language Processing"), ("2026-11-30", "DS6A-603", "Introduction to LLM"),
             ("2026-12-01", "DS5A-607", "Research Methodology"), ("2026-12-03", "DS5A-643", "Hadoop and Spark (Big Data)")]),
    (G_MSC, [("2026-11-23", "DS5B-605", "Reinforcement Learning"), ("2026-11-25", "DS5B-603", "Forecasting Methods"),
             ("2026-11-27", "DS5B-621", "Social Media Analytics"), ("2026-11-30", "DS6A-603", "Introduction to LLM"),
             ("2026-12-01", "DS5B-601", "Deep Learning"), ("2026-12-03", "DS5B-607", "Research Methodology")]),
    (G_M3, [("2026-11-23", "DS6A-201", "Design and Analysis of Algorithm"), ("2026-11-25", "DS6A-202", "Probability Distributions"),
            ("2026-11-27", "DS6A-203", "Computer Architecture"), ("2026-11-30", "DS6A-204", "Numerical Methods"),
            ("2026-12-01", "DS6A-205", "Communication Skills"), ("2026-12-03", "DS6A-206", "Object Oriented Programming")]),
    (G_M5, [("2026-11-26", "DS6A-301", "Datamining and Data Warehousing"), ("2026-11-28", "DS6A-302", "Java Programming"),
            ("2026-12-02", "DS6A-303", "Data Engineering"), ("2026-12-04", "DS6A-304", "Statistical Inference"),
            ("2026-12-07", "DS6A-305", "Soft Computing"), ("2026-12-09", "DS6A-306", "Computer Network")]),
    (G_M7, [("2026-11-26", "DS6A-401", "Data Visualization"), ("2026-11-28", "DS6A-402", "Big Data Computing"),
            ("2026-12-02", "DS6A-403", "Cloud Computing"), ("2026-12-04", "DS6A-404", "Forecasting Methods"),
            ("2026-12-07", "DS6A-406", "Machine Learning Using Python"), ("2026-12-09", "DS6A-405", "Cryptography")]),
    (G_M9, [("2026-11-26", "DS6A-501", "Multivariate Analytics"), ("2026-11-28", "DS6A-503", "Agentic AI"),
            ("2026-12-02", "DS6A-509", "Project Report Writing"), ("2026-12-04", "DS6A-511", "Natural Language Processing"),
            ("2026-12-07", "DS6A-505", "Artificial Intelligence: Foundations and Algorithms"),
            ("2026-12-09", "DS6A-507", "High Performance Computing")]),
]


def default_timetable() -> List[Dict[str, str]]:
    return [{"date": d, "slot": SLOT, "course": code, "course_name": name, "group": group}
            for group, items in _PRINTED for d, code, name in items]


def timetable_rows_clean(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Validate the table sent by the browser. Row numbers in messages match the table on screen."""
    if not rows:
        raise DataFormatError("The timetable is empty. Add at least one paper")
    out: List[Dict[str, str]] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise DataFormatError(f"Timetable row {i} is not valid")
        clean = {k: clean_name(str(row.get(k, "") or "")) for k in ("date", "slot", "course_name", "group")}
        clean["course"] = norm_code(str(row.get("course", "") or ""))
        if not any(clean.values()):
            continue                                    # a blank row left at the bottom of the table
        if not clean["date"]:
            raise DataFormatError(f"Timetable row {i}: the date is missing")
        if not clean["course"]:
            raise DataFormatError(f"Timetable row {i}: the paper code is missing")
        out.append(clean)
    if not out:
        raise DataFormatError("The timetable is empty. Add at least one paper")
    return out


def rows_from_sessions(sessions: Sequence[ExamSession], names: Dict[str, str]) -> List[Dict[str, str]]:
    return [{"date": s.date, "slot": s.slot, "course": c, "course_name": names.get(c, ""), "group": ""}
            for s in sessions for c in s.courses]
