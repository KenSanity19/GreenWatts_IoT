# Gmail API Setup for 2FA

## Prerequisites
- Google Cloud Console account
- Gmail account for sending emails

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Gmail API:
   - Go to "APIs & Services" > "Library"
   - Search for "Gmail API"
   - Click "Enable"

## Step 2: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Configure OAuth consent screen if prompted:
   - User Type: External
   - Add your email as test user
4. Application type: "Web application"
5. Add authorized redirect URIs:
   - `http://localhost:8000/oauth2callback` (for local testing)
6. Save and download the credentials JSON

## Step 3: Get Refresh Token

Run this Python script to get your refresh token:

```python
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json', SCOPES)
creds = flow.run_local_server(port=8000)

print("Refresh Token:", creds.refresh_token)
print("Client ID:", creds.client_id)
print("Client Secret:", creds.client_secret)
```

## Step 4: Set Environment Variables

Add these to your `.env` file:

```env
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REFRESH_TOKEN=your_refresh_token_here
GMAIL_SENDER=your_email@gmail.com
```

## Step 5: Update Django Settings

Ensure your `settings.py` has cache configured (for OTP storage):

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

## Testing

1. Try logging in with a user account
2. On first login from a new device, you should receive an OTP via email
3. Enter the 6-digit code to complete login
4. The device will be trusted for 30 days

## Troubleshooting

- **No email received**: Check spam folder, verify Gmail API is enabled
- **Invalid credentials**: Regenerate refresh token
- **Cache errors**: Ensure Django cache is properly configured
