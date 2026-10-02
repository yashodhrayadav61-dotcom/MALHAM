"""
database.py
-----------
Sets up the SQLite database schema and seeds it with demo data.
Run this file directly to reset and re-seed the database:
    python database.py
"""

import sqlite3
import os
from datetime import datetime, timedelta
import random

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "malham.db")


def get_db_connection():
    """Return a new database connection with Row factory enabled."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # allows dict-like access to rows
    return conn


# ── Schema ────────────────────────────────────────────────────────────

def create_tables():
    """Create all tables if they don't already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        -- Patients table
        CREATE TABLE IF NOT EXISTS patients (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_code    TEXT UNIQUE,
            name            TEXT NOT NULL,
            age             INTEGER,
            gender          TEXT,
            phone           TEXT,
            address         TEXT,
            blood_group     TEXT,
            registered_on   TEXT DEFAULT (date('now')),
            admission_date  TEXT,
            discharge_date  TEXT,
            status          TEXT DEFAULT 'admitted',  -- admitted / discharged / emergency
            department      TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        -- Doctors table
        CREATE TABLE IF NOT EXISTS doctors (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            specialization  TEXT,
            phone           TEXT,
            email           TEXT,
            status          TEXT DEFAULT 'available',  -- available / busy / off-duty
            shift           TEXT DEFAULT 'morning',    -- morning / evening / night
            created_at      TEXT DEFAULT (datetime('now'))
        );

        -- Beds table
        CREATE TABLE IF NOT EXISTS beds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bed_number  TEXT NOT NULL UNIQUE,
            ward        TEXT,
            bed_type    TEXT DEFAULT 'general',  -- general / icu / private / emergency
            status      TEXT DEFAULT 'available', -- available / occupied / reserved / maintenance
            patient_id  INTEGER,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        -- Medicines table
        CREATE TABLE IF NOT EXISTS medicines (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            category    TEXT,
            quantity    INTEGER DEFAULT 0,
            unit        TEXT DEFAULT 'tablets',
            expiry_date TEXT,
            supplier    TEXT,
            price       REAL DEFAULT 0.0,
            status      TEXT DEFAULT 'in-stock', -- in-stock / low-stock / out-of-stock
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- Prescriptions table
        CREATE TABLE IF NOT EXISTS prescriptions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            rx_code        TEXT UNIQUE,
            patient_id     INTEGER NOT NULL,
            doctor_id      INTEGER NOT NULL,
            visit_id       INTEGER,
            issued_on      TEXT DEFAULT (datetime('now')),
            diagnosis_note TEXT,
            general_advice TEXT,
            follow_up_date TEXT,
            status         TEXT DEFAULT 'active', -- active / completed / cancelled
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id)  REFERENCES doctors(id),
            FOREIGN KEY (visit_id)   REFERENCES visits(id)
        );

        -- Prescription Items table
        CREATE TABLE IF NOT EXISTS prescription_items (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id      INTEGER NOT NULL,
            medicine_id          INTEGER NOT NULL,
            dosage_pattern       TEXT NOT NULL,       -- e.g. "1-0-1"
            food_timing          TEXT DEFAULT 'after food', -- before food / after food / with food / any time
            duration_days        INTEGER DEFAULT 5,
            special_instructions TEXT,
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id),
            FOREIGN KEY (medicine_id)     REFERENCES medicines(id)
        );

        -- Dose Schedule table
        CREATE TABLE IF NOT EXISTS dose_schedule (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_item_id INTEGER NOT NULL,
            dose_time_label      TEXT NOT NULL,       -- Morning / Afternoon / Night
            dose_time            TEXT NOT NULL,       -- 08:00, 14:00, 20:00
            quantity             REAL NOT NULL,
            start_date           TEXT NOT NULL,
            end_date             TEXT NOT NULL,
            FOREIGN KEY (prescription_item_id) REFERENCES prescription_items(id)
        );

        -- Patient Registrations table
        CREATE TABLE IF NOT EXISTS patient_registrations (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT NOT NULL,
            age                   INTEGER NOT NULL,
            gender                TEXT NOT NULL,
            phone                 TEXT,
            address               TEXT,
            blood_group           TEXT,
            requested_by_user_id  INTEGER NOT NULL,
            requested_on          TEXT DEFAULT (datetime('now', 'localtime')),
            status                TEXT DEFAULT 'pending',
            reviewed_by_user_id   INTEGER,
            reviewed_on           TEXT,
            reviewer_notes        TEXT,
            patient_id            INTEGER,
            FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
            FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id),
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        -- Follow-ups table
        CREATE TABLE IF NOT EXISTS followups (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id      INTEGER NOT NULL,
            doctor_id       INTEGER,
            prescription_id INTEGER,
            followup_date   TEXT NOT NULL,
            reason          TEXT,
            purpose         TEXT,
            status          TEXT DEFAULT 'scheduled', -- scheduled / completed / missed / cancelled
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id)  REFERENCES doctors(id),
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
        );

        -- Reminders table
        CREATE TABLE IF NOT EXISTS reminders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id      INTEGER NOT NULL,
            prescription_id INTEGER,
            reminder_type   TEXT NOT NULL,            -- medication / appointment / follow-up / check-in
            message_text    TEXT NOT NULL,
            scheduled_for   TEXT NOT NULL,            -- YYYY-MM-DD HH:MM:SS
            status          TEXT DEFAULT 'pending',   -- pending / sent / failed / acknowledged / missed
            channel         TEXT DEFAULT 'whatsapp',
            created_on      TEXT DEFAULT (datetime('now')),
            sent_on         TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
        );

        -- Check-ins table
        CREATE TABLE IF NOT EXISTS checkins (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id      INTEGER NOT NULL,
            prescription_id INTEGER,
            checkin_date    TEXT DEFAULT (date('now')),
            question        TEXT,
            response        TEXT NOT NULL,            -- took all medicines / missed some / stopped treatment / not answered
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id)
        );

        -- WhatsApp Message Log table
        CREATE TABLE IF NOT EXISTS message_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id  INTEGER,
            phone       TEXT,
            message     TEXT NOT NULL,
            status      TEXT DEFAULT 'sent',
            sent_on     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        );

        -- Activity log (for recent activity feed)
        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            action      TEXT NOT NULL,
            description TEXT,
            category    TEXT,   -- patient / doctor / bed / medicine / system
            timestamp   TEXT DEFAULT (datetime('now'))
        );

        -- Doctor Attendance table
        CREATE TABLE IF NOT EXISTS attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id   INTEGER NOT NULL,
            date        TEXT NOT NULL,               -- YYYY-MM-DD
            status      TEXT DEFAULT 'present',      -- present / absent / half-day / on-leave
            check_in    TEXT,                        -- e.g. 08:30 AM
            check_out   TEXT,                        -- e.g. 04:30 PM
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        );

        -- Doctor Leave Requests table
        CREATE TABLE IF NOT EXISTS doctor_leaves (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id      INTEGER NOT NULL,
            leave_type     TEXT DEFAULT 'casual',     -- casual / sick / emergency / earned
            start_date     TEXT NOT NULL,
            end_date       TEXT NOT NULL,
            reason         TEXT,
            status         TEXT DEFAULT 'pending',    -- pending / approved / rejected
            applied_on     TEXT DEFAULT (datetime('now')),
            reviewed_by    TEXT,
            reviewer_notes TEXT,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        );

        -- Patient Visits table
        CREATE TABLE IF NOT EXISTS visits (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id   INTEGER NOT NULL,
            doctor_id    INTEGER,
            visit_date   TEXT NOT NULL,              -- YYYY-MM-DD
            visit_type   TEXT DEFAULT 'opd',         -- opd / emergency / admission
            reason       TEXT,
            triage_level TEXT DEFAULT 'stable',      -- critical / urgent / stable (for emergency)
            status       TEXT DEFAULT 'waiting',     -- waiting / in-treatment / discharged
            notes        TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        );

        -- Staff Members table
        CREATE TABLE IF NOT EXISTS staff_members (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_code         TEXT UNIQUE NOT NULL,
            name               TEXT NOT NULL,
            staff_role         TEXT NOT NULL,
            department_or_ward TEXT NOT NULL,
            shift              TEXT NOT NULL,
            phone              TEXT,
            status             TEXT DEFAULT 'available'
        );

        -- Staff Attendance table
        CREATE TABLE IF NOT EXISTS staff_attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id    INTEGER NOT NULL,
            date        TEXT NOT NULL,
            status      TEXT DEFAULT 'present',
            check_in    TEXT,
            check_out   TEXT,
            notes       TEXT,
            FOREIGN KEY (staff_id) REFERENCES staff_members(id)
        );

        -- Staff Leaves table
        CREATE TABLE IF NOT EXISTS staff_leaves (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id       INTEGER NOT NULL,
            leave_type     TEXT NOT NULL,
            start_date     TEXT NOT NULL,
            end_date       TEXT NOT NULL,
            reason         TEXT,
            status         TEXT DEFAULT 'pending',
            reviewer_notes TEXT,
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (staff_id) REFERENCES staff_members(id)
        );

        -- Users table (RBAC)
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL,              -- head_doctor / doctor / staff / patient
            display_name  TEXT NOT NULL,
            doctor_id     INTEGER,
            patient_id    INTEGER,
            staff_id      INTEGER,
            created_at    TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (doctor_id)  REFERENCES doctors(id),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (staff_id)   REFERENCES staff_members(id)
        );
    """)

    # Ensure patient_code and registered_on columns exist in patients table
    cursor.execute("PRAGMA table_info(patients)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'patient_code' not in cols:
        cursor.execute("ALTER TABLE patients ADD COLUMN patient_code TEXT")
    if 'registered_on' not in cols:
        cursor.execute("ALTER TABLE patients ADD COLUMN registered_on TEXT")

    # Ensure assigned_on and notes columns exist in beds table
    cursor.execute("PRAGMA table_info(beds)")
    bcols = [row[1] for row in cursor.fetchall()]
    if 'assigned_on' not in bcols:
        cursor.execute("ALTER TABLE beds ADD COLUMN assigned_on TEXT")
    if 'notes' not in bcols:
        cursor.execute("ALTER TABLE beds ADD COLUMN notes TEXT")

    # Ensure missing columns exist in medicines table
    cursor.execute("PRAGMA table_info(medicines)")
    mcols = [row[1] for row in cursor.fetchall()]
    if 'generic_name' not in mcols:
        cursor.execute("ALTER TABLE medicines ADD COLUMN generic_name TEXT")
    if 'form' not in mcols:
        cursor.execute("ALTER TABLE medicines ADD COLUMN form TEXT DEFAULT 'tablet'")
    if 'strength' not in mcols:
        cursor.execute("ALTER TABLE medicines ADD COLUMN strength TEXT")
    if 'reorder_level' not in mcols:
        cursor.execute("ALTER TABLE medicines ADD COLUMN reorder_level INTEGER DEFAULT 20")
    if 'unit_price' not in mcols:
        cursor.execute("ALTER TABLE medicines ADD COLUMN unit_price REAL DEFAULT 0.0")
    if 'last_updated' not in mcols:
        cursor.execute("ALTER TABLE medicines ADD COLUMN last_updated TEXT")

    # Create stock_log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_id     INTEGER NOT NULL,
            change_type     TEXT NOT NULL,            -- restock / dispense / adjustment
            quantity_change INTEGER NOT NULL,
            note            TEXT,
            logged_on       TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (medicine_id) REFERENCES medicines(id)
        );
    """)

    # Ensure missing columns exist in prescriptions table
    cursor.execute("PRAGMA table_info(prescriptions)")
    pcols = [row[1] for row in cursor.fetchall()]
    if 'rx_code' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN rx_code TEXT")
    if 'visit_id' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN visit_id INTEGER")
    if 'issued_on' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN issued_on TEXT")
    if 'diagnosis_note' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN diagnosis_note TEXT")
    if 'general_advice' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN general_advice TEXT")
    if 'follow_up_date' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN follow_up_date TEXT")
    if 'status' not in pcols:
        cursor.execute("ALTER TABLE prescriptions ADD COLUMN status TEXT DEFAULT 'active'")

    # Ensure missing columns exist in followups table
    cursor.execute("PRAGMA table_info(followups)")
    fcols = [row[1] for row in cursor.fetchall()]
    if 'prescription_id' not in fcols:
        cursor.execute("ALTER TABLE followups ADD COLUMN prescription_id INTEGER")
    if 'purpose' not in fcols:
        cursor.execute("ALTER TABLE followups ADD COLUMN purpose TEXT")

    conn.commit()
    conn.close()
    print("[OK] Tables created successfully.")


# ── Demo Data ─────────────────────────────────────────────────────────

def seed_demo_data():
    """Populate the database with realistic demo records."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if data already exists
    existing = cursor.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    if existing > 0:
        seed_attendance_and_leaves(cursor, datetime.now())
        seed_patients_and_visits(cursor, datetime.now())
        seed_beds_extended(cursor, datetime.now())
        seed_medicines_extended(cursor, datetime.now())
        seed_prescriptions_extended(cursor, datetime.now())
        seed_followups_and_reminders_extended(cursor, datetime.now())
        seed_users_extended(cursor)
        conn.commit()
        conn.close()
        print("[INFO] Demo data checked: Attendance/Leaves/Visits/Beds/Medicines/Prescriptions/Followups/Reminders/Users.")
        return

    now = datetime.now()

    # ── Patients ──────────────────────────────────────────────────
    patients = [
        ("Aarav Sharma",      32, "Male",   "9876543210", "12 MG Road, Mumbai",       "O+",  (now - timedelta(days=3)).strftime("%Y-%m-%d"), None,                                           "admitted",   "Cardiology"),
        ("Priya Nair",        28, "Female", "9123456780", "45 Park St, Kochi",        "A+",  (now - timedelta(days=7)).strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d"), "discharged", "Orthopedics"),
        ("Rohan Mehta",       45, "Male",   "9988776655", "78 Lal Bagh, Bangalore",   "B+",  (now - timedelta(days=1)).strftime("%Y-%m-%d"), None,                                           "emergency",  "Emergency"),
        ("Sneha Iyer",        55, "Female", "9001122334", "23 Jubilee Hills, Hyderabad","AB-",(now - timedelta(days=5)).strftime("%Y-%m-%d"), None,                                           "admitted",   "Neurology"),
        ("Vikram Singh",      60, "Male",   "9556677889", "90 Civil Lines, Delhi",    "O-",  (now - timedelta(days=2)).strftime("%Y-%m-%d"), None,                                           "emergency",  "Emergency"),
        ("Anjali Deshmukh",   22, "Female", "9334455667", "56 FC Road, Pune",         "A-",  (now - timedelta(days=10)).strftime("%Y-%m-%d"),(now - timedelta(days=4)).strftime("%Y-%m-%d"), "discharged", "Dermatology"),
        ("Karthik Rajan",     38, "Male",   "9778899001", "34 Anna Nagar, Chennai",   "B-",  (now - timedelta(days=4)).strftime("%Y-%m-%d"), None,                                           "admitted",   "Cardiology"),
        ("Meera Joshi",       41, "Female", "9112233445", "67 Banjara Hills, Hyderabad","O+", (now - timedelta(days=6)).strftime("%Y-%m-%d"), (now - timedelta(days=2)).strftime("%Y-%m-%d"), "discharged", "Gynecology"),
        ("Arjun Patel",       50, "Male",   "9445566778", "89 SG Highway, Ahmedabad", "AB+", now.strftime("%Y-%m-%d"),                       None,                                           "emergency",  "Emergency"),
        ("Divya Krishnan",    35, "Female", "9667788990", "12 MG Marg, Gangtok",      "A+",  (now - timedelta(days=8)).strftime("%Y-%m-%d"), (now - timedelta(days=3)).strftime("%Y-%m-%d"), "discharged", "ENT"),
        ("Rahul Verma",       29, "Male",   "9223344556", "45 Mall Road, Shimla",     "B+",  (now - timedelta(days=1)).strftime("%Y-%m-%d"), None,                                           "admitted",   "Orthopedics"),
        ("Lakshmi Sundaram",  65, "Female", "9889900112", "78 Beach Road, Vizag",     "O-",  (now - timedelta(days=3)).strftime("%Y-%m-%d"), None,                                           "admitted",   "Neurology"),
    ]
    cursor.executemany(
        "INSERT INTO patients (name,age,gender,phone,address,blood_group,admission_date,discharge_date,status,department) VALUES (?,?,?,?,?,?,?,?,?,?)",
        patients,
    )

    # ── Doctors ───────────────────────────────────────────────────
    doctors = [
        ("Dr. Suresh Kumar",     "Cardiologist",       "9000011111", "suresh@malham.in",    "available", "morning"),
        ("Dr. Anita Desai",      "Orthopedic Surgeon", "9000022222", "anita@malham.in",     "busy",      "morning"),
        ("Dr. Rajesh Pillai",    "Neurologist",        "9000033333", "rajesh@malham.in",     "available", "evening"),
        ("Dr. Fatima Sheikh",    "Emergency Medicine", "9000044444", "fatima@malham.in",     "busy",      "night"),
        ("Dr. Vikram Chauhan",   "Dermatologist",      "9000055555", "vikram@malham.in",     "off-duty",  "morning"),
        ("Dr. Pooja Menon",      "Gynecologist",       "9000066666", "pooja@malham.in",      "available", "evening"),
        ("Dr. Anil Bhatt",       "ENT Specialist",     "9000077777", "anil@malham.in",       "available", "morning"),
        ("Dr. Kavitha Rao",      "General Physician",  "9000088888", "kavitha@malham.in",    "busy",      "night"),
    ]
    cursor.executemany(
        "INSERT INTO doctors (name,specialization,phone,email,status,shift) VALUES (?,?,?,?,?,?)",
        doctors,
    )

    # ── Beds ──────────────────────────────────────────────────────
    wards   = ["General-A", "General-B", "ICU", "Private", "Emergency"]
    types   = ["general",   "general",   "icu", "private", "emergency"]
    statuses = ["available", "occupied", "reserved", "maintenance"]

    bed_rows = []
    bed_idx  = 1
    for ward, btype in zip(wards, types):
        for i in range(1, 11):  # 10 beds per ward = 50 total
            bed_number = f"{ward[:3].upper()}-{bed_idx:03d}"
            # Distribute statuses with a bias toward 'available'
            if btype == "emergency":
                status = random.choice(["available", "occupied", "occupied", "available"])
            else:
                status = random.choice(["available", "available", "occupied", "occupied", "reserved", "available"])
            patient_id = None
            if status == "occupied":
                # Assign a random admitted / emergency patient
                patient_id = random.choice([1, 3, 4, 5, 7, 9, 11, 12])
            bed_rows.append((bed_number, ward, btype, status, patient_id))
            bed_idx += 1
    cursor.executemany(
        "INSERT INTO beds (bed_number,ward,bed_type,status,patient_id) VALUES (?,?,?,?,?)",
        bed_rows,
    )

    # ── Medicines ─────────────────────────────────────────────────
    medicines = [
        ("Paracetamol 500mg",   "Analgesic",       500, "tablets", (now + timedelta(days=365)).strftime("%Y-%m-%d"), "MedSupply Co.",  2.50,  "in-stock"),
        ("Amoxicillin 250mg",   "Antibiotic",       120, "capsules",(now + timedelta(days=180)).strftime("%Y-%m-%d"), "PharmaCorp",     8.00,  "in-stock"),
        ("Ibuprofen 400mg",     "Anti-inflammatory", 30, "tablets", (now + timedelta(days=90)).strftime("%Y-%m-%d"),  "HealthMeds Ltd.",5.00,  "low-stock"),
        ("Metformin 500mg",     "Anti-diabetic",    200, "tablets", (now + timedelta(days=300)).strftime("%Y-%m-%d"), "DiaCare Pharma", 3.50,  "in-stock"),
        ("Atorvastatin 10mg",   "Statin",           150, "tablets", (now + timedelta(days=400)).strftime("%Y-%m-%d"), "CardioMeds",     6.00,  "in-stock"),
        ("Cetirizine 10mg",     "Antihistamine",      0, "tablets", (now + timedelta(days=60)).strftime("%Y-%m-%d"),  "AllerFree Inc.", 1.50,  "out-of-stock"),
        ("Omeprazole 20mg",     "Antacid",           75, "capsules",(now + timedelta(days=200)).strftime("%Y-%m-%d"), "GutWell Labs",   4.00,  "in-stock"),
        ("Aspirin 75mg",        "Blood Thinner",     45, "tablets", (now + timedelta(days=150)).strftime("%Y-%m-%d"), "MedSupply Co.",  1.00,  "low-stock"),
    ]
    cursor.executemany(
        "INSERT INTO medicines (name,category,quantity,unit,expiry_date,supplier,price,status) VALUES (?,?,?,?,?,?,?,?)",
        medicines,
    )

    seed_attendance_and_leaves(cursor, now)
    seed_staff_and_attendance(cursor, now)
    seed_patients_and_visits(cursor, now)
    seed_beds_extended(cursor, now)
    seed_medicines_extended(cursor, now)
    seed_prescriptions_extended(cursor, now)
    seed_followups_and_reminders_extended(cursor, now)
    seed_users_extended(cursor)

    conn.commit()
    conn.close()
    print("[OK] Demo data seeded successfully.")


def seed_attendance_and_leaves(cursor, now):
    """Seed attendance and leave records if not present."""
    att_count = cursor.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    if att_count == 0:
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        attendance_records = [
            (1, today,     'present',  '08:15', '16:00', 'On time'),
            (3, today,     'present',  '17:10', '23:00', 'Evening shift'),
            (4, today,     'present',  '20:25', '06:00', 'Night shift'),
            (5, today,     'on-leave', None,       None,       'Approved casual leave'),
            (6, today,     'present',  '17:15', '23:00', 'Evening shift'),
            (7, today,     'present',  '08:20', '16:00', 'On time'),
            (8, today,     'absent',   None,       None,       'Uninformed leave'),
            (1, yesterday, 'present',  '08:10', '16:00', 'Completed shift'),
            (2, yesterday, 'present',  '08:25', '16:00', 'Completed shift'),
            (3, yesterday, 'present',  '17:05', '23:00', 'Completed shift'),
            (5, yesterday, 'on-leave', None,       None,       'Casual leave'),
        ]
        cursor.executemany(
            "INSERT INTO attendance (doctor_id, date, status, check_in, check_out, notes) VALUES (?,?,?,?,?,?)",
            attendance_records,
        )

    leave_count = cursor.execute("SELECT COUNT(*) FROM doctor_leaves").fetchone()[0]
    if leave_count == 0:
        leave_records = [
            (5, 'casual',    now.strftime("%Y-%m-%d"), (now + timedelta(days=2)).strftime("%Y-%m-%d"), "Family function in hometown", "approved", (now - timedelta(days=2)).strftime("%Y-%m-%d"), "Admin", "Approved as per quota"),
            (2, 'sick',      (now + timedelta(days=3)).strftime("%Y-%m-%d"), (now + timedelta(days=4)).strftime("%Y-%m-%d"), "Severe migraine", "pending", (now - timedelta(hours=4)).strftime("%Y-%m-%d"), None, None),
            (7, 'emergency', (now + timedelta(days=5)).strftime("%Y-%m-%d"), (now + timedelta(days=6)).strftime("%Y-%m-%d"), "Urgent personal work", "pending", (now - timedelta(hours=2)).strftime("%Y-%m-%d"), None, None),
            (4, 'earned',    (now - timedelta(days=10)).strftime("%Y-%m-%d"), (now - timedelta(days=7)).strftime("%Y-%m-%d"), "Annual vacation", "approved", (now - timedelta(days=15)).strftime("%Y-%m-%d"), "Admin", "Enjoy your break"),
            (3, 'casual',    (now + timedelta(days=1)).strftime("%Y-%m-%d"), (now + timedelta(days=1)).strftime("%Y-%m-%d"), "Personal appointment", "rejected", (now - timedelta(days=1)).strftime("%Y-%m-%d"), "Admin", "Coverage not available for evening shift"),
        ]
        cursor.executemany(
            "INSERT INTO doctor_leaves (doctor_id, leave_type, start_date, end_date, reason, status, applied_on, reviewed_by, reviewer_notes) VALUES (?,?,?,?,?,?,?,?,?)",
            leave_records,
        )


def seed_patients_and_visits(cursor, now):
    """Ensure all patients have patient_code/registered_on and seed demo visits."""
    patients = cursor.execute("SELECT id, admission_date, created_at FROM patients ORDER BY id ASC").fetchall()
    for idx, p in enumerate(patients, start=1001):
        pid = p[0]
        code = f"P-{idx}"
        reg_date = p[1] if p[1] else (now - timedelta(days=5)).strftime("%Y-%m-%d")
        cursor.execute(
            "UPDATE patients SET patient_code = COALESCE(patient_code, ?), registered_on = COALESCE(registered_on, ?) WHERE id = ?",
            (code, reg_date, pid)
        )

    visit_count = cursor.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    if visit_count == 0:
        today = now.strftime("%Y-%m-%d")
        d1 = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        d2 = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        d3 = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        d4 = (now - timedelta(days=4)).strftime("%Y-%m-%d")
        d5 = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        d6 = (now - timedelta(days=6)).strftime("%Y-%m-%d")

        visits = [
            (3, 4, today, "emergency", "Severe Chest Pain & Trauma", "critical", "in-treatment", "ECG performed, continuous monitoring"),
            (9, 4, today, "emergency", "Acute Abdominal Pain & Vomiting", "critical", "waiting", "Triage assessed, awaiting Doctor"),
            (5, 4, today, "emergency", "High Fever & Dehydration", "urgent", "in-treatment", "IV fluids administered"),
            (1, 1, today, "opd", "Routine Cardiac Follow-up", None, "waiting", "BP check pending"),
            (11, 2, today, "opd", "Knee Joint Pain Review", None, "in-treatment", "X-ray ordered"),
            (8, 6, today, "opd", "Post-natal Consultation", None, "discharged", "Vitals normal, prescription renewed"),
            (2, 2, d1, "admission", "Orthopedic Surgery Recovery", None, "discharged", "Post-op recovery satisfactory"),
            (6, 5, d1, "opd", "Skin Rash Treatment", None, "discharged", "Topical ointment prescribed"),
            (10, 7, d1, "emergency", "Allergic Reaction & Swelling", "urgent", "discharged", "Antihistamine administered"),
            (12, 3, d2, "admission", "Neurological Evaluation", None, "in-treatment", "MRI scan scheduled"),
            (4, 3, d2, "opd", "Chronic Headache Checkup", None, "discharged", "Medication dosage adjusted"),
            (7, 1, d3, "admission", "Cardiovascular Monitoring", None, "in-treatment", "Stable under observation"),
            (1, 1, d3, "opd", "BP & Heart Rate Check", None, "discharged", "BP 120/80 mmHg, stable"),
            (3, 4, d4, "emergency", "Roadside Accident Injury", "urgent", "discharged", "Wound dressed, tetanus shot given"),
            (5, 4, d4, "emergency", "Dizziness & Low BP", "stable", "discharged", "Hydration therapy given"),
            (6, 5, d5, "opd", "Dermatology Follow-up", None, "discharged", "Condition improving nicely"),
            (2, 2, d5, "opd", "Post-surgery Check", None, "discharged", "Stitches removed clean"),
            (11, 2, d6, "opd", "Joint Stiffness", None, "discharged", "Physiotherapy recommended"),
            (8, 6, d6, "opd", "General Health Checkup", None, "discharged", "All basic parameters normal"),
            (10, 7, d6, "opd", "Ear Pain Evaluation", None, "discharged", "Ear drops prescribed"),
        ]

        cursor.executemany(
            "INSERT INTO visits (patient_id, doctor_id, visit_date, visit_type, reason, triage_level, status, notes) VALUES (?,?,?,?,?,?,?,?)",
            visits
        )


def seed_beds_extended(cursor, now):
    """Standardize ward names and populate/update bed assignments."""
    cursor.execute("UPDATE beds SET ward='General' WHERE ward IN ('General-A', 'General-B')")

    count = cursor.execute("SELECT COUNT(*) FROM beds").fetchone()[0]
    if count == 0:
        wards = ["General", "ICU", "Emergency", "Maternity", "Pediatric"]
        btypes = ["general", "icu", "emergency", "private", "general"]
        bed_rows = []
        b_id = 1
        for ward, btype in zip(wards, btypes):
            for i in range(1, 9):  # 8 beds per ward * 5 = 40 total
                code = f"{ward[:3].upper()}-{i:02d}"
                status = "available"
                pid = None
                assigned_on = None
                if b_id in [1, 3, 9, 17, 25]:
                    status = "occupied"
                elif b_id in [4, 12, 20]:
                    status = "reserved"
                elif b_id in [8, 28]:
                    status = "maintenance"
                bed_rows.append((code, ward, btype, status, pid, assigned_on, "Standard ward bed"))
                b_id += 1
        cursor.executemany(
            "INSERT INTO beds (bed_number, ward, bed_type, status, patient_id, assigned_on, notes) VALUES (?,?,?,?,?,?,?)",
            bed_rows
        )

    # Clean up duplicate patient assignments if any
    occupied = cursor.execute("SELECT id, patient_id FROM beds WHERE status='occupied' AND patient_id IS NOT NULL ORDER BY id ASC").fetchall()
    seen = set()
    for b_id, p_id in occupied:
        if p_id in seen:
            cursor.execute("UPDATE beds SET status='available', patient_id=NULL, assigned_on=NULL WHERE id=?", (b_id,))
        else:
            seen.add(p_id)
            cursor.execute(
                "UPDATE beds SET assigned_on = COALESCE(assigned_on, ?) WHERE id=?",
                ((now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M"), b_id)
            )

    # Link some occupied beds without patient_id to available admitted patients
    unassigned_beds = cursor.execute("SELECT id FROM beds WHERE status='occupied' AND patient_id IS NULL").fetchall()
    if unassigned_beds:
        admitted = cursor.execute(
            "SELECT id FROM patients WHERE id NOT IN (SELECT patient_id FROM beds WHERE patient_id IS NOT NULL) LIMIT ?",
            (len(unassigned_beds),)
        ).fetchall()
        for bed_row, pat_row in zip(unassigned_beds, admitted):
            cursor.execute(
                "UPDATE beds SET patient_id = ?, assigned_on = ? WHERE id = ?",
                (pat_row[0], (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M"), bed_row[0])
            )


# ── Standalone Execution ──────────────────────────────────────────────

def seed_medicines_extended(cursor, now):
    """Ensure medicines table has ~30 records with proper reorder levels, stock logs, and low/out/expiring statuses."""
    med_count = cursor.execute("SELECT COUNT(*) FROM medicines").fetchone()[0]

    d365 = (now + timedelta(days=365)).strftime("%Y-%m-%d")
    d180 = (now + timedelta(days=180)).strftime("%Y-%m-%d")
    d90  = (now + timedelta(days=90)).strftime("%Y-%m-%d")
    d15  = (now + timedelta(days=15)).strftime("%Y-%m-%d")
    d22  = (now + timedelta(days=22)).strftime("%Y-%m-%d")
    d_past = (now - timedelta(days=5)).strftime("%Y-%m-%d")

    if med_count <= 8:
        cursor.execute("DELETE FROM medicines")

        medicines_data = [
            ("Paracetamol 500mg", "Acetaminophen", "Analgesic", "tablet", "500mg", 450, 50, 2.50, d365, "MedSupply Co.", "in-stock"),
            ("Amoxicillin 250mg", "Amoxicillin", "Antibiotic", "capsule", "250mg", 15, 30, 8.00, d180, "PharmaCorp", "low-stock"),
            ("Ibuprofen 400mg", "Ibuprofen", "Painkiller", "tablet", "400mg", 20, 40, 5.00, d90, "HealthMeds Ltd.", "low-stock"),
            ("Metformin 500mg", "Metformin HCl", "Antidiabetic", "tablet", "500mg", 300, 50, 3.50, d365, "DiaCare Pharma", "in-stock"),
            ("Atorvastatin 10mg", "Atorvastatin", "Cardiac", "tablet", "10mg", 180, 30, 6.00, d365, "CardioMeds", "in-stock"),
            ("Cetirizine 10mg", "Cetirizine HCl", "Antihistamine", "tablet", "10mg", 0, 25, 1.50, d90, "AllerFree Inc.", "out-of-stock"),
            ("Omeprazole 20mg", "Omeprazole", "Gastrointestinal", "capsule", "20mg", 120, 30, 4.00, d180, "GutWell Labs", "in-stock"),
            ("Aspirin 75mg", "Acetylsalicylic Acid", "Cardiac", "tablet", "75mg", 12, 50, 1.00, d180, "MedSupply Co.", "low-stock"),
            ("Azithromycin 500mg", "Azithromycin", "Antibiotic", "tablet", "500mg", 80, 20, 15.00, d15, "PharmaCorp", "expiring"),
            ("Ceftriaxone 1g", "Ceftriaxone Sodium", "Antibiotic", "injection", "1g", 40, 15, 45.00, d22, "Injecta Pharma", "expiring"),
            ("Epinephrine 1mg", "Adrenaline", "Emergency", "injection", "1mg/ml", 5, 10, 60.00, d180, "EmergMed Ltd.", "low-stock"),
            ("Insulin Glargine 100IU", "Insulin Glargine", "Antidiabetic", "injection", "100IU/ml", 0, 15, 120.00, d90, "DiaCare Pharma", "out-of-stock"),
            ("Pantoprazole 40mg", "Pantoprazole", "Gastrointestinal", "tablet", "40mg", 220, 40, 5.50, d365, "GutWell Labs", "in-stock"),
            ("Losartan 50mg", "Losartan Potassium", "Cardiac", "tablet", "50mg", 160, 30, 7.00, d365, "CardioMeds", "in-stock"),
            ("Amlodipine 5mg", "Amlodipine Besylate", "Cardiac", "tablet", "5mg", 250, 40, 3.00, d365, "CardioMeds", "in-stock"),
            ("Ciprofloxacin 500mg", "Ciprofloxacin", "Antibiotic", "tablet", "500mg", 90, 20, 12.00, d180, "PharmaCorp", "in-stock"),
            ("Vitamin D3 60K", "Cholecalciferol", "Vitamin", "capsule", "60,000 IU", 140, 25, 18.00, d365, "NutriHealth", "in-stock"),
            ("Multivitamin Syrup", "Multivitamin & Minerals", "Vitamin", "syrup", "200ml", 8, 15, 35.00, d180, "NutriHealth", "low-stock"),
            ("Salbutamol Inhaler", "Salbutamol", "Emergency", "inhaler", "100mcg", 18, 20, 85.00, d365, "Respira Care", "low-stock"),
            ("Tramadol 50mg", "Tramadol HCl", "Painkiller", "tablet", "50mg", 60, 20, 14.00, d180, "HealthMeds Ltd.", "in-stock"),
            ("Ondansetron 4mg", "Ondansetron", "Antiemetic", "tablet", "4mg", 110, 25, 4.50, d365, "MedSupply Co.", "in-stock"),
            ("Dexamethasone 4mg", "Dexamethasone", "Steroid", "injection", "4mg/ml", 35, 15, 12.50, d180, "Injecta Pharma", "in-stock"),
            ("Furosemide 40mg", "Furosemide", "Diuretic", "tablet", "40mg", 0, 20, 2.80, d180, "CardioMeds", "out-of-stock"),
            ("Oral Rehydration Salts", "ORS Salts", "Emergency", "sachet", "21.8g", 500, 100, 1.20, d365, "EmergMed Ltd.", "in-stock"),
            ("Dicyclomine 20mg", "Dicyclomine HCl", "Antispasmodic", "tablet", "20mg", 75, 20, 3.20, d365, "GutWell Labs", "in-stock"),
            ("Levothyroxine 50mcg", "Levothyroxine Sodium", "Endocrine", "tablet", "50mcg", 210, 30, 4.80, d365, "ThyroCare Labs", "in-stock"),
            ("Ranitidine 150mg", "Ranitidine HCl", "Gastrointestinal", "tablet", "150mg", 0, 30, 2.00, d_past, "GutWell Labs", "out-of-stock"),
            ("Diclofenac Gel", "Diclofenac Sodium", "Painkiller", "ointment", "30g", 45, 15, 28.00, d365, "HealthMeds Ltd.", "in-stock"),
            ("Cough Syrup Complex", "Dextromethorphan", "Respiratory", "syrup", "100ml", 6, 15, 42.00, d180, "Respira Care", "low-stock"),
            ("Hydrocortisone 100mg", "Hydrocortisone Succinate", "Emergency", "injection", "100mg", 12, 15, 55.00, d180, "Injecta Pharma", "low-stock"),
        ]

        cursor.executemany(
            "INSERT INTO medicines (name, generic_name, category, form, strength, quantity, reorder_level, unit_price, expiry_date, supplier, status, last_updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))",
            medicines_data
        )

    log_count = cursor.execute("SELECT COUNT(*) FROM stock_log").fetchone()[0]
    if log_count == 0:
        logs = [
            (1, "restock", 500, "Initial batch received", (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")),
            (1, "dispense", -50, "Dispensed for Outpatient prescriptions", (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")),
            (2, "dispense", -105, "Ward pharmacy allocation", (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M")),
            (3, "dispense", -80, "ER emergency kits dispense", (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")),
            (9, "restock", 80, "Antibiotic stock replenishment", (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")),
            (11, "dispense", -15, "ICU crash cart stock", (now - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")),
        ]
        cursor.executemany(
            "INSERT INTO stock_log (medicine_id, change_type, quantity_change, note, logged_on) VALUES (?,?,?,?,?)",
            logs
        )


def seed_prescriptions_extended(cursor, now):
    """Seed about 8 demo prescriptions with prescription_items and dose_schedule rows."""
    from prescription_utils import generate_dose_schedule_rows

    p_count = cursor.execute("SELECT COUNT(*) FROM prescription_items").fetchone()[0]
    if p_count > 0:
        return

    today = now.strftime("%Y-%m-%d %H:%M:%S")

    demo_prescriptions = [
        {
            "rx_code": "RX-2001", "patient_id": 1, "doctor_id": 1, "visit_id": 4,
            "issued_on": (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Acute Hypertensive Episode & Mild Angina",
            "general_advice": "Low salt diet, light walking daily, avoid stress and heavy lifting.",
            "follow_up_date": (now + timedelta(days=5)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (15, "1-0-1", "after food", 7, "Take with full glass of water"),
                (8,  "1-0-0", "after food", 7, "Take immediately after morning breakfast"),
            ]
        },
        {
            "rx_code": "RX-2002", "patient_id": 3, "doctor_id": 4, "visit_id": 1,
            "issued_on": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Roadside Injury Trauma & Severe Leg Pain",
            "general_advice": "Rest leg elevated, clean and dress wound daily with antiseptic.",
            "follow_up_date": (now + timedelta(days=4)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (3,  "1-0-1", "after food", 5, "Take for pain management"),
                (2,  "1-1-1", "after food", 5, "Complete full antibiotic course"),
                (7,  "1-0-0", "before food", 5, "Take 30 mins before breakfast"),
            ]
        },
        {
            "rx_code": "RX-2003", "patient_id": 4, "doctor_id": 3, "visit_id": 11,
            "issued_on": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Migraine Headache & Acute Gastritis",
            "general_advice": "Avoid bright screens in dark rooms, maintain hydration.",
            "follow_up_date": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (20, "0.5-0-0.5", "after food", 3, "Only when headache is severe"),
                (13, "1-0-0", "before food", 10, "Morning dose before breakfast"),
            ]
        },
        {
            "rx_code": "RX-2004", "patient_id": 5, "doctor_id": 4, "visit_id": 3,
            "issued_on": (now - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "High Fever & Moderate Dehydration",
            "general_advice": "Drink ORS solution, rest in a cool room, sponge with lukewarm water.",
            "follow_up_date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (1,  "1-1-1", "after food", 3, "Take if fever exceeds 100°F"),
                (24, "1-1-1", "any time", 3, "Dissolve 1 sachet in 1 liter clean drinking water"),
            ]
        },
        {
            "rx_code": "RX-2005", "patient_id": 6, "doctor_id": 5, "visit_id": 8,
            "issued_on": (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Allergic Contact Dermatitis",
            "general_advice": "Avoid harsh soaps and hot water showers.",
            "follow_up_date": (now + timedelta(days=9)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (6,  "0-0-1", "after food", 7, "May cause drowsiness, take at bedtime"),
                (28, "1-0-1", "any time", 7, "Apply thin layer on clean affected skin"),
            ]
        },
        {
            "rx_code": "RX-2006", "patient_id": 7, "doctor_id": 1, "visit_id": 12,
            "issued_on": (now - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Hypercholesterolemia",
            "general_advice": "Strict low-fat diet, 30 min daily cardio exercise.",
            "follow_up_date": (now + timedelta(days=26)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (5,  "0-0-1", "after food", 30, "Night time dose after dinner"),
            ]
        },
        {
            "rx_code": "RX-2007", "patient_id": 11, "doctor_id": 2, "visit_id": 5,
            "issued_on": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Knee Osteoarthritis",
            "general_advice": "Perform joint flexibility exercises, use knee support brace.",
            "follow_up_date": (now + timedelta(days=13)).strftime("%Y-%m-%d"),
            "status": "active",
            "items": [
                (3,  "1-0-1", "after food", 10, "Take with milk or meal"),
                (17, "1-0-0", "after food", 4, "Once weekly on Sunday"),
            ]
        },
        {
            "rx_code": "RX-2008", "patient_id": 2, "doctor_id": 2, "visit_id": 7,
            "issued_on": (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"),
            "diagnosis_note": "Post-surgical Surgical Wound Recovery",
            "general_advice": "Keep surgical dressing clean and dry, avoid lifting heavy objects.",
            "follow_up_date": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
            "status": "completed",
            "items": [
                (9,  "1-0-0", "before food", 5, "Take at same time every morning"),
                (1,  "1-0-1", "after food", 5, "For mild surgical pain"),
            ]
        }
    ]

    for p in demo_prescriptions:
        cursor.execute(
            """INSERT INTO prescriptions 
               (rx_code, patient_id, doctor_id, visit_id, issued_on, diagnosis_note, general_advice, follow_up_date, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["rx_code"], p["patient_id"], p["doctor_id"], p["visit_id"], p["issued_on"], p["diagnosis_note"], p["general_advice"], p["follow_up_date"], p["status"])
        )
        rx_id = cursor.lastrowid

        for med_id, pattern, food, duration, instructions in p["items"]:
            med_row = cursor.execute("SELECT form FROM medicines WHERE id = ?", (med_id,)).fetchone()
            form = med_row["form"] if med_row and med_row["form"] else "tablet"

            cursor.execute(
                """INSERT INTO prescription_items
                   (prescription_id, medicine_id, dosage_pattern, food_timing, duration_days, special_instructions)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (rx_id, med_id, pattern, food, duration, instructions)
            )
            item_id = cursor.lastrowid

            start_d = p["issued_on"][:10]
            schedules = generate_dose_schedule_rows(item_id, pattern, form, start_d, duration)
            cursor.executemany(
                """INSERT INTO dose_schedule
                   (prescription_item_id, dose_time_label, dose_time, quantity, start_date, end_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                schedules
            )


def seed_followups_and_reminders_extended(cursor, now):
    """Seed reminders, checkins, message_log, and additional follow-up records."""
    r_count = cursor.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
    if r_count > 0:
        return

    today = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    d_minus_2 = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    d_minus_1 = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    d_plus_1  = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    d_plus_2  = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    d_plus_5  = (now + timedelta(days=5)).strftime("%Y-%m-%d")

    demo_reminders = [
        (1, 1, 'medication', 'Reminder: Your prescribed medicine Amlodipine 5mg (1 tablet, after food) is scheduled for 8:00 AM.', f"{d_minus_1} 08:00:00", 'acknowledged', 'whatsapp', f"{d_minus_2} 10:00:00", f"{d_minus_1} 08:00:05"),
        (1, 1, 'medication', 'Reminder: Your prescribed medicine Amlodipine 5mg (1 tablet, after food) is scheduled for 8:00 PM.', f"{d_minus_1} 20:00:00", 'acknowledged', 'whatsapp', f"{d_minus_2} 10:00:00", f"{d_minus_1} 20:00:05"),
        (1, 1, 'medication', 'Reminder: Your prescribed medicine Amlodipine 5mg (1 tablet, after food) is scheduled for 8:00 AM.', f"{today} 08:00:00", 'sent', 'whatsapp', f"{d_minus_2} 10:00:00", f"{today} 08:00:02"),
        (1, 1, 'medication', 'Reminder: Your prescribed medicine Amlodipine 5mg (1 tablet, after food) is scheduled for 8:00 PM.', f"{today} 20:00:00", 'pending', 'whatsapp', f"{d_minus_2} 10:00:00", None),

        (3, 2, 'medication', 'Reminder: Your prescribed medicine Ibuprofen 400mg (1 tablet, after food) is scheduled for 8:00 AM.', f"{d_minus_1} 08:00:00", 'missed', 'whatsapp', f"{d_minus_1} 07:00:00", f"{d_minus_1} 08:00:01"),
        (3, 2, 'medication', 'Reminder: Your prescribed medicine Amoxicillin 250mg (1 capsule, after food) is scheduled for 2:00 PM.', f"{d_minus_1} 14:00:00", 'missed', 'whatsapp', f"{d_minus_1} 07:00:00", f"{d_minus_1} 14:00:03"),
        (3, 2, 'medication', 'Reminder: Your prescribed medicine Ibuprofen 400mg (1 tablet, after food) is scheduled for 8:00 AM.', f"{today} 08:00:00", 'pending', 'whatsapp', f"{d_minus_1} 07:00:00", None),

        (4, 3, 'medication', 'Reminder: Your prescribed medicine Pantoprazole 40mg (1 tablet, before food) is scheduled for 8:00 AM.', f"{today} 08:00:00", 'sent', 'whatsapp', f"{d_minus_2} 09:00:00", f"{today} 08:00:01"),
        (4, 3, 'follow-up',  'Reminder: You have an upcoming follow-up appointment with Dr. Rajesh Pillai scheduled for tomorrow.', f"{d_plus_1} 09:00:00", 'pending', 'whatsapp', f"{d_minus_1} 09:00:00", None),

        (5, 4, 'medication', 'Reminder: Your prescribed medicine Paracetamol 500mg (1 tablet, after food) is scheduled for 8:00 AM.', f"{today} 08:00:00", 'pending', 'whatsapp', f"{today} 06:00:00", None),
        (5, 4, 'medication', 'Reminder: Your prescribed medicine Oral Rehydration Salts (1 sachet, any time) is scheduled for 2:00 PM.', f"{today} 14:00:00", 'pending', 'whatsapp', f"{today} 06:00:00", None),

        (6, 5, 'medication', 'Reminder: Your prescribed medicine Cetirizine 10mg (1 tablet, after food) is scheduled for 8:00 PM.', f"{d_minus_1} 20:00:00", 'missed', 'whatsapp', f"{d_minus_2} 12:00:00", f"{d_minus_1} 20:00:02"),

        (7, 6, 'appointment', 'Reminder: Upcoming lipid profile checkup scheduled for next week.', f"{d_plus_5} 09:00:00", 'pending', 'whatsapp', f"{d_minus_1} 10:00:00", None),
    ]

    cursor.executemany(
        """INSERT INTO reminders
           (patient_id, prescription_id, reminder_type, message_text, scheduled_for, status, channel, created_on, sent_on)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        demo_reminders
    )

    demo_checkins = [
        (1, 1, d_minus_1, 'Daily medication check-in', 'took all medicines', 'Patient reported feeling good, blood pressure stable.'),
        (3, 2, d_minus_1, 'Pain & antibiotic check-in', 'missed some', 'Patient missed afternoon dose due to stomach discomfort.'),
        (6, 5, d_minus_2, 'Dermatology allergy check-in', 'stopped treatment', 'Patient stopped taking Cetirizine due to extreme daytime drowsiness.'),
        (4, 3, today,     'Gastritis treatment check-in', 'took all medicines', 'Gastric reflux significantly reduced.'),
        (5, 4, today,     'Fever hydration check-in', 'not answered', 'Attempted phone call check-in, no response.'),
    ]

    cursor.executemany(
        """INSERT INTO checkins
           (patient_id, prescription_id, checkin_date, question, response, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        demo_checkins
    )

    demo_messages = [
        (1, "9876543210", "Reminder: Your prescribed medicine Amlodipine 5mg (1 tablet, after food) is scheduled for 8:00 AM.", "sent", f"{d_minus_1} 08:00:05"),
        (1, "9876543210", "Acknowledge: I have taken my 8:00 AM Amlodipine tablet.", "received", f"{d_minus_1} 08:12:30"),
        (1, "9876543210", "Reminder: Your prescribed medicine Amlodipine 5mg (1 tablet, after food) is scheduled for 8:00 PM.", "sent", f"{d_minus_1} 20:00:05"),
        (3, "9988776655", "Reminder: Your prescribed medicine Ibuprofen 400mg (1 tablet, after food) is scheduled for 8:00 AM.", "sent", f"{d_minus_1} 08:00:01"),
        (4, "9001122334", "Reminder: Your prescribed medicine Pantoprazole 40mg (1 tablet, before food) is scheduled for 8:00 AM.", "sent", f"{today} 08:00:01"),
        (6, "9334455667", "Reminder: Your prescribed medicine Cetirizine 10mg (1 tablet, after food) is scheduled for 8:00 PM.", "sent", f"{d_minus_1} 20:00:02"),
    ]

    cursor.executemany(
        """INSERT INTO message_log (patient_id, phone, message, status, sent_on) VALUES (?, ?, ?, ?, ?)""",
        demo_messages
    )

    f_count = cursor.execute("SELECT COUNT(*) FROM followups").fetchone()[0]
    if f_count <= 6:
        extra_followups = [
            (3, 4, d_minus_2, "Emergency Post-trauma Review", "missed", "Patient missed scheduled appointment."),
            (5, 4, d_minus_1, "Fever Re-evaluation", "missed", "Overdue follow-up visit."),
            (1, 1, d_plus_5,  "Hypertension Control Review", "scheduled", "Routine ECG & BP evaluation."),
            (11,2, d_plus_2,  "Knee Joint Assessment", "scheduled", "Evaluate physiotherapy progress."),
        ]
        cursor.executemany(
            "INSERT INTO followups (patient_id, doctor_id, followup_date, reason, status, notes) VALUES (?,?,?,?,?,?)",
            extra_followups
        )



def seed_staff_and_attendance(cursor, now):
    staff_count = cursor.execute("SELECT COUNT(*) FROM staff_members").fetchone()[0]
    if staff_count == 0:
        staff = [
            ("S-101", "Nurse Sarah", "Nurse", "General", "morning", "9001002001", "available"),
            ("S-102", "Nurse John", "Nurse", "ICU", "night", "9001002002", "busy"),
            ("S-103", "Ward Boy Ali", "Ward Boy", "Emergency", "evening", "9001002003", "available"),
            ("S-104", "Tech Mike", "Lab Technician", "Lab", "morning", "9001002004", "available"),
            ("S-105", "Nurse Emily", "Nurse", "Maternity", "morning", "9001002005", "off-duty"),
            ("S-106", "Pharm Dave", "Pharmacist", "Pharmacy", "afternoon", "9001002006", "available"),
            ("S-107", "Nurse Joy", "Nurse", "Pediatric", "night", "9001002007", "available"),
            ("S-108", "Recep Mark", "Receptionist", "Front Desk", "morning", "9001002008", "available"),
            ("S-109", "Ward Boy Sam", "Ward Boy", "ICU", "night", "9001002009", "on-leave"),
            ("S-110", "Nurse Maya", "Nurse", "Emergency", "evening", "9001002010", "available"),
        ]
        cursor.executemany(
            "INSERT INTO staff_members (staff_code, name, staff_role, department_or_ward, shift, phone, status) VALUES (?,?,?,?,?,?,?)",
            staff
        )

    att_count = cursor.execute("SELECT COUNT(*) FROM staff_attendance").fetchone()[0]
    if att_count == 0:
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # 7 days history for Nurse Sarah (staff_id 1)
        history = []
        for i in range(1, 8):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            history.append((1, d, 'present', '08:15', '16:00', 'On time'))
            
        # TODAY's records for everyone except Nurse Sarah (1)
        # 2: night (20:00), 3: evening (17:00), 4: morning (08:00), 5: morning, 6: afternoon (14:00)
        # 7: night, 8: morning, 9: night (on leave), 10: evening
        today_att = [
            (2, today, 'present', '20:15', '06:00', 'Night shift'),
            (3, today, 'present', '17:20', '23:00', 'Evening shift'),
            (4, today, 'present', '08:10', '16:00', 'Morning shift'),
            (5, today, 'present', '08:25', '16:00', 'Morning shift'),
            (6, today, 'present', '14:15', '22:00', 'Afternoon shift'),
            (7, today, 'present', '20:05', '06:00', 'Night shift'),
            (8, today, 'present', '08:05', '16:00', 'Morning shift'),
            (9, today, 'on-leave', None, None, 'Sick leave'),
            (10, today, 'present', '17:15', '23:00', 'Evening shift'),
        ]
        
        cursor.executemany(
            "INSERT INTO staff_attendance (staff_id, date, status, check_in, check_out, notes) VALUES (?,?,?,?,?,?)",
            history + today_att
        )

    leave_count = cursor.execute("SELECT COUNT(*) FROM staff_leaves").fetchone()[0]
    if leave_count == 0:
        leaves = [
            (1, 'casual', (now + timedelta(days=5)).strftime("%Y-%m-%d"), (now + timedelta(days=6)).strftime("%Y-%m-%d"), "Family event", "pending", None),
            (9, 'sick', today, (now + timedelta(days=2)).strftime("%Y-%m-%d"), "Fever", "approved", "Approved by Head Doc"),
        ]
        cursor.executemany(
            "INSERT INTO staff_leaves (staff_id, leave_type, start_date, end_date, reason, status, reviewer_notes) VALUES (?,?,?,?,?,?,?)",
            leaves
        )


def seed_users_extended(cursor):
    """Seed 4 demo accounts if not already seeded."""
    user_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        from werkzeug.security import generate_password_hash
        hashed_pass = generate_password_hash("password123")
        demo_users = [
            ("head_doc", hashed_pass, "head_doctor", "Dr. Suresh Kumar (Head)", 1, None, None),
            ("doc_anita", hashed_pass, "doctor", "Dr. Anita Desai", 2, None, None),
            ("staff_nurse", hashed_pass, "staff", "Nurse Sarah", None, None, 1),
            ("patient_aarav", hashed_pass, "patient", "Aarav Sharma", None, 1, None),
        ]
        cursor.executemany(
            "INSERT INTO users (username, password_hash, role, display_name, doctor_id, patient_id, staff_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            demo_users
        )
        
        # Seed Patient Registrations
        # Nurse Sarah (user_id=3)
        pending_registrations = [
            ("Priya Patel", 32, "Female", "9876543212", "45 Park Street, Delhi", "O+", 3, "pending")
        ]
        cursor.executemany(
            "INSERT INTO patient_registrations (name, age, gender, phone, address, blood_group, requested_by_user_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            pending_registrations
        )


if __name__ == "__main__":
    create_tables()
    seed_demo_data()
    print("[OK] Database ready at:", DATABASE)
