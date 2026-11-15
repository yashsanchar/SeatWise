"""Step 9: the revised timetable CSV, and the two notice-board lists (course-wise, room-wise)."""

import csv
import io
import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from seating import (ExamPlanner, default_timetable, get_rule, get_strategy, load_schedule_rows)
from seating.io_notice import render_course_list, render_room_list

ROOT = Path(__file__).resolve().parent.parent
TT_CSV = ROOT / "data" / "sample" / "timetable_nov_dec_2026.csv"
PDFS = ROOT / "data" / "pdf_samples"
LISTS = ["mba_ba_2025-27.pdf", "msc_dsa_2025-27.pdf", "mtech_2025-30.pdf", "mtech_2024-29.pdf",
         "DUMMY_MTECH_AIDS_2023-2028_7TH_SEM.pdf", "DUMMY_MTECH_AIDS_2022-2027_9TH_SEM.pdf"]
NO_STUDENTS = "No student list loaded yet. Load it on the Data tab first."


class Base(unittest.TestCase):
    def setUp(self):
        app_module.state.__init__()
        self.client = TestClient(app_module.app)

    def load_everything(self):
        """Timetable CSV through the normal upload box, then the six student PDFs through preview + confirm."""
        r = self.client.post("/api/tables", files={"schedule": ("tt.csv", TT_CSV.read_bytes(), "text/csv")})
        self.assertEqual(r.status_code, 200, r.text)
        for name in LISTS:
            body = self.client.post("/api/pdf/preview", data={"kind": "students"},
                                    files={"file": (name, (PDFS / name).read_bytes(), "application/pdf")}).json()
            r = self.client.post("/api/students/confirm", json={"group": body["suggested_group"], "rows": body["rows"]})
            self.assertEqual(r.status_code, 200, r.text)

    def plan(self):
        r = self.client.post("/api/plan", json={"rule": "fourway", "strategy": "hybrid"})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class TimetableCsvTests(Base):
    def test_csv_content(self):
        rows = load_schedule_rows(TT_CSV)
        self.assertEqual(len(rows), 36)
        self.assertEqual({r["slot"] for r in rows}, {"11:00 AM - 2:00 PM"})
        self.assertEqual({r["group"] for r in rows},
                         {"MBA BA sem 3", "MSc DSA sem 3", "M.Tech sem 3", "M.Tech sem 5", "M.Tech sem 7", "M.Tech sem 9"})
        codes = {r["course"] for r in rows}
        self.assertNotIn("DS5A-623", codes)                    # one MBA paper on 23 Nov: Financial Analytics
        self.assertIn("DS5A-621", codes)
        m3 = {r["course"]: r["course_name"] for r in rows if r["group"] == "M.Tech sem 3"}
        self.assertEqual(m3["DS6A-204"], "Numerical Methods")

    def test_csv_matches_builtin_timetable(self):
        mine = sorted((r["date"], r["course"], r["course_name"], r["group"]) for r in load_schedule_rows(TT_CSV))
        built_in = sorted((r["date"], r["course"], r["course_name"], r["group"]) for r in default_timetable())
        self.assertEqual(mine, built_in)

    def test_load_csv_then_plan_has_no_problems(self):
        self.load_everything()
        tt = self.client.get("/api/timetable").json()
        self.assertEqual((len(tt["rows"]), tt["days"], tt["sessions"], tt["warnings"]), (36, 12, 12, []))
        summary = self.client.get("/api/data").json()
        self.assertEqual(summary["students"], 163 + 55 + 45)
        self.assertEqual(summary["warnings"], [])               # no "papers with no students"
        body = self.plan()
        self.assertEqual((body["failed_sessions"], body["total_conflicts"]), (0, 0))
        self.assertEqual(len(body["sessions"]), 12)

    def test_scanned_message(self):
        r = self.client.post("/api/pdf/preview", data={"kind": "schedule"},
                             files={"file": ("t.pdf", (PDFS / "timetable_scanned.pdf").read_bytes(), "application/pdf")})
        self.assertEqual(r.status_code, 400)
        self.assertIn("scan or photo and has no readable text", r.json()["detail"])
        self.assertIn("timetable_nov_dec_2026.csv", r.json()["detail"])


class NoticeListTests(Base):
    def setUp(self):
        super().setUp()
        self.load_everything()
        self.plan_json = self.plan()

    def get(self, fmt, names=False):
        r = self.client.get(f"/api/download/{fmt}" + ("?names=1" if names else ""))
        self.assertEqual(r.status_code, 200, r.text)
        return r

    def seated(self):
        """(date, roll, course, room) of every seated student, from the existing CSV download."""
        rows = csv.DictReader(io.StringIO(self.get("csv").text))
        return [(r["date"], r["roll_no"], r["course"], r["room"], r["name"]) for r in rows]

    def pages(self, html):
        return html.split('<section class="session">')[1:]

    def test_headers_and_one_page_per_session(self):
        for fmt in ("notice-courses", "notice-rooms"):
            r = self.get(fmt)
            self.assertTrue(r.headers["content-type"].startswith("text/html"))
            self.assertIn("attachment", r.headers["content-disposition"])
            pages = self.pages(r.text)
            self.assertEqual(len(pages), 12)
            for p in pages:
                self.assertIn("SDSF End Semester Examination", p)
                self.assertRegex(p, r"20\d\d-\d\d-\d\d")
                self.assertIn("11:00 AM - 2:00 PM", p)
            self.assertIn("break-after: page", r.text)

    def test_course_list_each_student_once_under_right_course_and_room(self):
        pages = self.pages(self.get("notice-courses").text)
        seated = self.seated()
        found = []
        for page in pages:
            date = re.search(r"(20\d\d-\d\d-\d\d)", page).group(1)
            for block in page.split("<h2>")[1:]:
                course = re.match(r"([A-Z0-9-]+)", block).group(1)
                self.assertIn("&ndash;", block.split("</h2>")[0])           # course name shown
                rows = re.findall(r'class="roll">([^<]+)</span></span><span>(B-\d+)\*?', block)
                rolls = [r for r, _ in rows]
                self.assertEqual(rolls, sorted(rolls, key=lambda x: (re.sub(r"\d+", "", x), int(re.sub(r"\D", "", x)))))
                found += [(date, roll, course, room) for roll, room in rows]
        self.assertEqual(len(found), len(seated))
        self.assertEqual(sorted(found), sorted((d, r, c, room) for d, r, c, room, _ in seated))

    def test_room_list_each_student_once_under_right_room_and_course(self):
        pages = self.pages(self.get("notice-rooms").text)
        seated = self.seated()
        found = []
        for page in pages:
            date = re.search(r"(20\d\d-\d\d-\d\d)", page).group(1)
            for block in page.split("<h2>")[1:]:
                room = re.match(r"Room (B-\d+)", block).group(1)
                found += [(date, roll, course, room)
                          for roll, course in re.findall(r'class="roll">([^<]+)</span></span><span>([A-Z0-9-]+) ', block)]
        self.assertEqual(sorted(found), sorted((d, r, c, room) for d, r, c, room, _ in seated))

    def test_no_names_unless_asked(self):
        names = {n for *_, n in self.seated()}
        for fmt in ("notice-courses", "notice-rooms"):
            text = self.get(fmt).text
            self.assertFalse([n for n in list(names)[:40] if n in text], fmt)
            with_names = self.get(fmt, names=True).text
            self.assertTrue(any(n.replace("&", "&amp;") in with_names for n in list(names)[:10]))

    def test_provisional_marker(self):
        for fmt in ("notice-courses", "notice-rooms"):
            text = self.get(fmt).text
            self.assertIn("PROVISIONAL", text)
            self.assertTrue(("B-002*" in text) if fmt == "notice-courses" else ('B-002 <span class="tag">PROVISIONAL' in text))

    def test_unknown_format_and_empty_plan(self):
        self.assertEqual(self.client.get("/api/download/pdf").status_code, 404)
        for fmt in ("csv", "txt", "json"):
            self.assertEqual(self.get(fmt).status_code, 200)
        self.client.post("/api/reset")
        for fmt in ("notice-courses", "notice-rooms"):
            r = self.client.get(f"/api/download/{fmt}")
            self.assertEqual((r.status_code, r.json()["detail"]), (409, NO_STUDENTS))

    def test_plan_exists_but_not_for_this_data_gives_409(self):
        self.client.delete("/api/students/M.Tech%20sem%203")            # editing data drops the plan
        r = self.client.get("/api/download/notice-courses")
        self.assertEqual(r.status_code, 409)
        self.assertIn("No plan yet", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
