"""
Alert Service v2 — Email, SMS (Twilio), WhatsApp, Telegram.
Alert escalation: if no acknowledgement in 30 min, alert emergency contact.
"""
import os
import asyncio
from datetime import datetime
from typing import Optional


class AlertService:
    def __init__(self):
        self.smtp_email    = os.getenv("ALERT_EMAIL", "")
        self.smtp_password = os.getenv("ALERT_EMAIL_PASSWORD", "")
        self.twilio_sid    = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from   = os.getenv("TWILIO_FROM_NUMBER", "")
        self.doctor_phone  = os.getenv("DOCTOR_PHONE_NUMBER", "")
        self.tg_token      = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.tg_chat_id    = os.getenv("TELEGRAM_CHAT_ID", "")
        self.whatsapp_num  = os.getenv("WHATSAPP_NUMBER", "")
        self.hospital      = os.getenv("HOSPITAL_NAME", "GlaucoMonitor")
        self.threshold     = float(os.getenv("IOP_ALERT_THRESHOLD", "21"))
        self._cooldown_min = 30
        self._recent: dict = {}
        self._ack: dict    = {}   # tracks acknowledgements for escalation

    def _should_send(self, patient_id: str) -> bool:
        last = self._recent.get(patient_id)
        if last is None:
            return True
        return (datetime.utcnow() - last).total_seconds() / 60 > self._cooldown_min

    async def send_high_iop_alert(self, patient_name: str, patient_email: Optional[str],
                                   iop_value: float, risk_level: str,
                                   patient_id: str = "unknown",
                                   emergency_contact: Optional[dict] = None):
        if not self._should_send(patient_id):
            return
        self._recent[patient_id] = datetime.utcnow()
        self._ack[patient_id]    = False

        print(f"🚨 [ALERT] High IOP: {patient_name} → {iop_value} mmHg ({risk_level})")

        tasks = []
        if self.smtp_email and self.smtp_password and patient_email:
            tasks.append(self._send_email(patient_name, patient_email, iop_value, risk_level))
        if self.twilio_sid and self.doctor_phone:
            tasks.append(self._send_sms(patient_name, iop_value, risk_level, self.doctor_phone))
        if self.tg_token and self.tg_chat_id:
            tasks.append(self._send_telegram(patient_name, iop_value, risk_level))
        if self.twilio_sid and self.whatsapp_num:
            tasks.append(self._send_whatsapp(patient_name, iop_value, risk_level))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    print(f"Alert error: {r}")

        # Schedule escalation after 30 min if no acknowledgement
        if emergency_contact:
            asyncio.create_task(
                self._escalate_if_no_ack(patient_id, patient_name, iop_value,
                                          risk_level, emergency_contact)
            )

    async def acknowledge_alert(self, patient_id: str):
        self._ack[patient_id] = True

    async def _escalate_if_no_ack(self, patient_id, patient_name, iop, risk, contact):
        await asyncio.sleep(1800)  # wait 30 minutes
        if not self._ack.get(patient_id, True):
            print(f"🚨 [ESCALATION] No response for {patient_name} — alerting emergency contact")
            if self.twilio_sid and contact.get("phone"):
                await self._send_sms(
                    patient_name, iop, risk, contact["phone"],
                    escalation=True, contact_name=contact.get("name", "Emergency Contact")
                )

    async def _send_email(self, name, email, iop, risk):
        try:
            import yagmail
            yag  = yagmail.SMTP(self.smtp_email, self.smtp_password)
            body = f"""
<div style="font-family:Arial;max-width:600px;margin:auto">
<div style="background:#14532d;color:white;padding:20px;border-radius:8px 8px 0 0">
  <h2>⚠️ {self.hospital} — High IOP Alert</h2>
</div>
<div style="padding:20px;background:#f9f9f9;border-radius:0 0 8px 8px">
  <p><b>Patient:</b> {name}</p>
  <p><b>IOP Reading:</b> <span style="color:red;font-size:24px"><b>{iop} mmHg</b></span></p>
  <p><b>Risk Level:</b> <span style="color:red"><b>{risk}</b></span></p>
  <p><b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
  <hr>
  <p style="color:#666;font-size:12px">Normal IOP: 10–21 mmHg. Please consult physician immediately.</p>
</div></div>"""
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: yag.send(
                to=[email, self.smtp_email],
                subject=f"🚨 High IOP Alert: {name} — {iop} mmHg",
                contents=body
            ))
            print(f"📧 Email sent to {email}")
        except Exception as e:
            print(f"Email error: {e}")

    async def _send_sms(self, name, iop, risk, to_number,
                         escalation=False, contact_name="Doctor"):
        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_token)
            if escalation:
                msg = (f"URGENT — {self.hospital}: {contact_name}, patient {name} "
                       f"has IOP={iop}mmHg ({risk}). No doctor response in 30min. "
                       f"Please contact them immediately.")
            else:
                msg = (f"{self.hospital} ALERT: {name} has high IOP of {iop}mmHg "
                       f"({risk} risk). Immediate attention required.")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: client.messages.create(
                body=msg, from_=self.twilio_from, to=to_number
            ))
            print(f"📱 SMS sent to {to_number}")
        except Exception as e:
            print(f"SMS error: {e}")

    async def _send_telegram(self, name, iop, risk):
        try:
            import urllib.request
            msg  = f"🚨 *{self.hospital} Alert*\nPatient: {name}\nIOP: *{iop} mmHg*\nRisk: *{risk}*\nTime: {datetime.utcnow().strftime('%H:%M UTC')}"
            url  = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            data = f"chat_id={self.tg_chat_id}&text={msg}&parse_mode=Markdown".encode()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: urllib.request.urlopen(url, data))
            print(f"📨 Telegram alert sent")
        except Exception as e:
            print(f"Telegram error: {e}")

    async def _send_whatsapp(self, name, iop, risk):
        try:
            from twilio.rest import Client
            client = Client(self.twilio_sid, self.twilio_token)
            msg    = f"🚨 {self.hospital}: {name} IOP={iop}mmHg ({risk} risk). Immediate attention needed."
            loop   = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: client.messages.create(
                body=msg,
                from_=f"whatsapp:{self.twilio_from}",
                to=f"whatsapp:{self.whatsapp_num}"
            ))
            print(f"💬 WhatsApp alert sent")
        except Exception as e:
            print(f"WhatsApp error: {e}")
