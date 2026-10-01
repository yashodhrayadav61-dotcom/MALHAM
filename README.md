# MALHAM 🏥
> **ONE PLATFORM. ONE CONNECTED CARE JOURNEY.**  
> *Connecting Every Layer of Hospital Care*

MALHAM is a modern, unified hospital management platform designed to streamline clinical workflows, bed allocation, inventory tracking, smart prescriptions, follow-up adherence, and role-based access control.

---

## 🎯 The Problem

Modern healthcare facilities struggle with fragmented systems, disconnected departments, manual bed tracking, ambiguous prescriptions, and missed patient follow-ups. This leads to operational bottlenecks, delayed emergency response times, and poor patient care continuity. 

MALHAM solves this by providing **one connected platform** that unifies doctors, nursing staff, administrators, and patients into a single real-time care ecosystem.

---

## ✨ Key Features

1. **Role-Based Access Control (RBAC)**:
   - **Head Doctor**: Complete oversight over hospital operations, doctors' leave approvals, inventory, and clinical data.
   - **Doctor**: Manage patients, log visits, issue structured prescriptions, and track follow-ups.
   - **Staff / Nurse**: Register patients, handle emergency triage, assign/release beds, and update medicine inventory.
   - **Patient**: View personal medical records, active prescriptions, dosage schedules, and reminders in a dedicated profile view.

2. **Futuristic Dark-Themed Dashboard**:
   - Real-time patient footfall analytics and department breakdown charts.
   - Emergency overview table with critical pulse alerts.
   - Live doctor duty status and bed availability gauges.
   - Soft neon red (`#ff2a5f`) visual accents with smooth number count-up animations.

3. **Patients & Emergency Management**:
   - Patient registration and comprehensive search (Name, Code, Phone).
   - Triage level classification (`Critical`, `Urgent`, `Stable`).
   - Visit history timeline (OPD, Emergency, Admission).

4. **Beds & Ward Management**:
   - Interactive ward grid across General, ICU, Emergency, Maternity, and Pediatric wards.
   - Bed statuses: `Available`, `Occupied`, `Reserved`, `Maintenance`.
   - Real-time patient assignment and discharge workflow.

5. **Doctors & Roster Management**:
   - Doctor directory with specialization and shift tracking (Morning, Evening, Night).
   - Attendance logging and leave request approval pipeline.

6. **Medicines & Inventory Control**:
   - Stock level monitoring with automated low-stock and 30-day expiry warning cards.
   - Audit log tracking restock, dispense, and adjustment actions.

7. **Smart Prescriptions**:
   - Structured dosage pattern validation (e.g. `1-0-1`, `0.5-0-1`).
   - Automated dosage slot formatting (Morning, Afternoon, Night).
   - Multilingual advice rendering (English & Hindi).
   - Dedicated print-friendly paper stylesheet (`@media print`).

8. **Follow-ups & Reminders**:
   - Automated reminder generation for prescribed regimens.
   - Patient check-in response tracking (`Took all doses`, `Missed dose`, `Stopped treatment`).
   - At-risk patient panel highlighting non-adherent patients.
   - Simulated WhatsApp dispatch interface with live message log audit.

---

## 🛠️ Tech Stack

- **Backend**: Python 3, Flask
- **Database**: SQLite3 (Row factory enabled)
- **Frontend**: HTML5, Vanilla CSS (Dark Theme with `#ff2a5f` Neon Red Accents), JavaScript (ES6, Chart.js)
- **Authentication**: Werkzeug Security (SHA-256 Password Hashing), Flask Sessions

---

## 🚀 How to Install & Run (Windows Step-by-Step)

### Prerequisites
- Python 3.10+ installed on your system.

### 1. Open Terminal & Navigate to Project
```cmd
cd d:\MALHAM
```

### 2. Set Up Virtual Environment (Optional but Recommended)
```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```cmd
pip install -r requirements.txt
```

### 4. Restore Fresh Demo Database (Optional)
```cmd
python reset_demo.py
```

### 5. Start the Application
```cmd
python app.py
```

### 6. Access in Browser
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🔑 Quick Demo Accounts

You can log in manually using credentials or click the **Quick Demo Login** buttons on the login screen:

| Role | Username | Password | User Profile |
|---|---|---|---|
| **Head Doctor** | `head_doc` | `password123` | Dr. Suresh Kumar (Head of Hospital) |
| **Doctor** | `doc_anita` | `password123` | Dr. Anita Desai (Senior Physician) |
| **Staff / Nurse** | `staff_nurse` | `password123` | Nurse Sarah (Ward & Inventory Staff) |
| **Patient** | `patient_aarav` | `password123` | Aarav Sharma (Patient Profile) |

---

## 💬 WhatsApp Integration Note

> ℹ️ **Transparency Note**: In this hackathon demonstration build, outgoing WhatsApp notifications run in **Simulation Mode** (`WHATSAPP_MODE = "simulation"`).
> Outgoing messages are formatted and logged to the `message_log` database table without sending real SMS/WhatsApp messages. The abstraction layer in `whatsapp_service.py` is structured and ready for production deployment via the official Meta WhatsApp Business API / Twilio endpoint.

---

## 🧪 Running Tests

Run the full test suite (RBAC, Prescriptions, Follow-ups, and E2E Smoke Tests):
```cmd
python -m unittest test_roles_module.py test_prescriptions_module.py test_followups_module.py test_smoke_all.py
```
