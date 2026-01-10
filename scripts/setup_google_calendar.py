#!/usr/bin/env python3
"""
Google Calendar Setup Script

This script handles the one-time OAuth authorization flow for Google Calendar.

Usage:
    1. Download OAuth client credentials from Google Cloud Console:
       https://console.cloud.google.com/apis/credentials
       
    2. Save as data/google_credentials.json
    
    3. Run this script:
       python scripts/setup_google_calendar.py
       
    4. A browser will open for authorization
    
    5. After authorization, data/google_token.json is created
    
    6. Set GOOGLE_CALENDAR_ENABLED=true in your .env file

Prerequisites:
    pip install google-api-python-client google-auth-oauthlib
"""

import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    """Run Google Calendar OAuth setup."""
    print("=" * 60)
    print("🗓️  Google Calendar Setup for TeacherBOY")
    print("=" * 60)
    print()

    # Check for required libraries
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("❌ Required libraries not installed!")
        print()
        print("Run this command first:")
        print("  pip install google-api-python-client google-auth-oauthlib")
        print()
        return 1

    # Load configuration
    try:
        from src.config import settings
        credentials_file = settings.google_calendar_credentials_file
        token_file = settings.google_calendar_token_file
        calendar_id = settings.google_calendar_id
    except Exception:
        # Fallback defaults if config not loadable
        credentials_file = "data/google_credentials.json"
        token_file = "data/google_token.json"
        calendar_id = "primary"

    credentials_path = project_root / credentials_file
    token_path = project_root / token_file

    print(f"📁 Credentials file: {credentials_path}")
    print(f"📁 Token file: {token_path}")
    print(f"📅 Calendar ID: {calendar_id}")
    print()

    # Check if credentials file exists
    if not credentials_path.exists():
        print("❌ Credentials file not found!")
        print()
        print("To get credentials:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials")
        print("2. Create a project (if needed)")
        print("3. Enable 'Google Calendar API'")
        print("4. Create OAuth 2.0 Client ID (Desktop app)")
        print("5. Download the JSON file")
        print(f"6. Save as: {credentials_path}")
        print()
        return 1

    # Check if already authorized
    if token_path.exists():
        print("⚠️  Token file already exists!")
        response = input("Re-authorize? [y/N]: ").strip().lower()
        if response != 'y':
            print("Keeping existing authorization.")
            return 0
        token_path.unlink()

    # Ensure data directory exists
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Run OAuth flow
    print()
    print("🌐 Opening browser for authorization...")
    print("   (If browser doesn't open, copy the URL from the terminal)")
    print()

    try:
        from src.services.google_calendar_service import google_calendar_service

        # Configure and authorize
        google_calendar_service.configure(
            credentials_path=str(credentials_path),
            token_path=str(token_path),
            calendar_id=calendar_id,
        )

        # If not yet configured, run interactive flow
        if not google_calendar_service.is_configured():
            google_calendar_service._credentials_path = credentials_path
            google_calendar_service._token_path = token_path
            
            if not google_calendar_service.authorize_interactive():
                print("❌ Authorization failed!")
                return 1
    except Exception as e:
        print(f"❌ Error during authorization: {e}")
        return 1

    print()
    print("✅ Google Calendar authorized successfully!")
    print()
    print("Next steps:")
    print("1. Add to your .env file:")
    print("   GOOGLE_CALENDAR_ENABLED=true")
    print()
    print("2. (Optional) Specify a different calendar:")
    print("   GOOGLE_CALENDAR_ID=your-calendar-id@gmail.com")
    print()
    print("3. Restart TeacherBOY to use Google Calendar")
    print()

    # Test connection
    print("Testing connection...")
    try:
        import asyncio
        events = asyncio.run(google_calendar_service.get_upcoming_events(max_results=3))
        print(f"✅ Connection test successful! Found {len(events)} upcoming events.")
        
        if events:
            print("\nUpcoming events:")
            for event in events[:3]:
                print(f"  📌 {event.title} - {event.start.strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        print(f"⚠️  Connection test had issues: {e}")
        print("   This might be fine if you have no upcoming events.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
