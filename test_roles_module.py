"""
test_roles_module.py
--------------------
Unit tests for MALHAM Role-Based Access Control (RBAC) Module.
Runs test cases verifying authentication, authorization, role permissions,
leave approval restrictions, and patient privacy security.
"""

import unittest
import os
import sys
import tempfile
import sqlite3

# Import Flask app and DB helpers
import app as flask_app_module
from app import app
import database


class TestRBACModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up a test database with schema and demo users."""
        cls.orig_db = database.DATABASE
        cls.db_fd, cls.db_path = tempfile.mkstemp()
        database.DATABASE = cls.db_path
        flask_app_module.DATABASE = cls.db_path
        
        # Initialize tables and seed demo data
        database.create_tables()
        database.seed_demo_data()

        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        os.close(cls.db_fd)
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        database.DATABASE = cls.orig_db
        flask_app_module.DATABASE = cls.orig_db
        database.create_tables()
        database.seed_demo_data()

    def login(self, username, password):
        return self.client.post('/login', data=dict(
            username=username,
            password=password
        ), follow_redirects=True)

    def login_demo(self, demo_role):
        return self.client.post('/login', data=dict(
            demo_role=demo_role
        ), follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    # ── Test Cases ────────────────────────────────────────────────────

    def test_01_unauthenticated_redirect(self):
        """Unauthenticated requests to protected pages must redirect to /login."""
        self.logout()
        res = self.client.get('/', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.location)

        res_beds = self.client.get('/beds', follow_redirects=False)
        self.assertEqual(res_beds.status_code, 302)
        self.assertIn('/login', res_beds.location)

    def test_02_demo_logins(self):
        """Quick demo logins for all 4 roles should succeed and log in correct user."""
        # 1. Head Doctor
        res = self.login_demo('head_doctor')
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertIn('user_id', sess)

        # 2. Doctor
        res = self.login_demo('doctor')
        self.assertEqual(res.status_code, 200)

        # 3. Staff
        res = self.login_demo('staff')
        self.assertEqual(res.status_code, 200)

        # 4. Patient
        res = self.login_demo('patient')
        self.assertEqual(res.status_code, 200)

    def test_03_head_doctor_permissions(self):
        """Head doctor should have full access to all sections and leave approvals."""
        self.login_demo('head_doctor')

        # Dashboard, Patients, Beds, Doctors, Medicines, Prescriptions, Follow-ups
        for route in ['/', '/patients', '/beds', '/doctors', '/medicines', '/prescriptions', '/followups']:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f"Head doctor should access {route}")

        # Head doctor can view leaves tab
        res_leaves = self.client.get('/doctors?tab=leaves')
        self.assertEqual(res_leaves.status_code, 200)

        # Head doctor can approve a leave
        res_approve = self.client.post('/doctors/leave/2/action', data=dict(action='approve'), follow_redirects=True)
        self.assertEqual(res_approve.status_code, 200)

    def test_04_doctor_permissions(self):
        """Regular doctor can access medical modules, request leave, but cannot approve leave."""
        self.login_demo('doctor')

        # Allowed routes
        for route in ['/', '/patients', '/beds', '/doctors', '/medicines', '/prescriptions', '/followups', '/prescriptions/new']:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f"Doctor should access {route}")

        # Doctor attempting to approve leave must get 403
        res_approve = self.client.post('/doctors/leave/3/action', data=dict(action='reject'))
        self.assertEqual(res_approve.status_code, 403)

    def test_05_staff_permissions(self):
        """Staff can manage roster/attendance, beds, medicines, but cannot create prescriptions or see leaves."""
        self.login_demo('staff')

        # Allowed routes
        for route in ['/', '/patients', '/beds', '/doctors', '/medicines', '/prescriptions', '/followups']:
            res = self.client.get(route)
            self.assertEqual(res.status_code, 200, f"Staff should access {route}")

        # Staff cannot access new prescription form (403)
        res_new_rx = self.client.get('/prescriptions/new')
        self.assertEqual(res_new_rx.status_code, 403)

        # Staff cannot access leave approvals tab (403)
        res_leaves = self.client.get('/doctors?tab=leaves')
        self.assertEqual(res_leaves.status_code, 403)

    def test_06_patient_privacy_enforcement(self):
        """Patient can access ONLY their own profile and prescription; URL tampering gives 403."""
        self.login_demo('patient')

        # Patient (aarav = patient_id 1) can access /patients/1
        res_own_profile = self.client.get('/patients/1')
        self.assertEqual(res_own_profile.status_code, 200)

        # Patient attempting to access another patient's profile (/patients/2) MUST get 403 Forbidden
        res_other_profile = self.client.get('/patients/2')
        self.assertEqual(res_other_profile.status_code, 403)

        # Patient attempting to access dashboard or beds MUST get 403 Forbidden
        res_dashboard = self.client.get('/')
        self.assertEqual(res_dashboard.status_code, 403)

        res_beds = self.client.get('/beds')
        self.assertEqual(res_beds.status_code, 403)

        res_doctors = self.client.get('/doctors')
        self.assertEqual(res_doctors.status_code, 403)

        res_medicines = self.client.get('/medicines')
        self.assertEqual(res_medicines.status_code, 403)

        # Patient can access their own prescription (RX-2001 is for patient_id 1 -> rx_id 1)
        res_own_rx = self.client.get('/prescriptions/1')
        self.assertEqual(res_own_rx.status_code, 200)

        # Patient attempting to access another patient's prescription (RX-2002 is for patient_id 3 -> rx_id 2) MUST get 403
        res_other_rx = self.client.get('/prescriptions/2')
        self.assertEqual(res_other_rx.status_code, 403)


if __name__ == '__main__':
    unittest.main()
