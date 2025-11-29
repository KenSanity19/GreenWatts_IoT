from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

def get_attempt_key(username, user_type):
    return f"login_attempts_{user_type}_{username}"

def is_locked_out(username, user_type):
    key = get_attempt_key(username, user_type)
    attempts = cache.get(key, 0)
    return attempts >= 5

def record_failed_attempt(username, user_type):
    key = get_attempt_key(username, user_type)
    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, 300)  # 5 minutes = 300 seconds
    return attempts

def clear_attempts(username, user_type):
    key = get_attempt_key(username, user_type)
    cache.delete(key)

def get_lockout_time_remaining(username, user_type):
    key = get_attempt_key(username, user_type)
    try:
        ttl = cache.ttl(key)
        return max(0, ttl) if ttl else 0
    except AttributeError:
        return 0