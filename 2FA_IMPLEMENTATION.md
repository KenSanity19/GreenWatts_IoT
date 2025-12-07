# 2-Factor Authentication Implementation

## Overview

The GreenWatts user login now includes 2-Factor Authentication (2FA) using Gmail API. Users will receive a 6-digit OTP via email when logging in from a new device.

## Features

✅ **Device Fingerprinting**: Tracks devices using User-Agent and IP address
✅ **Trusted Devices**: Devices are trusted for 30 days after successful verification
✅ **Gmail API Integration**: Sends OTP via Gmail API (not SMTP)
✅ **10-Minute OTP Expiry**: Security codes expire after 10 minutes
✅ **Seamless UX**: Trusted devices skip 2FA

## How It Works

### Login Flow

1. **User enters credentials** on `index.html`
2. **System validates** username and password
3. **Device check**:
   - If device is trusted → Login directly
   - If new device → Send OTP via Gmail
4. **OTP verification** on `verify_otp.html`
5. **Device trusted** for 30 days after successful verification

### Device Fingerprinting

```python
fingerprint = SHA256(User-Agent + IP Address)
```

This creates a unique identifier for each device without storing personal data.

## Files Modified/Created

### New Files
- `greenwatts/users/two_factor.py` - 2FA logic
- `get_gmail_token.py` - Helper script for Gmail API setup
- `GMAIL_API_SETUP.md` - Gmail API configuration guide
- `2FA_IMPLEMENTATION.md` - This file

### Modified Files
- `greenwatts/users/views.py` - Updated `index()` view with 2FA

### Existing Files (Already Present)
- `greenwatts/users/templates/users/verify_otp.html` - OTP input page
- `utils/gmail_api.py` - Gmail API sender

## Setup Instructions

### 1. Install Dependencies

Dependencies are already in `requirements.txt`:
- `google-api-python-client`
- `google-auth-oauthlib`

### 2. Configure Gmail API

Follow the detailed guide in `GMAIL_API_SETUP.md`:

1. Create Google Cloud project
2. Enable Gmail API
3. Create OAuth 2.0 credentials
4. Run `python get_gmail_token.py` to get refresh token
5. Add credentials to `.env` file

### 3. Environment Variables

Add to your `.env` file:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token
GMAIL_SENDER=your_email@gmail.com
```

### 4. Run Migrations (if needed)

```bash
python manage.py migrate
```

### 5. Test the System

1. Clear browser cache/cookies
2. Login with a user account
3. Check email for OTP
4. Enter OTP to complete login
5. Try logging in again - should skip OTP (trusted device)

## Security Features

### OTP Security
- **6-digit random code**: 1 in 1,000,000 chance
- **10-minute expiry**: Reduces attack window
- **Single-use**: OTP deleted after verification
- **Cache-based storage**: No database persistence

### Device Trust
- **30-day trust period**: Balance between security and UX
- **Fingerprint-based**: Unique per device
- **Automatic expiry**: Trust expires after 30 days

### Rate Limiting
- Existing login attempt tracking still applies
- 5 failed attempts = 5-minute lockout

## API Functions

### `two_factor.py`

```python
generate_otp()
# Returns: 6-digit string

get_device_fingerprint(request)
# Returns: SHA256 hash of device info

is_trusted_device(username, fingerprint)
# Returns: Boolean

trust_device(username, fingerprint, days=30)
# Marks device as trusted

send_otp(username, email)
# Sends OTP via Gmail API
# Returns: Boolean (success/failure)

verify_otp(username, otp)
# Verifies OTP and deletes it
# Returns: Boolean
```

## User Experience

### First Login (New Device)
1. Enter username/password
2. See message: "A verification code has been sent to your email"
3. Check email for 6-digit code
4. Enter code on verification page
5. Login successful - device trusted for 30 days

### Subsequent Logins (Trusted Device)
1. Enter username/password
2. Login immediately - no OTP required

### After 30 Days
- Device trust expires
- User must verify again with OTP

## Troubleshooting

### No Email Received
- Check spam/junk folder
- Verify Gmail API is enabled in Google Cloud Console
- Check environment variables are set correctly
- Test with `utils/gmail_api.py` directly

### "Failed to send verification code"
- Check Gmail API credentials
- Verify refresh token is valid
- Check internet connection
- Review Django logs for errors

### OTP Not Working
- Check if OTP expired (10 minutes)
- Ensure correct 6-digit code
- Try requesting new OTP (logout and login again)

### Device Not Trusted
- Clear browser cache/cookies
- Check if 30 days have passed
- Verify cache is working: `python manage.py shell`
  ```python
  from django.core.cache import cache
  cache.set('test', 'value', 60)
  print(cache.get('test'))  # Should print 'value'
  ```

## Testing Checklist

- [ ] Login with valid credentials from new device
- [ ] Receive OTP email within 1 minute
- [ ] Enter correct OTP - login successful
- [ ] Enter incorrect OTP - error message shown
- [ ] Wait 10 minutes - OTP expires
- [ ] Login again from same device - no OTP required
- [ ] Clear cookies - OTP required again
- [ ] Test with different browsers
- [ ] Test with different IP addresses

## Future Enhancements

- SMS-based OTP as alternative
- Backup codes for account recovery
- Remember device checkbox
- Admin panel to view trusted devices
- Revoke device trust manually
- Push notification OTP

## Support

For issues or questions:
1. Check `GMAIL_API_SETUP.md` for configuration
2. Review Django logs: `python manage.py runserver`
3. Test Gmail API: `python -c "from utils.gmail_api import send_email_via_gmail; print(send_email_via_gmail('test@example.com', 'Test', 'Test'))"`

---

**Implementation Date**: January 2025
**Version**: 1.0
