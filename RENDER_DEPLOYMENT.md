# Render Deployment Guide with 2FA

## Environment Variables for Render

Add these environment variables in your Render dashboard:

### Required Variables

```
SECRET_KEY=your-production-secret-key-here
DEBUG=False
DATABASE_URL=your-render-postgres-url
ALLOWED_HOSTS=your-subdomain.onrender.com

# Gmail API for 2FA
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REFRESH_TOKEN=your_google_refresh_token
GMAIL_SENDER=your_email@gmail.com

# Python version
PYTHON_VERSION=3.11.0
```

## Step-by-Step Deployment

### 1. Update Render Environment Variables

Go to your Render dashboard → Your Web Service → Environment

Add all the variables listed above.

### 2. Update OAuth Redirect URIs

In Google Cloud Console:
1. Go to APIs & Services → Credentials
2. Edit your OAuth 2.0 Client ID
3. Add authorized redirect URIs:
   - `https://your-subdomain.onrender.com/oauth2callback`
   - Keep `http://localhost:8000/oauth2callback` for local testing

### 3. Create Cache Table (One-time)

After deployment, run this command in Render Shell:

```bash
python manage.py createcachetable
```

Or add to your build script in `render.yaml` or build command.

### 4. Deploy

Push your code to GitHub, Render will auto-deploy.

## Build Command

```bash
pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate && python manage.py createcachetable
```

## Start Command

```bash
gunicorn greenwatts.wsgi:application
```

## Testing on Render

1. Visit: `https://your-subdomain.onrender.com/`
2. Login with user credentials
3. Check email for OTP
4. Verify login works

## Troubleshooting

### No email received on production
- Check Render logs: `Logs` tab in dashboard
- Verify Gmail API credentials are set
- Check Google Cloud Console for API errors

### Cache errors
- Ensure `createcachetable` was run
- Check database connection

### 2FA not working
- Set `ENABLE_2FA=False` temporarily to debug
- Check environment variables are set correctly
- Review Render logs for errors
