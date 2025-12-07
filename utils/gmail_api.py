from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText
import base64
import os
import logging


def send_email_via_gmail(to_email, subject, message_text):
    """Sends an email using the Gmail API with a refresh token."""
    try:
        refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
        client_id = os.environ["GOOGLE_CLIENT_ID"]
        client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
        sender_email = os.environ["GMAIL_SENDER"]

        creds = Credentials(
            None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token"
        )

        service = build("gmail", "v1", credentials=creds)

        message = MIMEText(message_text)
        message["to"] = to_email
        message["from"] = sender_email
        message["subject"] = subject

        raw_message = {
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode()
        }

        sent_message = service.users().messages().send(userId="me", body=raw_message).execute()
        return sent_message
    except KeyError as e:
        logging.error(f"Missing environment variable: {e}")
        return None
    except HttpError as error:
        logging.error(f"An error occurred: {error}")
        return None
