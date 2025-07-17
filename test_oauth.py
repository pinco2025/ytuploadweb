#!/usr/bin/env python3

from auth_manager import AuthManager
from config import Config

def test_oauth_url():
    print("=== OAuth URL Generation Test ===")
    print(f"Config REDIRECT_URI: {Config.REDIRECT_URI}")
    
    # Initialize auth manager
    am = AuthManager()
    
    # Get first client
    clients = am.get_all_clients()
    if not clients:
        print("No clients found!")
        return
    
    client = clients[0]
    print(f"Testing with client: {client['id']}")
    
    # Test the OAuth flow
    try:
        success, message = am.authenticate_client(client['id'])
        print(f"Result: {success} - {message}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_oauth_url() 