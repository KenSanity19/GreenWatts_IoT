import hashlib
import secrets
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache

def get_device_fingerprint(request):
    """Generate device fingerprint from user agent and IP"""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip_address = request.META.get('REMOTE_ADDR', '')
    fingerprint = f"{user_agent}:{ip_address}"
    return hashlib.sha256(fingerprint.encode()).hexdigest()

def is_trusted_device(username, device_fingerprint):
    """Check if device is trusted"""
    key = f"trusted_device:{username}:{device_fingerprint}"
    return cache.get(key) is not None

def trust_device(username, device_fingerprint):
    """Mark device as trusted for 30 days"""
    key = f"trusted_device:{username}:{device_fingerprint}"
    cache.set(key, True, timeout=30*24*60*60)

def generate_otp():
    """Generate 6-digit OTP"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def store_otp(username, otp):
    """Store OTP with 10 minute expiry"""
    key = f"otp:{username}"
    cache.set(key, otp, timeout=600)

def verify_otp(username, otp):
    """Verify OTP and remove if valid"""
    key = f"otp:{username}"
    stored_otp = cache.get(key)
    if stored_otp and stored_otp == otp:
        cache.delete(key)
        return True
    return False

def send_otp_email(email, otp, office_name):
    """Send OTP via email"""
    from django.core.mail import send_mail
    from django.conf import settings
    import logging
    
    logger = logging.getLogger(__name__)
    
    subject = 'GreenWatts - Login Verification Code'
    message = f"""
Hello {office_name},

A login attempt was detected from a new device.

Your verification code is: {otp}

This code will expire in 10 minutes.

If you did not attempt to log in, please contact your administrator immediately.

Best regards,
GreenWatts Team
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        logger.info(f"OTP email sent successfully to {email}")
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {str(e)}")
        raise

def send_otp_email_gmail(to_email, otp):
    from utils.gmail_api import send_email_via_gmail
    send_email_via_gmail(
        to_email=to_email,
        subject="Your GreenWatts Verification Code",
        message_text=f"Your verification code is: {otp}"
    )
