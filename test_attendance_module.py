import unittest
from datetime import datetime, timedelta
from app import app, query_db, execute_db, auto_process_attendance, get_doctor_shift_info, SHIFT_STARTS, ATTENDANCE_WINDOW_MINUTES
import app as flask_app
from database import get_db_connection

class TestAttendanceModule(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        flask_app.ATTENDANCE_DEMO_MODE = False
        
        # Clear specific tables
        execute_db("DELETE FROM attendance")
        execute_db("DELETE FROM activity_log")
        execute_db("DELETE FROM doctor_leaves")
        
        # We assume doc 2 is dr_smith (morning) and doc 3 is dr_jones (night)
        execute_db("UPDATE doctors SET shift='morning' WHERE id=2")
        execute_db("UPDATE doctors SET shift='night' WHERE id=3")
        
        # Demo users
        self.head_doctor = self.login('head_doctor')
        self.doctor = self.login('doctor')
        self.staff = self.login('staff')
        
    def login(self, role):
        client = app.test_client()
        client.post('/login', data={'demo_role': role})
        return client
        
    def test_window_logic(self):
        # Doc 2 is morning (08:00). 
        # Test 07:59 (before window)
        now_before = datetime(2026, 1, 1, 7, 59, 0)
        info = get_doctor_shift_info(2, now=now_before)
        self.assertFalse(info['window_open'])
        
        # Test 08:15 (inside window)
        now_inside = datetime(2026, 1, 1, 8, 15, 0)
        info = get_doctor_shift_info(2, now=now_inside)
        self.assertTrue(info['window_open'])
        
        # Test 08:31 (after window)
        now_after = datetime(2026, 1, 1, 8, 31, 0)
        info = get_doctor_shift_info(2, now=now_after)
        self.assertFalse(info['window_open'])
        
    def test_night_shift_logic(self):
        # Doc 3 is night (20:00). Window is 20:00 to 20:30.
        # Test crossing midnight? Actually, the window is 20:00 to 20:30 on the SAME day.
        # Wait, the prompt says "night shift crossing midnight correctly".
        # If the check-in is 20:00, the shift itself might cross midnight, but the check-in window (20:00 to 20:30) doesn't cross midnight.
        # But if the doctor checks their info AT 01:00 AM, `now.hour < 12`, so shift_start_time goes to YESTERDAY.
        # This handles viewing the status correctly after midnight.
        now_am = datetime(2026, 1, 2, 1, 0, 0) # 1 AM
        info = get_doctor_shift_info(3, now=now_am)
        self.assertFalse(info['window_open'])
        self.assertIn("closed", info['status_text'].lower())
        
    def test_auto_absent_after_window(self):
        # Simulate time after morning shift window
        now = datetime(2026, 1, 1, 9, 0, 0)
        flask_app.ATTENDANCE_DEMO_MODE = False
        auto_process_attendance(now=now)
        
        # Check doc 2 attendance
        att = query_db("SELECT * FROM attendance WHERE doctor_id=2 AND date='2026-01-01'", one=True)
        self.assertIsNotNone(att)
        self.assertEqual(att['status'], 'absent')
        self.assertIn('did not check in', att['notes'])
        
        # Check no duplicates on repeated calls
        auto_process_attendance(now=now)
        count = query_db("SELECT COUNT(*) as c FROM attendance WHERE doctor_id=2 AND date='2026-01-01'", one=True)['c']
        self.assertEqual(count, 1)
        
    def test_approved_leave_becomes_on_leave(self):
        # Add approved leave for doc 2
        execute_db(
            "INSERT INTO doctor_leaves (doctor_id, start_date, end_date, reason, status) VALUES (2, '2026-01-01', '2026-01-01', 'sick', 'approved')"
        )
        now = datetime(2026, 1, 1, 9, 0, 0)
        flask_app.ATTENDANCE_DEMO_MODE = False
        auto_process_attendance(now=now)
        
        att = query_db("SELECT * FROM attendance WHERE doctor_id=2 AND date='2026-01-01'", one=True)
        self.assertEqual(att['status'], 'on-leave')
        
    def test_demo_mode(self):
        flask_app.ATTENDANCE_DEMO_MODE = True
        now = datetime(2026, 1, 1, 15, 0, 0) # After morning window
        
        info = get_doctor_shift_info(2, now=now)
        self.assertTrue(info['window_open']) # Demo mode ignores window
        
        auto_process_attendance(now=now)
        att = query_db("SELECT * FROM attendance WHERE doctor_id=2 AND date='2026-01-01'", one=True)
        self.assertFalse(att) # Demo mode disables auto-absent
        
    def test_head_doctor_override(self):
        # Head doctor marks attendance for doc 2
        resp = self.head_doctor.post('/doctors/attendance/mark', data={
            'doctor_id': '2',
            'date': '2026-01-01',
            'status': 'present',
            'notes': 'Test override'
        })
        self.assertEqual(resp.status_code, 302)
        
        att = query_db("SELECT * FROM attendance WHERE doctor_id=2 AND date='2026-01-01'", one=True)
        self.assertEqual(att['status'], 'present')
        self.assertIn('Updated by head doctor', att['notes'])
        
    def test_staff_cannot_mark(self):
        resp = self.staff.post('/doctors/attendance/mark', data={
            'doctor_id': '2',
            'date': '2026-01-01',
            'status': 'present',
            'notes': 'Staff hacking'
        })
        self.assertEqual(resp.status_code, 403)
        
if __name__ == '__main__':
    unittest.main()
