"""
whatsapp_service.py
-------------------
WhatsApp messaging abstraction layer for MALHAM.
Supports SIMULATION MODE (default) which logs outgoing messages to the database
without making external HTTP calls.
"""

from datetime import datetime
import os

# Configuration flag: "simulation" or "live"
WHATSAPP_MODE = os.environ.get("WHATSAPP_MODE", "simulation")


def send_whatsapp(phone, message, patient_id=None, db_conn=None):
    """
    Send a WhatsApp message to the specified phone number.
    In simulation mode, writes message to `message_log` table and returns success.
    """
    if not phone:
        phone = "9876543210"

    if WHATSAPP_MODE == "simulation":
        if db_conn:
            cursor = db_conn.cursor()
            cursor.execute(
                "INSERT INTO message_log (patient_id, phone, message, status, sent_on) VALUES (?, ?, ?, 'sent', ?)",
                (patient_id, phone, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            db_conn.commit()
        return True, "Message logged successfully via WhatsApp Simulation Mode."
    else:
        # PLACEHOLDER FOR FUTURE REAL WHATSAPP BUSINESS API CALL
        # Example Meta Graph API / Twilio WhatsApp integration:
        #
        # url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        # headers = {"Authorization": f"Bearer {WHATSAPP_API_TOKEN}", "Content-Type": "application/json"}
        # payload = {
        #     "messaging_product": "whatsapp",
        #     "to": phone,
        #     "type": "text",
        #     "text": {"body": message}
        # }
        # response = requests.post(url, json=payload, headers=headers)
        # return response.status_code == 200, response.text
        raise NotImplementedError("Live WhatsApp API credentials not configured in environment.")
