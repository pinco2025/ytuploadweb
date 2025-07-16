#!/usr/bin/env python3
"""
Test script to debug channel fetching issues
"""

import sys
import os
sys.path.append('.')

from youtube_service import YouTubeService

def test_channel_fetching():
    print("=" * 50)
    print("Testing YouTube Channel Fetching")
    print("=" * 50)
    
    try:
        print("1. Initializing YouTube service...")
        youtube_service = YouTubeService()
        print("✅ YouTube service initialized successfully")
        
        print("\n2. Testing authentication...")
        print(f"   Credentials object: {youtube_service.credentials}")
        print(f"   Credentials valid: {youtube_service.credentials and youtube_service.credentials.valid}")
        print(f"   Service object: {youtube_service.service}")
        
        print("\n3. Fetching channels...")
        channels = youtube_service.get_my_channels()
        
        print(f"\n4. Results:")
        print(f"   Found {len(channels)} channels")
        
        if channels:
            for i, channel in enumerate(channels, 1):
                print(f"   Channel {i}:")
                print(f"     - ID: {channel['id']}")
                print(f"     - Title: {channel['title']}")
                print(f"     - Description: {channel['description'][:100]}...")
                print()
        else:
            print("   ❌ No channels found")
            
            print("\n5. Possible reasons for no channels:")
            print("   - YouTube account has no channels")
            print("   - Insufficient OAuth permissions")
            print("   - Brand accounts not accessible")
            print("   - API quota issues")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_channel_fetching()
