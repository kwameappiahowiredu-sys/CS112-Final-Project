import csv
import hashlib
import hmac
import os
import sqlite3
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "gridcare.db"
REPORT_EXPORT_DIR = BASE / "reports" / "gridcare_reports"
SUBSTATION_SOURCES = [
    BASE / "data" / "clean" / "substations_clean.csv",
    BASE / "data" / "raw" / "substations.csv",
]
LINE_SOURCES = [
    BASE / "data" / "clean" / "lines_clean.csv",
    BASE / "data" / "raw" / "lines.csv",
]
CRITICALITY_SOURCES = [
    BASE / "reports" / "network_tables" / "criticality_ranking.csv",
]

CRITICALITY_TIERS = ["Critical", "High", "Moderate", "Low", "Unranked"]
PRIORITY_TIERS = ["Critical", "High"]
CRITICALITY_NOTICE = (
    "Criticality is derived from a graph model of a synthetic asset register. It "
    "describes network structure only and is not a power-flow or protection study."
)

ROLES = ["admin", "engineer", "technician", "customer_service"]

PERMISSIONS = {
    "admin": {"view_outages", "create_outage", "resolve_outage", "assign_work_order",
              "view_work_orders", "complete_work_order", "log_complaint", "view_complaints",
              "view_reports"},
    "engineer": {"view_outages", "create_outage", "resolve_outage", "view_work_orders",
                 "view_reports"},
    "technician": {"view_outages", "view_work_orders", "complete_work_order"},
    "customer_service": {"view_outages", "log_complaint", "view_complaints"},
}

SEVERITIES = ["Low", "Medium", "High", "Critical"]
OUTAGE_STATUSES = ["Open", "In Progress", "Resolved"]
WORK_ORDER_STATUSES = ["Pending", "Scheduled", "Completed"]
OUTAGE_TRANSITIONS = {
    "Open": {"In Progress", "Resolved"},
    "In Progress": {"Resolved"},
    "Resolved": set(),
}
WORK_ORDER_TRANSITIONS = {
    "Pending": {"Scheduled"},
    "Scheduled": {"Completed"},
    "Completed": set(),
}

DEMO_USERS = [
    ("admin1", "Admin#2026", "admin", "Ama Boateng"),
    ("engineer1", "Engineer#2026", "engineer", "Kwame Mensah"),
    ("tech1", "Technician#2026", "technician", "Yaw Owusu"),
    ("tech2", "Technician#2026", "technician", "Efua Darko"),
    ("service1", "Service#2026", "customer_service", "Akosua Nyarko"),
]

PBKDF2_ITERATIONS = 200000


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def init_db(db_path=DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'engineer', 'technician',
                                               'customer_service')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS substations (
            substation_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT,
            region TEXT NOT NULL,
            country TEXT,
            voltage_kv INTEGER,
            capacity_mva REAL,
            status TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lines (
            line_id INTEGER PRIMARY KEY,
            utility_id INTEGER,
            source_substation_id INTEGER NOT NULL,
            destination_substation_id INTEGER NOT NULL,
            voltage_kv INTEGER,
            length_km REAL,
            status TEXT,
            FOREIGN KEY (source_substation_id) REFERENCES substations(substation_id),
            FOREIGN KEY (destination_substation_id) REFERENCES substations(substation_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS substation_criticality (
            substation_id INTEGER PRIMARY KEY,
            rank INTEGER,
            tier TEXT NOT NULL CHECK (tier IN ('Critical', 'High', 'Moderate', 'Low')),
            score REAL,
            betweenness REAL,
            separated_if_lost INTEGER,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (substation_id) REFERENCES substations(substation_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS outages (
            outage_id INTEGER PRIMARY KEY AUTOINCREMENT,
            substation_id INTEGER NOT NULL,
            reported_by INTEGER NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('Low', 'Medium', 'High', 'Critical')),
            status TEXT NOT NULL DEFAULT 'Open'
                CHECK (status IN ('Open', 'In Progress', 'Resolved')),
            reported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            resolution_notes TEXT,
            FOREIGN KEY (substation_id) REFERENCES substations(substation_id),
            FOREIGN KEY (reported_by) REFERENCES users(user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS work_orders (
            work_order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            outage_id INTEGER NOT NULL UNIQUE,
            assigned_technician INTEGER,
            assigned_by INTEGER,
            scheduled_date TEXT,
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK (status IN ('Pending', 'Scheduled', 'Completed')),
            work_notes TEXT,
            completed_at TEXT,
            FOREIGN KEY (outage_id) REFERENCES outages(outage_id),
            FOREIGN KEY (assigned_technician) REFERENCES users(user_id),
            FOREIGN KEY (assigned_by) REFERENCES users(user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_contact TEXT,
            substation_id INTEGER,
            outage_id INTEGER,
            details TEXT NOT NULL,
            logged_by INTEGER NOT NULL,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (substation_id) REFERENCES substations(substation_id),
            FOREIGN KEY (outage_id) REFERENCES outages(outage_id),
            FOREIGN KEY (logged_by) REFERENCES users(user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS status_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by INTEGER NOT NULL,
            changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (changed_by) REFERENCES users(user_id)
        )
    """)
    conn.commit()
    return conn


def first_existing(paths):
    for path in paths:
        if path.exists():
            return path
    return None


def import_reference_data(conn):
    cur = conn.cursor()
    imported = {"substations": 0, "lines": 0, "criticality": 0}

    if cur.execute("SELECT COUNT(*) FROM substations").fetchone()[0] == 0:
        source = first_existing(SUBSTATION_SOURCES)
        if source:
            with open(source, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    cur.execute(
                        "INSERT OR IGNORE INTO substations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (int(row["Substation ID"]), row["Name"], row.get("Short Name"),
                         row["Region"], row.get("Country"),
                         int(float(row["Voltage (kV)"])), float(row["Capacity (MVA)"]),
                         row.get("Status")))
                    imported["substations"] += 1

    if cur.execute("SELECT COUNT(*) FROM lines").fetchone()[0] == 0:
        source = first_existing(LINE_SOURCES)
        if source:
            with open(source, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    cur.execute(
                        "INSERT OR IGNORE INTO lines VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (int(row["Line ID"]), int(row["Utility ID"]),
                         int(row["Source Substation ID"]),
                         int(row["Destination Substation ID"]),
                         int(float(row["Voltage (kV)"])), float(row["Length (km)"]),
                         row.get("Status")))
                    imported["lines"] += 1

    if cur.execute("SELECT COUNT(*) FROM substation_criticality").fetchone()[0] == 0:
        source = first_existing(CRITICALITY_SOURCES)
        if source:
            known = {row[0] for row in cur.execute(
                "SELECT substation_id FROM substations")}
            with open(source, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    substation_id = int(row["Substation ID"])
                    if substation_id not in known:
                        continue
                    cur.execute(
                        "INSERT OR IGNORE INTO substation_criticality "
                        "(substation_id, rank, tier, score, betweenness, "
                        "separated_if_lost) VALUES (?, ?, ?, ?, ?, ?)",
                        (substation_id, int(row["Rank"]), row["Criticality Tier"],
                         float(row["Criticality Score"]),
                         float(row["Betweenness Centrality"]),
                         int(float(row["Nodes Separated From Core"]))))
                    imported["criticality"] += 1

    conn.commit()
    return imported


def refresh_criticality(conn):
    source = first_existing(CRITICALITY_SOURCES)
    if source is None:
        return 0
    cur = conn.cursor()
    known = {row[0] for row in cur.execute("SELECT substation_id FROM substations")}
    cur.execute("DELETE FROM substation_criticality")
    imported = 0
    with open(source, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            substation_id = int(row["Substation ID"])
            if substation_id not in known:
                continue
            cur.execute(
                "INSERT INTO substation_criticality (substation_id, rank, tier, score, "
                "betweenness, separated_if_lost, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (substation_id, int(row["Rank"]), row["Criticality Tier"],
                 float(row["Criticality Score"]),
                 float(row["Betweenness Centrality"]),
                 int(float(row["Nodes Separated From Core"])),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            imported += 1
    conn.commit()
    return imported


def criticality_status(conn):
    row = conn.execute(
        "SELECT COUNT(*) AS total, MAX(imported_at) AS imported_at "
        "FROM substation_criticality").fetchone()
    return {"substations": row["total"] or 0,
            "imported_at": row["imported_at"] or "never"}


def seed_users(conn):
    cur = conn.cursor()
    created = []
    for username, password, role, full_name in DEMO_USERS:
        exists = cur.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if not exists:
            cur.execute(
                "INSERT INTO users (username, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                (username, full_name, hash_password(password), role))
            created.append((username, password, role))
    conn.commit()
    return created


def authenticate(conn, username, password):
    row = conn.execute(
        "SELECT user_id, username, full_name, password_hash, role FROM users WHERE username = ?",
        (username,)).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"user_id": row["user_id"], "username": row["username"],
            "full_name": row["full_name"], "role": row["role"]}


def can(user, capability):
    return capability in PERMISSIONS.get(user["role"], set())


def require(user, capability):
    if not can(user, capability):
        raise PermissionError(f"Role '{user['role']}' is not permitted to {capability}.")


def record_status_change(conn, entity, entity_id, old_status, new_status, user_id):
    conn.execute(
        "INSERT INTO status_history (entity, entity_id, old_status, new_status, changed_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (entity, entity_id, old_status, new_status, user_id))


def create_outage(conn, user, substation_id, description, severity):
    require(user, "create_outage")
    if not description.strip():
        raise ValueError("A description is required.")
    if severity not in SEVERITIES:
        raise ValueError(f"Severity must be one of {SEVERITIES}.")
    exists = conn.execute("SELECT 1 FROM substations WHERE substation_id = ?",
                          (substation_id,)).fetchone()
    if not exists:
        raise ValueError(f"Substation {substation_id} does not exist.")
    duplicate = conn.execute(
        "SELECT outage_id FROM outages WHERE substation_id = ? AND status != 'Resolved' "
        "AND description = ?", (substation_id, description.strip())).fetchone()
    if duplicate:
        raise ValueError(f"An identical unresolved outage already exists "
                         f"(ID {duplicate['outage_id']}).")
    cur = conn.execute(
        "INSERT INTO outages (substation_id, reported_by, description, severity, reported_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (substation_id, user["user_id"], description.strip(), severity,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    record_status_change(conn, "outage", cur.lastrowid, None, "Open", user["user_id"])
    conn.commit()
    return cur.lastrowid


def assign_work_order(conn, user, outage_id, technician_id, scheduled_date):
    require(user, "assign_work_order")
    outage = conn.execute("SELECT status FROM outages WHERE outage_id = ?",
                          (outage_id,)).fetchone()
    if outage is None:
        raise ValueError(f"Outage {outage_id} does not exist.")
    if outage["status"] == "Resolved":
        raise ValueError("A resolved outage cannot receive a new work order.")
    technician = conn.execute(
        "SELECT role FROM users WHERE user_id = ?", (technician_id,)).fetchone()
    if technician is None or technician["role"] != "technician":
        raise ValueError("The assignee must be a registered technician.")
    try:
        datetime.strptime(scheduled_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Scheduled date must use the format YYYY-MM-DD.")
    existing = conn.execute("SELECT work_order_id FROM work_orders WHERE outage_id = ?",
                            (outage_id,)).fetchone()
    if existing:
        raise ValueError(f"Outage {outage_id} already has work order "
                         f"{existing['work_order_id']}.")
    cur = conn.execute(
        "INSERT INTO work_orders (outage_id, assigned_technician, assigned_by, "
        "scheduled_date, status) VALUES (?, ?, ?, ?, 'Scheduled')",
        (outage_id, technician_id, user["user_id"], scheduled_date))
    record_status_change(conn, "work_order", cur.lastrowid, "Pending", "Scheduled",
                         user["user_id"])
    update_outage_status(conn, user, outage_id, "In Progress", commit=False)
    conn.commit()
    return cur.lastrowid


def update_outage_status(conn, user, outage_id, new_status, notes=None, commit=True):
    row = conn.execute("SELECT status FROM outages WHERE outage_id = ?",
                       (outage_id,)).fetchone()
    if row is None:
        raise ValueError(f"Outage {outage_id} does not exist.")
    old_status = row["status"]
    if new_status == old_status:
        return
    if new_status not in OUTAGE_TRANSITIONS[old_status]:
        raise ValueError(f"An outage cannot move from {old_status} to {new_status}.")
    if new_status == "Resolved":
        require(user, "resolve_outage")
        conn.execute(
            "UPDATE outages SET status = ?, resolved_at = ?, resolution_notes = ? "
            "WHERE outage_id = ?",
            (new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), notes, outage_id))
    else:
        conn.execute("UPDATE outages SET status = ? WHERE outage_id = ?",
                     (new_status, outage_id))
    record_status_change(conn, "outage", outage_id, old_status, new_status, user["user_id"])
    if commit:
        conn.commit()


def complete_work_order(conn, user, work_order_id, work_notes):
    require(user, "complete_work_order")
    row = conn.execute(
        "SELECT status, outage_id, assigned_technician FROM work_orders WHERE work_order_id = ?",
        (work_order_id,)).fetchone()
    if row is None:
        raise ValueError(f"Work order {work_order_id} does not exist.")
    if user["role"] == "technician" and row["assigned_technician"] != user["user_id"]:
        raise PermissionError("Technicians may only complete their own work orders.")
    if "Completed" not in WORK_ORDER_TRANSITIONS[row["status"]]:
        raise ValueError(f"A work order cannot move from {row['status']} to Completed.")
    if not work_notes.strip():
        raise ValueError("Work notes are required before completing a work order.")
    conn.execute(
        "UPDATE work_orders SET status = 'Completed', work_notes = ?, completed_at = ? "
        "WHERE work_order_id = ?",
        (work_notes.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), work_order_id))
    record_status_change(conn, "work_order", work_order_id, row["status"], "Completed",
                         user["user_id"])
    conn.commit()
    return row["outage_id"]


def log_complaint(conn, user, customer_name, contact, details, substation_id, outage_id):
    require(user, "log_complaint")
    if not customer_name.strip() or not details.strip():
        raise ValueError("Customer name and complaint details are required.")
    if outage_id is not None:
        exists = conn.execute("SELECT 1 FROM outages WHERE outage_id = ?",
                              (outage_id,)).fetchone()
        if not exists:
            raise ValueError(f"Outage {outage_id} does not exist.")
    if substation_id is not None:
        exists = conn.execute("SELECT 1 FROM substations WHERE substation_id = ?",
                              (substation_id,)).fetchone()
        if not exists:
            raise ValueError(f"Substation {substation_id} does not exist.")
    cur = conn.execute(
        "INSERT INTO complaints (customer_name, customer_contact, substation_id, outage_id, "
        "details, logged_by, logged_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (customer_name.strip(), contact.strip(), substation_id, outage_id, details.strip(),
         user["user_id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return cur.lastrowid


def fetch_outages(conn, status=None, region=None, tier=None):
    query = """
        SELECT o.outage_id, s.name AS substation, s.region, o.severity, o.status,
               COALESCE(c.tier, 'Unranked') AS criticality,
               o.reported_at, u.username AS reported_by,
               COALESCE(w.work_order_id, '') AS work_order,
               COALESCE(t.username, '') AS technician
        FROM outages o
        JOIN substations s ON s.substation_id = o.substation_id
        JOIN users u ON u.user_id = o.reported_by
        LEFT JOIN substation_criticality c ON c.substation_id = o.substation_id
        LEFT JOIN work_orders w ON w.outage_id = o.outage_id
        LEFT JOIN users t ON t.user_id = w.assigned_technician
    """
    clauses = []
    params = []
    if status and status != "All":
        clauses.append("o.status = ?")
        params.append(status)
    if region and region != "All":
        clauses.append("s.region = ?")
        params.append(region)
    if tier and tier != "All":
        clauses.append("COALESCE(c.tier, 'Unranked') = ?")
        params.append(tier)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY o.outage_id DESC"
    return conn.execute(query, params).fetchall()


def priority_queue(conn):
    return conn.execute("""
        SELECT o.outage_id, s.name AS substation, s.region, o.severity,
               COALESCE(c.tier, 'Unranked') AS criticality,
               COALESCE(c.rank, 9999) AS criticality_rank,
               COALESCE(c.separated_if_lost, 0) AS separated_if_lost,
               o.status, o.reported_at
        FROM outages o
        JOIN substations s ON s.substation_id = o.substation_id
        LEFT JOIN substation_criticality c ON c.substation_id = o.substation_id
        WHERE o.status != 'Resolved'
        ORDER BY
            CASE COALESCE(c.tier, 'Unranked')
                WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                WHEN 'Moderate' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END,
            CASE o.severity
                WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3 ELSE 4 END,
            o.reported_at
    """).fetchall()


def fetch_work_orders(conn, technician_id=None):
    query = """
        SELECT w.work_order_id, w.outage_id, s.name AS substation, s.region,
               o.severity, w.scheduled_date, w.status,
               COALESCE(t.username, '') AS technician
        FROM work_orders w
        JOIN outages o ON o.outage_id = w.outage_id
        JOIN substations s ON s.substation_id = o.substation_id
        LEFT JOIN users t ON t.user_id = w.assigned_technician
    """
    params = []
    if technician_id is not None:
        query += " WHERE w.assigned_technician = ?"
        params.append(technician_id)
    query += " ORDER BY w.work_order_id DESC"
    return conn.execute(query, params).fetchall()


def fetch_complaints(conn):
    return conn.execute("""
        SELECT c.complaint_id, c.customer_name, c.customer_contact,
               COALESCE(s.name, '') AS substation, COALESCE(c.outage_id, '') AS outage_id,
               c.details, c.logged_at, u.username AS logged_by
        FROM complaints c
        LEFT JOIN substations s ON s.substation_id = c.substation_id
        JOIN users u ON u.user_id = c.logged_by
        ORDER BY c.complaint_id DESC
    """).fetchall()


def operational_summary(conn):
    summary = {}
    for status in OUTAGE_STATUSES:
        summary[f"Outages {status}"] = conn.execute(
            "SELECT COUNT(*) FROM outages WHERE status = ?", (status,)).fetchone()[0]
    for status in WORK_ORDER_STATUSES:
        summary[f"Work orders {status}"] = conn.execute(
            "SELECT COUNT(*) FROM work_orders WHERE status = ?", (status,)).fetchone()[0]
    summary["Complaints logged"] = conn.execute(
        "SELECT COUNT(*) FROM complaints").fetchone()[0]
    summary["Substations in register"] = conn.execute(
        "SELECT COUNT(*) FROM substations").fetchone()[0]
    summary["Substations with criticality data"] = conn.execute(
        "SELECT COUNT(*) FROM substation_criticality").fetchone()[0]
    summary["Open outages on critical assets"] = conn.execute(
        "SELECT COUNT(*) FROM outages o "
        "JOIN substation_criticality c ON c.substation_id = o.substation_id "
        "WHERE o.status != 'Resolved' AND c.tier IN ('Critical', 'High')").fetchone()[0]
    average = conn.execute("""
        SELECT AVG(julianday(resolved_at) - julianday(reported_at)) * 24
        FROM outages WHERE resolved_at IS NOT NULL
    """).fetchone()[0]
    summary["Average resolution time (hours)"] = round(average, 2) if average else 0
    return summary


def outages_by_severity(conn):
    return conn.execute("""
        SELECT o.severity,
               COUNT(*) AS total,
               SUM(CASE WHEN o.status = 'Resolved' THEN 1 ELSE 0 END) AS resolved,
               ROUND(AVG(CASE WHEN o.resolved_at IS NOT NULL
                    THEN (julianday(o.resolved_at) - julianday(o.reported_at)) * 24 END),
                    2) AS mean_hours
        FROM outages o
        GROUP BY o.severity
        ORDER BY CASE o.severity
            WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
            WHEN 'Medium' THEN 3 ELSE 4 END
    """).fetchall()


def outages_by_criticality(conn):
    return conn.execute("""
        SELECT COALESCE(c.tier, 'Unranked') AS criticality,
               COUNT(*) AS total,
               SUM(CASE WHEN o.status = 'Resolved' THEN 1 ELSE 0 END) AS resolved,
               SUM(CASE WHEN o.status != 'Resolved' THEN 1 ELSE 0 END) AS open_now,
               ROUND(AVG(CASE WHEN o.resolved_at IS NOT NULL
                    THEN (julianday(o.resolved_at) - julianday(o.reported_at)) * 24 END),
                    2) AS mean_hours
        FROM outages o
        LEFT JOIN substation_criticality c ON c.substation_id = o.substation_id
        GROUP BY COALESCE(c.tier, 'Unranked')
        ORDER BY CASE COALESCE(c.tier, 'Unranked')
            WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
            WHEN 'Moderate' THEN 3 WHEN 'Low' THEN 4 ELSE 5 END
    """).fetchall()


def technician_workload(conn):
    return conn.execute("""
        SELECT u.username AS technician, u.full_name,
               COUNT(w.work_order_id) AS assigned,
               SUM(CASE WHEN w.status = 'Completed' THEN 1 ELSE 0 END) AS completed,
               SUM(CASE WHEN w.status != 'Completed' THEN 1 ELSE 0 END) AS outstanding
        FROM users u
        LEFT JOIN work_orders w ON w.assigned_technician = u.user_id
        WHERE u.role = 'technician'
        GROUP BY u.user_id
        ORDER BY assigned DESC, u.username
    """).fetchall()


def resolution_performance(conn):
    row = conn.execute("""
        SELECT COUNT(*) AS resolved,
               ROUND(MIN((julianday(resolved_at) - julianday(reported_at)) * 24), 2)
                   AS fastest,
               ROUND(AVG((julianday(resolved_at) - julianday(reported_at)) * 24), 2)
                   AS mean,
               ROUND(MAX((julianday(resolved_at) - julianday(reported_at)) * 24), 2)
                   AS slowest
        FROM outages WHERE resolved_at IS NOT NULL
    """).fetchone()
    return {
        "Outages resolved": row["resolved"] or 0,
        "Fastest resolution (hours)": row["fastest"] or 0,
        "Mean resolution (hours)": row["mean"] or 0,
        "Slowest resolution (hours)": row["slowest"] or 0,
    }


def complaint_linkage(conn):
    row = conn.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN outage_id IS NOT NULL THEN 1 ELSE 0 END) AS linked
        FROM complaints
    """).fetchone()
    total = row["total"] or 0
    linked = row["linked"] or 0
    return {
        "Complaints logged": total,
        "Linked to an outage": linked,
        "Unlinked": total - linked,
        "Linkage rate %": round(100 * linked / total, 1) if total else 0.0,
    }


def export_reports(conn, directory=None):
    directory = Path(directory or REPORT_EXPORT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    exports = {
        "outages": fetch_outages(conn),
        "work_orders": fetch_work_orders(conn),
        "complaints": fetch_complaints(conn),
        "priority_queue": priority_queue(conn),
        "outages_by_region": outages_by_region(conn),
        "outages_by_severity": outages_by_severity(conn),
        "outages_by_criticality": outages_by_criticality(conn),
        "technician_workload": technician_workload(conn),
    }
    for name, rows in exports.items():
        path = directory / f"{name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if rows:
                writer.writerow(rows[0].keys())
                writer.writerows([tuple(row) for row in rows])
            else:
                writer.writerow(["no rows"])
        written.append(path)

    summaries = {
        "operational_summary": operational_summary(conn),
        "resolution_performance": resolution_performance(conn),
        "complaint_linkage": complaint_linkage(conn),
    }
    for name, mapping in summaries.items():
        path = directory / f"{name}.csv"
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Measure", "Value"])
            writer.writerows(mapping.items())
        written.append(path)
    return written


def outages_by_region(conn):
    return conn.execute("""
        SELECT s.region, COUNT(*) AS total,
               SUM(CASE WHEN o.status = 'Resolved' THEN 1 ELSE 0 END) AS resolved
        FROM outages o JOIN substations s ON s.substation_id = o.substation_id
        GROUP BY s.region ORDER BY total DESC
    """).fetchall()


class DateField(ttk.Frame):
    def __init__(self, master, initial=None):
        super().__init__(master)
        self.entry = ttk.Entry(self, width=14)
        self.entry.insert(0, initial or datetime.now().strftime("%Y-%m-%d"))
        self.entry.grid(row=0, column=0, padx=(0, 6))
        self.entry.bind("<KeyRelease>", lambda event: self.validate())

        for label, days in [("Today", 0), ("+1", 1), ("+7", 7)]:
            ttk.Button(self, text=label, width=5,
                       command=lambda offset=days: self.shift(offset)).grid(
                row=0, column=1 + [0, 1, 7].index(days), padx=2)

        self.feedback = ttk.Label(self, text="", font=("Segoe UI", 8))
        self.feedback.grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 0))
        self.validate()

    def shift(self, days):
        target = datetime.now() + timedelta(days=days)
        self.entry.delete(0, tk.END)
        self.entry.insert(0, target.strftime("%Y-%m-%d"))
        self.validate()

    def get(self):
        return self.entry.get().strip()

    def is_valid(self):
        try:
            datetime.strptime(self.get(), "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def validate(self):
        if self.is_valid():
            self.feedback.config(text="Format accepted (YYYY-MM-DD)",
                                 foreground="#1b5e20")
        else:
            self.feedback.config(text="Use the format YYYY-MM-DD",
                                 foreground="#b00020")
        return self.is_valid()


class LoginFrame(ttk.Frame):
    def __init__(self, master, conn, on_success):
        super().__init__(master, padding=24)
        self.conn = conn
        self.on_success = on_success

        ttk.Label(self, text="GridCare-Lite", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 4))
        ttk.Label(self, text="Outage and Maintenance Management System").grid(
            row=1, column=0, columnspan=2, pady=(0, 16))

        ttk.Label(self, text="Username").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        self.username = ttk.Entry(self, width=28)
        self.username.grid(row=2, column=1, padx=6, pady=6)

        ttk.Label(self, text="Password").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        self.password = ttk.Entry(self, width=28, show="*")
        self.password.grid(row=3, column=1, padx=6, pady=6)

        ttk.Button(self, text="Log In", command=self.attempt_login).grid(
            row=4, column=0, columnspan=2, pady=12)
        self.status = ttk.Label(self, text="", foreground="#b00020")
        self.status.grid(row=5, column=0, columnspan=2)

        self.password.bind("<Return>", lambda event: self.attempt_login())
        self.username.focus_set()

    def attempt_login(self):
        username = self.username.get().strip()
        password = self.password.get()
        if not username or not password:
            self.status.config(text="Enter both a username and a password.")
            return
        user = authenticate(self.conn, username, password)
        if user is None:
            self.status.config(text="Invalid username or password.")
            self.password.delete(0, tk.END)
            return
        self.status.config(text="")
        self.on_success(user)


class OutagesTab(ttk.Frame):
    def __init__(self, master, conn, user):
        super().__init__(master, padding=12)
        self.conn = conn
        self.user = user

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Status").pack(side="left", padx=(0, 4))
        self.status_filter = ttk.Combobox(filters, values=["All"] + OUTAGE_STATUSES,
                                          state="readonly", width=14)
        self.status_filter.set("All")
        self.status_filter.pack(side="left", padx=(0, 12))

        regions = [row[0] for row in self.conn.execute(
            "SELECT DISTINCT region FROM substations ORDER BY region")]
        ttk.Label(filters, text="Region").pack(side="left", padx=(0, 4))
        self.region_filter = ttk.Combobox(filters, values=["All"] + regions,
                                          state="readonly", width=22)
        self.region_filter.set("All")
        self.region_filter.pack(side="left", padx=(0, 12))

        ttk.Label(filters, text="Criticality").pack(side="left", padx=(0, 4))
        self.tier_filter = ttk.Combobox(filters, values=["All"] + CRITICALITY_TIERS,
                                        state="readonly", width=12)
        self.tier_filter.set("All")
        self.tier_filter.pack(side="left", padx=(0, 12))

        ttk.Button(filters, text="Apply", command=self.refresh).pack(side="left")
        if can(user, "resolve_outage"):
            ttk.Button(filters, text="Mark Selected Resolved",
                       command=self.resolve_selected).pack(side="right")

        columns = ("outage_id", "substation", "region", "severity", "status",
                   "criticality", "reported_at", "reported_by", "work_order",
                   "technician")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=16)
        widths = {"outage_id": 70, "substation": 190, "region": 120, "severity": 75,
                  "status": 85, "criticality": 85, "reported_at": 140,
                  "reported_by": 95, "work_order": 75, "technician": 95}
        for column in columns:
            self.tree.heading(column, text=column.replace("_", " ").title())
            self.tree.column(column, width=widths[column], minwidth=60,
                             anchor="w", stretch=True)
        self.tree.tag_configure("critical", background="#ffe0e0")
        self.tree.tag_configure("high", background="#fff0d9")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in fetch_outages(self.conn, self.status_filter.get(),
                                 self.region_filter.get(), self.tier_filter.get()):
            tier = row["criticality"]
            tags = ("critical",) if tier == "Critical" else (
                ("high",) if tier == "High" else ())
            self.tree.insert("", "end", values=tuple(row), tags=tags)

    def resolve_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select an outage first.")
            return
        outage_id = self.tree.item(selection[0])["values"][0]
        try:
            update_outage_status(self.conn, self.user, int(outage_id), "Resolved",
                                 notes="Resolved from the outage dashboard.")
        except (ValueError, PermissionError) as error:
            messagebox.showerror("Cannot resolve outage", str(error))
            return
        messagebox.showinfo("Outage resolved", f"Outage {outage_id} is now Resolved.")
        self.refresh()


class NewOutageTab(ttk.Frame):
    def __init__(self, master, conn, user, on_change):
        super().__init__(master, padding=12)
        self.conn = conn
        self.user = user
        self.on_change = on_change

        self.substations = self.conn.execute(
            "SELECT substation_id, name, region FROM substations ORDER BY name").fetchall()
        labels = [f"{row['substation_id']} - {row['name']} ({row['region']})"
                  for row in self.substations]

        ttk.Label(self, text="Substation").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.substation = ttk.Combobox(self, values=labels, state="readonly", width=52)
        self.substation.grid(row=0, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(self, text="Severity").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.severity = ttk.Combobox(self, values=SEVERITIES, state="readonly", width=20)
        self.severity.set("Medium")
        self.severity.grid(row=1, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(self, text="Description").grid(row=2, column=0, sticky="ne", padx=6, pady=6)
        self.description = tk.Text(self, width=52, height=8)
        self.description.grid(row=2, column=1, padx=6, pady=6, sticky="w")

        ttk.Button(self, text="Log Outage", command=self.submit).grid(
            row=3, column=1, sticky="w", padx=6, pady=10)
        self.feedback = ttk.Label(self, text="")
        self.feedback.grid(row=4, column=1, sticky="w", padx=6)

    def submit(self):
        index = self.substation.current()
        if index < 0:
            self.feedback.config(text="Select a substation.", foreground="#b00020")
            return
        substation_id = self.substations[index]["substation_id"]
        description = self.description.get("1.0", tk.END).strip()
        try:
            outage_id = create_outage(self.conn, self.user, substation_id, description,
                                      self.severity.get())
        except (ValueError, PermissionError) as error:
            self.feedback.config(text=str(error), foreground="#b00020")
            return
        self.description.delete("1.0", tk.END)
        self.feedback.config(text=f"Outage {outage_id} logged.", foreground="#1b5e20")
        self.on_change()


class WorkOrdersTab(ttk.Frame):
    def __init__(self, master, conn, user, on_change):
        super().__init__(master, padding=12)
        self.conn = conn
        self.user = user
        self.on_change = on_change

        if can(user, "assign_work_order"):
            self.build_assignment_form()

        columns = ("work_order_id", "outage_id", "substation", "region", "severity",
                   "scheduled_date", "status", "technician")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        widths = {"work_order_id": 90, "outage_id": 80, "substation": 200, "region": 130,
                  "severity": 80, "scheduled_date": 120, "status": 100, "technician": 110}
        for column in columns:
            self.tree.heading(column, text=column.replace("_", " ").title())
            self.tree.column(column, width=widths[column], minwidth=60,
                             anchor="w", stretch=True)
        self.tree.pack(fill="both", expand=True, pady=(12, 8))

        actions = ttk.Frame(self)
        actions.pack(fill="x")
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left")
        if can(user, "complete_work_order"):
            ttk.Label(actions, text="Work notes").pack(side="left", padx=(16, 4))
            self.notes = ttk.Entry(actions, width=42)
            self.notes.pack(side="left")
            ttk.Button(actions, text="Mark Complete",
                       command=self.complete_selected).pack(side="left", padx=8)
        self.feedback = ttk.Label(self, text="")
        self.feedback.pack(anchor="w", pady=(8, 0))
        self.refresh()

    def build_assignment_form(self):
        form = ttk.LabelFrame(self, text="Assign a work order", padding=10)
        form.pack(fill="x")

        ttk.Label(form, text="Outage").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.outage_box = ttk.Combobox(form, state="readonly", width=46)
        self.outage_box.grid(row=0, column=1, padx=6, pady=4, sticky="w")

        ttk.Label(form, text="Technician").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self.technician_box = ttk.Combobox(form, state="readonly", width=30)
        self.technician_box.grid(row=1, column=1, padx=6, pady=4, sticky="w")

        ttk.Label(form, text="Scheduled date").grid(
            row=2, column=0, sticky="ne", padx=6, pady=4)
        self.scheduled = DateField(form)
        self.scheduled.grid(row=2, column=1, padx=6, pady=4, sticky="w")

        ttk.Button(form, text="Assign", command=self.assign).grid(
            row=3, column=1, sticky="w", padx=6, pady=8)
        self.load_assignment_options()

    def load_assignment_options(self):
        self.open_outages = self.conn.execute("""
            SELECT o.outage_id, s.name AS substation, o.severity
            FROM outages o
            JOIN substations s ON s.substation_id = o.substation_id
            LEFT JOIN work_orders w ON w.outage_id = o.outage_id
            WHERE w.work_order_id IS NULL AND o.status != 'Resolved'
            ORDER BY o.outage_id DESC
        """).fetchall()
        self.outage_box["values"] = [
            f"{row['outage_id']} - {row['substation']} ({row['severity']})"
            for row in self.open_outages]
        self.technicians = self.conn.execute(
            "SELECT user_id, username, full_name FROM users WHERE role = 'technician' "
            "ORDER BY username").fetchall()
        self.technician_box["values"] = [
            f"{row['username']} - {row['full_name']}" for row in self.technicians]

    def assign(self):
        outage_index = self.outage_box.current()
        technician_index = self.technician_box.current()
        if outage_index < 0 or technician_index < 0:
            self.feedback.config(text="Select an outage and a technician.",
                                 foreground="#b00020")
            return
        try:
            work_order_id = assign_work_order(
                self.conn, self.user, self.open_outages[outage_index]["outage_id"],
                self.technicians[technician_index]["user_id"], self.scheduled.get())
        except (ValueError, PermissionError) as error:
            self.feedback.config(text=str(error), foreground="#b00020")
            return
        self.feedback.config(text=f"Work order {work_order_id} created.",
                             foreground="#1b5e20")
        self.load_assignment_options()
        self.refresh()
        self.on_change()

    def complete_selected(self):
        selection = self.tree.selection()
        if not selection:
            self.feedback.config(text="Select a work order first.", foreground="#b00020")
            return
        work_order_id = self.tree.item(selection[0])["values"][0]
        try:
            complete_work_order(self.conn, self.user, int(work_order_id), self.notes.get())
        except (ValueError, PermissionError) as error:
            self.feedback.config(text=str(error), foreground="#b00020")
            return
        self.notes.delete(0, tk.END)
        self.feedback.config(text=f"Work order {work_order_id} completed.",
                             foreground="#1b5e20")
        self.refresh()
        self.on_change()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        technician_id = self.user["user_id"] if self.user["role"] == "technician" else None
        for row in fetch_work_orders(self.conn, technician_id):
            self.tree.insert("", "end", values=tuple(row))
        if hasattr(self, "outage_box"):
            self.load_assignment_options()


class ComplaintsTab(ttk.Frame):
    def __init__(self, master, conn, user):
        super().__init__(master, padding=12)
        self.conn = conn
        self.user = user

        if can(user, "log_complaint"):
            form = ttk.LabelFrame(self, text="Log a customer complaint", padding=10)
            form.pack(fill="x")

            ttk.Label(form, text="Customer name").grid(row=0, column=0, sticky="e",
                                                       padx=6, pady=4)
            self.customer = ttk.Entry(form, width=32)
            self.customer.grid(row=0, column=1, padx=6, pady=4, sticky="w")

            ttk.Label(form, text="Contact").grid(row=0, column=2, sticky="e", padx=6, pady=4)
            self.contact = ttk.Entry(form, width=24)
            self.contact.grid(row=0, column=3, padx=6, pady=4, sticky="w")

            self.substations = self.conn.execute(
                "SELECT substation_id, name FROM substations ORDER BY name").fetchall()
            ttk.Label(form, text="Substation").grid(row=1, column=0, sticky="e",
                                                    padx=6, pady=4)
            self.substation_box = ttk.Combobox(
                form, state="readonly", width=40,
                values=[f"{row['substation_id']} - {row['name']}"
                        for row in self.substations])
            self.substation_box.grid(row=1, column=1, columnspan=2, padx=6, pady=4,
                                     sticky="w")

            ttk.Label(form, text="Link to outage ID").grid(row=2, column=0, sticky="e",
                                                           padx=6, pady=4)
            self.outage_entry = ttk.Entry(form, width=12)
            self.outage_entry.grid(row=2, column=1, padx=6, pady=4, sticky="w")

            ttk.Label(form, text="Details").grid(row=3, column=0, sticky="ne", padx=6, pady=4)
            self.details = tk.Text(form, width=64, height=5)
            self.details.grid(row=3, column=1, columnspan=3, padx=6, pady=4, sticky="w")

            ttk.Button(form, text="Log Complaint", command=self.submit).grid(
                row=4, column=1, sticky="w", padx=6, pady=8)
            self.feedback = ttk.Label(form, text="")
            self.feedback.grid(row=5, column=1, columnspan=3, sticky="w", padx=6)

        columns = ("complaint_id", "customer_name", "customer_contact", "substation",
                   "outage_id", "details", "logged_at", "logged_by")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=12)
        widths = {"complaint_id": 90, "customer_name": 140, "customer_contact": 120,
                  "substation": 180, "outage_id": 80, "details": 260, "logged_at": 150,
                  "logged_by": 100}
        for column in columns:
            self.tree.heading(column, text=column.replace("_", " ").title())
            self.tree.column(column, width=widths[column], minwidth=60,
                             anchor="w", stretch=True)
        self.tree.pack(fill="both", expand=True, pady=(12, 0))
        self.refresh()

    def submit(self):
        index = self.substation_box.current()
        substation_id = self.substations[index]["substation_id"] if index >= 0 else None
        outage_text = self.outage_entry.get().strip()
        if outage_text and not outage_text.isdigit():
            self.feedback.config(text="Outage ID must be a number.", foreground="#b00020")
            return
        try:
            complaint_id = log_complaint(
                self.conn, self.user, self.customer.get(), self.contact.get(),
                self.details.get("1.0", tk.END), substation_id,
                int(outage_text) if outage_text else None)
        except (ValueError, PermissionError) as error:
            self.feedback.config(text=str(error), foreground="#b00020")
            return
        self.customer.delete(0, tk.END)
        self.contact.delete(0, tk.END)
        self.outage_entry.delete(0, tk.END)
        self.details.delete("1.0", tk.END)
        self.feedback.config(text=f"Complaint {complaint_id} logged.", foreground="#1b5e20")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in fetch_complaints(self.conn):
            self.tree.insert("", "end", values=tuple(row))


class ReportsTab(ttk.Frame):
    def __init__(self, master, conn, user):
        super().__init__(master, padding=10)
        self.conn = conn

        actions = ttk.Frame(self)
        actions.pack(fill="x")
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(actions, text="Export all reports to CSV",
                   command=self.export).pack(side="left", padx=8)
        ttk.Button(actions, text="Reload criticality from the analysis",
                   command=self.reload_criticality).pack(side="left")
        self.feedback = ttk.Label(actions, text="")
        self.feedback.pack(side="left", padx=8)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, pady=(10, 0))

        self.summary = self.build_table(
            notebook, "Summary", ("metric", "value"),
            {"metric": 320, "value": 140})
        self.performance = self.build_table(
            notebook, "Resolution", ("metric", "value"),
            {"metric": 320, "value": 140})
        self.priority = self.build_table(
            notebook, "Priority queue",
            ("outage_id", "substation", "region", "severity", "criticality",
             "criticality_rank", "separated_if_lost", "status", "reported_at"),
            {"outage_id": 70, "substation": 180, "region": 120, "severity": 75,
             "criticality": 85, "criticality_rank": 60, "separated_if_lost": 70,
             "status": 90, "reported_at": 140})
        self.criticality = self.build_table(
            notebook, "By criticality",
            ("criticality", "total", "resolved", "open_now", "mean_hours"),
            {"criticality": 130, "total": 80, "resolved": 80, "open_now": 80,
             "mean_hours": 110})
        self.severity = self.build_table(
            notebook, "By severity",
            ("severity", "total", "resolved", "mean_hours"),
            {"severity": 130, "total": 80, "resolved": 80, "mean_hours": 110})
        self.regions = self.build_table(
            notebook, "By region", ("region", "total", "resolved"),
            {"region": 240, "total": 100, "resolved": 100})
        self.workload = self.build_table(
            notebook, "Technicians",
            ("technician", "full_name", "assigned", "completed", "outstanding"),
            {"technician": 110, "full_name": 180, "assigned": 90, "completed": 90,
             "outstanding": 95})
        self.complaints = self.build_table(
            notebook, "Complaints", ("metric", "value"),
            {"metric": 260, "value": 140})

        ttk.Label(self, text=CRITICALITY_NOTICE, wraplength=1000,
                  foreground="#5b6b7d").pack(anchor="w", pady=(8, 0))
        self.refresh()

    def build_table(self, notebook, title, columns, widths):
        frame = ttk.Frame(notebook, padding=8)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=14)
        for column in columns:
            tree.heading(column, text=column.replace("_", " ").title())
            tree.column(column, width=widths[column], minwidth=60, anchor="w",
                        stretch=True)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        tree.tag_configure("critical", background="#ffe0e0")
        tree.tag_configure("high", background="#fff0d9")
        notebook.add(frame, text=title)
        return tree

    def fill(self, tree, rows, tier_index=None):
        tree.delete(*tree.get_children())
        for row in rows:
            values = tuple(row.values()) if isinstance(row, dict) else tuple(row)
            tags = ()
            if tier_index is not None:
                tier = values[tier_index]
                tags = ("critical",) if tier == "Critical" else (
                    ("high",) if tier == "High" else ())
            tree.insert("", "end", values=values, tags=tags)

    def refresh(self):
        self.fill(self.summary, list(operational_summary(self.conn).items()))
        self.fill(self.performance, list(resolution_performance(self.conn).items()))
        self.fill(self.priority, priority_queue(self.conn), tier_index=4)
        self.fill(self.criticality, outages_by_criticality(self.conn), tier_index=0)
        self.fill(self.severity, outages_by_severity(self.conn))
        self.fill(self.regions, outages_by_region(self.conn))
        self.fill(self.workload, technician_workload(self.conn))
        self.fill(self.complaints, list(complaint_linkage(self.conn).items()))
        self.feedback.config(text="")

    def export(self):
        written = export_reports(self.conn)
        self.feedback.config(text=f"{len(written)} files written to "
                                  f"{REPORT_EXPORT_DIR}", foreground="#1b5e20")

    def reload_criticality(self):
        imported = refresh_criticality(self.conn)
        self.refresh()
        if imported:
            self.feedback.config(
                text=f"Reloaded criticality for {imported} substations",
                foreground="#1b5e20")
        else:
            self.feedback.config(
                text="No criticality file found. Run task2_1_network_analysis.py first.",
                foreground="#b00020")


class Dashboard(ttk.Frame):
    def __init__(self, master, conn, user, on_logout):
        super().__init__(master, padding=8)
        self.conn = conn
        self.user = user

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header,
                  text=f"GridCare-Lite  |  {user['full_name']} ({user['role']})",
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(header, text="Log Out", command=on_logout).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.tabs = {}
        if can(user, "view_outages"):
            self.tabs["outages"] = OutagesTab(self.notebook, conn, user)
            self.notebook.add(self.tabs["outages"], text="Outages")
        if can(user, "create_outage"):
            self.tabs["new_outage"] = NewOutageTab(self.notebook, conn, user, self.refresh_all)
            self.notebook.add(self.tabs["new_outage"], text="New Outage")
        if can(user, "view_work_orders"):
            self.tabs["work_orders"] = WorkOrdersTab(self.notebook, conn, user,
                                                     self.refresh_all)
            self.notebook.add(self.tabs["work_orders"], text="Work Orders")
        if can(user, "view_complaints"):
            self.tabs["complaints"] = ComplaintsTab(self.notebook, conn, user)
            self.notebook.add(self.tabs["complaints"], text="Complaints")
        if can(user, "view_reports"):
            self.tabs["reports"] = ReportsTab(self.notebook, conn, user)
            self.notebook.add(self.tabs["reports"], text="Reports")

    def refresh_all(self):
        for key in ("outages", "work_orders", "complaints", "reports"):
            tab = self.tabs.get(key)
            if tab is not None:
                tab.refresh()


class Application(tk.Tk):
    def __init__(self, conn):
        super().__init__()
        self.conn = conn
        self.title("GridCare-Lite")
        self.geometry("1180x680")
        self.current = None
        self.show_login()

    def clear(self):
        if self.current is not None:
            self.current.destroy()
            self.current = None

    def show_login(self):
        self.clear()
        self.title("GridCare-Lite - Login")
        self.current = LoginFrame(self, self.conn, self.show_dashboard)
        self.current.pack(expand=True)

    def show_dashboard(self, user):
        self.clear()
        self.title(f"GridCare-Lite - {user['role'].replace('_', ' ').title()} Dashboard")
        self.current = Dashboard(self, self.conn, user, self.show_login)
        self.current.pack(fill="both", expand=True)


def bootstrap():
    conn = init_db()
    imported = import_reference_data(conn)
    created = seed_users(conn)
    return conn, imported, created


def main():
    conn, imported, created = bootstrap()
    if imported["substations"]:
        print(f"Imported {imported['substations']} substations and "
              f"{imported['lines']} lines into {DB_PATH}")
    if imported["criticality"]:
        print(f"Imported criticality ratings for {imported['criticality']} substations "
              f"from the network analysis")
    else:
        print("No criticality ratings found. Run task2_1_network_analysis.py to enable "
              "criticality-aware reporting.")
    if created:
        print("Demo accounts created:")
        for username, password, role in created:
            print(f"  {username:<12} {password:<18} {role}")
    Application(conn).mainloop()
    conn.close()


if __name__ == "__main__":
    main()
