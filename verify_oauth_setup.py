#!/usr/bin/env python3
"""
OAuth Setup Verification Script
This script helps verify that your OAuth configuration is correct.
"""

import json
import os
from config import Config

def verify_clients_json():
    """Verify clients.json configuration."""
    print("🔍 Checking clients.json...")
    
    if not os.path.exists('clients.json'):
        print("❌ clients.json not found!")
        print("📝 Create clients.json with your OAuth credentials:")
        print("""
[
  {
    "id": "client1",
    "name": "My YouTube Client",
    "client_id": "your-client-id.apps.googleusercontent.com",
    "client_secret": "your-client-secret"
  }
]
        """)
        return False
    
    try:
        with open('clients.json', 'r') as f:
            clients = json.load(f)
        
        if not clients:
            print("❌ clients.json is empty!")
            return False
        
        print(f"✅ Found {len(clients)} client(s) in clients.json")
        
        for i, client in enumerate(clients, 1):
            print(f"\n📋 Client {i}:")
            print(f"   ID: {client.get('id', 'Missing')}")
            print(f"   Name: {client.get('name', 'Missing')}")
            print(f"   Client ID: {client.get('client_id', 'Missing')[:30]}...")
            print(f"   Client Secret: {'✅ Set' if client.get('client_secret') else '❌ Missing'}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in clients.json: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading clients.json: {e}")
        return False

def verify_config():
    """Verify config.py settings."""
    print("\n🔍 Checking config.py...")
    
    print(f"✅ Redirect URI: {Config.REDIRECT_URI}")
    print(f"✅ Auth URI: {Config.AUTH_URI}")
    print(f"✅ Token URI: {Config.TOKEN_URI}")
    
    return True

def verify_tokens_directory():
    """Verify tokens directory exists."""
    print("\n🔍 Checking tokens directory...")
    
    if not os.path.exists('tokens'):
        print("📁 Creating tokens directory...")
        os.makedirs('tokens', exist_ok=True)
        print("✅ Tokens directory created")
    else:
        print("✅ Tokens directory exists")
    
    return True

def main():
    print("=" * 60)
    print("🔐 OAuth Setup Verification")
    print("=" * 60)
    
    # Check all components
    clients_ok = verify_clients_json()
    config_ok = verify_config()
    tokens_ok = verify_tokens_directory()
    
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    
    if all([clients_ok, config_ok, tokens_ok]):
        print("✅ All checks passed!")
        print("\n🎯 Next steps:")
        print("1. Make sure you added http://localhost:5000/oauth2callback to Google Cloud Console")
        print("2. Run: python app.py")
        print("3. Visit: http://localhost:5000")
        print("4. Test the OAuth flow")
    else:
        print("❌ Some checks failed. Please fix the issues above.")
    
    print("\n" + "=" * 60)
    print("📝 Google Cloud Console Configuration:")
    print("=" * 60)
    print("1. Go to: https://console.cloud.google.com/")
    print("2. Select your project")
    print("3. Go to 'APIs & Services' > 'Credentials'")
    print("4. Find your OAuth 2.0 Client ID")
    print("5. Add this redirect URI:")
    print(f"   {Config.REDIRECT_URI}")
    print("6. Click 'Save'")
    print("=" * 60)

if __name__ == "__main__":
    main() 