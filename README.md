# SeatWise - Exam Seating Backend

Python 3.8+. The `seating` package is standard library only; the API (`app.py`) needs FastAPI (see below).
Goal: seat students for each exam session so that no two students of the **same course** sit beside each other.

## Quick start

```
python main.py --demo                                  # run on the sample data in data/sample
python main.py --students S.csv --rooms R.csv --schedule X.csv --rule fourway --strategy hybrid
python main.py --demo --validate-only                  # only check that the files load
python main.py --benchmark                             # timing experiments (DAA + Computer Architecture)
python -m unittest discover -s tests -t .              # all tests (needs fastapi + httpx for the API tests); or: python -m pytest -q
```
Results go to `output/`: `seating_all.csv` (one row per seated student), `plan.json` (for the API/frontend later),
`grids.txt` (printable room grids), `benchmarks.csv`.

Options: `--rule horizontal` (only left/right count as "beside") or `fourway` (also front/back, default);
`--strategy greedy | backtracking | hybrid` (default hybrid).

## API (FastAPI)

```
pip install -r requirements.txt
uvicorn app:app --reload          # then open http://127.0.0.1:8000/docs  (interactive page, try every endpoint)
```
| Endpoint | Purpose |
|---|---|
| `GET /api/options` | rule and strategy names for dropdowns |
| `POST /api/data` | multipart upload: `students` is required; `rooms` and `schedule` are optional and replace the in-app tables; or form field `demo=true` |
| `POST /api/pdf/preview` | multipart `kind` (students/rooms/schedule) + `file` (PDF): reads it and returns what was found. **Loads nothing.** Scanned PDFs get a plain 400 message |
| `POST /api/students/confirm` | JSON `{group, rows:[{roll_no,name,include}]}`: loads one checked student list for one group (same group again replaces it) |
| `DELETE /api/students/{group}` | forget one loaded list |
| `POST /api/tables` | multipart `rooms` and/or `schedule` (CSV/Excel) without a student file |
| `GET /api/data` | summary of what is loaded (students, papers/sessions, warnings); 409 when nothing is loaded at all |
| `POST /api/reset` | back to the empty start: clears students, plan and timetable, restores the built-in rooms. The page calls it on every load |
| `GET /api/rooms`, `PUT /api/rooms`, `POST /api/rooms/reset` | the room editor: list rooms (layout = one string of 1/0 per row), save the edited list, go back to the built-in rooms |
| `GET /api/timetable`, `PUT /api/timetable`, `POST /api/timetable/reset` | the timetable table: one row per paper (date, slot, course, course_name, group) |
| `POST /api/plan` | JSON `{"rule": "fourway", "strategy": "hybrid"}` -> seating for every session (`SessionPlan.to_dict()` + `conflicts` count from `verify.py`) |
| `GET /api/download/csv\|json\|txt\|notice-courses\|notice-rooms` | latest plan as a file. `notice-courses` / `notice-rooms` are the printable notice-board lists (HTML); add `?names=1` to print student names too (default: roll numbers only) |
| `GET /api/compare?rule=fourway` | runs greedy, backtracking and hybrid on every session; CSV of search steps and time side by side (advanced mode) |
| `GET /api/benchmarks` | DAA + Computer Architecture experiments (run once, cached) |

Notes: **the server keeps nothing between requests** (needed for Vercel, where every request runs on a fresh copy). The loaded data travels with the browser: every `/api/...` response carries the current state in the `X-Seatwise-State` header (compressed) and the page sends it back with the next request. A request without the header starts empty. Downloads are fetched by the page (not plain links) so they carry the header too; the plan is rebuilt from the data + rule + strategy. The page calls `POST /api/reset` every time it opens, so every visit starts empty. Uploads are capped at 4 MB per file (Vercel's request limit is 4.5 MB). Tests use `tests/session_client.py`, a TestClient that keeps the header like the browser does.
If a `frontend/` folder exists, `app.py` serves it at `/`; otherwise `/` redirects to `/docs`.
Bad files return HTTP 400 with the backend's own readable message. Tests: `tests/test_api.py` (FastAPI `TestClient`).

## Rooms and timetable (in the app)

The app starts with the built-in **rooms B-002, B-003, B-004 (Block B) and A-201 to A-204 (Block A)** and **no timetable and no student lists**: the Data tab, the
Timetable tab and the Seating plan tab are empty until you load something. The timetable comes from an upload on the Data
tab (the Exam schedule box); `POST /api/timetable/reset` (the "Reset to printed timetable" button on a loaded timetable)
loads the built-in printed one (12 exam days, 36 papers). Rooms and timetable are edited on their own tabs and saved with
one button; saving drops the old seating plan because it no longer matches. A plan needs both a student list and a timetable;
the API answers 409 with "No student list loaded yet..." or "No exam timetable loaded yet..." until they are loaded.
* **Rooms tab**: click a seat to switch it on/off (drag to paint several, click a row/column number for a whole line),
  `+ Row` / `- Row` / `+ Column` / `- Column`, rename, "Use this room", add or delete rooms. Every built-in room is
  labelled **Provisional** (also on the seating plan and in the text download) until you tick "Layout checked against
  the real room". Rooms are described as "files" (what people call rows: a stack of benches from front to back) with a
  walking lane (a no-seat column) between files, drawn from the front. B-002: 6 benches of 2 / 6 of 3 / 9 of 2 (48 seats).
  B-003: 9 of 2 / 7 of 3 / 7 of 2 (53). B-004: no rows, single chairs, placeholder 6 x 8 = 48 and pillars at unknown
  places. A-201: 9 of 3 / 9 of 3 / 9 of 1 (63). A-202: 3 of 1 / 5 of 3 / 5 of 3 (33). A-203: 5 of 3 / 5 of 3 (30).
  A-204: 8 of 3 / 8 of 3 (48). All provisional until confirmed in the rooms.
* **Timetable tab**: empty state ("No timetable loaded", with a button to the Data tab) until a timetable is loaded; then an editable table (date picker, time, paper code, paper name, group). Codes are cleaned on save
  (`ds6a - 201`, `DS6A – 201` -> `DS6A-201`). Papers are told apart by code; the same paper listed by two groups on the
  same day (DS6A-603) is one paper. Not listed on purpose: DS5A-623 (MBA writes one paper on 23 Nov, DS5A-621; the revised PDF prints DS5A-623 too, please confirm) and Engineering Economics.
* Uploading a rooms or schedule file on the Data tab (optional) replaces the matching tab's table.
* `data/sample/students_placeholder.csv` is a test aid only (used by the API tests): 231 students for the six groups, each with the papers
  of their group (MBA without DS5A-623). The app itself has no built-in student lists.

## Normal view and advanced mode

Open `http://127.0.0.1:8000` for the teacher view: load files, choose how students may sit next to each other,
generate, download. The strategy is always hybrid.
Open `http://127.0.0.1:8000/?advanced=1` for the evaluation view: strategy dropdown, "solved by ... (N search steps)"
per room, the Experiments tab and **Compare strategies (CSV)** (`strategy_comparison.csv`, one row per exam
session plus a TOTAL row; timing is the fastest of 3 runs). On easy data the three strategies are close; the gap shows
when rooms are tight.

## Input files (CSV; Excel exports work - delimiter, BOM and header spelling are detected)

Only the students file is needed; the other two are optional because rooms and the timetable live in the app.

**students.csv** - one row per (student, course they are enrolled in). A student with 5 papers has 5 rows.
`Roll No, Student Name, Course Code [, Course Name]`

**rooms.csv** - one row per room. Seat/row numbers are 1-based, row 1 = front.
`Room ID, Name, Rows, Cols, Blocked Seats, Layout, Available`
* `Blocked Seats`: `row-col` items separated by `;` e.g. `1-1;5-6` (broken desk, pillar, aisle)
* `Layout` (optional, replaces rows/cols/blocked): rows separated by `/`; `1` = seat, `0` or `X` = no seat.
  `11111/11011/11111` is a 3x5 room with the middle seat of row 2 missing. Short rows are padded with "no seat".
* `Available`: yes/no (rooms under repair can stay in the file)

**schedule.csv** - one row per paper. Rows with the same Date + Slot are written together.
`Date, Slot, Course Code [, Course Name] [, Group]`

If a header is unusual, pass `column_maps` to `load_all(...)`, e.g.
`{"students": {"roll_no": "ID Card", "course": "Paper"}}`.
Course codes and roll numbers ignore case and inner spaces (`cs 201` = `CS201`).
Problems are reported as warnings (duplicate rows, a student with two papers in one slot, courses missing from the
schedule...) instead of crashing; a session that cannot be seated is reported with the reason, and the rest still run.

## Where each subject lives

| Subject | Files | What to show |
|---|---|---|
| DAA | `strategies.py`, `feasibility.py`, `allocator.py` | Greedy with max-heap O(N log K); backtracking with pruning; hybrid; feasibility via bipartite matching (Konig); balanced room allocation; `benchmarks.py` A, B |
| OOP | `models.py`, `rules.py`, `strategies.py`, `errors.py`, `planner.py` | Strategy pattern (`SeatingStrategy`), polymorphic `AdjacencyRule`, factories `get_rule`/`get_strategy`, encapsulated `Room`/`Seat`, exception hierarchy |
| Computer Architecture | `seat_encoding.py`, `bitops.py`, `feasibility.parity`, `benchmarks.py` C, D | 32-bit packed seat word (shifts/masks); `mask & (mask << 1)` row check; `(row ^ col) & 1` checkerboard parity (XOR gate); flat vs nested memory layout and row/column-major traversal |

## Pipeline

load CSVs -> for each session: collect students -> pick rooms (largest first) -> spread students across rooms
-> feasibility check per room -> solve each room (greedy, else backtracking) -> verify -> export.
If the tightest set of rooms cannot be solved, one more room is added and it retries.

## Notes for the viva

* Greedy is O(N log K) but can dead-end; backtracking is complete but exponential in the worst case, so it is only the fallback.
* A room can hold at most `capacity - max matching` students of one course under the four-way rule (grid graph is bipartite).
* Seats may be left empty when the room has spare seats - sometimes that is the only valid arrangement.
* Python hides most cache effects; the memory-layout benchmark shows the direction, not C-level numbers.

## PDF and Excel input (step 5)

The Data tab accepts **PDF, CSV or Excel** and routes by file type. `pdf_import.py` (API layer only, uses `pdfplumber` and
`openpyxl`; `seating/` is still standard library only) only *reads*; nothing is loaded until the teacher confirms.

* **Student lists (PDF, one per batch, several can be chosen at once).** The parser finds every roll number
  (`DS6A-2501` style) and takes the name after it. Handled: merged rows, glued serial numbers, wrapped names,
  blank enrolment numbers, fee/category/gender columns, `OLD STUDENT`. Lines with no roll number (cancelled /
  transferred rows) are not loaded and are listed in the preview; a row marked CANCELLED/TFR or a repeated roll
  number arrives unticked. The preview table lets the teacher fix names/rolls, untick rows and choose the group
  (suggested from the roll prefix: DS5A-25 MBA BA sem 3, DS5B-25 MSc DSA sem 3, DS6A-25 M.Tech sem 3, DS6A-24 M.Tech sem 5).
  Names are display only. The parser reads only the four real lists reliably; a new layout may need fixing in the preview.
* **Cohort rule** (`seating/cohorts.py`): every student of a group writes every paper the timetable lists for that
  group. The two exceptions (MBA BA: not DS5A-623; M.Tech sem 3: only Numerical Methods) hold because those papers are
  not in the timetable. Editing the timetable changes the students' papers automatically.
* **Rooms / schedule PDFs**: only if the PDF has a text layer and a real table (header row such as `Room ID, Rows, Cols`
  or `DATE, TIME, COURSE CODE, SUBJECT`). Dates `23-11-2026` become `2026-11-23`; blank merged date/time cells are filled
  from the row above. They also go through a preview; confirming uses the normal Rooms / Timetable tabs, where they can be fixed.
* **Scanned PDFs** (no text layer; no OCR here) are refused with: "This PDF has no readable text ... Use the timetable
  table in the app or upload a CSV." (wording differs slightly for students and rooms).
* **Excel**: `.xlsx` (first sheet) is converted to CSV text. A PDF sent straight to `POST /api/data` is refused.
* Student source is either CSV/Excel rows or PDF lists: uploading a CSV drops PDF lists, confirming a PDF list drops a CSV.
* Sem 7 and sem 9 have no real lists yet: until a list is loaded for them, their papers show in the "no students" warning and those days are empty.
  Two made-up lists for them are in the next section.
* Sample files for tests: `data/pdf_samples/` (the four lists, the scanned timetable, two small text-PDF tables).

## Light / dark theme (step 7)
* The toggle is at the top right of the top bar. Default is dark; the choice is kept in the browser (localStorage) and applied by a tiny script in `<head>` before the page paints.
* All colours are CSS variables in `frontend/styles.css`: the dark values are in `:root`, the light values in `:root[data-theme="light"]`. `--accent` is the fill colour (buttons, active tab); `--accent-text` is the darker amber used for text and small details in the light theme.

## Dummy student lists (M.Tech sem 7 and sem 9)
* Two separate PDFs (also in `data/pdf_samples/`): `DUMMY_MTECH_AIDS_2023-2028_7TH_SEM.pdf` (55 students, DS6A-2301...) and `DUMMY_MTECH_AIDS_2022-2027_9TH_SEM.pdf` (45 students, DS6A-2201...). The names are **made up**, not real students. The app itself has nothing built in for them.
* Load them yourself on the Data tab like any PDF: choose both in the Students box, select **Load files**, and confirm each one in the check screen (they are suggested as "M.Tech sem 7" / "M.Tech sem 9").
* To use the real lists later: on the Data tab remove the dummy list with the x on its "Student lists loaded" chip, then load the real PDF for that group.
* `make_dummy_lists.py` makes them again (needs `pip install reportlab`; seeded, so the result is the same each time). Change `count` there for another batch size.

## Fresh start (step 8)
* The server starts with no timetable and no student lists (only the built-in rooms). On every page load the frontend first calls `POST /api/reset`, so a refresh always starts clean, even when the server kept running.
* **Data tab** (what was loaded): only the Students and Papers numbers (Papers shows once a timetable is loaded), the "Student lists loaded" chips (x removes a list) and, when a timetable is loaded, the "Papers in the schedule with no students" warning. The three upload cards (Students, Rooms, Exam schedule) sit in one row; long file names are cut with an ellipsis (full list in the tooltip).
* **Timetable tab**: "No timetable loaded" until one is uploaded. **Seating plan tab**: says what is missing (student list and/or timetable); Generate works as soon as both are loaded.
* A student list can be loaded before the timetable. Its group is any group name of the built-in timetable until a timetable is loaded.

## Revised timetable (Nov-Dec 2026) and the scanned PDF

The revised timetable PDF is a phone scan with no text layer and the app does not do OCR, so uploading it shows
"This PDF is a scan or photo and has no readable text. Upload the timetable as a CSV or Excel file ...". Use
`data/sample/timetable_nov_dec_2026.csv` instead: Data tab, Exam schedule box (columns Date, Slot, Course Code, Course Name,
Group; 36 rows, 12 exam days). It holds the same rows as the built-in "printed" timetable (`default_timetable()` in
`seating/presets.py`), so the two agree. Choices made when transcribing: MBA on 23 Nov has DS5A-621 only (DS5A-623 left
out) and M.Tech sem 3 writes Numerical Methods for DS6A-204. DS6A-603 is one paper shared by MBA and MSc.

## Notice-board lists (Seating plan tab, after Generate seating)

* **Course-wise list (printable)** - `GET /api/download/notice-courses` -> `course_wise_list.html`. For every session and every
  course: course code and name, then every roll number of that course (sorted) with its room and seat (R = row, S = seat).
* **Room-wise list (printable)** - `GET /api/download/notice-rooms` -> `room_wise_list.html`. For every session and every room:
  every roll number there (sorted) with its course and seat.
* Self-contained HTML (light colours, print CSS, a new page for every session, header with date, slot and "SDSF End
  Semester Examination"). Open the file and print it (A4). Roll numbers only; `?names=1` adds names. Provisional rooms are marked
  `*` in the lists (full PROVISIONAL tag on the room headings) with a footnote. A session with many students runs onto more than one page.
* Code: `seating/io_notice.py` (standard library only); tests in `tests/test_step9.py`.

## Running on Vercel (online memory)
Vercel runs every request on a fresh copy of the app, so a Python variable cannot remember a visitor's data.
`seating/session_store.py` saves each visitor's state (students, lists from PDFs, rooms, timetable, rule and strategy
names) in Upstash Redis under a random session ID kept in a cookie (`seatwise_session`, forgotten after 24 hours).
Plans are not stored: they are rebuilt from the saved data when needed (downloads), because the solvers always give
the same answer. If `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` (or `KV_REST_API_URL`/`KV_REST_API_TOKEN`) are not
set, nothing is stored online and the app keeps one state in plain memory, as on a laptop. This is a small
remembering store, not a full database. Vercel starts the app from `app.py` (`main.py` is only the command-line tool).
Uploads are limited to 4 MB per file because Vercel rejects request bodies over 4.5 MB. Files are only written to temporary folders.
