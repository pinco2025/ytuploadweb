import os
os.environ['REDIRECT_URI'] = 'http://localhost:5000/oauth2callback'
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    
    # Google API Project
    GOOGLE_PROJECT_ID = os.environ.get('GOOGLE_PROJECT_ID')
    
    # YouTube API OAuth2 credentials
    YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
    YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
    
    # YouTube Channel Configuration
    YOUTUBE_CHANNEL_ID = os.environ.get('YOUTUBE_CHANNEL_ID')
    
    # OAuth2 settings
    REDIRECT_URI = os.environ.get('REDIRECT_URI') or 'http://localhost:5000/oauth2callback'
    AUTH_URI = os.environ.get('AUTH_URI') or 'https://accounts.google.com/o/oauth2/auth'
    TOKEN_URI = os.environ.get('TOKEN_URI') or 'https://oauth2.googleapis.com/token'
    AUTH_PROVIDER_X509_CERT_URL = os.environ.get('AUTH_PROVIDER_X509_CERT_URL') or 'https://www.googleapis.com/oauth2/v1/certs'
    
    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 * 1024  # 16GB max file size
    UPLOAD_FOLDER = 'uploads'
