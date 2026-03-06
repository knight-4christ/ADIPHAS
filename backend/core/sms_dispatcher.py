import os
import logging
from twilio.rest import Client
from typing import List, Optional

logger = logging.getLogger(__name__)

class SMSDispatcher:
    """
    Dispatcher responsible for sending SMS alerts via Twilio.
    Supports broad alerts for public health anomalies.
    """
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER")
        
        self.enabled = all([self.account_sid, self.auth_token, self.from_number])
        self.client = None
        
        if self.enabled:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info("SMS Dispatcher initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
                self.enabled = False
        else:
            logger.warning("SMS Dispatcher disabled — Twilio credentials not found in environment.")

    def send_sms(self, to_number: str, message: str) -> bool:
        """Sends a single SMS message."""
        if not self.enabled or not self.client:
            logger.warning(f"SMS Dispatcher disabled. Would have sent to {to_number}: {message}")
            return False
            
        try:
            self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            logger.info(f"SMS alert sent successfully to {to_number}.")
            return True
        except Exception as e:
            logger.error(f"Failed to send SMS to {to_number}: {e}")
            return False

    def broadcast_anomaly_alert(self, users: List[object], disease: str, location: str, risk_level: str):
        """Broadcasts an anomaly alert to a list of users."""
        if not self.enabled:
            logger.info(f"SMS Broadcast skipped (Disabled): {disease} outbreak detected in {location}.")
            return

        alert_msg = f"ADIPHAS ALERT: Critical {disease} anomaly detected in {location}. Risk Level: {risk_level}. Immediate surveillance required."
        
        for user in users:
            if hasattr(user, 'phone_number') and user.phone_number:
                self.send_sms(user.phone_number, alert_msg)

# Singleton instance
sms_dispatcher = SMSDispatcher()
