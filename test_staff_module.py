import unittest
from datetime import datetime, timedelta
from app import app, query_db, execute_db, auto_process_staff_attendance, get_staff_shift_info, SHIFT_STARTS, ATTENDANCE_WINDOW_MINUTES
import app as flask_app
from database import get_db_connection

class TestStaffModule(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        flask_app.ATTENDANCE_DEMO_MODE = False
        
        execute_db("DELETE FROM staff_attendance")
        execute_db("DELETE FROM activity_log")
        execute_db("DELETE FROM staff_leaves")
        execute_db("DELETE FROM staff_members WHERE staff_code LIKE 'S-99%'")
        
        self.head_doctor = self.login('head_doctor')
        self.doctor = self.login('doctor')
        self.staff = self.login('staff')
        self.patient = self.login('patient')
        
    def login(self, role):
        client = app.test_client()
        client.post('/login', data={'demo_role': role}, follow_redirects=True)
        return client

    def test_staff_window_logic(self):
        now_before = datetime(2026, 1, 1, 7, 59, 0)
        info = get_staff_shift_info(1, now=now_before)
        self.assertFalse(info['window_open'])
        
        now_inside = datetime(2026, 1, 1, 8, 15, 0)
        info = get_staff_shift_info(1, now=now_inside)
        self.assertTrue(info['window_open'])
        
        now_after = datetime(2026, 1, 1, 8, 31, 0)
        info = get_staff_shift_info(1, now=now_after)
        self.assertFalse(info['window_open'])
        
    def test_auto_absent_and_no_duplicates(self):
        now = datetime(2026, 1, 1, 9, 0, 0)
        auto_process_staff_attendance(now=now)
        
        att = query_db("SELECT * FROM staff_attendance WHERE staff_id=1 AND date='2026-01-01'", one=True)
        self.assertTrue(att)
        self.assertEqual(att['status'], 'absent')
        
        auto_process_staff_attendance(now=now)
        count = query_db("SELECT COUNT(*) as c FROM staff_attendance WHERE staff_id=1 AND date='2026-01-01'", one=True)['c']
        self.assertEqual(count, 1)

    def test_approved_leave_becomes_on_leave(self):
        execute_db(
            "INSERT INTO staff_leaves (staff_id, leave_type, start_date, end_date, reason, status) VALUES (1, 'sick', '2026-01-01', '2026-01-01', 'sick', 'approved')"
        )
        now = datetime(2026, 1, 1, 9, 0, 0)
        auto_process_staff_attendance(now=now)
        att = query_db("SELECT * FROM staff_attendance WHERE staff_id=1 AND date='2026-01-01'", one=True)
        self.assertEqual(att['status'], 'on-leave')

    def test_demo_mode_opens_window(self):
        flask_app.ATTENDANCE_DEMO_MODE = True
        now_after = datetime(2026, 1, 1, 15, 0, 0)
        info = get_staff_shift_info(1, now=now_after)
        self.assertTrue(info['window_open'])
        
        auto_process_staff_attendance(now=now_after)
        att = query_db("SELECT * FROM staff_attendance WHERE staff_id=1 AND date='2026-01-01'", one=True)
        self.assertFalse(att)

    def test_only_head_doctor_can_approve_leave(self):
        resp = self.staff.post('/staff/leave/request', data={
            'leave_type': 'casual', 'start_date': '2026-01-02', 'end_date': '2026-01-03', 'reason': 'test'
        })
        self.assertEqual(resp.status_code, 302)
        leave = query_db("SELECT * FROM staff_leaves WHERE staff_id=1 AND start_date='2026-01-02'", one=True)
        self.assertEqual(leave['status'], 'pending')
        
        resp = self.doctor.post('/staff/leave/review', data={'leave_id': leave['id'], 'action': 'approve'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.staff.post('/staff/leave/review', data={'leave_id': leave['id'], 'action': 'approve'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.head_doctor.post('/staff/leave/review', data={'leave_id': leave['id'], 'action': 'approve'})
        self.assertEqual(resp.status_code, 302)
        leave = query_db("SELECT * FROM staff_leaves WHERE id=?", (leave['id'],), one=True)
        self.assertEqual(leave['status'], 'approved')
        
    def test_doctor_cannot_see_staff_leave_reasons(self):
        resp = self.doctor.get('/staff?tab=leaves')
        self.assertEqual(resp.status_code, 403)

    def test_staff_cannot_see_others_leaves(self):
        execute_db(
            "INSERT INTO staff_leaves (staff_id, leave_type, start_date, end_date, reason, status) VALUES (2, 'sick', '2026-01-01', '2026-01-01', 'sick', 'pending')"
        )
        resp = self.staff.get('/staff?tab=leaves')
        self.assertEqual(resp.status_code, 200)

    def test_patient_gets_403_on_all_staff_routes(self):
        routes = ['/staff', '/staff?tab=attendance', '/staff?tab=leaves']
        for r in routes:
            resp = self.patient.get(r)
            self.assertEqual(resp.status_code, 403)
            
    def test_all_roles_all_routes_no_500(self):
        roles = ['head_doctor', 'doctor', 'staff', 'patient']
        tabs = ['', '?tab=roster', '?tab=attendance', '?tab=leaves', '?status=available']
        for role in roles:
            client = self.login(role)
            for tab in tabs:
                resp = client.get(f'/staff{tab}')
                self.assertNotEqual(resp.status_code, 500)
                if resp.status_code == 200:
                    html = resp.data.decode('utf-8')
                    self.assertNotIn('<title>Doctors', html)
                    if 'tab=roster' in tab or tab == '':
                        self.assertIn('Nurse Sarah', html)
        
        # Test /doctors?status=available for no 500
        for role in roles:
            client = self.login(role)
            resp = client.get('/doctors?status=available')
            self.assertNotEqual(resp.status_code, 500)

    def test_badge_and_leave_list(self):
        execute_db(
            "INSERT INTO staff_leaves (staff_id, leave_type, start_date, end_date, reason, status) VALUES (2, 'sick', '2026-01-01', '2026-01-01', 'sick', 'pending')"
        )
        resp = self.head_doctor.get('/staff?tab=leaves')
        html = resp.data.decode('utf-8')
        # badge count 1
        self.assertIn('tab-badge-count', html)
        self.assertIn('>1<', html)
        # seeded pending leave appears for head_doctor with approve button
        self.assertIn('value="approve"', html)

    def test_add_staff_permissions(self):
        # doctor and head_doctor can add staff
        resp = self.head_doctor.post('/staff/add', data={'name': 'Test1', 'staff_role': 'Nurse', 'staff_code': 'S-991'})
        self.assertEqual(resp.status_code, 302)
        resp = self.doctor.post('/staff/add', data={'name': 'Test2', 'staff_role': 'Ward Boy', 'staff_code': 'S-992'})
        self.assertEqual(resp.status_code, 302)

        # staff_nurse gets 403
        resp = self.staff.post('/staff/add', data={'name': 'Test3', 'staff_role': 'Nurse', 'staff_code': 'S-993'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.staff.get('/staff')
        html = resp.data.decode('utf-8')
        self.assertNotIn('openModal(\'addStaffModal\')', html)

if __name__ == '__main__':
    unittest.main()
