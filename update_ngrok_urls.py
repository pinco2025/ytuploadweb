#!/usr/bin/env python3
"""
Simple script to update ngrok URLs in the Discord configuration.
Run this script when your ngrok URLs change daily.
"""

import json
import requests
from datetime import datetime

def update_ngrok_urls():
    """Update ngrok URLs in Discord configuration."""
    
    print("🔄 Discord Webhook URL Updater")
    print("=" * 40)
    
    # Get new URLs from user
    print("\nEnter your new ngrok URLs:")
    print("(You can find these in your ngrok dashboard)")
    
    base_url = input("\nEnter the base ngrok URL (e.g., https://abc123.ngrok-free.app): ").strip()
    
    if not base_url:
        print("❌ No URL provided. Exiting.")
        return
    
    # Remove trailing slash if present
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    
    # Construct full URLs
    submit_url = f"{base_url}/webhook/discord-input"
    nocap_url = f"{base_url}/webhook/back"
    
    print(f"\n📋 Generated URLs:")
    print(f"Submit Job: {submit_url}")
    print(f"No Cap Job: {nocap_url}")
    
    # Confirm with user
    confirm = input("\n✅ Update configuration with these URLs? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Update cancelled.")
        return
    
    # Update configuration file
    try:
        config = {
            "webhook_urls": {
                "submit_job": submit_url,
                "nocap_job": nocap_url
            },
            "timeout_seconds": 30,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open('discord_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        print("✅ Configuration updated successfully!")
        print(f"📅 Last updated: {config['last_updated']}")
        
        # Test the URLs if Flask app is running
        test_urls = input("\n🧪 Test the URLs with running Flask app? (y/n): ").strip().lower()
        
        if test_urls == 'y':
            test_webhook_urls(submit_url, nocap_url)
        
    except Exception as e:
        print(f"❌ Error updating configuration: {e}")

def test_webhook_urls(submit_url, nocap_url):
    """Test the webhook URLs with the Flask app."""
    
    print("\n🧪 Testing webhook URLs...")
    
    # Test data
    test_data = {
        "user": "test_user",
        "images": [
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg",
            "https://example.com/image3.jpg",
            "https://example.com/image4.jpg"
        ],
        "audios": [
            "https://example.com/audio1.mp3",
            "https://example.com/audio2.mp3",
            "https://example.com/audio3.mp3",
            "https://example.com/audio4.mp3"
        ]
    }
    
    # Test endpoints
    endpoints = [
        ("/submitjob", "Submit Job"),
        ("/nocapjob", "No Cap Job")
    ]
    
    base_url = "http://localhost:5000"
    
    for endpoint, name in endpoints:
        print(f"\nTesting {name} endpoint...")
        
        try:
            response = requests.post(
                f"{base_url}{endpoint}",
                json=test_data,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✅ {name}: SUCCESS")
                print(f"   Response: {response.json()}")
            else:
                print(f"❌ {name}: FAILED (Status: {response.status_code})")
                print(f"   Response: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"❌ {name}: Flask app not running")
        except Exception as e:
            print(f"❌ {name}: Error - {e}")

def show_current_config():
    """Show current configuration."""
    
    try:
        with open('discord_config.json', 'r') as f:
            config = json.load(f)
        
        print("📋 Current Configuration:")
        print("=" * 40)
        print(f"Submit Job: {config['webhook_urls']['submit_job']}")
        print(f"No Cap Job: {config['webhook_urls']['nocap_job']}")
        print(f"Timeout: {config['timeout_seconds']} seconds")
        print(f"Last Updated: {config.get('last_updated', 'Unknown')}")
        
    except FileNotFoundError:
        print("❌ Configuration file not found.")
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        show_current_config()
    else:
        update_ngrok_urls() 