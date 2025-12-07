# 2FA Migration Guide for Existing Users

## Overview

This guide helps existing GreenWatts users understand and adapt to the new 2-Factor Authentication system.

## What Changed?

### Before (Old System)
- Username + Password → Login directly

### After (New System with 2FA)
- **First login from a device**: Username + Password → OTP via Email → Login
- **Subsequent logins (same device)**: Username + Password → Login directly (trusted for 30 days)

## User Impact

### ✅ Minimal Impact
- **Trusted devices**: No change - login works as before
- **Same browser/computer**: Only verify once every 30 days
- **Quick verification**: 6-digit code takes seconds to enter

### ⚠️ When Users Need OTP
- First time logging in
- After clearing browser cookies/cache
- After 30 days on the same device
- Logging in from a new device/browser
- Logging in from a different location/IP

## User Communication Template

### Email to Users

```
Subject: Enhanced Security - 2-Factor Authentication Now Active

Dear GreenWatts User,

We've enhanced the security of your account with 2-Factor Authentication (2FA).

What this means for you:
- When logging in from a new device, you'll receive a 6-digit code via email
- Enter the code to complete your login
- Your device will be trusted for 30 days - no code needed during this time

First Login Steps:
1. Enter your username and password as usual
2. Check your email for a 6-digit verification code
3. Enter the code on the verification page
4. You're logged in! This device is now trusted for 30 days

Benefits:
✓ Enhanced account security
✓ Protection against unauthorized access
✓ Minimal disruption - verify once per device per month

Need Help?
- Code not received? Check your spam folder
- Code expired? Simply login again to get a new one
- Questions? Contact support

Thank you for helping us keep your data secure!

Best regards,
GreenWatts Team
```

## Admin Checklist

### Before Deployment

- [ ] Configure Gmail API credentials
- [ ] Test 2FA with test accounts
- [ ] Run `python test_2fa.py` successfully
- [ ] Prepare user communication email
- [ ] Update user documentation/help pages
- [ ] Train support team on 2FA troubleshooting

### During Deployment

- [ ] Deploy code to production
- [ ] Verify environment variables are set
- [ ] Test login flow in production
- [ ] Monitor error logs for issues
- [ ] Send user communication email

### After Deployment

- [ ] Monitor support tickets for 2FA issues
- [ ] Track email delivery success rate
- [ ] Collect user feedback
- [ ] Document common issues and solutions

## Rollback Plan

If issues arise, you can temporarily disable 2FA:

### Option 1: Quick Disable (Emergency)

Edit `greenwatts/users/views.py`, in the `index` function:

```python
# Comment out 2FA check
# if is_trusted_device(username, device_fingerprint):
#     auth.login(request, user)
#     return redirect('users:dashboard')
# else:
#     if send_otp(username, office.email):
#         request.session['pending_2fa_user'] = username
#         request.session['device_fingerprint'] = device_fingerprint
#         return redirect('users:verify_otp')
#     else:
#         messages.error(request, 'Failed to send verification code. Please try again.')

# Replace with direct login
auth.login(request, user)
return redirect('users:dashboard')
```

### Option 2: Feature Flag (Recommended)

Add to `settings.py`:

```python
ENABLE_2FA = os.environ.get('ENABLE_2FA', 'True') == 'True'
```

Update `views.py`:

```python
from django.conf import settings

if settings.ENABLE_2FA:
    # 2FA logic here
else:
    # Direct login
    auth.login(request, user)
    return redirect('users:dashboard')
```

Then toggle in `.env`:

```env
ENABLE_2FA=False  # Disable 2FA
ENABLE_2FA=True   # Enable 2FA
```

## Monitoring

### Key Metrics to Track

1. **OTP Delivery Rate**
   - Monitor Gmail API success rate
   - Track email delivery failures

2. **User Login Success Rate**
   - Compare before/after 2FA deployment
   - Identify login friction points

3. **Support Tickets**
   - Track 2FA-related issues
   - Common problems and solutions

4. **Device Trust Rate**
   - How many users have trusted devices
   - Average time between OTP requests

### Monitoring Queries

```python
# Django shell
from django.core.cache import cache
from greenwatts.users.models import Office

# Check cache health
cache.set('test', 'value', 60)
print(cache.get('test'))  # Should print 'value'

# Count active users
print(Office.objects.filter(is_active=True).count())
```

## Troubleshooting Guide for Support Team

### Issue: User not receiving OTP

**Diagnosis:**
1. Check spam/junk folder
2. Verify email address in user profile
3. Check Gmail API status
4. Review Django logs for errors

**Solution:**
- Ask user to check spam folder
- Verify email address is correct
- Resend OTP (user logs in again)
- If persistent, check Gmail API credentials

### Issue: OTP expired

**Diagnosis:**
- OTP expires after 10 minutes
- User took too long to enter code

**Solution:**
- User logs in again to get new OTP
- Explain 10-minute expiry time

### Issue: Device not staying trusted

**Diagnosis:**
- User clearing cookies/cache
- Browser in private/incognito mode
- Cache not working properly

**Solution:**
- Explain cookie requirement
- Ask user to use normal browser mode
- Check Django cache configuration

### Issue: Wrong OTP error

**Diagnosis:**
- User entered incorrect code
- Code expired
- Typo in entry

**Solution:**
- Ask user to double-check code
- Request new OTP (login again)
- Ensure 6-digit code is entered correctly

## FAQ for Users

**Q: Why do I need to verify my login?**
A: To protect your account from unauthorized access. This ensures only you can access your energy data.

**Q: How often will I need to enter a code?**
A: Only once per device every 30 days, or when logging in from a new device.

**Q: What if I don't receive the code?**
A: Check your spam folder. If still not received, try logging in again or contact support.

**Q: Can I skip 2FA?**
A: No, 2FA is required for all users to ensure account security.

**Q: What if I change my email?**
A: Contact your administrator to update your email address in the system.

**Q: Is my data safe?**
A: Yes! 2FA adds an extra layer of security to protect your energy monitoring data.

## Success Metrics

### Week 1
- [ ] 90%+ OTP delivery success rate
- [ ] <5% support tickets related to 2FA
- [ ] All users successfully logged in at least once

### Week 2-4
- [ ] 95%+ users have trusted devices
- [ ] <2% support tickets related to 2FA
- [ ] Positive user feedback

### Month 2+
- [ ] 2FA is seamless for users
- [ ] Minimal support overhead
- [ ] Enhanced security posture

## Conclusion

The 2FA implementation enhances security with minimal user friction. Most users will only verify once per device per month, making it a seamless security upgrade.

For technical details, see `2FA_IMPLEMENTATION.md`.

---

**Deployment Date**: _To be filled_
**Prepared by**: GreenWatts Development Team
