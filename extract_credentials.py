#!/usr/bin/env python3
"""
Helper script to extract credentials from Google OAuth2 JSON files
and populate both .env file and clients.json for multi-client support.
"""

import json
import os
import sys
import glob
from pathlib import Path

def extract_credentials_from_json(json_file_path):
    """Extract credentials from Google OAuth2 JSON file."""
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        
        # Handle both web and installed app credentials
        if 'web' in data:
            creds = data['web']
            app_type = 'web'
        elif 'installed' in data:
            creds = data['installed']
            app_type = 'installed'
        else:
            raise ValueError("Invalid credentials file format")
        
        return {
            'client_id': creds.get('client_id'),
            'client_secret': creds.get('client_secret'),
            'project_id': creds.get('project_id'),
            'auth_uri': creds.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
            'token_uri': creds.get('token_uri', 'https://oauth2.googleapis.com/token'),
            'auth_provider_x509_cert_url': creds.get('auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
            'redirect_uris': creds.get('redirect_uris', ['http://localhost:8080/']),
            'app_type': app_type
        }
    
    except FileNotFoundError:
        print(f"Error: File '{json_file_path}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file '{json_file_path}'.")
        return None
    except Exception as e:
        print(f"Error reading credentials: {e}")
        return None

def find_credential_files():
    """Find all credential JSON files in the current directory."""
    credential_files = []
    
    # Look for common credential file patterns
    patterns = [
        'credentials*.json',
        'client_secret*.json',
        '*_credentials.json',
        'oauth2_credentials*.json'
    ]
    
    for pattern in patterns:
        credential_files.extend(glob.glob(pattern))
    
    # Remove duplicates and sort
    credential_files = sorted(list(set(credential_files)))
    
    return credential_files

def update_env_file(credentials):
    """Update .env file with extracted credentials."""
    env_file = Path('.env')
    
    # Read existing .env file
    env_lines = []
    if env_file.exists():
        with open(env_file, 'r') as f:
            env_lines = f.readlines()
    
    # Create updated environment variables
    new_env_vars = {
        'GOOGLE_PROJECT_ID': credentials['project_id'],
        'YOUTUBE_CLIENT_ID': credentials['client_id'],
        'YOUTUBE_CLIENT_SECRET': credentials['client_secret'],
        'AUTH_URI': credentials['auth_uri'],
        'TOKEN_URI': credentials['token_uri'],
        'AUTH_PROVIDER_X509_CERT_URL': credentials['auth_provider_x509_cert_url'],
        'REDIRECT_URI': credentials['redirect_uris'][0] if credentials['redirect_uris'] else 'http://localhost:8080/'
    }
    
    # Update existing lines or add new ones
    updated_lines = []
    updated_vars = set()
    
    for line in env_lines:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            key = line.split('=')[0]
            if key in new_env_vars:
                updated_lines.append(f"{key}={new_env_vars[key]}\n")
                updated_vars.add(key)
            else:
                updated_lines.append(line + '\n')
        else:
            updated_lines.append(line + '\n')
    
    # Add any new variables that weren't in the original file
    for key, value in new_env_vars.items():
        if key not in updated_vars:
            updated_lines.append(f"{key}={value}\n")
    
    # Write updated .env file
    with open(env_file, 'w') as f:
        f.writelines(updated_lines)
    
    print(f"✅ Updated .env file with credentials from JSON file")
    print(f"📁 Project ID: {credentials['project_id']}")
    print(f"🔑 Client ID: {credentials['client_id'][:20]}...")
    print(f"🔐 App Type: {credentials['app_type']}")

def main():
    """Main function to extract credentials and update .env file."""
    # Look for credentials.json in current directory
    json_file = 'credentials.json'
    
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    
    if not os.path.exists(json_file):
        print(f"❌ Error: '{json_file}' not found.")
        print("\nUsage:")
        print("  python extract_credentials.py [path_to_credentials.json]")
        print("\nOr simply place your 'credentials.json' file in this directory and run:")
        print("  python extract_credentials.py")
        return
    
    print(f"📖 Reading credentials from '{json_file}'...")
    credentials = extract_credentials_from_json(json_file)
    
    if credentials:
        update_env_file(credentials)
        print("\n✅ Done! Your .env file has been updated with the credentials.")
        print("\n🚀 You can now run your Flask application with:")
        print("   python app.py")
        print("\n📝 Note: You may also need to update your clients.json file manually")
        print("   or use the new multi-client authentication system.")
    else:
        print("❌ Failed to extract credentials. Please check your JSON file.")

if __name__ == "__main__":
    main()
