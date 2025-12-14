import random
import hashlib
from datetime import datetime, timedelta
from django.core.cache import cache
from utils.gmail_api import send_email_via_gmail


def generate_otp():
    """Generate a 6-digit OTP"""
    return str(random.randint(100000, 999999))


def get_device_fingerprint(request):
    """Generate device fingerprint from user agent and IP"""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    ip_address = request.META.get('REMOTE_ADDR', '')
    fingerprint = hashlib.sha256(f"{user_agent}{ip_address}".encode()).hexdigest()
    return fingerprint


def is_trusted_device(username, device_fingerprint):
    """Check if device is trusted"""
    cache_key = f"trusted_device_{username}_{device_fingerprint}"
    return cache.get(cache_key) is not None


def trust_device(username, device_fingerprint, days=30):
    """Mark device as trusted for specified days"""
    cache_key = f"trusted_device_{username}_{device_fingerprint}"
    cache.set(cache_key, True, timeout=days * 24 * 60 * 60)


def send_otp(username, email):
    """Generate and send OTP via Gmail API"""
    otp = generate_otp()
    cache_key = f"otp_{username}"
    cache.set(cache_key, otp, timeout=600)  # 10 minutes
    
    subject = "GreenWatts - Login Verification Code"
    message = f"""
Hello,

Your verification code is: {otp}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

Best regards,
GreenWatts Team
"""
    
    result = send_email_via_gmail(email, subject, message)
    return result is not None


def verify_otp(username, otp):
    """Verify OTP"""
    cache_key = f"otp_{username}"
    stored_otp = cache.get(cache_key)
    
    if stored_otp and stored_otp == otp:
        cache.delete(cache_key)
        return True
    return False