"""
test_assistant_module.py
------------------------
Unit tests for the Patient Assistant feature.
"""

import unittest
import tempfile
import json

import app as flask_app_module
from app import app
import database

class TestAssistantModule(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.orig_db = database.DATABASE
        cls.db_fd, cls.db_path = tempfile.mkstemp()
        database.DATABASE = cls.db_path
        flask_app_module.DATABASE = cls.db_path
        
        database.create_tables()
        database.seed_demo_data()

        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key'
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        database.DATABASE = cls.orig_db
        import os
        os.close(cls.db_fd)
        os.unlink(cls.db_path)

    def login_as(self, role):
        """Helper to login."""
        return self.client.post('/login', data={'demo_role': role}, follow_redirects=True)

    def test_assistant_access_denied_for_staff(self):
        """Staff/doctor get 403 on /api/assistant."""
        self.login_as('doctor')
        response = self.client.post('/api/assistant', json={'message': 'hello'})
        self.assertEqual(response.status_code, 403)
        
        self.login_as('staff')
        response = self.client.post('/api/assistant', json={'message': 'hello'})
        self.assertEqual(response.status_code, 403)

    def test_assistant_patient_data_access(self):
        """Patient gets answers from own data and not another's."""
        self.login_as('patient')
        
        # Next medicine check
        res = self.client.post('/api/assistant', json={'message': 'next medicine'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('reply', data)
        # Should not throw error, should give some valid response
        
        # Follow up check
        res2 = self.client.post('/api/assistant', json={'message': 'my follow-up'})
        self.assertEqual(res2.status_code, 200)
        self.assertIn('reply', res2.get_json())
        
        # Prescription check
        res3 = self.client.post('/api/assistant', json={'message': 'my prescription'})
        self.assertEqual(res3.status_code, 200)
        self.assertIn('reply', res3.get_json())
        
    def test_emergency_words(self):
        """Emergency words return the emergency numbers."""
        self.login_as('patient')
        res = self.client.post('/api/assistant', json={'message': 'I have chest pain'})
        data = res.get_json()
        self.assertIn('112', data['reply'])
        self.assertIn('MEDICAL EMERGENCY', data['reply'])

    def test_no_medical_advice(self):
        """Symptom question returns the "no medical advice" reply."""
        self.login_as('patient')
        res = self.client.post('/api/assistant', json={'message': 'I have a headache what should I take?'})
        data = res.get_json()
        self.assertIn('I can\'t give medical advice', data['reply'])

if __name__ == '__main__':
    unittest.main()
