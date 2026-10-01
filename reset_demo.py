"""
reset_demo.py
-------------
Resets the MALHAM SQLite database to a clean, fresh demo state.
Deletes malham.db if present, recreates all tables, and seeds demo data
for all modules:
  - Patients & Visits (with triage levels and statuses)
  - Doctors, Attendance, and Leave requests
  - Beds Management across all wards
  - Medicines Inventory & Stock log
  - Smart Prescriptions & Items
  - Reminders, Follow-ups, Check-ins, & Simulated WhatsApp message log
  - 4 Demo Users with hashed passwords (head_doc, doc_anita, staff_nurse, patient_aarav)

Usage:
    python reset_demo.py
"""

import os
import sys
import database


def reset_demo():
    db_path = database.DATABASE
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print(f"[RESET] Deleted existing database: {db_path}")
        except Exception as e:
            print(f"[WARNING] Could not delete {db_path}: {e}")

    print("[RESET] Recreating database schema and tables...")
    database.create_tables()

    print("[RESET] Seeding clean demo data for all modules & demo accounts...")
    database.seed_demo_data()

    print(f"\n[SUCCESS] MALHAM demo database successfully restored at:\n  {db_path}\n")


if __name__ == "__main__":
    reset_demo()
