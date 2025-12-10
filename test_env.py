import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

print(f"GMAIL_SENDER: {os.environ.get('GMAIL_SENDER')}")
print(f"GOOGLE_CLIENT_ID: {os.environ.get('GOOGLE_CLIENT_ID')}")
print(f"GOOGLE_REFRESH_TOKEN: {os.environ.get('GOOGLE_REFRESH_TOKEN')[:20]}...")