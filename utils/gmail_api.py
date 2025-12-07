from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText
import base64
import os


def send_email_via_gmail(to_email, subject, message_text):
    creds = Credentials(
        None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token"
    )

    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(message_text)
    message["to"] = to_email
    message["from"] = os.environ["GMAIL_SENDER"]
    message["subject"] = subject

    raw_message = {
        "raw": base64.urlsafe_b64encode(message.as_bytes()).decode()
    }

    sent = service.users().messages().send(userId="me", body=raw_message).execute()
    return sent
