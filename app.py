"""
app.py
------
Main Flask application for MALHAM – Connecting Every Layer of Hospital Care.
Run with:  python app.py
"""

import os
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, g
from werkzeug.security import check_password_hash
from database import get_db_connection, create_tables, seed_demo_data

app = Flask(__name__)

# Session secret key loaded from environment variable with a development fallback
app.secret_key = os.environ.get("SECRET_KEY", "malham_dev_secret_key_2026_secure")

# Ensure malham.db exists and is seeded on a fresh clone startup
from database import DATABASE
if not os.path.exists(DATABASE):
    print("[INFO] Database file malham.db not found. Initializing and seeding...")
    create_tables()
    seed_demo_data()

# ── SHIFT CONFIGURATIONS ────────────────────────────────────────────────
SHIFT_STARTS = {
    "morning": "08:00",
    "afternoon": "14:00",
    "evening": "17:00",
    "night": "20:00"
}
ATTENDANCE_WINDOW_MINUTES = 30
ATTENDANCE_DEMO_MODE = os.environ.get("ATTENDANCE_DEMO_MODE", "False").lower() in ["true", "1", "yes"]


# ── Error Handlers ────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden_error(e):
    return render_template("403.html"), 403

@app.errorhandler(404)
def not_found_error(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


@app.before_request
def require_login():
    endpoint = request.endpoint
    if endpoint in ('login', 'static') or (request.path and request.path.startswith('/static')):
        return None

    if 'user_id' not in session:
        return redirect(url_for('login'))

    g.user = get_current_user()
    if not g.user:
        session.clear()
        return redirect(url_for('login'))


@app.context_processor
def inject_globals():
    return dict(
        current_user=getattr(g, 'user', None),
        attendance_demo_mode=ATTENDANCE_DEMO_MODE
    )


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'user') or not g.user:
                return redirect(url_for('login'))
            if g.user['role'] not in roles:
                return render_template('403.html'), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def query_db(sql, args=(), one=False):
    """Execute a read query and return results as a list of dicts."""
    conn = get_db_connection()
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    result = [dict(row) for row in rows]
    return result[0] if one and result else result


def execute_db(sql, args=()):
    """Execute a write query (INSERT, UPDATE, DELETE) and commit."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, args)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id


def log_activity(action, description, category='doctor'):
    """Record an event in the activity_log table."""
    execute_db(
        "INSERT INTO activity_log (action, description, category, timestamp) VALUES (?, ?, ?, datetime('now'))",
        (action, description, category)
    )



def auto_process_attendance(now=None):
    """Process auto-absent logic for doctors whose check-in window has passed."""
    if ATTENDANCE_DEMO_MODE:
        return
        
    if now is None:
        now = datetime.now()
        
    date_str = now.strftime("%Y-%m-%d")
    
    # Get all doctors
    doctors = query_db("SELECT id, shift, status FROM doctors")
    for doc in doctors:
        doc_id = doc['id']
        shift = doc['shift'] or 'morning'
        shift_start_str = SHIFT_STARTS.get(shift, "08:00")
        
        try:
            start_hour, start_minute = map(int, shift_start_str.split(':'))
        except:
            continue
            
        shift_start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        
        # Handle night shift crossing midnight
        if shift == 'night' and now.hour < 12:
            shift_start_time -= timedelta(days=1)
            date_str = shift_start_time.strftime("%Y-%m-%d")
            
        window_end_time = shift_start_time + timedelta(minutes=ATTENDANCE_WINDOW_MINUTES)
        
        if now > window_end_time:
            # Window has passed. Check if they have an attendance record for today
            existing = query_db("SELECT id FROM attendance WHERE doctor_id=? AND date=?", (doc_id, date_str), one=True)
            if not existing:
                # Check for approved leaves covering today
                # Leave logic: start_date <= date_str <= end_date AND status='approved'
                # Note: SQLite date strings can be compared directly if format is YYYY-MM-DD
                leave = query_db(
                    "SELECT id FROM doctor_leaves WHERE doctor_id=? AND status='approved' AND start_date <= ? AND end_date >= ?",
                    (doc_id, date_str, date_str), one=True
                )
                
                if leave:
                    att_status = "on-leave"
                    notes = "Auto-marked on-leave (Approved Leave)"
                    # Update doctor status just in case
                    execute_db("UPDATE doctors SET status='on-leave' WHERE id=?", (doc_id,))
                else:
                    att_status = "absent"
                    notes = "Auto-marked absent: did not check in during shift window"
                    execute_db("UPDATE doctors SET status='off-duty' WHERE id=?", (doc_id,))
                    
                execute_db(
                    "INSERT INTO attendance (doctor_id, date, status, notes) VALUES (?, ?, ?, ?)",
                    (doc_id, date_str, att_status, notes)
                )



def get_staff_shift_info(staff_id, now=None):
    if now is None:
        now = datetime.now()
    
    staff = query_db("SELECT shift FROM staff_members WHERE id=?", (staff_id,), one=True)
    if not staff:
        return None
        
    shift = staff['shift'] or 'morning'
    shift_start_str = SHIFT_STARTS.get(shift, "08:00")
    try:
        start_hour, start_minute = map(int, shift_start_str.split(':'))
    except:
        start_hour, start_minute = 8, 0
        
    shift_start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    
    if shift == 'night' and now.hour < 12:
        shift_start_time -= timedelta(days=1)
        
    date_str = shift_start_time.strftime("%Y-%m-%d")
    window_end_time = shift_start_time + timedelta(minutes=ATTENDANCE_WINDOW_MINUTES)
    
    is_open = shift_start_time <= now <= window_end_time
    if ATTENDANCE_DEMO_MODE:
        is_open = True
        
    marked = query_db("SELECT status, check_in FROM staff_attendance WHERE staff_id=? AND date=?", (staff_id, date_str), one=True)
    
    leave = query_db(
        "SELECT id FROM staff_leaves WHERE staff_id=? AND status='approved' AND start_date <= ? AND end_date >= ?",
        (staff_id, date_str, date_str), one=True
    )
    
    status_text = ""
    if marked:
        if marked['status'] == 'present':
            status_text = f"Already checked in at {marked['check_in']}"
        elif marked['status'] == 'on-leave':
            status_text = "You are on approved leave today"
        else:
            status_text = "Absent"
    elif leave:
        status_text = "You are on approved leave today"
        is_open = False
    elif is_open:
        mins = int((window_end_time - now).total_seconds() / 60)
        status_text = f"Window open for {max(0, mins)} more minutes" if not ATTENDANCE_DEMO_MODE else "Window open (Demo Mode)"
    elif now < shift_start_time:
        status_text = f"Check-in opens at {shift_start_str} and closes at {window_end_time.strftime('%H:%M')}"
    else:
        status_text = f"Window closed at {window_end_time.strftime('%H:%M')}"
        
    return {
        'shift': shift,
        'shift_start': shift_start_str,
        'window_open': is_open and not marked,
        'status_text': status_text,
        'marked_today': bool(marked),
        'att_record': marked
    }

def auto_process_staff_attendance(now=None):
    if now is None:
        now = datetime.now()
        
    if ATTENDANCE_DEMO_MODE:
        return
        
    staff_members = query_db("SELECT id, shift FROM staff_members")
    for staff in staff_members:
        staff_id = staff['id']
        shift = staff['shift'] or 'morning'
        shift_start_str = SHIFT_STARTS.get(shift, "08:00")
        try:
            h, m = map(int, shift_start_str.split(':'))
        except:
            h, m = 8, 0
            
        shift_start_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if shift == 'night' and now.hour < 12:
            shift_start_time -= timedelta(days=1)
            
        date_str = shift_start_time.strftime("%Y-%m-%d")
        window_end_time = shift_start_time + timedelta(minutes=ATTENDANCE_WINDOW_MINUTES)
        
        if now > window_end_time:
            existing = query_db("SELECT id FROM staff_attendance WHERE staff_id=? AND date=?", (staff_id, date_str), one=True)
            if not existing:
                leave = query_db(
                    "SELECT id FROM staff_leaves WHERE staff_id=? AND status='approved' AND start_date <= ? AND end_date >= ?",
                    (staff_id, date_str, date_str), one=True
                )
                
                att_status = 'on-leave' if leave else 'absent'
                notes = 'Auto-marked as on-leave based on approved request' if leave else 'System auto-marked: did not check in'
                
                execute_db(
                    "INSERT INTO staff_attendance (staff_id, date, status, notes) VALUES (?, ?, ?, ?)",
                    (staff_id, date_str, att_status, notes)
                )

def get_doctor_shift_info(doctor_id, now=None):
    if now is None:
        now = datetime.now()
    
    doc = query_db("SELECT shift FROM doctors WHERE id=?", (doctor_id,), one=True)
    if not doc:
        return None
        
    shift = doc['shift'] or 'morning'
    shift_start_str = SHIFT_STARTS.get(shift, "08:00")
    try:
        start_hour, start_minute = map(int, shift_start_str.split(':'))
    except:
        start_hour, start_minute = 8, 0
        
    shift_start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    
    if shift == 'night' and now.hour < 12:
        shift_start_time -= timedelta(days=1)
        
    date_str = shift_start_time.strftime("%Y-%m-%d")
    window_end_time = shift_start_time + timedelta(minutes=ATTENDANCE_WINDOW_MINUTES)
    
    is_open = shift_start_time <= now <= window_end_time
    if ATTENDANCE_DEMO_MODE:
        is_open = True
        
    marked = query_db("SELECT status, check_in FROM attendance WHERE doctor_id=? AND date=?", (doctor_id, date_str), one=True)
    
    leave = query_db(
        "SELECT id FROM doctor_leaves WHERE doctor_id=? AND status='approved' AND start_date <= ? AND end_date >= ?",
        (doctor_id, date_str, date_str), one=True
    )
    
    status_text = ""
    if marked:
        if marked['status'] == 'present':
            status_text = f"Already checked in at {marked['check_in']}"
        elif marked['status'] == 'on-leave':
            status_text = "You are on approved leave today"
        else:
            status_text = "Absent"
    elif leave:
        status_text = "You are on approved leave today"
        is_open = False
    elif is_open:
        mins = int((window_end_time - now).total_seconds() / 60)
        status_text = f"Window open for {max(0, mins)} more minutes" if not ATTENDANCE_DEMO_MODE else "Window open (Demo Mode)"
    elif now < shift_start_time:
        status_text = f"Check-in opens at {shift_start_str} and closes at {window_end_time.strftime('%H:%M')}"
    else:
        status_text = f"Window closed at {window_end_time.strftime('%H:%M')}"
        
    return {
        'shift': shift,
        'shift_start': shift_start_str,
        'window_open': is_open and not marked,
        'status_text': status_text,
        'marked_today': bool(marked),
        'att_record': marked
    }

# ── Auth Routes ───────────────────────────────────────────────────────



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        demo_role = request.form.get("demo_role")
        conn = get_db_connection()
        if demo_role:
            user = conn.execute("SELECT * FROM users WHERE role = ? LIMIT 1", (demo_role,)).fetchone()
            conn.close()
            if user:
                session['user_id'] = user['id']
                if user['role'] == 'patient':
                    if user['patient_id']:
                        return redirect(url_for('patient_profile', patient_id=user['patient_id']))
                    return redirect(url_for('patients_list'))
                return redirect(url_for('dashboard'))
            return render_template("login.html", error=f"Demo user for role '{demo_role}' not found.")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            if user['role'] == 'patient':
                if user['patient_id']:
                    return redirect(url_for('patient_profile', patient_id=user['patient_id']))
                return redirect(url_for('patients_list'))
            return redirect(url_for('dashboard'))
        else:
            return render_template("login.html", error="Invalid username or password.")

    if 'user_id' in session and getattr(g, 'user', None):
        if g.user['role'] == 'patient':
            if g.user['patient_id']:
                return redirect(url_for('patient_profile', patient_id=g.user['patient_id']))
            return redirect(url_for('patients_list'))
        return redirect(url_for('dashboard'))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
@role_required('head_doctor', 'doctor', 'staff')
def dashboard():
    """Main dashboard page."""
    auto_process_attendance()
    auto_process_staff_attendance()

    # --- Summary counts ---------------------------------------------------
    total_patients    = query_db("SELECT COUNT(*) AS c FROM patients", one=True)["c"]
    admitted_patients = query_db("SELECT COUNT(*) AS c FROM visits WHERE visit_type='admission' AND status!='discharged'", one=True)["c"]
    emergency_patients = query_db("SELECT COUNT(*) AS c FROM visits WHERE visit_type='emergency' AND status!='discharged'", one=True)["c"]
    discharged_patients = query_db("SELECT COUNT(*) AS c FROM visits WHERE status='discharged'", one=True)["c"]

    # --- Bed summary -------------------------------------------------------
    beds_available  = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='available'", one=True)["c"]
    beds_occupied   = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='occupied'", one=True)["c"]
    beds_reserved   = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='reserved'", one=True)["c"]
    beds_maintenance = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='maintenance'", one=True)["c"]
    beds_total      = query_db("SELECT COUNT(*) AS c FROM beds", one=True)["c"]

    # --- Doctor summary ----------------------------------------------------
    doctors_available = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='available'", one=True)["c"]
    doctors_busy      = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='busy'", one=True)["c"]
    doctors_offduty   = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='off-duty'", one=True)["c"]
    doctors_total     = query_db("SELECT COUNT(*) AS c FROM doctors", one=True)["c"]

    # --- Medicine summary --------------------------------------------------
    meds_in_stock    = query_db("SELECT COUNT(*) AS c FROM medicines WHERE quantity > COALESCE(reorder_level, 20)", one=True)["c"]
    meds_low_stock   = query_db("SELECT COUNT(*) AS c FROM medicines WHERE quantity > 0 AND quantity <= COALESCE(reorder_level, 20)", one=True)["c"]
    meds_out_stock   = query_db("SELECT COUNT(*) AS c FROM medicines WHERE quantity = 0", one=True)["c"]

    # --- Emergency patients list -------------------------------------------
    emergency_list = query_db(
        "SELECT p.name, p.age, p.gender, p.blood_group, v.visit_date AS admission_date, v.triage_level, v.status AS visit_status "
        "FROM visits v "
        "JOIN patients p ON v.patient_id = p.id "
        "WHERE v.visit_type='emergency' AND v.status!='discharged' "
        "ORDER BY CASE v.triage_level WHEN 'critical' THEN 1 WHEN 'urgent' THEN 2 ELSE 3 END, v.visit_date DESC"
    )

    # --- Recent activity ---------------------------------------------------
    recent_activity = query_db(
        "SELECT action, description, category, timestamp "
        "FROM activity_log ORDER BY timestamp DESC LIMIT 10"
    )

    # --- Upcoming follow-ups -----------------------------------------------
    upcoming_followups = query_db(
        "SELECT f.followup_date, f.reason, f.status AS fstatus, "
        "       p.name AS patient_name, d.name AS doctor_name "
        "FROM followups f "
        "JOIN patients p ON f.patient_id = p.id "
        "JOIN doctors  d ON f.doctor_id  = d.id "
        "WHERE f.status = 'scheduled' "
        "ORDER BY f.followup_date ASC LIMIT 5"
    )

    # --- Department-wise patient count (for chart) -------------------------
    dept_counts = query_db(
        "SELECT department, COUNT(*) AS count FROM patients WHERE department IS NOT NULL AND department!='' GROUP BY department ORDER BY count DESC"
    )

    footfall = query_db(
        "SELECT visit_date AS date, COUNT(*) AS count "
        "FROM visits GROUP BY visit_date ORDER BY visit_date ASC"
    )

    # --- Prescriptions summary ---------------------------------------------
    active_prescriptions = query_db("SELECT COUNT(*) AS c FROM prescriptions WHERE status='active'", one=True)["c"]

    # --- Follow-ups & Reminders summary -----------------------------------
    pending_reminders = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='pending'", one=True)["c"]
    today_date = datetime.now().strftime("%Y-%m-%d")
    overdue_followups = query_db("SELECT COUNT(*) AS c FROM followups WHERE (status='missed' OR (status='scheduled' AND followup_date < ?))", (today_date,), one=True)["c"]

    # --- Staff summary -----------------------------------------------------
    staff_total = query_db("SELECT COUNT(*) AS c FROM staff_members", one=True)["c"]
    staff_present = query_db("SELECT COUNT(*) AS c FROM staff_attendance WHERE date=? AND status='present'", (today_date,), one=True)["c"]
    
    shift_info = None
    if g.user and g.user['doctor_id']:
        shift_info = get_doctor_shift_info(g.user['doctor_id'])
    elif g.user and g.user['staff_id']:
        shift_info = get_staff_shift_info(g.user['staff_id'])
        
    pending_registrations_count = 0
    if g.user and g.user['role'] in ['head_doctor', 'doctor']:
        pending_registrations_count = query_db("SELECT COUNT(*) AS c FROM patient_registrations WHERE status = 'pending'", one=True)["c"]

    return render_template(
        "dashboard.html",
        shift_info=shift_info,

        total_patients=total_patients,
        admitted_patients=admitted_patients,
        emergency_patients=emergency_patients,
        discharged_patients=discharged_patients,
        beds_available=beds_available,
        beds_occupied=beds_occupied,
        beds_reserved=beds_reserved,
        beds_maintenance=beds_maintenance,
        beds_total=beds_total,
        doctors_available=doctors_available,
        doctors_busy=doctors_busy,
        doctors_offduty=doctors_offduty,
        doctors_total=doctors_total,
        staff_total=staff_total,
        staff_present=staff_present,
        meds_in_stock=meds_in_stock,
        meds_low_stock=meds_low_stock,
        meds_out_stock=meds_out_stock,
        active_prescriptions=active_prescriptions,
        pending_reminders=pending_reminders,
        overdue_followups=overdue_followups,
        emergency_list=emergency_list,
        recent_activity=recent_activity,
        upcoming_followups=upcoming_followups,
        dept_counts=dept_counts,
        footfall=footfall,
        pending_registrations_count=pending_registrations_count,
    )



# ── Staff Management Routes ──────────────────────────────────────────

@app.route("/staff")
@role_required('head_doctor', 'doctor', 'staff')
def staff():
    """Staff management view with roster, attendance, and leave requests."""
    auto_process_staff_attendance()
    active_tab = request.args.get("tab", "roster")
    search_query = request.args.get("q", "").strip()
    
    if active_tab == 'leaves' and g.user['role'] == 'doctor':
        return render_template('403.html'), 403

    # Stat counters
    staff_total = query_db("SELECT COUNT(*) AS c FROM staff_members", one=True)["c"]
    staff_available = query_db("SELECT COUNT(*) AS c FROM staff_members WHERE status='available'", one=True)["c"]
    
    # Filtered Staff list query
    query = "SELECT * FROM staff_members WHERE 1=1"
    params = []

    if search_query:
        query += " AND (name LIKE ? OR staff_role LIKE ? OR department_or_ward LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term])

    shift_filter = request.args.get("shift", "").strip()
    if shift_filter:
        query += " AND shift = ?"
        params.append(shift_filter)
        
    status_filter = request.args.get("status", "").strip()
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY name ASC"
    staff_list = query_db(query, params)

    # Attendance
    today_date = datetime.now().strftime("%Y-%m-%d")
    att_date = request.args.get("att_date", today_date)
    
    att_query = """
        SELECT s.id as staff_id, s.name as staff_name, s.staff_role, s.shift,
               a.status as att_status, a.check_in, a.check_out, a.notes
        FROM staff_members s
        LEFT JOIN staff_attendance a ON s.id = a.staff_id AND a.date = ?
        ORDER BY s.name ASC
    """
    attendance_list = query_db(att_query, [att_date])

    # Leaves
    if g.user['role'] == 'staff':
        leaves = query_db("""
            SELECT l.*, s.name as staff_name, s.staff_role 
            FROM staff_leaves l
            JOIN staff_members s ON l.staff_id = s.id
            WHERE l.staff_id = ?
            ORDER BY l.created_at DESC
        """, (g.user['staff_id'],))
    else:
        leaves = query_db("""
            SELECT l.*, s.name as staff_name, s.staff_role 
            FROM staff_leaves l
            JOIN staff_members s ON l.staff_id = s.id
            ORDER BY l.created_at DESC
        """)

    pending_leaves_count = sum(1 for l in leaves if l['status'] == 'pending')

    shift_info = None
    if g.user['role'] == 'staff' and g.user['staff_id']:
        shift_info = get_staff_shift_info(g.user['staff_id'])
        
    return render_template(
        "staff.html",
        active_tab=active_tab,
        staff_list=staff_list,
        attendance_list=attendance_list,
        leaves=leaves,
        pending_leaves_count=pending_leaves_count,
        staff_total=staff_total,
        staff_available=staff_available,
        att_date=att_date,
        today_date=today_date,
        shift_info=shift_info
    )

@app.route("/staff/attendance/self_mark", methods=["POST"])
@role_required('staff')
def staff_self_mark_attendance():
    user = get_current_user()
    staff_id = user['staff_id'] if user else None
    if not staff_id:
        return "Not authorized", 403
        
    now = datetime.now()
    
    staff = query_db("SELECT shift FROM staff_members WHERE id=?", (staff_id,), one=True)
    if not staff:
        return "Staff not found", 404
        
    shift = staff['shift'] or 'morning'
    shift_start_str = SHIFT_STARTS.get(shift, "08:00")
    try:
        start_hour, start_minute = map(int, shift_start_str.split(':'))
    except:
        start_hour, start_minute = 8, 0
        
    shift_start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    
    if shift == 'night' and now.hour < 12:
        shift_start_time -= timedelta(days=1)
        
    date_str = shift_start_time.strftime("%Y-%m-%d")
    
    existing = query_db("SELECT id FROM staff_attendance WHERE staff_id=? AND date=?", (staff_id, date_str), one=True)
    if existing:
        return "Already marked today", 400
        
    window_end_time = shift_start_time + timedelta(minutes=ATTENDANCE_WINDOW_MINUTES)
    
    if not ATTENDANCE_DEMO_MODE:
        if now < shift_start_time or now > window_end_time:
            return "Check-in window is closed", 403
            
    leave = query_db(
        "SELECT id FROM staff_leaves WHERE staff_id=? AND status='approved' AND start_date <= ? AND end_date >= ?",
        (staff_id, date_str, date_str), one=True
    )
    if leave:
        return "You are on approved leave today", 403
            
    check_in_time = now.strftime("%H:%M")
    execute_db(
        "INSERT INTO staff_attendance (staff_id, date, status, check_in, notes) VALUES (?, ?, 'present', ?, 'Self-marked')",
        (staff_id, date_str, check_in_time)
    )
    execute_db("UPDATE staff_members SET status='busy' WHERE id=?", (staff_id,))
    
    log_activity("Attendance Self-Marked", f"Staff {staff_id} self-marked attendance for {date_str}", "system")
    
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/staff/attendance/mark", methods=["POST"])
@role_required('head_doctor')
def staff_mark_attendance():
    staff_id = request.form.get("staff_id")
    date_str = request.form.get("date")
    status = request.form.get("status")
    check_in = request.form.get("check_in") or None
    check_out = request.form.get("check_out") or None
    notes = request.form.get("notes", "").strip()

    notes += " (Updated by head doctor)"

    existing = query_db("SELECT id FROM staff_attendance WHERE staff_id=? AND date=?", (staff_id, date_str), one=True)
    if existing:
        execute_db(
            """UPDATE staff_attendance 
               SET status=?, check_in=?, check_out=?, notes=?
               WHERE id=?""",
            (status, check_in, check_out, notes, existing['id'])
        )
    else:
        execute_db(
            "INSERT INTO staff_attendance (staff_id, date, status, check_in, check_out, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (staff_id, date_str, status, check_in, check_out, notes)
        )
    
    return redirect(url_for("staff", tab="attendance", att_date=date_str))

@app.route("/staff/attendance/reset_demo", methods=["POST"])
@role_required('head_doctor')
def reset_staff_demo_attendance():
    if not ATTENDANCE_DEMO_MODE:
        return render_template('403.html'), 403
        
    staff_id = request.form.get("staff_id")
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    if staff_id:
        execute_db("DELETE FROM staff_attendance WHERE staff_id=? AND date=?", (staff_id, date_str))
        execute_db("UPDATE staff_members SET status='available' WHERE id=?", (staff_id,))
        
        staff = query_db("SELECT name FROM staff_members WHERE id=?", (staff_id,), one=True)
        staff_name = staff['name'] if staff else f"Staff #{staff_id}"
        from flask import flash
        flash(f"Successfully reset today's attendance for {staff_name}.", "success")
        
    return redirect(url_for("staff", tab="attendance"))

@app.route("/staff/leave/request", methods=["POST"])
@role_required('staff')
def staff_request_leave():
    staff_id = g.user['staff_id']
    leave_type = request.form.get("leave_type")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    reason = request.form.get("reason")

    if start_date and end_date and leave_type:
        execute_db(
            "INSERT INTO staff_leaves (staff_id, leave_type, start_date, end_date, reason, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (staff_id, leave_type, start_date, end_date, reason)
        )
        log_activity("Leave Requested", f"Staff {staff_id} requested {leave_type} leave", "system")
    return redirect(url_for("staff", tab="leaves"))

@app.route("/staff/leave/review", methods=["POST"])
@role_required('head_doctor')
def staff_review_leave():
    leave_id = request.form.get("leave_id")
    action = request.form.get("action")  # approve or reject
    notes = request.form.get("reviewer_notes", "")

    new_status = 'approved' if action == 'approve' else 'rejected'
    
    if leave_id:
        execute_db(
            "UPDATE staff_leaves SET status=?, reviewer_notes=? WHERE id=?",
            (new_status, notes, leave_id)
        )
        log_activity("Leave Reviewed", f"Staff leave {leave_id} {new_status}", "system")
    return redirect(url_for("staff", tab="leaves"))


# ── Placeholder routes for sidebar links ──────────────────────────────

# ── Patients & Emergency Management Routes ───────────────────────────

@app.route("/patients")
@role_required('head_doctor', 'doctor', 'staff')
def patients():
    """Patients management view with tabs: All Patients, Visits, Emergency."""
    active_tab = request.args.get("tab", "patients")
    search_query = request.args.get("q", "").strip()
    visit_type_filter = request.args.get("visit_type", "").strip()
    status_filter = request.args.get("status", "").strip()
    triage_filter = request.args.get("triage", "").strip()

    today_date = datetime.now().strftime("%Y-%m-%d")

    # Summary Card Counts
    total_patients_count = query_db("SELECT COUNT(*) AS c FROM patients", one=True)["c"]
    todays_footfall_count = query_db("SELECT COUNT(*) AS c FROM visits WHERE visit_date = ?", (today_date,), one=True)["c"]
    active_emergency_count = query_db("SELECT COUNT(*) AS c FROM visits WHERE visit_type = 'emergency' AND status != 'discharged'", one=True)["c"]
    discharged_today_count = query_db("SELECT COUNT(*) AS c FROM visits WHERE status = 'discharged' AND visit_date = ?", (today_date,), one=True)["c"]

    # 1. Patients List Query (Tab: patients)
    patients_sql = (
        "SELECT p.*, "
        "       COUNT(v.id) AS total_visits, "
        "       MAX(v.visit_date) AS last_visit_date "
        "FROM patients p "
        "LEFT JOIN visits v ON p.id = v.patient_id "
        "WHERE 1=1 "
    )
    p_params = []
    if search_query:
        patients_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR p.phone LIKE ? OR p.address LIKE ?) "
        term = f"%{search_query}%"
        p_params.extend([term, term, term, term])

    patients_sql += "GROUP BY p.id ORDER BY p.id DESC"
    patients_list = query_db(patients_sql, p_params)

    # 2. Visits List Query (Tab: visits)
    visits_sql = (
        "SELECT v.*, p.name AS patient_name, p.patient_code, p.phone, p.age, p.gender, "
        "       d.name AS doctor_name, d.specialization "
        "FROM visits v "
        "JOIN patients p ON v.patient_id = p.id "
        "LEFT JOIN doctors d ON v.doctor_id = d.id "
        "WHERE 1=1 "
    )
    v_params = []
    if search_query:
        visits_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR p.phone LIKE ? OR v.reason LIKE ?) "
        term = f"%{search_query}%"
        v_params.extend([term, term, term, term])

    if visit_type_filter:
        visits_sql += "AND v.visit_type = ? "
        v_params.append(visit_type_filter)

    if status_filter:
        visits_sql += "AND v.status = ? "
        v_params.append(status_filter)

    visits_sql += "ORDER BY v.visit_date DESC, v.id DESC"
    visits_list = query_db(visits_sql, v_params)

    # 3. Emergency List Query (Tab: emergency) - Sorted by triage level critical > urgent > stable
    emergency_sql = (
        "SELECT v.*, p.name AS patient_name, p.patient_code, p.age, p.gender, p.blood_group, p.phone, "
        "       d.name AS doctor_name "
        "FROM visits v "
        "JOIN patients p ON v.patient_id = p.id "
        "LEFT JOIN doctors d ON v.doctor_id = d.id "
        "WHERE v.visit_type = 'emergency' "
    )
    e_params = []
    if search_query:
        emergency_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR p.phone LIKE ? OR v.reason LIKE ?) "
        term = f"%{search_query}%"
        e_params.extend([term, term, term, term])

    if triage_filter:
        emergency_sql += "AND v.triage_level = ? "
        e_params.append(triage_filter)

    if status_filter:
        emergency_sql += "AND v.status = ? "
        e_params.append(status_filter)

    emergency_sql += "ORDER BY CASE v.triage_level WHEN 'critical' THEN 1 WHEN 'urgent' THEN 2 WHEN 'stable' THEN 3 ELSE 4 END, v.id DESC"
    emergency_list = query_db(emergency_sql, e_params)

    # Doctors list for modal selects
    doctors_list = query_db("SELECT id, name, specialization FROM doctors ORDER BY name ASC")

    user = get_current_user()
    if user and user['role'] in ['head_doctor', 'doctor']:
        pending_registrations = query_db("""
            SELECT r.*, u.display_name AS requested_by_name
            FROM patient_registrations r
            JOIN users u ON r.requested_by_user_id = u.id
            ORDER BY CASE r.status WHEN 'pending' THEN 1 ELSE 2 END, r.id DESC
        """)
        pending_registrations_count = query_db("SELECT COUNT(*) AS c FROM patient_registrations WHERE status = 'pending'", one=True)["c"]
    else:
        user_id = user['id'] if user else 0
        pending_registrations = query_db("""
            SELECT r.*, u.display_name AS requested_by_name
            FROM patient_registrations r
            JOIN users u ON r.requested_by_user_id = u.id
            WHERE r.requested_by_user_id = ?
            ORDER BY CASE r.status WHEN 'pending' THEN 1 ELSE 2 END, r.id DESC
        """, [user_id])
        pending_registrations_count = 0

    return render_template(
        "patients.html",
        active_tab=active_tab,
        total_patients_count=total_patients_count,
        todays_footfall_count=todays_footfall_count,
        active_emergency_count=active_emergency_count,
        discharged_today_count=discharged_today_count,
        patients=patients_list,
        visits=visits_list,
        emergency_visits=emergency_list,
        doctors=doctors_list,
        pending_registrations=pending_registrations,
        pending_registrations_count=pending_registrations_count,
        search_query=search_query,
        visit_type_filter=visit_type_filter,
        status_filter=status_filter,
        triage_filter=triage_filter,
        today_date=today_date,
    )


@app.route("/patients/add", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def add_patient():
    """Register a new patient."""
    name = request.form.get("name", "").strip()
    age = request.form.get("age", type=int)
    gender = request.form.get("gender", "Male").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    blood_group = request.form.get("blood_group", "").strip()
    department = request.form.get("department", "General").strip()

    if name:
        user = get_current_user()
        if user and user['role'] == 'staff':
            execute_db(
                "INSERT INTO patient_registrations (name, age, gender, phone, address, blood_group, requested_by_user_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                (name, age, gender, phone, address, blood_group, user['id'])
            )
            log_activity("Patient Registration Requested", f"{name} requested by staff", "patient")
            return redirect(url_for("patients", tab="pending"))
        else:
            max_id_row = query_db("SELECT MAX(id) AS m FROM patients", one=True)
            next_num = (max_id_row["m"] or 0) + 1001
            patient_code = f"P-{next_num}"
            registered_on = datetime.now().strftime("%Y-%m-%d")

            execute_db(
                "INSERT INTO patients (patient_code, name, age, gender, phone, address, blood_group, registered_on, status, department) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'admitted', ?)",
                (patient_code, name, age, gender, phone, address, blood_group, registered_on, department)
            )
            log_activity("Patient Registered", f"{name} ({patient_code}) registered", "patient")

    return redirect(url_for("patients", tab="patients"))


@app.route("/patients/registration/<int:reg_id>/review", methods=["POST"])
@role_required('head_doctor', 'doctor')
def review_patient_registration(reg_id):
    """Review pending patient registrations."""
    action = request.form.get("action")
    notes = request.form.get("notes", "").strip()
    user = get_current_user()
    
    reg = query_db("SELECT * FROM patient_registrations WHERE id=?", (reg_id,), one=True)
    if not reg or reg['status'] != 'pending':
        return redirect(url_for("patients", tab="pending"))

    if action == "approve":
        max_id_row = query_db("SELECT MAX(id) AS m FROM patients", one=True)
        next_num = (max_id_row["m"] or 0) + 1001
        patient_code = f"P-{next_num}"
        registered_on = datetime.now().strftime("%Y-%m-%d")

        patient_id = execute_db(
            "INSERT INTO patients (patient_code, name, age, gender, phone, address, blood_group, registered_on, status, department) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'admitted', 'General')",
            (patient_code, reg['name'], reg['age'], reg['gender'], reg['phone'], reg['address'], reg['blood_group'], registered_on)
        )
        
        execute_db(
            "UPDATE patient_registrations SET status='approved', reviewed_by_user_id=?, reviewed_on=datetime('now', 'localtime'), patient_id=? WHERE id=?",
            (user['id'], patient_id, reg_id)
        )
        log_activity("Patient Registration Approved", f"Registration for {reg['name']} approved by {user['role']}", "patient")
    elif action == "reject":
        execute_db(
            "UPDATE patient_registrations SET status='rejected', reviewed_by_user_id=?, reviewed_on=datetime('now', 'localtime'), reviewer_notes=? WHERE id=?",
            (user['id'], notes, reg_id)
        )
        log_activity("Patient Registration Rejected", f"Registration for {reg['name']} rejected", "patient")

    return redirect(url_for("patients", tab="pending"))


@app.route("/patients/<int:patient_id>/edit", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def edit_patient(patient_id):
    """Update patient details."""
    name = request.form.get("name", "").strip()
    age = request.form.get("age", type=int)
    gender = request.form.get("gender", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    blood_group = request.form.get("blood_group", "").strip()

    if name:
        execute_db(
            "UPDATE patients SET name=?, age=?, gender=?, phone=?, address=?, blood_group=? WHERE id=?",
            (name, age, gender, phone, address, blood_group, patient_id)
        )
        log_activity("Patient Updated", f"Patient #{patient_id} details updated", "patient")

    return redirect(url_for("patients", tab="patients"))


@app.route("/patients/visit/add", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def add_visit():
    """Log a new patient visit."""
    patient_id = request.form.get("patient_id")
    doctor_id = request.form.get("doctor_id")
    visit_date = request.form.get("visit_date", datetime.now().strftime("%Y-%m-%d"))
    visit_type = request.form.get("visit_type", "opd")
    reason = request.form.get("reason", "").strip()
    triage_level = request.form.get("triage_level", "stable") if visit_type == "emergency" else None
    status = request.form.get("status", "waiting")
    notes = request.form.get("notes", "").strip()

    if patient_id:
        execute_db(
            "INSERT INTO visits (patient_id, doctor_id, visit_date, visit_type, reason, triage_level, status, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (patient_id, doctor_id if doctor_id else None, visit_date, visit_type, reason, triage_level, status, notes)
        )

        patient = query_db("SELECT name, patient_code FROM patients WHERE id=?", (patient_id,), one=True)
        pname = patient["name"] if patient else f"Patient #{patient_id}"

        if visit_type == "emergency":
            execute_db("UPDATE patients SET status='emergency' WHERE id=?", (patient_id,))
            log_activity("Emergency Visit Logged", f"Emergency ({triage_level}) logged for {pname}", "patient")
            return redirect(url_for("patients", tab="emergency"))
        else:
            log_activity("Visit Logged", f"{visit_type.upper()} visit logged for {pname}", "patient")
            return redirect(url_for("patients", tab="visits"))

    return redirect(url_for("patients"))


@app.route("/patients/visit/<int:visit_id>/status", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def update_visit_status(visit_id):
    """Update visit status (waiting / in-treatment / discharged)."""
    new_status = request.form.get("status")
    if new_status in ["waiting", "in-treatment", "discharged"]:
        execute_db("UPDATE visits SET status=? WHERE id=?", (new_status, visit_id))

        visit = query_db("SELECT v.*, p.name FROM visits v JOIN patients p ON v.patient_id = p.id WHERE v.id=?", (visit_id,), one=True)
        if visit:
            if new_status == "discharged" and visit["visit_type"] == "emergency":
                active_em = query_db("SELECT COUNT(*) AS c FROM visits WHERE patient_id=? AND visit_type='emergency' AND status!='discharged' AND id!=?", (visit["patient_id"], visit_id), one=True)["c"]
                if active_em == 0:
                    execute_db("UPDATE patients SET status='discharged' WHERE id=?", (visit["patient_id"],))

            log_activity("Visit Status Updated", f"Visit #{visit_id} for {visit['name']} marked '{new_status}'", "patient")

    return redirect(request.referrer or url_for("patients", tab="visits"))


@app.route("/patients/<int:patient_id>")
@role_required('head_doctor', 'doctor', 'staff', 'patient')
def patient_profile(patient_id):
    """View detailed patient profile and full visit history."""
    if g.user['role'] == 'patient' and g.user['patient_id'] != patient_id:
        return render_template('403.html'), 403

    patient = query_db("SELECT * FROM patients WHERE id=?", (patient_id,), one=True)
    if not patient:
        return redirect(url_for("patients"))

    visit_history = query_db(
        "SELECT v.*, d.name AS doctor_name, d.specialization "
        "FROM visits v "
        "LEFT JOIN doctors d ON v.doctor_id = d.id "
        "WHERE v.patient_id=? "
        "ORDER BY v.visit_date DESC, v.id DESC",
        (patient_id,)
    )

    prescriptions_list = query_db(
        "SELECT pr.*, d.name AS doctor_name, "
        "       (SELECT COUNT(*) FROM prescription_items WHERE prescription_id = pr.id) AS item_count "
        "FROM prescriptions pr "
        "LEFT JOIN doctors d ON pr.doctor_id = d.id "
        "WHERE pr.patient_id=? "
        "ORDER BY pr.issued_on DESC, pr.id DESC",
        (patient_id,)
    )

    for rx in prescriptions_list:
        rx["med_items"] = query_db(
            "SELECT pi.*, m.name AS medicine_name, m.generic_name, m.form "
            "FROM prescription_items pi "
            "JOIN medicines m ON pi.medicine_id = m.id "
            "WHERE pi.prescription_id=?",
            (rx["id"],)
        )

    doctors_list = query_db("SELECT id, name, specialization FROM doctors ORDER BY name ASC")
    today_date = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "patient_profile.html",
        patient=patient,
        visit_history=visit_history,
        prescriptions=prescriptions_list,
        doctors=doctors_list,
        today_date=today_date,
    )

# ── Beds Management Routes ───────────────────────────────────────────

@app.route("/beds")
@role_required('head_doctor', 'doctor', 'staff')
def beds():
    """Beds management view with visual bed grid, ward filters, and status controls."""
    ward_filter = request.args.get("ward", "").strip()
    status_filter = request.args.get("status", "").strip()
    error_msg = request.args.get("error", "").strip()

    # Summary Card Metrics
    beds_total = query_db("SELECT COUNT(*) AS c FROM beds", one=True)["c"]
    beds_available = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='available'", one=True)["c"]
    beds_occupied = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='occupied'", one=True)["c"]
    beds_reserved = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='reserved'", one=True)["c"]
    beds_maintenance = query_db("SELECT COUNT(*) AS c FROM beds WHERE status='maintenance'", one=True)["c"]
    emergency_available = query_db(
        "SELECT COUNT(*) AS c FROM beds WHERE status='available' AND (ward LIKE '%Emergency%' OR bed_type='emergency')",
        one=True
    )["c"]

    # Ward-wise Occupancy Breakdown
    ward_breakdown = query_db(
        "SELECT ward, "
        "       COUNT(*) AS total, "
        "       SUM(CASE WHEN status='available' THEN 1 ELSE 0 END) AS available, "
        "       SUM(CASE WHEN status='occupied' THEN 1 ELSE 0 END) AS occupied, "
        "       SUM(CASE WHEN status='reserved' THEN 1 ELSE 0 END) AS reserved, "
        "       SUM(CASE WHEN status='maintenance' THEN 1 ELSE 0 END) AS maintenance "
        "FROM beds "
        "GROUP BY ward "
        "ORDER BY ward ASC"
    )

    # Filtered Beds Query
    query = (
        "SELECT b.*, p.name AS patient_name, p.patient_code, p.phone AS patient_phone "
        "FROM beds b "
        "LEFT JOIN patients p ON b.patient_id = p.id "
        "WHERE 1=1 "
    )
    params = []

    if ward_filter:
        query += "AND b.ward = ? "
        params.append(ward_filter)

    if status_filter:
        query += "AND b.status = ? "
        params.append(status_filter)

    query += "ORDER BY b.ward ASC, b.bed_number ASC"
    beds_list = query_db(query, params)

    # Group beds by ward for grid display
    grouped_beds = {}
    for bed in beds_list:
        w = bed["ward"] or "General"
        if w not in grouped_beds:
            grouped_beds[w] = []
        grouped_beds[w].append(bed)

    # List of unique wards for dropdown
    wards_rows = query_db("SELECT DISTINCT ward FROM beds ORDER BY ward ASC")
    wards_list = [r["ward"] for r in wards_rows if r["ward"]]

    # Unassigned Patients (patients without an active occupied bed)
    unassigned_patients = query_db(
        "SELECT id, name, patient_code, phone "
        "FROM patients "
        "WHERE id NOT IN (SELECT patient_id FROM beds WHERE patient_id IS NOT NULL AND status='occupied') "
        "ORDER BY name ASC"
    )

    return render_template(
        "beds.html",
        beds_total=beds_total,
        beds_available=beds_available,
        beds_occupied=beds_occupied,
        beds_reserved=beds_reserved,
        beds_maintenance=beds_maintenance,
        emergency_available=emergency_available,
        ward_breakdown=ward_breakdown,
        grouped_beds=grouped_beds,
        beds=beds_list,
        wards=wards_list,
        unassigned_patients=unassigned_patients,
        ward_filter=ward_filter,
        status_filter=status_filter,
        error_msg=error_msg,
    )


@app.route("/beds/add", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def add_bed():
    """Add a new hospital bed."""
    bed_number = request.form.get("bed_number", "").strip().upper()
    ward = request.form.get("ward", "General").strip()
    bed_type = request.form.get("bed_type", "general").strip()
    notes = request.form.get("notes", "").strip()

    if bed_number and ward:
        existing = query_db("SELECT id FROM beds WHERE bed_number=?", (bed_number,), one=True)
        if not existing:
            execute_db(
                "INSERT INTO beds (bed_number, ward, bed_type, status, notes) VALUES (?, ?, ?, 'available', ?)",
                (bed_number, ward, bed_type, notes)
            )
            log_activity("Bed Added", f"Bed {bed_number} ({ward}) registered", "bed")

    return redirect(url_for("beds"))


@app.route("/beds/<int:bed_id>/assign", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def assign_bed(bed_id):
    """Assign an available or reserved bed to a patient."""
    patient_id = (
        request.form.get("patient_id", type=int) 
        if request.form.get("patient_id") 
        else (request.json.get("patient_id") if request.is_json and request.json else None)
    )

    bed = query_db("SELECT * FROM beds WHERE id=?", (bed_id,), one=True)
    if not bed:
        if request.is_json:
            return jsonify(error="Bed not found"), 404
        return redirect(url_for("beds"))

    # VALIDATION 1: Prevent assigning a bed that is already occupied
    if bed["status"] == "occupied":
        if request.is_json:
            return jsonify(error="Bed is already occupied"), 400
        return redirect(url_for("beds", error="bed_occupied"))

    if patient_id:
        # VALIDATION 2: Prevent assigning one patient to two beds
        existing_bed = query_db(
            "SELECT id, bed_number FROM beds WHERE patient_id=? AND status='occupied' AND id!=?",
            (patient_id, bed_id),
            one=True
        )
        if existing_bed:
            if request.is_json:
                return jsonify(error=f"Patient is already assigned to bed {existing_bed['bed_number']}"), 400
            return redirect(url_for("beds", error="patient_already_assigned"))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        execute_db(
            "UPDATE beds SET status='occupied', patient_id=?, assigned_on=? WHERE id=?",
            (patient_id, now_str, bed_id)
        )
        execute_db("UPDATE patients SET status='admitted' WHERE id=?", (patient_id,))

        patient = query_db("SELECT name FROM patients WHERE id=?", (patient_id,), one=True)
        pname = patient["name"] if patient else f"Patient #{patient_id}"
        log_activity("Bed Assigned", f"Bed {bed['bed_number']} assigned to {pname}", "bed")

    return redirect(url_for("beds"))


@app.route("/beds/<int:bed_id>/release", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def release_bed(bed_id):
    """Release/Discharge a bed."""
    bed = query_db("SELECT * FROM beds WHERE id=?", (bed_id,), one=True)
    if bed:
        pid = bed["patient_id"]
        execute_db("UPDATE beds SET status='available', patient_id=NULL, assigned_on=NULL WHERE id=?", (bed_id,))
        if pid:
            execute_db("UPDATE patients SET status='discharged' WHERE id=?", (pid,))
        log_activity("Bed Released", f"Bed {bed['bed_number']} marked available", "bed")

    return redirect(url_for("beds"))


@app.route("/beds/<int:bed_id>/status", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def update_bed_status(bed_id):
    """Update bed status (reserved / maintenance / available)."""
    new_status = request.form.get("status")
    notes = request.form.get("notes", "").strip()

    if new_status in ["available", "reserved", "maintenance"]:
        if new_status in ["available", "maintenance"]:
            execute_db("UPDATE beds SET status=?, patient_id=NULL, assigned_on=NULL, notes=? WHERE id=?", (new_status, notes, bed_id))
        else:
            execute_db("UPDATE beds SET status=?, notes=? WHERE id=?", (new_status, notes, bed_id))

        bed = query_db("SELECT bed_number FROM beds WHERE id=?", (bed_id,), one=True)
        bnum = bed["bed_number"] if bed else f"Bed #{bed_id}"
        log_activity("Bed Status Change", f"Bed {bnum} set to '{new_status}'", "bed")

    return redirect(url_for("beds"))

# ── Doctor Management Routes ──────────────────────────────────────────


@app.route("/staff/add", methods=["POST"])
@role_required('head_doctor', 'doctor')
def add_staff():
    name = request.form.get("name", "").strip()
    staff_code = request.form.get("staff_code", "").strip()
    staff_role = request.form.get("staff_role", "").strip()
    department = request.form.get("department_or_ward", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "available").strip()
    shift = request.form.get("shift", "morning").strip()

    if name and staff_role:
        execute_db(
            "INSERT INTO staff_members (staff_code, name, staff_role, department_or_ward, phone, status, shift) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (staff_code, name, staff_role, department, phone, status, shift)
        )
        log_activity("Staff Added", f"{name} ({staff_role}) registered", "staff")

    return redirect(url_for("staff", tab="roster"))

@app.route("/staff/<int:staff_id>/edit", methods=["POST"])
@role_required('head_doctor', 'doctor')
def edit_staff(staff_id):
    name = request.form.get("name", "").strip()
    staff_code = request.form.get("staff_code", "").strip()
    staff_role = request.form.get("staff_role", "").strip()
    department = request.form.get("department_or_ward", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "available").strip()
    shift = request.form.get("shift", "morning").strip()

    if name and staff_role:
        execute_db(
            "UPDATE staff_members SET staff_code=?, name=?, staff_role=?, department_or_ward=?, phone=?, status=?, shift=? WHERE id=?",
            (staff_code, name, staff_role, department, phone, status, shift, staff_id)
        )
        log_activity("Staff Edited", f"{name} details updated", "staff")

    return redirect(url_for("staff", tab="roster"))

@app.route("/doctors")
@role_required('head_doctor', 'doctor', 'staff')
def doctors():
    """Doctors management view with roster, attendance, and leave requests."""
    auto_process_attendance()
    active_tab = request.args.get("tab", "roster")
    search_query = request.args.get("q", "").strip()
    spec_filter = request.args.get("specialization", "").strip()
    status_filter = request.args.get("status", "").strip()
    shift_filter = request.args.get("shift", "").strip()

    if active_tab == 'leaves' and g.user['role'] == 'staff':
        return render_template('403.html'), 403

    # Stat counters
    doctors_total = query_db("SELECT COUNT(*) AS c FROM doctors", one=True)["c"]
    doctors_available = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='available'", one=True)["c"]
    doctors_busy = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='busy'", one=True)["c"]
    doctors_offduty = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='off-duty'", one=True)["c"]
    doctors_onleave = query_db("SELECT COUNT(*) AS c FROM doctors WHERE status='on-leave'", one=True)["c"]
    pending_leaves_count = query_db("SELECT COUNT(*) AS c FROM doctor_leaves WHERE status='pending'", one=True)["c"]

    # Filtered Doctor list query
    query = "SELECT * FROM doctors WHERE 1=1"
    params = []

    if search_query:
        query += " AND (name LIKE ? OR specialization LIKE ? OR phone LIKE ? OR email LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term, term])

    if spec_filter:
        query += " AND specialization = ?"
        params.append(spec_filter)

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    if shift_filter:
        query += " AND shift = ?"
        params.append(shift_filter)

    query += " ORDER BY name ASC"
    doctors_list = query_db(query, params)

    # Unique specializations list for filter dropdown
    specializations_rows = query_db("SELECT DISTINCT specialization FROM doctors ORDER BY specialization ASC")
    specializations = [r["specialization"] for r in specializations_rows if r["specialization"]]

    # Attendance query for today
    today_date = datetime.now().strftime("%Y-%m-%d")
    att_date = request.args.get("att_date", today_date).strip()

    attendance_list = query_db(
        "SELECT d.id AS doctor_id, d.name AS doctor_name, d.specialization, d.shift, d.status AS current_status, "
        "       a.id AS attendance_id, a.date, a.status AS att_status, a.check_in, a.check_out, a.notes "
        "FROM doctors d "
        "LEFT JOIN attendance a ON d.id = a.doctor_id AND a.date = ? "
        "ORDER BY d.name ASC",
        (att_date,)
    )

    # Leave requests query based on role
    leave_sql = (
        "SELECT l.*, d.name AS doctor_name, d.specialization, d.phone, d.email "
        "FROM doctor_leaves l "
        "JOIN doctors d ON l.doctor_id = d.id "
    )
    leave_params = []
    if g.user['role'] == 'doctor':
        leave_sql += "WHERE l.doctor_id = ? "
        leave_params.append(g.user['doctor_id'] or 0)
    leave_sql += "ORDER BY CASE WHEN l.status='pending' THEN 0 ELSE 1 END, l.applied_on DESC"

    leave_requests = query_db(leave_sql, leave_params)

    
    shift_info = None
    if g.user and g.user['doctor_id']:
        shift_info = get_doctor_shift_info(g.user['doctor_id'])
        
    return render_template(
        "doctors.html",
        shift_info=shift_info,

        active_tab=active_tab,
        doctors=doctors_list,
        doctors_total=doctors_total,
        doctors_available=doctors_available,
        doctors_busy=doctors_busy,
        doctors_offduty=doctors_offduty,
        doctors_onleave=doctors_onleave,
        pending_leaves_count=pending_leaves_count,
        specializations=specializations,
        search_query=search_query,
        spec_filter=spec_filter,
        status_filter=status_filter,
        shift_filter=shift_filter,
        attendance_list=attendance_list,
        att_date=att_date,
        today_date=today_date,
        leave_requests=leave_requests,
    )


@app.route("/doctors/add", methods=["POST"])
@role_required('head_doctor')
def add_doctor():
    """Add a new doctor to the roster."""
    name = request.form.get("name", "").strip()
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "available").strip()
    shift = request.form.get("shift", "morning").strip()

    if name and specialization:
        execute_db(
            "INSERT INTO doctors (name, specialization, phone, email, status, shift) VALUES (?, ?, ?, ?, ?, ?)",
            (name, specialization, phone, email, status, shift)
        )
        log_activity("Doctor Added", f"Dr. {name} ({specialization}) registered", "doctor")

    return redirect(url_for("doctors", tab="roster"))


@app.route("/doctors/<int:doctor_id>/edit", methods=["POST"])
@role_required('head_doctor')
def edit_doctor(doctor_id):
    """Update existing doctor details."""
    name = request.form.get("name", "").strip()
    specialization = request.form.get("specialization", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "available").strip()
    shift = request.form.get("shift", "morning").strip()

    if name:
        execute_db(
            "UPDATE doctors SET name=?, specialization=?, phone=?, email=?, status=?, shift=? WHERE id=?",
            (name, specialization, phone, email, status, shift, doctor_id)
        )
        log_activity("Doctor Updated", f"Dr. {name} details updated", "doctor")

    return redirect(url_for("doctors", tab="roster"))


@app.route("/doctors/<int:doctor_id>/status", methods=["POST"])
@role_required('head_doctor', 'staff')
def update_doctor_status(doctor_id):
    """Quick update of doctor duty status."""
    new_status = request.form.get("status") or (request.json.get("status") if request.is_json else None)

    if new_status in ["available", "busy", "off-duty", "on-leave"]:
        execute_db("UPDATE doctors SET status=? WHERE id=?", (new_status, doctor_id))
        doc = query_db("SELECT name FROM doctors WHERE id=?", (doctor_id,), one=True)
        doc_name = doc["name"] if doc else f"Doctor #{doctor_id}"
        log_activity("Status Change", f"{doc_name} status changed to '{new_status}'", "doctor")

    if request.is_json:
        return jsonify(success=True, status=new_status)
    return redirect(request.referrer or url_for("doctors", tab="roster"))




@app.route("/doctors/attendance/reset_demo", methods=["POST"])
@role_required('head_doctor')
def reset_demo_attendance():
    """Reset today's attendance for a specific doctor in demo mode."""
    if not ATTENDANCE_DEMO_MODE:
        return render_template('403.html'), 403
        
    doctor_id = request.form.get("doctor_id")
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    if doctor_id:
        # Also need to consider night shift crossing midnight logic? 
        # The simplest is to just delete any record for this doctor today.
        execute_db("DELETE FROM attendance WHERE doctor_id=? AND date=?", (doctor_id, date_str))
        
        # We should also reset the doctor's status to their default based on shift or just available?
        # A simple reset is fine.
        execute_db("UPDATE doctors SET status='available' WHERE id=?", (doctor_id,))
        
        doc = query_db("SELECT name FROM doctors WHERE id=?", (doctor_id,), one=True)
        doc_name = doc['name'] if doc else f"Doctor #{doctor_id}"
        log_activity("Demo Reset", f"Reset today's attendance for {doc_name}", "doctor")
        
        from flask import flash
        flash(f"Successfully reset today's attendance for {doc_name}.", "success")
        
    return redirect(url_for("doctors", tab="attendance"))

@app.route("/doctors/attendance/self_mark", methods=["POST"])
@role_required('doctor')
def self_mark_attendance():
    """Doctor self-marking attendance."""
    user = get_current_user()
    doctor_id = user['doctor_id'] if user else None
    if not doctor_id:
        return "Not authorized", 403
        
    now = datetime.now()
    
    # Get doctor shift
    doc = query_db("SELECT shift FROM doctors WHERE id=?", (doctor_id,), one=True)
    if not doc:
        return "Doctor not found", 404
        
    shift = doc['shift'] or 'morning'
    shift_start_str = SHIFT_STARTS.get(shift, "08:00")
    try:
        start_hour, start_minute = map(int, shift_start_str.split(':'))
    except:
        start_hour, start_minute = 8, 0
        
    shift_start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    
    # Handle night shift crossing midnight
    if shift == 'night' and now.hour < 12:
        shift_start_time -= timedelta(days=1)
        
    date_str = shift_start_time.strftime("%Y-%m-%d")
    
    # Check if already marked today
    existing = query_db("SELECT id FROM attendance WHERE doctor_id=? AND date=?", (doctor_id, date_str), one=True)
    if existing:
        return "Already marked today", 400
        
    window_end_time = shift_start_time + timedelta(minutes=ATTENDANCE_WINDOW_MINUTES)
    
    if not ATTENDANCE_DEMO_MODE:
        if now < shift_start_time or now > window_end_time:
            return "Check-in window is closed", 403
            
    # Check if on approved leave today
    leave = query_db(
        "SELECT id FROM doctor_leaves WHERE doctor_id=? AND status='approved' AND start_date <= ? AND end_date >= ?",
        (doctor_id, date_str, date_str), one=True
    )
    if leave:
        return "You are on approved leave today", 403
            
    # Mark present
    check_in_time = now.strftime("%H:%M")
    execute_db(
        "INSERT INTO attendance (doctor_id, date, status, check_in, notes) VALUES (?, ?, 'present', ?, 'Self-marked')",
        (doctor_id, date_str, check_in_time)
    )
    execute_db("UPDATE doctors SET status='available' WHERE id=?", (doctor_id,))
    
    log_activity("Attendance Self-Marked", f"Doctor {doctor_id} self-marked attendance for {date_str}", "doctor")
    
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/doctors/attendance/mark", methods=["POST"])
@role_required('head_doctor')
def mark_attendance():
    """Mark check-in / check-out / attendance status for a doctor."""
    doctor_id = request.form.get("doctor_id")
    date = request.form.get("date", datetime.now().strftime("%Y-%m-%d"))
    att_status = request.form.get("status", "present")
    check_in = request.form.get("check_in", "")
    check_out = request.form.get("check_out", "")
    notes = request.form.get("notes", "").strip()
    
    if notes:
        notes += " (Updated by head doctor)"
    else:
        notes = "Updated by head doctor"

    if doctor_id:
        existing = query_db("SELECT id FROM attendance WHERE doctor_id=? AND date=?", (doctor_id, date), one=True)
        if existing:
            execute_db(
                "UPDATE attendance SET status=?, check_in=?, check_out=?, notes=? WHERE doctor_id=? AND date=?",
                (att_status, check_in, check_out, notes, doctor_id, date)
            )
        else:
            execute_db(
                "INSERT INTO attendance (doctor_id, date, status, check_in, check_out, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (doctor_id, date, att_status, check_in, check_out, notes)
            )

        if date == datetime.now().strftime("%Y-%m-%d"):
            if att_status == "on-leave":
                execute_db("UPDATE doctors SET status='on-leave' WHERE id=?", (doctor_id,))
            elif att_status == "absent":
                execute_db("UPDATE doctors SET status='off-duty' WHERE id=?", (doctor_id,))
            elif att_status == "present":
                current = query_db("SELECT status FROM doctors WHERE id=?", (doctor_id,), one=True)
                if current and current["status"] in ["off-duty", "on-leave"]:
                    execute_db("UPDATE doctors SET status='available' WHERE id=?", (doctor_id,))

        doc = query_db("SELECT name FROM doctors WHERE id=?", (doctor_id,), one=True)
        doc_name = doc["name"] if doc else f"Doctor #{doctor_id}"
        log_activity("Attendance Marked", f"Attendance '{att_status}' recorded for {doc_name} on {date}", "doctor")

    return redirect(url_for("doctors", tab="attendance", att_date=date))


@app.route("/doctors/leave/request", methods=["POST"])
@role_required('head_doctor', 'doctor')
def request_leave():
    """Submit a doctor leave request."""
    doctor_id = request.form.get("doctor_id")
    if g.user['role'] == 'doctor' and g.user['doctor_id']:
        doctor_id = g.user['doctor_id']

    leave_type = request.form.get("leave_type", "casual")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    reason = request.form.get("reason", "").strip()

    if doctor_id and start_date and end_date:
        execute_db(
            "INSERT INTO doctor_leaves (doctor_id, leave_type, start_date, end_date, reason, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (doctor_id, leave_type, start_date, end_date, reason)
        )
        doc = query_db("SELECT name FROM doctors WHERE id=?", (doctor_id,), one=True)
        doc_name = doc["name"] if doc else f"Doctor #{doctor_id}"
        log_activity("Leave Submitted", f"Leave request submitted by {doc_name} ({start_date} to {end_date})", "doctor")

    return redirect(url_for("doctors", tab="leaves"))


@app.route("/doctors/leave/<int:leave_id>/action", methods=["POST"])
@role_required('head_doctor')
def review_leave(leave_id):
    """Approve or Reject a doctor leave request."""
    action = request.form.get("action")
    reviewer_notes = request.form.get("reviewer_notes", "").strip()

    if action in ["approve", "reject"]:
        new_status = "approved" if action == "approve" else "rejected"
        execute_db(
            "UPDATE doctor_leaves SET status=?, reviewed_by='Admin', reviewer_notes=? WHERE id=?",
            (new_status, reviewer_notes, leave_id)
        )

        leave = query_db("SELECT * FROM doctor_leaves WHERE id=?", (leave_id,), one=True)
        if leave:
            doc = query_db("SELECT name FROM doctors WHERE id=?", (leave["doctor_id"],), one=True)
            doc_name = doc["name"] if doc else f"Doctor #{leave['doctor_id']}"

            today = datetime.now().strftime("%Y-%m-%d")
            if action == "approve" and leave["start_date"] <= today <= leave["end_date"]:
                execute_db("UPDATE doctors SET status='on-leave' WHERE id=?", (leave["doctor_id"],))

            log_activity("Leave Reviewed", f"Leave request for {doc_name} was {new_status}", "doctor")

    return redirect(url_for("doctors", tab="leaves"))

# ── Medicines & Inventory Routes ───────────────────────────────────────

@app.route("/medicines")
@role_required('head_doctor', 'doctor', 'staff')
def medicines():
    """Medicines & Inventory management view with search, filters, low stock alerts, restock & dispense."""
    search_query = request.args.get("q", "").strip()
    category_filter = request.args.get("category", "").strip()
    status_filter = request.args.get("status", "").strip()
    error_msg = request.args.get("error", "").strip()

    today_date = datetime.now().strftime("%Y-%m-%d")
    expiring_threshold = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    # Summary Metrics
    total_medicines = query_db("SELECT COUNT(*) AS c FROM medicines", one=True)["c"]
    low_stock_count = query_db("SELECT COUNT(*) AS c FROM medicines WHERE quantity > 0 AND quantity <= COALESCE(reorder_level, 20)", one=True)["c"]
    out_of_stock_count = query_db("SELECT COUNT(*) AS c FROM medicines WHERE quantity = 0", one=True)["c"]
    expiring_soon_count = query_db("SELECT COUNT(*) AS c FROM medicines WHERE expiry_date IS NOT NULL AND expiry_date <= ?", (expiring_threshold,), one=True)["c"]

    # Low Stock & Expiry Alert Panel List
    alerts_list = query_db(
        "SELECT * FROM medicines "
        "WHERE quantity <= COALESCE(reorder_level, 20) OR (expiry_date IS NOT NULL AND expiry_date <= ?) "
        "ORDER BY quantity ASC, expiry_date ASC",
        (expiring_threshold,)
    )

    # Main Filtered Medicines Query
    query = "SELECT * FROM medicines WHERE 1=1 "
    params = []

    if search_query:
        query += "AND (name LIKE ? OR generic_name LIKE ? OR supplier LIKE ? OR category LIKE ?) "
        term = f"%{search_query}%"
        params.extend([term, term, term, term])

    if category_filter:
        query += "AND category = ? "
        params.append(category_filter)

    if status_filter == "in-stock":
        query += "AND quantity > COALESCE(reorder_level, 20) "
    elif status_filter == "low-stock":
        query += "AND quantity > 0 AND quantity <= COALESCE(reorder_level, 20) "
    elif status_filter == "out-of-stock":
        query += "AND quantity = 0 "
    elif status_filter == "expiring-soon":
        query += "AND expiry_date IS NOT NULL AND expiry_date <= ? "
        params.append(expiring_threshold)

    query += "ORDER BY name ASC"
    medicines_list = query_db(query, params)

    # Categories list for filter dropdown
    categories_rows = query_db("SELECT DISTINCT category FROM medicines WHERE category IS NOT NULL AND category!='' ORDER BY category ASC")
    categories_list = [r["category"] for r in categories_rows]

    return render_template(
        "medicines.html",
        total_medicines=total_medicines,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        expiring_soon_count=expiring_soon_count,
        alerts_list=alerts_list,
        medicines=medicines_list,
        categories=categories_list,
        search_query=search_query,
        category_filter=category_filter,
        status_filter=status_filter,
        error_msg=error_msg,
        today_date=today_date,
        expiring_threshold=expiring_threshold,
    )


@app.route("/medicines/add", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def add_medicine():
    """Add a new medicine to inventory."""
    name = request.form.get("name", "").strip()
    generic_name = request.form.get("generic_name", "").strip()
    category = request.form.get("category", "General").strip()
    form = request.form.get("form", "tablet").strip()
    strength = request.form.get("strength", "").strip()
    quantity = request.form.get("quantity", type=int, default=0)
    reorder_level = request.form.get("reorder_level", type=int, default=20)
    unit_price = request.form.get("unit_price", type=float, default=0.0)
    expiry_date = request.form.get("expiry_date", "").strip()
    supplier = request.form.get("supplier", "").strip()

    if name:
        status = "out-of-stock" if quantity == 0 else ("low-stock" if quantity <= reorder_level else "in-stock")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        med_id = execute_db(
            "INSERT INTO medicines (name, generic_name, category, form, strength, quantity, reorder_level, unit_price, expiry_date, supplier, status, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, generic_name, category, form, strength, quantity, reorder_level, unit_price, expiry_date, supplier, status, now_str)
        )

        if quantity > 0:
            execute_db(
                "INSERT INTO stock_log (medicine_id, change_type, quantity_change, note, logged_on) VALUES (?, 'restock', ?, 'Initial stock added', ?)",
                (med_id, quantity, now_str)
            )

        log_activity("Medicine Added", f"{name} ({strength}) added to inventory", "medicine")

    return redirect(url_for("medicines"))


@app.route("/medicines/<int:med_id>/edit", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def edit_medicine(med_id):
    """Update medicine parameters."""
    name = request.form.get("name", "").strip()
    generic_name = request.form.get("generic_name", "").strip()
    category = request.form.get("category", "").strip()
    form = request.form.get("form", "").strip()
    strength = request.form.get("strength", "").strip()
    reorder_level = request.form.get("reorder_level", type=int, default=20)
    unit_price = request.form.get("unit_price", type=float, default=0.0)
    expiry_date = request.form.get("expiry_date", "").strip()
    supplier = request.form.get("supplier", "").strip()

    if name:
        med = query_db("SELECT quantity FROM medicines WHERE id=?", (med_id,), one=True)
        qty = med["quantity"] if med else 0
        status = "out-of-stock" if qty == 0 else ("low-stock" if qty <= reorder_level else "in-stock")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        execute_db(
            "UPDATE medicines SET name=?, generic_name=?, category=?, form=?, strength=?, reorder_level=?, unit_price=?, expiry_date=?, supplier=?, status=?, last_updated=? WHERE id=?",
            (name, generic_name, category, form, strength, reorder_level, unit_price, expiry_date, supplier, status, now_str, med_id)
        )
        log_activity("Medicine Updated", f"{name} details updated", "medicine")

    return redirect(url_for("medicines"))


@app.route("/medicines/<int:med_id>/restock", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def restock_medicine(med_id):
    """Restock medicine stock."""
    qty_add = request.form.get("quantity_change", type=int) or request.form.get("quantity", type=int, default=0)
    if not qty_add and request.is_json and request.json:
        qty_add = request.json.get("quantity_change") or request.json.get("quantity")

    note = request.form.get("note", "Restocked batch").strip() if request.form else "Restocked batch"

    if qty_add and qty_add > 0:
        med = query_db("SELECT * FROM medicines WHERE id=?", (med_id,), one=True)
        if med:
            new_qty = med["quantity"] + qty_add
            reorder = med["reorder_level"] or 20
            new_status = "low-stock" if new_qty <= reorder else "in-stock"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            execute_db("UPDATE medicines SET quantity=?, status=?, last_updated=? WHERE id=?", (new_qty, new_status, now_str, med_id))
            execute_db("INSERT INTO stock_log (medicine_id, change_type, quantity_change, note, logged_on) VALUES (?, 'restock', ?, ?, ?)", (med_id, qty_add, note, now_str))

            log_activity("Stock Restocked", f"{med['name']} restocked +{qty_add} units", "medicine")

    return redirect(url_for("medicines"))


@app.route("/medicines/<int:med_id>/dispense", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def dispense_medicine(med_id):
    """Dispense medicine stock."""
    qty_sub = request.form.get("quantity_change", type=int) or request.form.get("quantity", type=int, default=0)
    if not qty_sub and request.is_json and request.json:
        qty_sub = request.json.get("quantity_change") or request.json.get("quantity")

    note = request.form.get("note", "Dispensed to patient").strip() if request.form else "Dispensed to patient"

    med = query_db("SELECT * FROM medicines WHERE id=?", (med_id,), one=True)
    if not med:
        if request.is_json:
            return jsonify(error="Medicine not found"), 404
        return redirect(url_for("medicines"))

    current_qty = med["quantity"]

    # EDGE CASE VALIDATION: Reject dispense if requested > current_qty (negative stock)
    if qty_sub is None or qty_sub <= 0 or qty_sub > current_qty:
        if request.is_json:
            return jsonify(error=f"Cannot dispense {qty_sub} units. Available stock is only {current_qty}."), 400
        return redirect(url_for("medicines", error="insufficient_stock"))

    new_qty = current_qty - qty_sub
    reorder = med["reorder_level"] or 20
    new_status = "out-of-stock" if new_qty == 0 else ("low-stock" if new_qty <= reorder else "in-stock")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    execute_db("UPDATE medicines SET quantity=?, status=?, last_updated=? WHERE id=?", (new_qty, new_status, now_str, med_id))
    execute_db("INSERT INTO stock_log (medicine_id, change_type, quantity_change, note, logged_on) VALUES (?, 'dispense', ?, ?, ?)", (med_id, -qty_sub, note, now_str))

    log_activity("Stock Dispensed", f"{med['name']} dispensed -{qty_sub} units", "medicine")

    if request.is_json:
        return jsonify(success=True, new_quantity=new_qty, status=new_status)
    return redirect(url_for("medicines"))


@app.route("/medicines/<int:med_id>")
@role_required('head_doctor', 'doctor', 'staff')
def medicine_detail(med_id):
    """View medicine detail and stock log history."""
    medicine = query_db("SELECT * FROM medicines WHERE id=?", (med_id,), one=True)
    if not medicine:
        return redirect(url_for("medicines"))

    logs = query_db("SELECT * FROM stock_log WHERE medicine_id=? ORDER BY logged_on DESC, id DESC", (med_id,))
    today_date = datetime.now().strftime("%Y-%m-%d")

    return render_template("medicine_detail.html", medicine=medicine, logs=logs, today_date=today_date)

# ── Smart Prescriptions Management Routes ───────────────────────────

@app.route("/prescriptions")
@role_required('head_doctor', 'doctor', 'staff')
def prescriptions():
    """Prescriptions list view with search, filters, and summary metrics."""
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()

    today_date = datetime.now().strftime("%Y-%m-%d")

    # Summary Card Metrics
    total_count = query_db("SELECT COUNT(*) AS c FROM prescriptions", one=True)["c"]
    active_today_count = query_db(
        "SELECT COUNT(*) AS c FROM prescriptions WHERE status='active' AND date(issued_on) = ?",
        (today_date,),
        one=True
    )["c"]

    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    followups_due_week_count = query_db(
        "SELECT COUNT(*) AS c FROM prescriptions WHERE status='active' AND follow_up_date BETWEEN ? AND ?",
        (today_date, next_week),
        one=True
    )["c"]

    sql = (
        "SELECT pr.*, p.name AS patient_name, p.patient_code, p.age, p.gender, "
        "       d.name AS doctor_name, d.specialization, "
        "       (SELECT COUNT(*) FROM prescription_items WHERE prescription_id = pr.id) AS item_count "
        "FROM prescriptions pr "
        "JOIN patients p ON pr.patient_id = p.id "
        "LEFT JOIN doctors d ON pr.doctor_id = d.id "
        "WHERE 1=1 "
    )
    params = []

    if search_query:
        sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR pr.rx_code LIKE ?) "
        term = f"%{search_query}%"
        params.extend([term, term, term])

    if status_filter and status_filter != "all":
        sql += "AND pr.status = ? "
        params.append(status_filter)

    sql += "ORDER BY pr.issued_on DESC, pr.id DESC"
    prescriptions_list = query_db(sql, params)

    for rx in prescriptions_list:
        rx["med_items"] = query_db(
            "SELECT pi.*, m.name AS medicine_name, m.generic_name, m.form "
            "FROM prescription_items pi "
            "JOIN medicines m ON pi.medicine_id = m.id "
            "WHERE pi.prescription_id=?",
            (rx["id"],)
        )

    return render_template(
        "prescriptions.html",
        prescriptions=prescriptions_list,
        total_count=total_count,
        active_today_count=active_today_count,
        followups_due_week_count=followups_due_week_count,
        search_query=search_query,
        status_filter=status_filter,
        today_date=today_date,
    )


@app.route("/prescriptions/new")
@role_required('head_doctor', 'doctor')
def new_prescription():
    """Render new prescription creation form."""
    patient_id = request.args.get("patient_id", type=int)

    patients_list = query_db("SELECT id, patient_code, name, age, gender FROM patients ORDER BY name ASC")
    doctors_list = query_db("SELECT id, name, specialization FROM doctors WHERE status != 'off-duty' ORDER BY name ASC")
    if not doctors_list:
        doctors_list = query_db("SELECT id, name, specialization FROM doctors ORDER BY name ASC")

    medicines_list = query_db("SELECT id, name, generic_name, form, strength, quantity, status FROM medicines ORDER BY name ASC")

    patient_visits = []
    if patient_id:
        patient_visits = query_db("SELECT id, visit_date, visit_type, reason FROM visits WHERE patient_id=? ORDER BY visit_date DESC", (patient_id,))

    today_date = datetime.now().strftime("%Y-%m-%d")

    return render_template(
        "prescription_new.html",
        patients=patients_list,
        doctors=doctors_list,
        medicines=medicines_list,
        selected_patient_id=patient_id,
        patient_visits=patient_visits,
        today_date=today_date,
    )


@app.route("/prescriptions/add", methods=["POST"])
@role_required('head_doctor', 'doctor')
def add_prescription():
    """Create a new prescription with validation and dose schedule generation."""
    from prescription_utils import validate_dosage_pattern, generate_dose_schedule_rows

    patient_id = request.form.get("patient_id", type=int)
    doctor_id = request.form.get("doctor_id", type=int)
    visit_id = request.form.get("visit_id", type=int) or None
    diagnosis_note = request.form.get("diagnosis_note", "").strip()
    general_advice = request.form.get("general_advice", "").strip()
    follow_up_date = request.form.get("follow_up_date", "").strip() or None

    if not patient_id or not doctor_id:
        if request.is_json:
            return jsonify(error="Patient and Doctor are required."), 400
        return redirect(url_for("new_prescription", error="Patient and Doctor are required."))

    medicine_ids = request.form.getlist("medicine_id[]")
    dosage_patterns = request.form.getlist("dosage_pattern[]")
    food_timings = request.form.getlist("food_timing[]")
    duration_days_list = request.form.getlist("duration_days[]")
    special_instructions_list = request.form.getlist("special_instructions[]")

    if not medicine_ids:
        if request.is_json:
            return jsonify(error="At least one medicine must be prescribed."), 400
        return redirect(url_for("new_prescription", error="At least one medicine must be prescribed."))

    validated_items = []
    warnings = []

    for i in range(len(medicine_ids)):
        m_id_str = medicine_ids[i]
        if not m_id_str:
            continue
        m_id = int(m_id_str)
        pattern = dosage_patterns[i].strip() if i < len(dosage_patterns) else "1-0-1"
        food_timing = food_timings[i].strip() if i < len(food_timings) else "after food"
        dur = int(duration_days_list[i]) if (i < len(duration_days_list) and duration_days_list[i].isdigit()) else 5
        instr = special_instructions_list[i].strip() if i < len(special_instructions_list) else ""

        is_valid, _ = validate_dosage_pattern(pattern)
        if not is_valid:
            err_msg = f"Invalid dosage pattern '{pattern}'. Must be 3 dash-separated numbers (e.g. 1-0-1 or 0.5-0-1)."
            if request.is_json:
                return jsonify(error=err_msg), 400
            return redirect(url_for("new_prescription", error=err_msg, patient_id=patient_id))

        med = query_db("SELECT id, name, form, quantity FROM medicines WHERE id=?", (m_id,), one=True)
        if med and med["quantity"] == 0:
            warnings.append(f"Medicine '{med['name']}' is out of stock (0 remaining). Prescribed with warning.")

        form = med["form"] if med and med["form"] else "tablet"

        validated_items.append({
            "medicine_id": m_id,
            "dosage_pattern": pattern,
            "food_timing": food_timing,
            "duration_days": dur,
            "special_instructions": instr,
            "form": form
        })

    if not validated_items:
        if request.is_json:
            return jsonify(error="No valid medicines provided."), 400
        return redirect(url_for("new_prescription", error="No valid medicines provided."))

    count_row = query_db("SELECT COUNT(*) AS c FROM prescriptions", one=True)
    next_num = (count_row["c"] or 0) + 2001
    rx_code = f"RX-{next_num}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rx_id = execute_db(
        "INSERT INTO prescriptions (rx_code, patient_id, doctor_id, visit_id, issued_on, diagnosis_note, general_advice, follow_up_date, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
        (rx_code, patient_id, doctor_id, visit_id, now_str, diagnosis_note, general_advice, follow_up_date)
    )

    start_date_str = now_str[:10]

    for item in validated_items:
        item_id = execute_db(
            "INSERT INTO prescription_items (prescription_id, medicine_id, dosage_pattern, food_timing, duration_days, special_instructions) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rx_id, item["medicine_id"], item["dosage_pattern"], item["food_timing"], item["duration_days"], item["special_instructions"])
        )

        schedules = generate_dose_schedule_rows(item_id, item["dosage_pattern"], item["form"], start_date_str, item["duration_days"])
        for sch in schedules:
            execute_db(
                "INSERT INTO dose_schedule (prescription_item_id, dose_time_label, dose_time, quantity, start_date, end_date) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                sch
            )

    patient = query_db("SELECT name FROM patients WHERE id=?", (patient_id,), one=True)
    p_name = patient["name"] if patient else f"Patient #{patient_id}"
    log_activity("Prescription Created", f"{rx_code} issued for {p_name} ({len(validated_items)} medicines)", "medicine")

    return redirect(url_for("view_prescription", prescription_id=rx_id))


@app.route("/prescriptions/<int:prescription_id>")
@role_required('head_doctor', 'doctor', 'staff', 'patient')
def view_prescription(prescription_id):
    """Patient-friendly view of prescription with dosage schedule and English/Hindi toggle."""
    from prescription_utils import format_dosage_slots, FOOD_TIMING_TRANSLATIONS

    rx = query_db(
        "SELECT pr.*, p.name AS patient_name, p.patient_code, p.age, p.gender, p.blood_group, p.phone, "
        "       d.name AS doctor_name, d.specialization, d.phone AS doctor_phone "
        "FROM prescriptions pr "
        "JOIN patients p ON pr.patient_id = p.id "
        "LEFT JOIN doctors d ON pr.doctor_id = d.id "
        "WHERE pr.id=?",
        (prescription_id,),
        one=True
    )
    if not rx:
        return redirect(url_for("prescriptions"))

    if g.user['role'] == 'patient' and rx['patient_id'] != g.user['patient_id']:
        return render_template('403.html'), 403

    items_raw = query_db(
        "SELECT pi.*, m.name AS medicine_name, m.generic_name, m.form, m.strength "
        "FROM prescription_items pi "
        "JOIN medicines m ON pi.medicine_id = m.id "
        "WHERE pi.prescription_id=?",
        (prescription_id,)
    )

    items = []
    for it in items_raw:
        form = it["form"] or "tablet"
        slots = format_dosage_slots(it["dosage_pattern"], form)
        food_timing_en, food_timing_hi = FOOD_TIMING_TRANSLATIONS.get(
            it["food_timing"].lower() if it["food_timing"] else "after food",
            ("After food", "खाने के बाद")
        )

        schedules = query_db(
            "SELECT * FROM dose_schedule WHERE prescription_item_id=? ORDER BY id ASC",
            (it["id"],)
        )

        items.append({
            "id": it["id"],
            "medicine_name": it["medicine_name"],
            "generic_name": it["generic_name"],
            "form": form,
            "strength": it["strength"],
            "dosage_pattern": it["dosage_pattern"],
            "food_timing": it["food_timing"],
            "food_timing_en": food_timing_en,
            "food_timing_hi": food_timing_hi,
            "duration_days": it["duration_days"],
            "special_instructions": it["special_instructions"],
            "slots": slots,
            "schedules": schedules,
        })

    return render_template(
        "prescription_view.html",
        rx=rx,
        items=items,
    )


@app.route("/prescriptions/<int:prescription_id>/status", methods=["POST"])
@role_required('head_doctor', 'doctor')
def update_prescription_status(prescription_id):
    """Update prescription status (active / completed / cancelled)."""
    new_status = request.form.get("status", "").strip().lower()
    if new_status in ["active", "completed", "cancelled"]:
        execute_db("UPDATE prescriptions SET status=? WHERE id=?", (new_status, prescription_id))
        rx = query_db("SELECT rx_code FROM prescriptions WHERE id=?", (prescription_id,), one=True)
        rx_code = rx["rx_code"] if rx else f"#{prescription_id}"
        log_activity("Prescription Status Updated", f"{rx_code} status changed to '{new_status}'", "medicine")

    return redirect(url_for("view_prescription", prescription_id=prescription_id))


# ── Follow-ups & Reminders Module Routes ───────────────────────────

@app.route("/followups")
@role_required('head_doctor', 'doctor', 'staff')
def followups():
    """Follow-ups, Reminders, Check-ins and WhatsApp Message Log view."""
    active_tab = request.args.get("tab", "reminders").strip().lower()
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    type_filter = request.args.get("type", "").strip()

    today_date = datetime.now().strftime("%Y-%m-%d")

    # 1. Summary Cards Metrics
    pending_reminders_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='pending'", one=True)["c"]
    sent_today_count = query_db(
        "SELECT COUNT(*) AS c FROM reminders WHERE status IN ('sent', 'acknowledged') AND date(sent_on) = ?",
        (today_date,),
        one=True
    )["c"]
    upcoming_followups_count = query_db(
        "SELECT COUNT(*) AS c FROM followups WHERE status='scheduled' AND followup_date >= ?",
        (today_date,),
        one=True
    )["c"]
    overdue_followups_count = query_db(
        "SELECT COUNT(*) AS c FROM followups WHERE (status='missed' OR (status='scheduled' AND followup_date < ?))",
        (today_date,),
        one=True
    )["c"]

    ack_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='acknowledged'", one=True)["c"]
    missed_rem_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='missed'", one=True)["c"]
    total_finished = ack_count + missed_rem_count
    if total_finished > 0:
        adherence_percentage = round((ack_count / total_finished) * 100, 1)
    else:
        adherence_percentage = 100.0

    # 2. At-Risk Patients List
    at_risk_sql = (
        "SELECT DISTINCT p.id, p.name, p.patient_code, p.phone, p.age, p.gender, "
        "       (SELECT COUNT(*) FROM reminders WHERE patient_id = p.id AND status='missed') AS missed_reminders_count, "
        "       (SELECT COUNT(*) FROM followups WHERE patient_id = p.id AND (status='missed' OR (status='scheduled' AND followup_date < ?))) AS overdue_followups_count, "
        "       (SELECT response FROM checkins WHERE patient_id = p.id ORDER BY id DESC LIMIT 1) AS last_checkin_response "
        "FROM patients p "
        "WHERE p.id IN (SELECT patient_id FROM reminders WHERE status='missed') "
        "   OR p.id IN (SELECT patient_id FROM followups WHERE status='missed' OR (status='scheduled' AND followup_date < ?)) "
        "   OR p.id IN (SELECT patient_id FROM checkins WHERE response IN ('stopped treatment', 'missed some'))"
    )
    at_risk_patients = query_db(at_risk_sql, (today_date, today_date))

    # 3. Tab Data Queries

    # Tab 1: Reminders List
    rem_sql = (
        "SELECT r.*, p.name AS patient_name, p.patient_code, p.phone, "
        "       pr.rx_code "
        "FROM reminders r "
        "JOIN patients p ON r.patient_id = p.id "
        "LEFT JOIN prescriptions pr ON r.prescription_id = pr.id "
        "WHERE 1=1 "
    )
    rem_params = []
    if search_query:
        rem_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR r.message_text LIKE ?) "
        term = f"%{search_query}%"
        rem_params.extend([term, term, term])
    if status_filter and status_filter != 'all':
        rem_sql += "AND r.status = ? "
        rem_params.append(status_filter)
    if type_filter and type_filter != 'all':
        rem_sql += "AND r.reminder_type = ? "
        rem_params.append(type_filter)

    rem_sql += "ORDER BY CASE r.status WHEN 'pending' THEN 1 WHEN 'sent' THEN 2 WHEN 'missed' THEN 3 ELSE 4 END, r.scheduled_for ASC"
    reminders_list = query_db(rem_sql, rem_params)

    # Tab 2: Follow-ups List
    fu_sql = (
        "SELECT f.*, p.name AS patient_name, p.patient_code, p.phone, "
        "       d.name AS doctor_name, d.specialization, "
        "       pr.rx_code "
        "FROM followups f "
        "JOIN patients p ON f.patient_id = p.id "
        "LEFT JOIN doctors d ON f.doctor_id = d.id "
        "LEFT JOIN prescriptions pr ON f.prescription_id = pr.id "
        "WHERE 1=1 "
    )
    fu_params = []
    if search_query:
        fu_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR f.reason LIKE ? OR f.purpose LIKE ?) "
        term = f"%{search_query}%"
        fu_params.extend([term, term, term, term])
    if status_filter and status_filter != 'all':
        fu_sql += "AND f.status = ? "
        fu_params.append(status_filter)

    fu_sql += "ORDER BY f.followup_date ASC, f.id DESC"
    followups_list = query_db(fu_sql, fu_params)

    # Tab 3: Check-ins List
    ci_sql = (
        "SELECT c.*, p.name AS patient_name, p.patient_code, p.phone, "
        "       pr.rx_code "
        "FROM checkins c "
        "JOIN patients p ON c.patient_id = p.id "
        "LEFT JOIN prescriptions pr ON c.prescription_id = pr.id "
        "WHERE 1=1 "
    )
    ci_params = []
    if search_query:
        ci_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR c.notes LIKE ? OR c.response LIKE ?) "
        term = f"%{search_query}%"
        ci_params.extend([term, term, term, term])
    if status_filter and status_filter != 'all':
        ci_sql += "AND c.response = ? "
        ci_params.append(status_filter)

    ci_sql += "ORDER BY c.checkin_date DESC, c.id DESC"
    checkins_list = query_db(ci_sql, ci_params)

    # Tab 4: Message Log (WhatsApp Chat Bubbles)
    msg_sql = (
        "SELECT m.*, p.name AS patient_name, p.patient_code "
        "FROM message_log m "
        "LEFT JOIN patients p ON m.patient_id = p.id "
        "WHERE 1=1 "
    )
    msg_params = []
    if search_query:
        msg_sql += "AND (p.name LIKE ? OR p.patient_code LIKE ? OR m.phone LIKE ? OR m.message LIKE ?) "
        term = f"%{search_query}%"
        msg_params.extend([term, term, term, term])

    msg_sql += "ORDER BY m.sent_on ASC, m.id ASC"
    messages_list = query_db(msg_sql, msg_params)

    grouped_messages = {}
    for msg in messages_list:
        key = msg["patient_name"] or msg["phone"] or "Unknown"
        if key not in grouped_messages:
            grouped_messages[key] = []
        grouped_messages[key].append(msg)

    patients_list = query_db("SELECT id, patient_code, name, phone FROM patients ORDER BY name ASC")
    doctors_list = query_db("SELECT id, name, specialization FROM doctors ORDER BY name ASC")
    prescriptions_list = query_db("SELECT id, rx_code, patient_id FROM prescriptions ORDER BY id DESC")

    return render_template(
        "followups.html",
        active_tab=active_tab,
        pending_reminders_count=pending_reminders_count,
        sent_today_count=sent_today_count,
        upcoming_followups_count=upcoming_followups_count,
        overdue_followups_count=overdue_followups_count,
        adherence_percentage=adherence_percentage,
        at_risk_patients=at_risk_patients,
        reminders=reminders_list,
        followups=followups_list,
        checkins=checkins_list,
        messages=messages_list,
        grouped_messages=grouped_messages,
        patients=patients_list,
        doctors=doctors_list,
        prescriptions=prescriptions_list,
        search_query=search_query,
        status_filter=status_filter,
        type_filter=type_filter,
        today_date=today_date,
    )


@app.route("/followups/generate/<int:prescription_id>", methods=["POST"])
@role_required('head_doctor', 'doctor')
def generate_reminders_route(prescription_id):
    """Generate medication and follow-up reminders for a prescription."""
    from prescription_utils import generate_reminders_for_prescription
    conn = get_db_connection()
    count = generate_reminders_for_prescription(conn, prescription_id)
    conn.close()

    log_activity("Reminders Generated", f"Generated {count} new reminders for RX-{prescription_id}", "medicine")
    return redirect(request.referrer or url_for("followups", tab="reminders"))


@app.route("/followups/add", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def add_followup():
    """Schedule a new follow-up appointment."""
    patient_id = request.form.get("patient_id", type=int)
    doctor_id = request.form.get("doctor_id", type=int) or None
    prescription_id = request.form.get("prescription_id", type=int) or None
    followup_date = request.form.get("followup_date", "").strip()
    purpose = request.form.get("purpose", "").strip() or request.form.get("reason", "").strip()
    notes = request.form.get("notes", "").strip()

    if patient_id and followup_date:
        execute_db(
            "INSERT INTO followups (patient_id, doctor_id, prescription_id, followup_date, reason, purpose, status, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)",
            (patient_id, doctor_id, prescription_id, followup_date, purpose, purpose, notes)
        )
        patient = query_db("SELECT name FROM patients WHERE id=?", (patient_id,), one=True)
        pname = patient["name"] if patient else f"Patient #{patient_id}"
        log_activity("Follow-up Scheduled", f"Follow-up for {pname} scheduled on {followup_date}", "patient")

    return redirect(url_for("followups", tab="followups"))


@app.route("/followups/<int:followup_id>/status", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def update_followup_status(followup_id):
    """Update status of a follow-up (scheduled / completed / missed / cancelled)."""
    new_status = request.form.get("status", "").strip().lower()
    if new_status in ["scheduled", "completed", "missed", "cancelled"]:
        execute_db("UPDATE followups SET status=? WHERE id=?", (new_status, followup_id))
        log_activity("Follow-up Status Updated", f"Follow-up #{followup_id} status marked '{new_status}'", "patient")

    return redirect(request.referrer or url_for("followups", tab="followups"))


@app.route("/reminders/<int:reminder_id>/send", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def send_single_reminder(reminder_id):
    """Send a single pending reminder via WhatsApp layer."""
    from whatsapp_service import send_whatsapp
    conn = get_db_connection()
    rem = conn.execute("SELECT r.*, p.phone FROM reminders r JOIN patients p ON r.patient_id = p.id WHERE r.id = ?", (reminder_id,)).fetchone()

    if rem:
        rem_dict = dict(rem)
        phone = rem_dict.get("phone") or "9876543210"
        msg = rem_dict["message_text"]
        patient_id = rem_dict["patient_id"]

        send_whatsapp(phone, msg, patient_id=patient_id, db_conn=conn)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE reminders SET status='sent', sent_on=? WHERE id=?", (now_str, reminder_id))
        conn.commit()

        log_activity("WhatsApp Reminder Sent", f"Reminder sent to Patient #{patient_id}", "patient")

    conn.close()
    return redirect(request.referrer or url_for("followups", tab="reminders"))


@app.route("/reminders/send-due", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def send_due_reminders():
    """Send all pending reminders whose scheduled time has arrived or passed (Demo Action Button)."""
    from whatsapp_service import send_whatsapp
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    due_reminders = conn.execute(
        "SELECT r.*, p.phone FROM reminders r JOIN patients p ON r.patient_id = p.id WHERE r.status='pending'",
    ).fetchall()

    sent_count = 0
    for rem in due_reminders:
        rem_dict = dict(rem)
        phone = rem_dict.get("phone") or "9876543210"
        msg = rem_dict["message_text"]
        patient_id = rem_dict["patient_id"]

        send_whatsapp(phone, msg, patient_id=patient_id, db_conn=conn)
        conn.execute("UPDATE reminders SET status='sent', sent_on=? WHERE id=?", (now_str, rem_dict["id"]))
        sent_count += 1

    conn.commit()
    conn.close()

    log_activity("Bulk Reminders Sent", f"{sent_count} pending reminders sent via WhatsApp simulation", "patient")
    return redirect(request.referrer or url_for("followups", tab="reminders"))


@app.route("/reminders/<int:reminder_id>/acknowledge", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff', 'patient')
def acknowledge_reminder(reminder_id):
    """Mark reminder as acknowledged by patient."""
    conn = get_db_connection()
    rem = conn.execute("SELECT r.*, p.phone FROM reminders r JOIN patients p ON r.patient_id = p.id WHERE r.id=?", (reminder_id,)).fetchone()
    if rem:
        rem_dict = dict(rem)
        if g.user['role'] == 'patient' and rem_dict['patient_id'] != g.user['patient_id']:
            conn.close()
            return render_template('403.html'), 403

        conn.execute("UPDATE reminders SET status='acknowledged' WHERE id=?", (reminder_id,))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reply_msg = f"Acknowledge: I have taken my scheduled medication / received reminder."
        conn.execute("INSERT INTO message_log (patient_id, phone, message, status, sent_on) VALUES (?, ?, ?, 'received', ?)",
                     (rem_dict["patient_id"], rem_dict["phone"] or "9876543210", reply_msg, now_str))
        conn.commit()

    conn.close()
    return redirect(request.referrer or url_for("followups", tab="reminders"))


@app.route("/reminders/<int:reminder_id>/missed", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff')
def mark_reminder_missed(reminder_id):
    """Mark reminder as missed."""
    execute_db("UPDATE reminders SET status='missed' WHERE id=?", (reminder_id,))
    return redirect(request.referrer or url_for("followups", tab="reminders"))


@app.route("/checkins/add", methods=["POST"])
@role_required('head_doctor', 'doctor', 'staff', 'patient')
def add_checkin():
    """Record patient check-in response."""
    patient_id = request.form.get("patient_id", type=int)
    if g.user['role'] == 'patient':
        patient_id = g.user['patient_id']

    prescription_id = request.form.get("prescription_id", type=int) or None
    checkin_date = request.form.get("checkin_date", datetime.now().strftime("%Y-%m-%d"))
    question = request.form.get("question", "Medication Adherence Check-in").strip()
    response = request.form.get("response", "took all medicines").strip()
    notes = request.form.get("notes", "").strip()

    if patient_id and response:
        execute_db(
            "INSERT INTO checkins (patient_id, prescription_id, checkin_date, question, response, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (patient_id, prescription_id, checkin_date, question, response, notes)
        )
        patient = query_db("SELECT name FROM patients WHERE id=?", (patient_id,), one=True)
        pname = patient["name"] if patient else f"Patient #{patient_id}"

        if response == "stopped treatment":
            log_activity("Patient Risk Alert", f"🚨 {pname} reported STOPPED TREATMENT on check-in!", "patient")
        else:
            log_activity("Check-in Recorded", f"Check-in ({response}) recorded for {pname}", "patient")

    return redirect(request.referrer or url_for("followups", tab="checkins"))


@app.route("/followups/adherence")
@role_required('head_doctor', 'doctor', 'staff')
def get_adherence_stats():
    """Return JSON endpoint with patient adherence metrics."""
    total_rem = query_db("SELECT COUNT(*) AS c FROM reminders", one=True)["c"]
    ack_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='acknowledged'", one=True)["c"]
    missed_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='missed'", one=True)["c"]
    pending_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='pending'", one=True)["c"]
    sent_count = query_db("SELECT COUNT(*) AS c FROM reminders WHERE status='sent'", one=True)["c"]

    total_finished = ack_count + missed_count
    pct = round((ack_count / total_finished) * 100, 1) if total_finished > 0 else 100.0

    stopped_count = query_db("SELECT COUNT(DISTINCT patient_id) AS c FROM checkins WHERE response='stopped treatment'", one=True)["c"]

    return jsonify(
        total_reminders=total_rem,
        acknowledged=ack_count,
        missed=missed_count,
        pending=pending_count,
        sent=sent_count,
        adherence_percentage=pct,
        stopped_treatment_patients_count=stopped_count
    )


# ── API endpoint for chart data (used by JavaScript) ──────────────────

@app.route("/api/dashboard-stats")
@role_required('head_doctor', 'doctor', 'staff')
def api_dashboard_stats():
    """Return JSON data for the dashboard charts."""
    dept_counts = query_db(
        "SELECT department, COUNT(*) AS count FROM patients WHERE department IS NOT NULL AND department!='' GROUP BY department ORDER BY count DESC"
    )
    footfall = query_db(
        "SELECT visit_date AS date, COUNT(*) AS count "
        "FROM visits GROUP BY visit_date ORDER BY visit_date ASC"
    )
    bed_stats = {
        "available": query_db("SELECT COUNT(*) AS c FROM beds WHERE status='available'", one=True)["c"],
        "occupied":  query_db("SELECT COUNT(*) AS c FROM beds WHERE status='occupied'", one=True)["c"],
        "reserved":  query_db("SELECT COUNT(*) AS c FROM beds WHERE status='reserved'", one=True)["c"],
    }
    return jsonify(departments=dept_counts, footfall=footfall, beds=bed_stats)


# ── Assistant Endpoint (Patient Only) ─────────────────────────────────

@app.route("/api/assistant", methods=["POST"])
@role_required("patient")
def api_assistant():
    from assistant_service import handle_assistant_query
    
    data = request.get_json() or {}
    message = data.get("message", "")
    
    user = get_current_user()
    patient_id = user['patient_id'] if (user and 'patient_id' in user.keys()) else None
    
    if not patient_id:
        return jsonify({"reply": "I'm sorry, your account is not linked to a patient profile."}), 400
        
    reply = handle_assistant_query(patient_id, message)
    return jsonify({"reply": reply})


# ── Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    create_tables()
    seed_demo_data()
    # Debug mode is controlled by FLASK_DEBUG environment variable (off by default)
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
    print(f"\n  MALHAM is running at http://127.0.0.1:5000 (Debug: {debug_mode})\n")
    app.run(debug=debug_mode, port=5000)
