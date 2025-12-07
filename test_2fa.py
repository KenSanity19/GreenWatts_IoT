"""
Test script for 2FA implementation
Run this to verify the 2FA system is working correctly
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'greenwatts.settings')
django.setup()

from django.core.cache import cache
from greenwatts.users.two_factor import generate_otp, verify_otp, send_otp
from utils.gmail_api import send_email_via_gmail


def test_cache():
    """Test if Django cache is working"""
    print("Testing cache...")
    cache.set('test_key', 'test_value', 60)
    result = cache.get('test_key')
    if result == 'test_value':
        print("✓ Cache is working")
        return True
    else:
        print("✗ Cache is NOT working")
        return False


def test_otp_generation():
    """Test OTP generation"""
    print("\nTesting OTP generation...")
    otp = generate_otp()
    if len(otp) == 6 and otp.isdigit():
        print(f"✓ OTP generated: {otp}")
        return True
    else:
        print("✗ OTP generation failed")
        return False


def test_otp_verification():
    """Test OTP verification"""
    print("\nTesting OTP verification...")
    test_username = "test_user"
    test_otp = "123456"
    
    # Store OTP
    cache.set(f"otp_{test_username}", test_otp, 600)
    
    # Verify correct OTP
    if verify_otp(test_username, test_otp):
        print("✓ OTP verification works")
        return True
    else:
        print("✗ OTP verification failed")
        return False


def test_gmail_api():
    """Test Gmail API configuration"""
    print("\nTesting Gmail API configuration...")
    
    required_vars = [
        'GOOGLE_CLIENT_ID',
        'GOOGLE_CLIENT_SECRET',
        'GOOGLE_REFRESH_TOKEN',
        'GMAIL_SENDER'
    ]
    
    missing = []
    for var in required_vars:
        if not os.environ.get(var):
            missing.append(var)
    
    if missing:
        print(f"✗ Missing environment variables: {', '.join(missing)}")
        print("  Please configure Gmail API (see GMAIL_API_SETUP.md)")
        return False
    else:
        print("✓ All Gmail API environment variables are set")
        return True


def test_send_email(test_email=None):
    """Test sending email via Gmail API"""
    if not test_email:
        test_email = input("\nEnter your email to test (or press Enter to skip): ").strip()
    
    if not test_email:
        print("Skipping email send test")
        return None
    
    print(f"\nSending test email to {test_email}...")
    result = send_email_via_gmail(
        test_email,
        "GreenWatts 2FA Test",
        "This is a test email from GreenWatts 2FA system. If you received this, the Gmail API is working correctly!"
    )
    
    if result:
        print("✓ Email sent successfully! Check your inbox.")
        return True
    else:
        print("✗ Failed to send email. Check your Gmail API configuration.")
        return False


def main():
    print("=" * 60)
    print("GreenWatts 2FA System Test")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Cache", test_cache()))
    results.append(("OTP Generation", test_otp_generation()))
    results.append(("OTP Verification", test_otp_verification()))
    results.append(("Gmail API Config", test_gmail_api()))
    
    # Optional email test
    email_result = test_send_email()
    if email_result is not None:
        results.append(("Email Sending", email_result))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:20} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! 2FA system is ready.")
    else:
        print("\n⚠️  Some tests failed. Please check the configuration.")
        print("   See GMAIL_API_SETUP.md for setup instructions.")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
