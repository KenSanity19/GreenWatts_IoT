"""
Check if current environment token works
"""
import os
from dotenv import load_dotenv
from utils.gmail_api import send_email_via_gmail

load_dotenv()

def test_current_token():
    refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN')
    if refresh_token:
        print(f"Current refresh token: {refresh_token}")
        
        # Test sending email
        result = send_email_via_gmail(
            "test@example.com", 
            "Test", 
            "Test message"
        )
        
        if result:
            print("✅ Current token works! Use this for production:")
            print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
        else:
            print("❌ Current token doesn't work")
    else:
        print("No GOOGLE_REFRESH_TOKEN found in .env")

if __name__ == "__main__":
    test_current_token()