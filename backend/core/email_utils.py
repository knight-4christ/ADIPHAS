import os
import requests
import logging

logger = logging.getLogger(__name__)

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "greatifet12@gmail.com")

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Sends an HTML email using Brevo Transactional API to bypass Render SMTP blocks."""
    if not BREVO_API_KEY:
        logger.warning(f"BREVO_API_KEY is missing! Please set it in your Render environment variables.")
        logger.debug(f"Mock Email to {to_email} | Subject: {subject}")
        return True

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "sender": {"name": "ADIPHAS Notifications", "email": SENDER_EMAIL},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201, 202]:
            logger.info(f"Email successfully sent to {to_email} via Brevo. Response: {response.text}")
            return True
        else:
            logger.error(f"Brevo API error for {to_email}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send email to {to_email} via Brevo: {e}")
        return False

def send_verification_email(to_email: str, username: str, token: str, backend_url: str):
    """Sends a verification email to the user."""
    verify_url = f"{backend_url}/api/auth/verify-email?token={token}"
    
    html = f"""
    <html>
      <head></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #0284c7;">ADIPHAS Health Intelligence</h2>
            <p>Hello {username},</p>
            <p>Thank you for registering on ADIPHAS. Please verify your email address to receive personalized outbreak alerts and health advisories.</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{verify_url}" style="background-color: #0284c7; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Verify My Email</a>
            </p>
            <p>If the button doesn't work, copy and paste this link into your browser:</p>
            <p><small>{verify_url}</small></p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888;">This is an automated message. Please do not reply.</p>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, "Verify your ADIPHAS Account", html)

def send_password_reset_email(to_email: str, username: str, token: str, backend_url: str):
    """Sends a password reset email to the user."""
    # We will pass the token in the URL. In the UI, the user will enter this token or we will have a reset page.
    # For a Streamlit frontend, we can direct them back to the app with the token in the URL as a query param.
    frontend_url = os.getenv("FRONTEND_URL", "https://adiphas.streamlit.app")
    reset_url = f"{frontend_url}/?reset_token={token}"
    
    html = f"""
    <html>
      <head></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            <h2 style="color: #0284c7;">ADIPHAS Password Reset</h2>
            <p>Hello {username},</p>
            <p>We received a request to reset the password for your ADIPHAS account.</p>
            <p>If you made this request, please click the button below to reset your password:</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #0284c7; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reset My Password</a>
            </p>
            <p>Or manually enter this reset code on the login page: <strong>{token}</strong></p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888;">If you did not request a password reset, please ignore this email.</p>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, "Reset your ADIPHAS Password", html)

def send_alert_notification(to_email: str, username: str, disease: str, location: str, risk_level: str, action: str):
    """Sends a critical health alert to the user."""
    try:
        color = "#dc2626" if risk_level in ["High", "Critical"] else "#ca8a04"
    
    html = f"""
    <html>
      <head></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 2px solid {color}; border-radius: 8px;">
            <h2 style="color: {color};">🚨 ADIPHAS Health Alert</h2>
            <p>Hello {username},</p>
            <p>Our autonomous surveillance engine has detected a health signal near your location:</p>
            <ul>
                <li><strong>Outbreak/Signal:</strong> {disease}</li>
                <li><strong>Location:</strong> {location}</li>
                <li><strong>Risk Level:</strong> <span style="color: {color}; font-weight: bold;">{risk_level}</span></li>
            </ul>
            <div style="background-color: #f8fafc; padding: 15px; border-left: 4px solid {color}; margin: 20px 0;">
                <strong>Recommended Action:</strong><br/>
                {action}
            </div>
            <p>Please log in to your <a href="{frontend_url}/?nav=Command_Centre">ADIPHAS dashboard</a> for the full intelligence briefing and local health feed.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888;">You are receiving this because you are a registered user on ADIPHAS.</p>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, f"ADIPHAS Alert: {disease} in {location}", html)
    except Exception as e:
        logger.error(f"Failed to process alert notification for {to_email}: {e}")
        return False

def send_situational_briefing(to_email: str, username: str, briefing_content: str, is_expert: bool):
    """Sends the 2-hour periodic StAMP situational briefing to the user."""
    try:
        import markdown
        # Convert markdown briefing to HTML
        html_briefing = markdown.markdown(briefing_content)
        
        header = "Expert Intelligence Briefing" if is_expert else "Community Health Update"
    
    import os
    frontend_url = os.getenv("FRONTEND_URL", "https://adiphas.streamlit.app")
    
    html = f"""
    <html>
      <head></head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9fafb; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-top: 5px solid #0284c7; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #0284c7; margin-top: 0;">ADIPHAS {header}</h2>
            <p>Hello {username},</p>
            <p>Here is your latest automated situational health briefing from the ADIPHAS Intelligence Engine.</p>
            
            <div style="background-color: #f1f5f9; padding: 20px; border-radius: 6px; margin: 25px 0;">
                {html_briefing}
            </div>
            
            <p style="text-align: center; margin-top: 30px;">
                <a href="{frontend_url}/?nav=Command_Centre" style="background-color: #0284c7; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-weight: bold;">Go to Dashboard</a>
            </p>
            
            <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0 20px 0;">
            <p style="font-size: 11px; color: #888; text-align: center;">You are receiving this automated summary because you are a registered user on ADIPHAS.</p>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, f"ADIPHAS {header}", html)
    except Exception as e:
        logger.error(f"Failed to process situational briefing email for {to_email}: {e}")
        return False
