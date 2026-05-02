import os
import sys
from dotenv import load_dotenv

# Ensure backend is in path
sys.path.append(os.getcwd())

# Force load .env from the root
load_dotenv()

from backend.core.email_utils import send_email

# Manually reload the variables into the module state if necessary
import backend.core.email_utils as email_utils
email_utils.SMTP_USER = os.getenv("SMTP_USER")
email_utils.SMTP_PASS = os.getenv("SMTP_PASSWORD")

subject = "ADIPHAS System Activation: Success"
html = """
<div style="font-family: sans-serif; background-color: #0f172a; color: #f8fafc; padding: 40px; border-radius: 12px; border: 1px solid #1e293b;">
    <h1 style="color: #0ea5e9;">ADIPHAS System Live</h1>
    <p>Congratulations! Your automated health intelligence engine is now <strong>officially operational</strong>.</p>
    <div style="background: #1e293b; padding: 20px; border-radius: 8px; margin: 20px 0;">
        <h3 style="color: #38bdf8; margin-top: 0;">Verified Systems:</h3>
        <ul style="list-style: none; padding-left: 0;">
            <li>SMTP Dispatcher (Gmail)</li>
            <li>Google OAuth Integration</li>
            <li>2-Hour Briefing Scheduler</li>
            <li>Autonomous Risk Scoring</li>
        </ul>
    </div>
    <p style="color: #94a3b8; font-size: 14px;">This is an automated system confirmation. You will now receive briefings every 2 hours if enabled in your profile.</p>
</div>
"""

print(f"Using SMTP_USER: {email_utils.SMTP_USER}")
print("Attempting to send test email to greatifet12@gmail.com...")
success = send_email("greatifet12@gmail.com", subject, html)

if success:
    print("SUCCESS: Email delivered.")
else:
    print("FAILED: Check logs for SMTP errors.")
