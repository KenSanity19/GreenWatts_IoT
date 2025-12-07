# Render Environment Variables Setup

## Copy these to Render Dashboard

Go to: Dashboard → Your Service → Environment → Add Environment Variable

```
SECRET_KEY=generate-a-new-secret-key-for-production
DEBUG=False
DATABASE_URL=auto-filled-by-render
PYTHON_VERSION=3.11.0

GOOGLE_CLIENT_ID=paste-your-client-id
GOOGLE_CLIENT_SECRET=paste-your-client-secret
GOOGLE_REFRESH_TOKEN=paste-your-refresh-token
GMAIL_SENDER=your-email@gmail.com

ENABLE_2FA=True
```

## Important Notes

1. **SECRET_KEY**: Generate new one for production
2. **DATABASE_URL**: Auto-filled if you link Render PostgreSQL
3. **Gmail API**: Use same values from your local .env
4. **ALLOWED_HOSTS**: Already configured in settings.py for .onrender.com

## After Adding Variables

1. Save changes
2. Render will auto-redeploy
3. Run in Shell: `python manage.py createcachetable`
4. Test login at your subdomain
