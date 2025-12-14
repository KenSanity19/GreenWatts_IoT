"""
Helper script to generate Gmail API refresh token
Run this once to get your refresh token for the .env file
"""

from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_refresh_token():
    print("Gmail API Token Generator")
    print("=" * 50)
    print("\nMake sure you have 'credentials.json' in this directory")
    print("Download it from Google Cloud Console > APIs & Services > Credentials\n")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds = flow.run_local_server(port=9001)
        
        print("\n" + "=" * 50)
        print("SUCCESS! Add these to your .env file:")
        print("=" * 50)
        print(f"\nGOOGLE_CLIENT_ID={creds.client_id}")
        print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
        print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
        print(f"GMAIL_SENDER=your_email@gmail.com")
        print("\n" + "=" * 50)
        
    except FileNotFoundError:
        print("\nERROR: credentials.json not found!")
        print("Download it from Google Cloud Console first.")
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    get_refresh_token()