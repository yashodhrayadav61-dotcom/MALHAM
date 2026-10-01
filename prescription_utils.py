"""
prescription_utils.py
----------------------
Pattern conversion logic and dosage schedule utilities for MALHAM.
Converts dosage patterns like "1-0-1" or "0.5-0-1" into structured, human-readable slot lists.
"""

import re
from datetime import datetime, timedelta

SLOT_LABELS = [
    ("Morning", "08:00", "सुबह"),
    ("Afternoon", "14:00", "दोपहर"),
    ("Night", "20:00", "रात"),
]

FORM_TRANSLATIONS = {
    "tablet": ("tablet", "गोली"),
    "capsule": ("capsule", "कैप्सूल"),
    "injection": ("injection", "इंजेक्शन"),
    "syrup": ("spoon", "चम्मच"),
    "ointment": ("application", "लेप"),
    "inhaler": ("puff", "पफ"),
}

FOOD_TIMING_TRANSLATIONS = {
    "before food": ("Before food", "खाने से पहले"),
    "after food": ("After food", "खाने के बाद"),
    "with food": ("With food", "खाने के साथ"),
    "any time": ("Any time", "किसी भी समय"),
}


def parse_dose_value(val_str):
    """Parse a single dose quantity string like '1', '0.5', '1/2', '0' into float."""
    v = val_str.strip()
    if v == "1/2" or v == "½":
        return 0.5
    try:
        val = float(v)
        return val if val >= 0 else 0.0
    except ValueError:
        return None


def validate_dosage_pattern(pattern):
    """
    Validate a dosage pattern string.
    Must be exactly three dash-separated numbers/fractions (e.g. '1-0-1', '0.5-0-1', '1/2-0-1').
    Returns (is_valid, parsed_list_of_floats).
    """
    if not pattern or not isinstance(pattern, str):
        return False, []

    parts = pattern.strip().split("-")
    if len(parts) != 3:
        return False, []

    floats = []
    for p in parts:
        val = parse_dose_value(p)
        if val is None:
            return False, []
        floats.append(val)

    return True, floats


def format_dosage_slots(pattern, form="tablet"):
    """
    Convert a dosage pattern like '1-0-1' into a structured list of slot objects.
    Each slot object contains:
    {
        'label': 'Morning' / 'Afternoon' / 'Night',
        'time': '08:00' / '14:00' / '20:00',
        'qty': float,
        'readable_en': '1 tablet' / 'No tablet',
        'readable_hi': '1 गोली' / 'कोई नहीं',
        'active': bool
    }
    """
    valid, values = validate_dosage_pattern(pattern)
    if not valid:
        return []

    unit_en, unit_hi = FORM_TRANSLATIONS.get(form.lower(), ("tablet", "गोली"))

    slots = []
    for (label, default_time, label_hi), qty in zip(SLOT_LABELS, values):
        active = qty > 0
        if qty == 0.5:
            qty_str = "0.5"
            qty_hi = "आधा"
        elif qty == int(qty):
            qty_str = str(int(qty))
            qty_hi = str(int(qty))
        else:
            qty_str = str(qty)
            qty_hi = str(qty)

        if active:
            read_en = f"{qty_str} {unit_en if qty <= 1 else unit_en + 's'}"
            read_hi = f"{qty_hi} {unit_hi}"
        else:
            read_en = f"No {unit_en}"
            read_hi = f"कोई {unit_hi} नहीं"

        slots.append({
            "label": label,
            "label_hi": label_hi,
            "time": default_time,
            "qty": qty,
            "readable_en": read_en,
            "readable_hi": read_hi,
            "active": active,
        })

    return slots


def generate_dose_schedule_rows(prescription_item_id, pattern, form="tablet", start_date=None, duration_days=1):
    """
    Generate database rows for dose_schedule based on prescription item.
    Only creates rows for slots where quantity > 0.
    """
    slots = format_dosage_slots(pattern, form)
    if not slots:
        return []

    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    try:
        s_dt = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        s_dt = datetime.now()

    e_dt = s_dt + timedelta(days=max(1, duration_days) - 1)
    end_date_str = e_dt.strftime("%Y-%m-%d")

    schedule_rows = []
    for slot in slots:
        if slot["active"]:
            schedule_rows.append((
                prescription_item_id,
                slot["label"],
                slot["time"],
                slot["qty"],
                start_date,
                end_date_str
            ))

    return schedule_rows


def format_time_12h(time_str):
    """Convert '08:00' to '8:00 AM' or '20:00' to '8:00 PM'."""
    try:
        t = datetime.strptime(time_str[:5], "%H:%M")
        s = t.strftime("%I:%M %p")
        return s.lstrip("0")
    except Exception:
        return time_str


def generate_reminders_for_prescription(conn, prescription_id):
    """
    Generate medication reminders for the next 3 days and follow-up appointment reminder
    for a given prescription ID.
    Deduplicates to prevent double entries if executed multiple times.
    Returns the count of newly inserted reminders.
    """
    cursor = conn.cursor()

    rx = cursor.execute(
        "SELECT pr.*, p.name AS patient_name, d.name AS doctor_name "
        "FROM prescriptions pr "
        "JOIN patients p ON pr.patient_id = p.id "
        "LEFT JOIN doctors d ON pr.doctor_id = d.id "
        "WHERE pr.id = ?",
        (prescription_id,)
    ).fetchone()

    if not rx:
        return 0

    patient_id = rx["patient_id"]
    rx_dict = dict(rx)
    created_count = 0
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    items = cursor.execute(
        "SELECT pi.*, m.name AS medicine_name, m.generic_name, m.form "
        "FROM prescription_items pi "
        "JOIN medicines m ON pi.medicine_id = m.id "
        "WHERE pi.prescription_id = ?",
        (prescription_id,)
    ).fetchall()

    for item in items:
        med_name = item["medicine_name"]
        form = item["form"] or "tablet"
        unit_en, _ = FORM_TRANSLATIONS.get(form.lower(), ("tablet", "गोली"))
        food_timing = item["food_timing"] or "after food"

        schedules = cursor.execute(
            "SELECT * FROM dose_schedule WHERE prescription_item_id = ?",
            (item["id"],)
        ).fetchall()

        for day_offset in range(3):
            target_date = (now + timedelta(days=day_offset)).strftime("%Y-%m-%d")

            for sch in schedules:
                qty = sch["quantity"]
                dose_time = sch["dose_time"]
                time_12h = format_time_12h(dose_time)

                if qty == 0.5:
                    qty_str = "0.5"
                elif qty == int(qty):
                    qty_str = str(int(qty))
                else:
                    qty_str = str(qty)

                dose_unit_str = f"{qty_str} {unit_en if qty <= 1 else unit_en + 's'}"
                message_text = f"Reminder: Your prescribed medicine {med_name} ({dose_unit_str}, {food_timing}) is scheduled for {time_12h}."
                scheduled_for = f"{target_date} {dose_time}:00"

                dup = cursor.execute(
                    "SELECT COUNT(*) FROM reminders WHERE patient_id = ? AND prescription_id = ? AND scheduled_for = ? AND message_text = ?",
                    (patient_id, prescription_id, scheduled_for, message_text)
                ).fetchone()[0]

                if dup == 0:
                    cursor.execute(
                        "INSERT INTO reminders (patient_id, prescription_id, reminder_type, message_text, scheduled_for, status, channel, created_on) "
                        "VALUES (?, ?, 'medication', ?, ?, 'pending', 'whatsapp', ?)",
                        (patient_id, prescription_id, message_text, scheduled_for, now_str)
                    )
                    created_count += 1

    follow_up_date = rx_dict.get("follow_up_date")
    if follow_up_date:
        try:
            f_dt = datetime.strptime(follow_up_date, "%Y-%m-%d")
            rem_dt = f_dt - timedelta(days=1)
            rem_date_str = rem_dt.strftime("%Y-%m-%d")
            rem_scheduled = f"{rem_date_str} 09:00:00"
        except ValueError:
            rem_scheduled = f"{now.strftime('%Y-%m-%d')} 09:00:00"

        doc_name = rx_dict.get("doctor_name") or "your doctor"
        fu_message = f"Reminder: You have an upcoming follow-up appointment with {doc_name} scheduled for {follow_up_date}."

        dup_fu = cursor.execute(
            "SELECT COUNT(*) FROM reminders WHERE patient_id = ? AND prescription_id = ? AND reminder_type IN ('appointment', 'follow-up') AND scheduled_for = ?",
            (patient_id, prescription_id, rem_scheduled)
        ).fetchone()[0]

        if dup_fu == 0:
            cursor.execute(
                "INSERT INTO reminders (patient_id, prescription_id, reminder_type, message_text, scheduled_for, status, channel, created_on) "
                "VALUES (?, ?, 'follow-up', ?, ?, 'pending', 'whatsapp', ?)",
                (patient_id, prescription_id, fu_message, rem_scheduled, now_str)
            )
            created_count += 1

        existing_fu = cursor.execute(
            "SELECT COUNT(*) FROM followups WHERE patient_id = ? AND followup_date = ?",
            (patient_id, follow_up_date)
        ).fetchone()[0]

        if existing_fu == 0:
            cursor.execute(
                "INSERT INTO followups (patient_id, doctor_id, prescription_id, followup_date, reason, purpose, status, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, 'scheduled', 'Auto-created from prescription')",
                (patient_id, rx_dict.get("doctor_id"), prescription_id, follow_up_date, rx_dict.get("diagnosis_note") or "Post-prescription follow-up", rx_dict.get("diagnosis_note") or "Post-prescription follow-up")
            )

    conn.commit()
    return created_count
