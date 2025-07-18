"""
Configuration module for Flask app and Google/YouTube API settings.
Loads environment variables and provides a Config class for Flask.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Flask and API configuration loaded from environment variables or defaults."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    
    # Google API Project
    GOOGLE_PROJECT_ID = os.environ.get('GOOGLE_PROJECT_ID')
    
    # YouTube API OAuth2 credentials
    YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
    YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
    
    # YouTube Channel Configuration
    YOUTUBE_CHANNEL_ID = os.environ.get('YOUTUBE_CHANNEL_ID')
    
    # OAuth2 settings - Fixed to localhost
    REDIRECT_URI = 'http://localhost:5000/oauth2callback'
    AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
    TOKEN_URI = 'https://oauth2.googleapis.com/token'
    AUTH_PROVIDER_X509_CERT_URL = 'https://www.googleapis.com/oauth2/v1/certs'
    
    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 * 1024  # 16GB max file size
    UPLOAD_FOLDER = 'uploads'

    ENABLE_N8N_JOBS = os.environ.get('ENABLE_N8N_JOBS', 'true').lower() == 'true'
    ENABLE_DISCORD_JOB = os.environ.get('ENABLE_DISCORD_JOB', 'true').lower() == 'true'
    ENABLE_YOUTUBE_UPLOAD = os.environ.get('ENABLE_YOUTUBE_UPLOAD', 'true').lower() == 'true'
