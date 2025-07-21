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
    ENABLE_INSTAGRAM_UPLOAD = os.environ.get('ENABLE_INSTAGRAM_UPLOAD', 'true').lower() == 'true'
    
    # Instagram API Configuration
    INSTAGRAM_APP_ID = os.environ.get('INSTAGRAM_APP_ID')
    INSTAGRAM_APP_SECRET = os.environ.get('INSTAGRAM_APP_SECRET')
    INSTAGRAM_REDIRECT_URI = 'http://localhost:5000/instagram_oauth_callback'
    
    # Gemini AI Configuration
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
