"""
Lazy-loaded 2FA module to avoid importing heavy Gmail API modules at startup.
"""
from ..lazy_imports import gmail_api


def lazy_send_otp(username, email):
    """Lazy wrapper for send_otp function."""
    from .two_factor import send_otp
    return send_otp(username, email)


def lazy_verify_otp(username, otp):
    """Lazy wrapper for verify_otp function."""
    from .two_factor import verify_otp
    return verify_otp(username, otp)


def lazy_get_device_fingerprint(request):
    """Lazy wrapper for get_device_fingerprint function."""
    from .two_factor import get_device_fingerprint
    return get_device_fingerprint(request)


def lazy_is_trusted_device(username, fingerprint):
    """Lazy wrapper for is_trusted_device function."""
    from .two_factor import is_trusted_device
    return is_trusted_device(username, fingerprint)


def lazy_trust_device(username, fingerprint):
    """Lazy wrapper for trust_device function."""
    from .two_factor import trust_device
    return trust_device(username, fingerprint)