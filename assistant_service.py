import datetime
from app import query_db

HELPLINE_NUMBER = "1800-000-0000"
EMERGENCY_NUMBERS = "Emergency: 112 | Ambulance: 102"
TIMINGS_MSG = "Our hospital is open 24/7. OPD visiting hours are 9:00 AM to 5:00 PM (Monday-Saturday). We are located at 123 Care Avenue, Health City."
NO_ADVICE_MSG = f"I can't give medical advice, diagnose, or suggest dose changes. Please call our helpline at {HELPLINE_NUMBER} or visit the hospital."

EMERGENCY_WORDS = ['chest pain', 'bleeding', 'breathless', 'unconscious', 'accident', 'stroke', 'poison', 'suicide', 'heart attack', 'emergency']
TIMING_WORDS = ['timing', 'timings', 'visiting', 'hours', 'open', 'location', 'address']
HUMAN_WORDS = ['human', 'call', 'helpline', 'representative', 'agent', 'support', 'talk']
MEDICINE_WORDS = ['medicine', 'dose', 'pill', 'next medicine']
FOLLOWUP_WORDS = ['follow-up', 'followup', 'appointment', 'visit', 'my follow-up']
PRESCRIPTION_WORDS = ['prescription', 'rx', 'my prescription']

def sanitize_input(text):
    if not text:
        return ""
    return str(text).replace('<', '&lt;').replace('>', '&gt;')[:200]

def handle_assistant_query(patient_id, user_message):
    msg = sanitize_input(user_message).lower()
    
    # 1. Emergency Check
    if any(word in msg for word in EMERGENCY_WORDS):
        return f"🚨 MEDICAL EMERGENCY: Please call {EMERGENCY_NUMBERS} immediately or go to the nearest emergency room."
    
    # 2. Human / Helpline Check
    if any(word in msg for word in HUMAN_WORDS):
        return f"You can reach our hospital helpline at {HELPLINE_NUMBER}."
        
    # 3. Timings / Location
    if any(word in msg for word in TIMING_WORDS):
        return TIMINGS_MSG
        
    # 4. Next Medicine
    if any(word in msg for word in MEDICINE_WORDS):
        query = """
            SELECT m.name, ds.quantity, pi.food_timing, ds.dose_time_label, ds.dose_time
            FROM dose_schedule ds
            JOIN prescription_items pi ON ds.prescription_item_id = pi.id
            JOIN medicines m ON pi.medicine_id = m.id
            JOIN prescriptions p ON pi.prescription_id = p.id
            WHERE p.patient_id = ? AND p.status = 'active'
            ORDER BY ds.dose_time ASC
            LIMIT 1
        """
        row = query_db(query, [patient_id], one=True)
        if row:
            return f"One of your active medicines is {row['quantity']} unit(s) of {row['name']} scheduled for {row['dose_time']} ({row['dose_time_label']}), {row['food_timing']}."
        return "I couldn't find any active medicines for you right now."
        
    # 5. Follow-up
    if any(word in msg for word in FOLLOWUP_WORDS):
        query = """
            SELECT f.followup_date, d.name as doctor_name
            FROM followups f
            LEFT JOIN doctors d ON f.doctor_id = d.id
            WHERE f.patient_id = ? AND f.status = 'scheduled'
            ORDER BY f.followup_date ASC
            LIMIT 1
        """
        row = query_db(query, [patient_id], one=True)
        if row:
            doc = row['doctor_name'] if row['doctor_name'] else "your doctor"
            return f"Your next scheduled follow-up is on {row['followup_date'][:10]} with Dr. {doc}."
        return "You have no scheduled follow-ups at the moment."
        
    # 6. Prescription
    if any(word in msg for word in PRESCRIPTION_WORDS):
        query = "SELECT id, rx_code, issued_on FROM prescriptions WHERE patient_id = ? ORDER BY issued_on DESC LIMIT 1"
        row = query_db(query, [patient_id], one=True)
        if row:
            # We return a simple HTML link
            return f"Your latest prescription ({row['rx_code']}) was issued on {row['issued_on'][:10]}. <a href='/prescriptions/{row['id']}/view' style='color:var(--theme-primary); text-decoration:underline;'>Click here to view it</a>."
        return "I couldn't find any prescriptions for you."
        
    # 7. Fallback (No medical advice)
    return NO_ADVICE_MSG
