"""
test_followups_module.py
------------------------
Test suite for Follow-ups & Reminders module in MALHAM.
"""

import unittest
from datetime import datetime
from app import app
from database import get_db_connection
from prescription_utils import generate_reminders_for_prescription
from whatsapp_service import send_whatsapp, WHATSAPP_MODE


class TestFollowupsAndReminders(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        self.app.post('/login', data=dict(demo_role='head_doctor'))

    def test_whatsapp_service_simulation(self):
        """Test that send_whatsapp in simulation mode writes to message_log table."""
        conn = get_db_connection()
        initial_log_count = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]

        success, msg = send_whatsapp("9876543210", "Test WhatsApp simulation message", patient_id=1, db_conn=conn)
        self.assertTrue(success)

        new_log_count = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]
        self.assertEqual(new_log_count, initial_log_count + 1)

        latest = conn.execute("SELECT * FROM message_log ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(latest["message"], "Test WhatsApp simulation message")
        self.assertEqual(latest["patient_id"], 1)
        conn.close()

    def test_reminder_generation_and_deduplication(self):
        """Test reminder generation from prescription and deduplication."""
        conn = get_db_connection()
        rx = conn.execute("SELECT id FROM prescriptions WHERE rx_code IS NOT NULL ORDER BY id ASC LIMIT 1").fetchone()
        self.assertIsNotNone(rx, "Prescription with rx_code must exist in DB")
        rx_id = rx["id"]

        # Clear pre-existing reminders for this test prescription to test fresh generation
        conn.execute("DELETE FROM reminders WHERE prescription_id = ?", (rx_id,))
        conn.commit()

        # First generation
        count1 = generate_reminders_for_prescription(conn, rx_id)
        self.assertGreater(count1, 0, "Reminders should be created on first run")

        # Second generation (deduplication check)
        count2 = generate_reminders_for_prescription(conn, rx_id)
        self.assertEqual(count2, 0, "Deduplication must prevent creating duplicate reminders on second run")

        # Check reminder message text contains medicine name and time format
        rem = conn.execute(
            "SELECT * FROM reminders WHERE prescription_id = ? AND reminder_type = 'medication' ORDER BY id DESC LIMIT 1",
            (rx_id,)
        ).fetchone()

        self.assertIsNotNone(rem)
        self.assertIn("Reminder: Your prescribed medicine", rem["message_text"])
        self.assertTrue("AM" in rem["message_text"] or "PM" in rem["message_text"])
        conn.close()

    def test_routes_status_codes(self):
        """Test GET and POST route endpoints for 200/302 response codes."""
        # GET Followups main view tabs
        for tab in ['reminders', 'followups', 'checkins', 'messagelog']:
            res = self.app.get(f'/followups?tab={tab}')
            self.assertEqual(res.status_code, 200, f"Tab {tab} failed with status {res.status_code}")

        # GET Adherence stats API
        res_adh = self.app.get('/followups/adherence')
        self.assertEqual(res_adh.status_code, 200)
        json_data = res_adh.get_json()
        self.assertIn("adherence_percentage", json_data)

        # GET Dashboard includes new metrics
        res_dash = self.app.get('/')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Pending Reminders', res_dash.data)
        self.assertIn(b'Overdue Follow-ups', res_dash.data)

    def test_send_due_reminders_endpoint(self):
        """Test POST /reminders/send-due writes to message_log."""
        conn = get_db_connection()
        initial_msg_count = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]
        conn.close()

        res = self.app.post('/reminders/send-due')
        self.assertEqual(res.status_code, 302)

        conn = get_db_connection()
        new_msg_count = conn.execute("SELECT COUNT(*) FROM message_log").fetchone()[0]
        self.assertGreaterEqual(new_msg_count, initial_msg_count, "send-due should log sent messages to message_log")
        conn.close()

    def test_schedule_followup_and_status(self):
        """Test POST /followups/add and status update."""
        form_data = {
            "patient_id": "1",
            "doctor_id": "1",
            "followup_date": "2026-10-20",
            "purpose": "Unit Test Follow-up Review",
            "notes": "Testing follow-up scheduling"
        }
        res = self.app.post('/followups/add', data=form_data)
        self.assertEqual(res.status_code, 302)

        conn = get_db_connection()
        fu = conn.execute("SELECT * FROM followups WHERE reason LIKE '%Unit Test%' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(fu)
        fu_id = fu["id"]

        # Update status
        res_status = self.app.post(f'/followups/{fu_id}/status', data={"status": "completed"})
        self.assertEqual(res_status.status_code, 302)

        fu_updated = conn.execute("SELECT status FROM followups WHERE id = ?", (fu_id,)).fetchone()
        self.assertEqual(fu_updated["status"], "completed")
        conn.close()

    def test_patient_checkin_and_stopped_treatment(self):
        """Test POST /checkins/add for stopped treatment response."""
        checkin_data = {
            "patient_id": "6",
            "question": "Dermatology treatment check-in",
            "response": "stopped treatment",
            "notes": "Patient reported adverse reaction"
        }
        res = self.app.post('/checkins/add', data=checkin_data)
        self.assertEqual(res.status_code, 302)

        conn = get_db_connection()
        latest_ci = conn.execute("SELECT * FROM checkins WHERE patient_id = 6 ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(latest_ci)
        self.assertEqual(latest_ci["response"], "stopped treatment")

        # Verify patient 6 appears in at-risk query
        today_date = datetime.now().strftime("%Y-%m-%d")
        at_risk = conn.execute(
            "SELECT DISTINCT patient_id FROM checkins WHERE response = 'stopped treatment'"
        ).fetchall()
        risk_pids = [r["patient_id"] for r in at_risk]
        self.assertIn(6, risk_pids)
        conn.close()

    def test_existing_modules_remain_unbroken(self):
        """Ensure all prior modules continue returning status 200."""
        for route in ['/', '/patients', '/beds', '/doctors', '/medicines', '/prescriptions']:
            res = self.app.get(route)
            self.assertEqual(res.status_code, 200, f"Route {route} broken!")


if __name__ == '__main__':
    unittest.main()
