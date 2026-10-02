import unittest
from app import app, execute_db, query_db
from database import get_db_connection

class TestPermissionsModule(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        
        # Clean up tables we'll insert into
        execute_db("DELETE FROM patient_registrations")
        execute_db("DELETE FROM patients WHERE name LIKE 'Test%'")
        execute_db("DELETE FROM beds WHERE bed_number LIKE 'TEST%'")
        execute_db("DELETE FROM staff_members WHERE staff_code LIKE 'TEST%'")
        execute_db("DELETE FROM doctors WHERE name LIKE 'Test%'")
        
        self.head_doctor = self.login('head_doctor')
        self.doctor = self.login('doctor')
        self.staff = self.login('staff')
        self.patient = self.login('patient')
        
    def login(self, role):
        client = app.test_client()
        client.post('/login', data={'demo_role': role}, follow_redirects=True)
        return client

    def test_post_doctors_add_permissions(self):
        resp = self.head_doctor.post('/doctors/add', data={'name': 'Test Doc', 'specialization': 'General'})
        self.assertEqual(resp.status_code, 302)
        
        resp = self.doctor.post('/doctors/add', data={'name': 'Test Doc2', 'specialization': 'General'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.staff.post('/doctors/add', data={'name': 'Test Doc3', 'specialization': 'General'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.patient.post('/doctors/add', data={'name': 'Test Doc4', 'specialization': 'General'})
        self.assertEqual(resp.status_code, 403)

    def test_post_staff_add_permissions(self):
        resp = self.head_doctor.post('/staff/add', data={'name': 'Test Staff', 'staff_role': 'Nurse', 'staff_code': 'TEST-1'})
        self.assertEqual(resp.status_code, 302)
        
        resp = self.doctor.post('/staff/add', data={'name': 'Test Staff2', 'staff_role': 'Nurse', 'staff_code': 'TEST-2'})
        self.assertEqual(resp.status_code, 302)
        
        resp = self.staff.post('/staff/add', data={'name': 'Test Staff3', 'staff_role': 'Nurse', 'staff_code': 'TEST-3'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.patient.post('/staff/add', data={'name': 'Test Staff4', 'staff_role': 'Nurse', 'staff_code': 'TEST-4'})
        self.assertEqual(resp.status_code, 403)
        
    def test_post_beds_add_permissions(self):
        resp = self.head_doctor.post('/beds/add', data={'bed_number': 'TEST-B1', 'ward': 'General', 'bed_type': 'general'})
        self.assertEqual(resp.status_code, 302)
        
        resp = self.doctor.post('/beds/add', data={'bed_number': 'TEST-B2', 'ward': 'General', 'bed_type': 'general'})
        self.assertEqual(resp.status_code, 302)
        
        resp = self.staff.post('/beds/add', data={'bed_number': 'TEST-B3', 'ward': 'General', 'bed_type': 'general'})
        self.assertEqual(resp.status_code, 302)
        
        resp = self.patient.post('/beds/add', data={'bed_number': 'TEST-B4', 'ward': 'General', 'bed_type': 'general'})
        self.assertEqual(resp.status_code, 403)
        
    def test_patient_registration_flow(self):
        # 1. Staff requests registration
        resp = self.staff.post('/patients/add', data={'name': 'Test Pending Patient', 'age': 30, 'gender': 'Male', 'phone': '12345'})
        self.assertEqual(resp.status_code, 302)
        
        # Verify it's in pending and NOT in patients
        reg = query_db("SELECT * FROM patient_registrations WHERE name='Test Pending Patient'", one=True)
        self.assertIsNotNone(reg)
        self.assertEqual(reg['status'], 'pending')
        
        pat = query_db("SELECT * FROM patients WHERE name='Test Pending Patient'")
        self.assertEqual(pat, [])
        
        # 2. Staff cannot approve
        resp = self.staff.post(f'/patients/registration/{reg["id"]}/review', data={'action': 'approve'})
        self.assertEqual(resp.status_code, 403)
        
        # 3. Doctor approves
        resp = self.doctor.post(f'/patients/registration/{reg["id"]}/review', data={'action': 'approve'})
        self.assertEqual(resp.status_code, 302)
        
        # Verify it is approved and patient is created
        reg_updated = query_db("SELECT * FROM patient_registrations WHERE id=?", (reg['id'],), one=True)
        self.assertEqual(reg_updated['status'], 'approved')
        
        pat_updated = query_db("SELECT * FROM patients WHERE id=?", (reg_updated['patient_id'],), one=True)
        self.assertNotEqual(pat_updated, [])
        self.assertEqual(pat_updated['name'], 'Test Pending Patient')
        
        # 4. Double approval is blocked
        resp = self.doctor.post(f'/patients/registration/{reg["id"]}/review', data={'action': 'reject'})
        self.assertEqual(resp.status_code, 302)
        
        reg_double = query_db("SELECT * FROM patient_registrations WHERE id=?", (reg['id'],), one=True)
        self.assertEqual(reg_double['status'], 'approved') # Status didn't change
        
    def test_patient_registration_rejection(self):
        # Staff requests registration
        self.staff.post('/patients/add', data={'name': 'Test Rejected Patient', 'age': 25, 'gender': 'Female'})
        reg = query_db("SELECT * FROM patient_registrations WHERE name='Test Rejected Patient'", one=True)
        
        # Head doctor rejects
        resp = self.head_doctor.post(f'/patients/registration/{reg["id"]}/review', data={'action': 'reject', 'notes': 'Fake'})
        self.assertEqual(resp.status_code, 302)
        
        reg_updated = query_db("SELECT * FROM patient_registrations WHERE id=?", (reg['id'],), one=True)
        self.assertEqual(reg_updated['status'], 'rejected')
        self.assertEqual(reg_updated['reviewer_notes'], 'Fake')
        
        pat_updated = query_db("SELECT * FROM patients WHERE name='Test Rejected Patient'")
        self.assertEqual(pat_updated, [])
        
    def test_staff_sees_only_own_requests(self):
        execute_db("INSERT INTO patient_registrations (name, age, gender, requested_by_user_id) VALUES ('Other Patient', 30, 'Male', 999)")
        resp = self.staff.get('/patients?tab=pending')
        html = resp.data.decode('utf-8')
        self.assertNotIn('Other Patient', html)
        
    def test_no_500s_all_pages(self):
        roles = ['head_doctor', 'doctor', 'staff', 'patient']
        urls = ['/doctors', '/staff', '/beds', '/patients', '/patients?tab=pending', '/prescriptions', '/prescriptions/1', '/patients/1']
        
        for role in roles:
            client = self.login(role)
            for url in urls:
                resp = client.get(url)
                # patient won't have access to /doctors, /staff, /beds, /patients, /prescriptions so they get 403 or redirect
                # but no 500
                self.assertNotEqual(resp.status_code, 500, f"URL {url} failed with 500 for role {role}")
                
    def test_pending_absent_from_lists(self):
        self.staff.post('/patients/add', data={'name': 'Invisible Patient', 'age': 40, 'gender': 'Male'})
        
        resp = self.head_doctor.get('/patients?tab=patients')
        html = resp.data.decode('utf-8')
        self.assertNotIn('Invisible Patient', html)
        
        resp = self.head_doctor.get('/beds')
        html = resp.data.decode('utf-8')
        self.assertNotIn('Invisible Patient', html)

    def test_prescription_create_permissions(self):
        # GET /prescriptions/new
        resp = self.staff.get('/prescriptions/new')
        self.assertEqual(resp.status_code, 403)
        
        resp = self.patient.get('/prescriptions/new')
        self.assertEqual(resp.status_code, 403)
        
        resp = self.doctor.get('/prescriptions/new')
        self.assertEqual(resp.status_code, 200)

        # POST /prescriptions/add
        resp = self.staff.post('/prescriptions/add', data={})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.patient.post('/prescriptions/add', data={})
        self.assertEqual(resp.status_code, 403)

        # POST /prescriptions/<id>/status
        resp = self.staff.post('/prescriptions/1/status', data={'status': 'completed'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.patient.post('/prescriptions/1/status', data={'status': 'completed'})
        self.assertEqual(resp.status_code, 403)
        
        resp = self.doctor.post('/prescriptions/1/status', data={'status': 'completed'})
        self.assertEqual(resp.status_code, 302) # Redirects back to view

    def test_prescription_view_staff(self):
        resp = self.staff.get('/prescriptions')
        self.assertEqual(resp.status_code, 200)
        
        resp = self.staff.get('/prescriptions/1')
        self.assertEqual(resp.status_code, 200)

    def test_prescription_create_buttons_hidden(self):
        # Staff should not see create buttons on /prescriptions
        resp = self.staff.get('/prescriptions')
        html = resp.data.decode('utf-8')
        self.assertNotIn('Issue New Prescription', html)
        
        # Staff should not see Issue Prescription on /patients/1
        resp = self.staff.get('/patients/1')
        html = resp.data.decode('utf-8')
        self.assertNotIn('Issue Prescription', html)
        self.assertNotIn('Create First Prescription', html)

if __name__ == '__main__':
    unittest.main()
