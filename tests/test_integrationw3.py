import csv
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "cliniccare_lite"))

import gridcare_lite_prototype as gridcare

try:
    import app as web
    from utils import security
    CLINIC_AVAILABLE = True
    CLINIC_ERROR = ""
except ImportError as error:
    web = None
    CLINIC_AVAILABLE = False
    CLINIC_ERROR = str(error)

RAW = BASE / "data" / "raw"
CLEAN = BASE / "data" / "clean"
NETWORK_TABLES = BASE / "reports" / "network_tables"
BI_TABLES = BASE / "reports" / "bi_tables"

PRODUCTION_ITERATIONS = gridcare.PBKDF2_ITERATIONS
PRODUCTION_ROUNDS = security.BCRYPT_ROUNDS if CLINIC_AVAILABLE else 12
CSV_GOOD = b"date,systolic,diastolic\n2026-08-20,128,82\n2026-08-21,131,84\n"


def setUpModule():
    gridcare.PBKDF2_ITERATIONS = 1000
    if CLINIC_AVAILABLE:
        security.BCRYPT_ROUNDS = 4


def tearDownModule():
    gridcare.PBKDF2_ITERATIONS = PRODUCTION_ITERATIONS
    if CLINIC_AVAILABLE:
        security.BCRYPT_ROUNDS = PRODUCTION_ROUNDS


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class TestGridDataFlowsIntoGridCare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RAW / "substations.csv").exists():
            raise unittest.SkipTest("Run generate_datasets.py first")

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = Path(handle.name)
        self.conn = gridcare.init_db(self.db_path)
        gridcare.import_reference_data(self.conn)
        gridcare.seed_users(self.conn)
        self.admin = gridcare.authenticate(self.conn, "admin1", "Admin#2026")
        self.engineer = gridcare.authenticate(self.conn, "engineer1", "Engineer#2026")
        self.technician = gridcare.authenticate(self.conn, "tech1", "Technician#2026")
        self.service = gridcare.authenticate(self.conn, "service1", "Service#2026")

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)

    def source_register(self):
        preferred = CLEAN / "substations_clean.csv"
        return read_csv(preferred if preferred.exists() else RAW / "substations.csv")

    def test_every_register_substation_reaches_the_application(self):
        register = self.source_register()
        stored = self.conn.execute(
            "SELECT substation_id, name, region FROM substations").fetchall()
        self.assertEqual(len(stored), len(register))
        by_id = {int(row["Substation ID"]): row for row in register}
        for row in stored:
            with self.subTest(substation=row["substation_id"]):
                self.assertEqual(row["name"], by_id[row["substation_id"]]["Name"])
                self.assertEqual(row["region"], by_id[row["substation_id"]]["Region"])

    def test_outage_cannot_be_logged_against_an_asset_outside_the_register(self):
        highest = max(int(row["Substation ID"]) for row in self.source_register())
        with self.assertRaises(ValueError):
            gridcare.create_outage(self.conn, self.engineer, highest + 1,
                                   "Phantom asset", "High")

    def test_outage_on_a_critical_substation_flows_through_to_reporting(self):
        ranking_path = NETWORK_TABLES / "criticality_ranking.csv"
        if ranking_path.exists():
            ranking = read_csv(ranking_path)
            target = int(ranking[0]["Substation ID"])
            expected_region = ranking[0]["Region"]
        else:
            target = 1
            expected_region = self.conn.execute(
                "SELECT region FROM substations WHERE substation_id = 1").fetchone()[0]

        outage = gridcare.create_outage(self.conn, self.engineer, target,
                                        "Busbar fault on a critical asset", "Critical")
        work_order = gridcare.assign_work_order(
            self.conn, self.admin, outage, self.technician["user_id"],
            (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
        gridcare.complete_work_order(self.conn, self.technician, work_order,
                                     "Replaced the failed section.")
        gridcare.update_outage_status(self.conn, self.admin, outage, "Resolved",
                                      notes="Supply restored.")

        rows = {row["region"]: row for row in gridcare.outages_by_region(self.conn)}
        self.assertIn(expected_region, rows)
        self.assertEqual(rows[expected_region]["total"], 1)
        self.assertEqual(rows[expected_region]["resolved"], 1)

        summary = gridcare.operational_summary(self.conn)
        self.assertEqual(summary["Outages Resolved"], 1)
        self.assertEqual(summary["Work orders Completed"], 1)

    def test_complaint_links_an_outage_to_a_real_substation(self):
        outage = gridcare.create_outage(self.conn, self.engineer, 2, "Feeder trip", "High")
        complaint = gridcare.log_complaint(self.conn, self.service, "Ama Serwaa",
                                           "0244000000", "No supply since 06:00.", 2,
                                           outage)
        row = self.conn.execute("""
            SELECT c.complaint_id, s.name AS substation, o.status
            FROM complaints c
            JOIN substations s ON s.substation_id = c.substation_id
            JOIN outages o ON o.outage_id = c.outage_id
            WHERE c.complaint_id = ?""", (complaint,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Open")

    def test_reference_import_preserves_line_endpoints(self):
        orphans = self.conn.execute("""
            SELECT COUNT(*) FROM lines l
            WHERE l.source_substation_id NOT IN (SELECT substation_id FROM substations)
               OR l.destination_substation_id NOT IN (SELECT substation_id FROM substations)
        """).fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_status_history_records_the_whole_journey(self):
        outage = gridcare.create_outage(self.conn, self.engineer, 3, "Cable fault", "High")
        work_order = gridcare.assign_work_order(
            self.conn, self.admin, outage, self.technician["user_id"], "2026-09-10")
        gridcare.complete_work_order(self.conn, self.technician, work_order, "Repaired.")
        gridcare.update_outage_status(self.conn, self.admin, outage, "Resolved")
        history = self.conn.execute(
            "SELECT entity, new_status FROM status_history ORDER BY history_id").fetchall()
        journey = [(row["entity"], row["new_status"]) for row in history]
        self.assertEqual(journey, [
            ("outage", "Open"),
            ("work_order", "Scheduled"),
            ("outage", "In Progress"),
            ("work_order", "Completed"),
            ("outage", "Resolved"),
        ])


@unittest.skipUnless(CLINIC_AVAILABLE,
                     f"ClinicCare-Lite dependencies unavailable: {CLINIC_ERROR}")
class TestClinicCareEndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="integration_clinic_"))
        self.service = web.configure(self.root)
        web.app.config["TESTING"] = True
        self.client = web.app.test_client()
        self.clinician, _ = self.service.register_user(
            "12350000", "Dr Adjoa Asare", "adjoa@cliniccare.test", "Clinic#2026",
            "Clinic#2026")
        self.patient, _ = self.service.register_user(
            "12342024", "Kojo Amankwah", "kojo@cliniccare.test", "Patient#2026",
            "Patient#2026")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_task_to_review_journey_touches_every_module(self):
        due = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        task, errors = self.service.create_task(
            self.clinician, "Weekly blood-pressure log", "Upload seven days of readings.",
            due, [self.patient.user_id], ["date", "systolic", "diastolic"])
        self.assertEqual(errors, [])

        assigned = [note for note in self.service.inbox(self.patient.user_id)
                    if note.category == "task"]
        self.assertEqual(len(assigned), 1)

        submission, errors = self.service.submit_task(
            self.patient, task.task_id, "bp.csv", CSV_GOOD)
        self.assertEqual(errors, [])
        self.assertEqual(submission.completeness["status"], "Complete")
        self.assertTrue(submission.on_time)

        clinician_alerts = [note for note in self.service.inbox(self.clinician.user_id)
                            if note.category == "submission"]
        self.assertEqual(len(clinician_alerts), 1)

        pending = self.service.submissions_for_clinic(self.clinician.clinic_id,
                                                      status="Pending")
        self.assertEqual(len(pending), 1)

        reviewed, errors = self.service.review_submission(
            self.clinician, submission.submission_id, "Needs Follow-up",
            "Please repeat next week.")
        self.assertEqual(errors, [])

        outcome_notes = [note for note in self.service.inbox(self.patient.user_id)
                         if note.category == "review"]
        self.assertEqual(len(outcome_notes), 1)
        self.assertIn("Needs Follow-up", outcome_notes[0].body)

        view = self.service.patient_task_view(self.patient.user_id)
        self.assertEqual(view[0]["status"], "Needs Follow-up")

        metrics = self.service.clinic_metrics(self.clinician.clinic_id)
        self.assertEqual(metrics["Submissions received"], 1)
        self.assertEqual(metrics["Reviews completed"], 1)
        self.assertEqual(metrics["Submissions awaiting review"], 0)
        self.assertEqual(metrics["Task completion rate %"], 100.0)

        engagement = self.service.engagement_summary(self.patient.user_id)
        self.assertGreater(engagement["engagement_points"], 0)
        self.assertEqual(engagement["on_time_streak"], 1)

        history = self.service.patient_analytics(self.patient.user_id)
        self.assertEqual(history["submissions"], 1)
        self.assertEqual(history["on_time_submissions"], 1)

    def test_appointment_journey_updates_analytics_and_engagement(self):
        when = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        appointment, errors = self.service.schedule_appointment(
            self.clinician, self.patient.user_id, when, "Review")
        self.assertEqual(errors, [])
        before = self.service.engagement_summary(self.patient.user_id)["engagement_points"]

        self.service.set_appointment_status(self.clinician, appointment.appointment_id,
                                            "Attended")
        after = self.service.engagement_summary(self.patient.user_id)["engagement_points"]
        self.assertGreater(after, before)
        self.assertEqual(self.service.clinic_metrics(self.clinician.clinic_id)
                         ["Appointment no-show rate %"], 0.0)

    def test_web_journey_matches_the_service_layer(self):
        due = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        self.client.post("/login", data={"user_id": "12350000",
                                         "password": "Clinic#2026"},
                         follow_redirects=True)
        response = self.client.post("/clinician/tasks", data={
            "title": "Medication checklist", "description": "Complete and upload.",
            "due_date": due, "expected_fields": "date, medication",
            "patients": [self.patient.user_id]}, follow_redirects=True)
        self.assertIn(b"assigned to", response.data)
        self.client.get("/logout")

        self.client.post("/login", data={"user_id": "12342024",
                                         "password": "Patient#2026"},
                         follow_redirects=True)
        page = self.client.get("/patient/tasks")
        self.assertIn(b"Medication checklist", page.data)
        self.client.get("/logout")

        tasks = self.service.tasks_for_clinic("CLINIC01")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].expected_fields, ["date", "medication"])

    def test_notifications_never_cross_between_patients(self):
        other, _ = self.service.register_user("12342025", "Esi Mensah",
                                              "esi@cliniccare.test", "Patient#2026",
                                              "Patient#2026")
        due = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        task, _ = self.service.create_task(self.clinician, "Private task", "Upload.",
                                           due, [self.patient.user_id])
        self.service.submit_task(self.patient, task.task_id, "bp.csv", CSV_GOOD)
        for note in self.service.inbox(other.user_id):
            with self.subTest(subject=note.subject):
                self.assertNotIn("Private task", note.subject)
                self.assertNotIn(self.patient.full_name, note.body)


class TestAnalysisArtefactsAgree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [CLEAN / "substations_clean.csv", CLEAN / "lines_clean.csv"]
        if any(not path.exists() for path in required):
            raise unittest.SkipTest("Run run_week1.py first")
        cls.substations = read_csv(CLEAN / "substations_clean.csv")
        cls.lines = read_csv(CLEAN / "lines_clean.csv")

    def test_network_tables_cover_the_same_estate(self):
        path = NETWORK_TABLES / "node_metrics.csv"
        if not path.exists():
            self.skipTest("Run task2_1_network_analysis.py first")
        metrics = read_csv(path)
        self.assertEqual(len(metrics), len(self.substations))
        identifiers = {row["Substation ID"] for row in self.substations}
        self.assertEqual({row["Substation ID"] for row in metrics}, identifiers)

    def test_bridges_are_real_lines(self):
        path = NETWORK_TABLES / "bridge_lines.csv"
        if not path.exists():
            self.skipTest("Run task2_1_network_analysis.py first")
        bridges = read_csv(path)
        line_ids = {row["Line ID"] for row in self.lines}
        for row in bridges:
            with self.subTest(line=row["Line ID"]):
                self.assertIn(row["Line ID"], line_ids)

    def test_recommendations_reference_real_places(self):
        path = BI_TABLES / "strategic_recommendations.csv"
        if not path.exists():
            self.skipTest("Run task2_3_business_intelligence.py first")
        recommendations = read_csv(path)
        regions = {row["Region"] for row in self.substations}
        names = {row["Short Name"] for row in self.substations}
        aliases = set()
        footprint = BI_TABLES / "utility_footprint.csv"
        if footprint.exists():
            aliases = {row["Alias"] for row in read_csv(footprint)}
        for row in recommendations:
            area = row["Area"]
            with self.subTest(area=area):
                recognised = (area == "National" or area in regions or area in aliases
                              or any(name in area for name in names))
                self.assertTrue(recognised, f"Unrecognised area: {area}")

    def test_reliability_regions_match_the_register(self):
        path = BI_TABLES / "regional_reliability.csv"
        if not path.exists():
            self.skipTest("Run task2_3_business_intelligence.py first")
        reliability = read_csv(path)
        regions = {row["Region"] for row in self.substations}
        self.assertEqual({row["Region"] for row in reliability}, regions)

    def test_documentation_facts_match_the_data(self):
        path = BASE / "reports" / "headline_facts.json"
        if not path.exists():
            self.skipTest("Run task3_3_documentation.py first")
        import json
        facts = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(facts["substations"], len(self.substations))
        self.assertEqual(facts["lines"], len(self.lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
