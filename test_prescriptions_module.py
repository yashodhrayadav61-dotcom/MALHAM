"""
test_prescriptions_module.py
----------------------------
Test suite for Smart Prescriptions module and pattern validation logic in MALHAM.
"""

import sys
import unittest
from prescription_utils import validate_dosage_pattern, format_dosage_slots, generate_dose_schedule_rows
from app import app
from database import get_db_connection, create_tables, seed_demo_data

class TestPrescriptionUtils(unittest.TestCase):

    def test_validate_dosage_pattern(self):
        # Valid patterns
        valid, vals = validate_dosage_pattern("1-0-1")
        self.assertTrue(valid)
        self.assertEqual(vals, [1.0, 0.0, 1.0])

        valid, vals = validate_dosage_pattern("0.5-0-1")
        self.assertTrue(valid)
        self.assertEqual(vals, [0.5, 0.0, 1.0])

        valid, vals = validate_dosage_pattern("1/2-1-1/2")
        self.assertTrue(valid)
        self.assertEqual(vals, [0.5, 1.0, 0.5])

        # Invalid patterns
        valid, _ = validate_dosage_pattern("abc")
        self.assertFalse(valid)

        valid, _ = validate_dosage_pattern("1-1")
        self.assertFalse(valid)

        valid, _ = validate_dosage_pattern("1-0-1-1")
        self.assertFalse(valid)

        valid, _ = validate_dosage_pattern("1-a-1")
        self.assertFalse(valid)

    def test_format_dosage_slots(self):
        slots = format_dosage_slots("1-0-1", "tablet")
        self.assertEqual(len(slots), 3)
        self.assertEqual(slots[0]["label"], "Morning")
        self.assertTrue(slots[0]["active"])
        self.assertEqual(slots[0]["readable_en"], "1 tablet")

        self.assertEqual(slots[1]["label"], "Afternoon")
        self.assertFalse(slots[1]["active"])
        self.assertEqual(slots[1]["readable_en"], "No tablet")

        self.assertEqual(slots[2]["label"], "Night")
        self.assertTrue(slots[2]["active"])
        self.assertEqual(slots[2]["readable_en"], "1 tablet")

    def test_generate_dose_schedule_rows(self):
        rows = generate_dose_schedule_rows(101, "1-0-1", "tablet", "2026-10-01", 5)
        # Should generate 2 active slots (Morning & Night)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "Morning")
        self.assertEqual(rows[0][2], "08:00")
        self.assertEqual(rows[0][3], 1.0)
        self.assertEqual(rows[1][1], "Night")
        self.assertEqual(rows[1][2], "20:00")
        self.assertEqual(rows[1][3], 1.0)


class TestFlaskRoutes(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        self.app.post('/login', data=dict(demo_role='head_doctor'))

    def test_dashboard_route(self):
        res = self.app.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Active Prescriptions', res.data)

    def test_prescriptions_list_route(self):
        res = self.app.get('/prescriptions')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Prescriptions Directory', res.data)

    def test_prescriptions_search_and_filter(self):
        res = self.app.get('/prescriptions?q=RX-2001')
        self.assertEqual(res.status_code, 200)

        res_filter = self.app.get('/prescriptions?status=active')
        self.assertEqual(res_filter.status_code, 200)

    def test_new_prescription_route(self):
        res = self.app.get('/prescriptions/new')
        self.assertEqual(res.status_code, 200)

        res_patient = self.app.get('/prescriptions/new?patient_id=1')
        self.assertEqual(res_patient.status_code, 200)

    def test_view_prescription_route(self):
        res = self.app.get('/prescriptions/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'MALHAM HEALTHCARE', res.data)
        self.assertIn(b'Follow your doctor', res.data)

    def test_invalid_pattern_rejection(self):
        # Post with invalid pattern 'abc' via JSON -> expecting 400
        payload = {
            "patient_id": 1,
            "doctor_id": 1,
            "medicine_id[]": ["1"],
            "dosage_pattern[]": ["abc"]
        }
        res = self.app.post('/prescriptions/add', json=payload)
        self.assertEqual(res.status_code, 400)

    def test_add_prescription_and_dose_schedule(self):
        form_data = {
            "patient_id": "1",
            "doctor_id": "1",
            "diagnosis_note": "Test Diagnosis",
            "general_advice": "Test Advice",
            "follow_up_date": "2026-10-15",
            "medicine_id[]": ["1", "3"],
            "dosage_pattern[]": ["1-0-1", "0.5-0-1"],
            "food_timing[]": ["after food", "before food"],
            "duration_days[]": ["5", "3"],
            "special_instructions[]": ["With water", "Before sleep"]
        }
        res = self.app.post('/prescriptions/add', data=form_data)
        self.assertEqual(res.status_code, 302)  # Should redirect to view_prescription

        # Check in DB that prescription and dose_schedule rows were created
        conn = get_db_connection()
        latest_rx = conn.execute("SELECT * FROM prescriptions ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(latest_rx)
        self.assertEqual(latest_rx["diagnosis_note"], "Test Diagnosis")

        items = conn.execute("SELECT * FROM prescription_items WHERE prescription_id=?", (latest_rx["id"],)).fetchall()
        self.assertEqual(len(items), 2)

        item1_id = items[0]["id"]
        schedules = conn.execute("SELECT * FROM dose_schedule WHERE prescription_item_id=?", (item1_id,)).fetchall()
        self.assertTrue(len(schedules) > 0)
        conn.close()

    def test_update_prescription_status(self):
        res = self.app.post('/prescriptions/1/status', data={"status": "completed"})
        self.assertEqual(res.status_code, 302)

        conn = get_db_connection()
        rx = conn.execute("SELECT status FROM prescriptions WHERE id=1").fetchone()
        self.assertEqual(rx["status"], "completed")
        conn.close()

    def test_patient_profile_prescriptions(self):
        res = self.app.get('/patients/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Prescriptions History', res.data)

    def test_other_modules_unbroken(self):
        for route in ['/patients', '/beds', '/doctors', '/medicines']:
            res = self.app.get(route)
            self.assertEqual(res.status_code, 200, f"Route {route} broken!")


if __name__ == '__main__':
    unittest.main()
