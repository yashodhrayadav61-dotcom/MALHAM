"""
test_smoke_all.py
-----------------
Comprehensive Smoke Test & End-to-End Flow Suite for MALHAM.

1. Resets the database to clean demo state.
2. For each of the 4 demo roles (head_doctor, doctor, staff, patient):
   - Logs in.
   - Requests every GET route in the application (substituting real IDs).
   - Asserts NO route returns 500 (Server Error).
   - Verifies role-based authorization (200 OK vs 403 Forbidden).
3. Executes a complete End-to-End (E2E) workflow:
   - Register a new patient
   - Log an emergency visit
   - Assign an available bed
   - Create a smart prescription
   - Generate automated medication reminders
   - Dispatch due reminders via simulated WhatsApp service
   - Assert new rows exist in message_log table.

Usage:
    python -m unittest test_smoke_all.py
"""

import os
import unittest
from app import app
from database import get_db_connection, create_tables, seed_demo_data
import reset_demo


class TestSmokeAllRolesAndE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Reset database to clean demo state at start of test class."""
        reset_demo.reset_demo()

    def setUp(self):
        """Configure test client for each test."""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'smoke_test_secret_key'
        self.client = app.test_client()

    def login_demo(self, demo_role):
        """Helper to submit quick demo login button."""
        return self.client.post('/login', data=dict(
            demo_role=demo_role
        ), follow_redirects=True)

    def get_first_med_id(self):
        conn = get_db_connection()
        row = conn.execute("SELECT id FROM medicines ORDER BY id ASC LIMIT 1").fetchone()
        conn.close()
        return row['id'] if row else 9

    # ── Role GET Route Smoke Tests ────────────────────────────────────

    def test_head_doctor_all_get_routes(self):
        """Head doctor should have access to all system GET routes without 500s."""
        self.login_demo('head_doctor')
        med_id = self.get_first_med_id()
        
        routes = [
            '/',
            '/patients',
            '/patients/1',
            '/patients/2',
            '/beds',
            '/doctors',
            '/medicines',
            f'/medicines/{med_id}',
            '/prescriptions',
            '/prescriptions/new',
            '/prescriptions/1',
            '/followups',
            '/followups/adherence',
            '/api/dashboard-stats',
        ]

        for route in routes:
            response = self.client.get(route)
            self.assertNotEqual(response.status_code, 500, f"Route {route} returned 500 for head_doctor!")
            self.assertEqual(response.status_code, 200, f"Route {route} expected 200 for head_doctor, got {response.status_code}")

    def test_doctor_all_get_routes(self):
        """Doctor role should access clinical & operational GET routes without 500s."""
        self.login_demo('doctor')
        med_id = self.get_first_med_id()

        routes = [
            '/',
            '/patients',
            '/patients/1',
            '/patients/2',
            '/beds',
            '/doctors',
            '/medicines',
            f'/medicines/{med_id}',
            '/prescriptions',
            '/prescriptions/new',
            '/prescriptions/1',
            '/followups',
            '/followups/adherence',
            '/api/dashboard-stats',
        ]

        for route in routes:
            response = self.client.get(route)
            self.assertNotEqual(response.status_code, 500, f"Route {route} returned 500 for doctor!")
            self.assertEqual(response.status_code, 200, f"Route {route} expected 200 for doctor, got {response.status_code}")

    def test_staff_all_get_routes(self):
        """Staff/Nurse role should access staff GET routes without 500s."""
        self.login_demo('staff')
        med_id = self.get_first_med_id()

        routes = [
            '/',
            '/patients',
            '/patients/1',
            '/patients/2',
            '/beds',
            '/doctors',
            '/medicines',
            f'/medicines/{med_id}',
            '/prescriptions',
            '/prescriptions/1',
            '/followups',
            '/followups/adherence',
            '/api/dashboard-stats',
        ]

        for route in routes:
            response = self.client.get(route)
            self.assertNotEqual(response.status_code, 500, f"Route {route} returned 500 for staff!")
            self.assertEqual(response.status_code, 200, f"Route {route} expected 200 for staff, got {response.status_code}")

        # Verify doctor-only routes return 403 Forbidden for staff (never 500)
        doctor_only_routes = ['/prescriptions/new']
        for route in doctor_only_routes:
            response = self.client.get(route)
            self.assertNotEqual(response.status_code, 500, f"Route {route} returned 500 for staff!")
            self.assertEqual(response.status_code, 403, f"Route {route} expected 403 for staff, got {response.status_code}")

    def test_patient_all_get_routes_permissions(self):
        """Patient role should get 403 on staff/admin pages and 200 on their own profile."""
        self.login_demo('patient')
        med_id = self.get_first_med_id()

        # Allowed routes for Aarav Sharma (patient_id=1)
        allowed_routes = [
            '/patients/1',
            '/prescriptions/1',
        ]
        for route in allowed_routes:
            response = self.client.get(route)
            self.assertNotEqual(response.status_code, 500, f"Route {route} returned 500 for patient!")
            self.assertEqual(response.status_code, 200, f"Route {route} expected 200 for patient, got {response.status_code}")

        # Restricted routes (should return 403 Forbidden, NEVER 500)
        restricted_routes = [
            '/',
            '/patients',
            '/patients/2',  # other patient's profile
            '/beds',
            '/doctors',
            '/medicines',
            f'/medicines/{med_id}',
            '/prescriptions',
            '/prescriptions/new',
            '/followups',
            '/followups/adherence',
            '/api/dashboard-stats',
        ]

        for route in restricted_routes:
            response = self.client.get(route)
            self.assertNotEqual(response.status_code, 500, f"Route {route} returned 500 for patient!")
            self.assertEqual(response.status_code, 403, f"Route {route} expected 403 Forbidden for patient, got {response.status_code}")

    # ── End-to-End Workflow Test ──────────────────────────────────────

    def test_full_e2e_clinical_workflow(self):
        """
        Complete E2E Flow:
        Register Patient -> Log Visit -> Assign Bed -> Create Prescription ->
        Generate Reminders -> Send Due Reminders -> Assert Message Log.
        """
        # Login as Head Doctor
        login_res = self.login_demo('head_doctor')
        self.assertEqual(login_res.status_code, 200)

        conn = get_db_connection()
        med_id = self.get_first_med_id()

        # Step 1: Register Patient
        reg_res = self.client.post('/patients/add', data=dict(
            name='E2E Smoke Patient',
            age='42',
            gender='Female',
            phone='9887766554',
            blood_group='O+',
            status='emergency',
            department='Emergency',
            address='123 Hackathon Way'
        ), follow_redirects=True)
        self.assertEqual(reg_res.status_code, 200)

        new_patient = conn.execute("SELECT * FROM patients WHERE name='E2E Smoke Patient'").fetchone()
        self.assertIsNotNone(new_patient, "E2E Registered patient not found in database!")
        p_id = new_patient['id']

        # Step 2: Log Visit
        visit_res = self.client.post('/patients/visit/add', data=dict(
            patient_id=p_id,
            doctor_id=1,
            visit_type='emergency',
            reason='Acute Chest Discomfort',
            triage_level='critical',
            notes='Admitted via Triage Bay 1'
        ), follow_redirects=True)
        self.assertEqual(visit_res.status_code, 200)

        new_visit = conn.execute("SELECT * FROM visits WHERE patient_id=? ORDER BY id DESC LIMIT 1", (p_id,)).fetchone()
        self.assertIsNotNone(new_visit, "E2E Visit record not found in database!")
        v_id = new_visit['id']

        # Step 3: Assign Bed (find an available bed first)
        avail_bed = conn.execute("SELECT * FROM beds WHERE status='available' LIMIT 1").fetchone()
        self.assertIsNotNone(avail_bed, "No available bed found for assignment!")
        bed_id = avail_bed['id']

        assign_res = self.client.post(f'/beds/{bed_id}/assign', data=dict(
            patient_id=p_id
        ), follow_redirects=True)
        self.assertEqual(assign_res.status_code, 200)

        assigned_bed = conn.execute("SELECT * FROM beds WHERE id=?", (bed_id,)).fetchone()
        self.assertEqual(assigned_bed['status'], 'occupied')
        self.assertEqual(assigned_bed['patient_id'], p_id)

        # Step 4: Create Prescription (using array fields medicine_id[], dosage_pattern[], etc.)
        rx_res = self.client.post('/prescriptions/add', data={
            'patient_id': str(p_id),
            'doctor_id': '1',
            'visit_id': str(v_id),
            'diagnosis_note': 'Acute Angina Sub-category 2',
            'general_advice': 'Bed rest, continuous oxygen monitoring',
            'follow_up_date': '2026-10-15',
            'medicine_id[]': [str(med_id)],
            'dosage_pattern[]': ['1-0-1'],
            'food_timing[]': ['after food'],
            'duration_days[]': ['5'],
            'special_instructions[]': ['Take after meals']
        }, follow_redirects=True)
        self.assertEqual(rx_res.status_code, 200)

        new_rx = conn.execute("SELECT * FROM prescriptions WHERE patient_id=? ORDER BY id DESC LIMIT 1", (p_id,)).fetchone()
        self.assertIsNotNone(new_rx, "E2E Prescription record not found!")
        rx_id = new_rx['id']

        # Step 5: Generate Reminders
        gen_res = self.client.post(f'/followups/generate/{rx_id}', follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)

        reminders_count = conn.execute("SELECT COUNT(*) FROM reminders WHERE patient_id=?", (p_id,)).fetchone()[0]
        self.assertGreater(reminders_count, 0, "No reminders generated for prescription!")

        # Step 6: Check message_log initial count
        initial_log_count = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]

        # Step 7: Send Due Reminders
        send_res = self.client.post('/reminders/send-due', follow_redirects=True)
        self.assertEqual(send_res.status_code, 200)

        # Step 8: Assert message_log has new rows
        new_log_count = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]
        self.assertGreater(new_log_count, initial_log_count, "message_log count did not increase after send-due!")

        conn.close()


if __name__ == '__main__':
    unittest.main()
