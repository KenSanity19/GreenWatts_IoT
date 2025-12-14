"""
Extract credentials from environment variables to create credentials.json
"""
import json
import os
from dotenv import load_dotenv

load_dotenv()

def extract_credentials():
    try:
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            print("ERROR: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not found in .env")
            return
        
        credentials = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        
        with open('credentials.json', 'w') as f:
            json.dump(credentials, f, indent=2)
        
        print("SUCCESS: credentials.json created from .env file")
        print("Now run: python get_gmail_token.py")
        
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    extract_credentials()