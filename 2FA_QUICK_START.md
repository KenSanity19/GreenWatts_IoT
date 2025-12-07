# 2FA Quick Start Guide

## 🚀 Quick Setup (5 Minutes)

### Step 1: Get Gmail API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → Enable Gmail API
3. Create OAuth 2.0 credentials
4. Download `credentials.json`

### Step 2: Generate Refresh Token

```bash
python get_gmail_token.py
```

This will open a browser and give you the tokens to add to `.env`

### Step 3: Configure Environment

Add to `.env`:

```env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REFRESH_TOKEN=your_refresh_token_here
GMAIL_SENDER=your_email@gmail.com
```

### Step 4: Test the System

```bash
python test_2fa.py
```

### Step 5: Run Server

```bash
python manage.py runserver
```

## ✅ Testing

1. Open browser in incognito mode
2. Go to `http://localhost:8000/`
3. Login with user credentials
4. Check email for OTP
5. Enter OTP to complete login

## 📋 Files Overview

| File | Purpose |
|------|---------|
| `greenwatts/users/two_factor.py` | 2FA logic |
| `utils/gmail_api.py` | Gmail sender |
| `get_gmail_token.py` | Token generator |
| `test_2fa.py` | Test script |
| `GMAIL_API_SETUP.md` | Detailed setup |
| `2FA_IMPLEMENTATION.md` | Full documentation |

## 🔧 Common Issues

### No email received?
- Check spam folder
- Verify Gmail API is enabled
- Run `python test_2fa.py` to diagnose

### "Failed to send verification code"?
- Check `.env` variables are set
- Regenerate refresh token
- Test with: `python -c "from utils.gmail_api import send_email_via_gmail; send_email_via_gmail('test@example.com', 'Test', 'Test')"`

### OTP not working?
- Check if expired (10 min limit)
- Ensure 6-digit code is correct
- Clear cache: `python manage.py shell` → `from django.core.cache import cache; cache.clear()`

## 🎯 How It Works

```
User Login → Check Device → New Device? → Send OTP → Verify → Trust Device (30 days)
                              ↓
                         Trusted Device → Login Directly
```

## 📞 Need Help?

1. Read `2FA_IMPLEMENTATION.md` for details
2. Check `GMAIL_API_SETUP.md` for Gmail setup
3. Run `python test_2fa.py` to diagnose issues
4. Check Django logs for errors

---

**Ready in 5 minutes!** 🎉
