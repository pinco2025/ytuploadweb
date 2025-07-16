import os
import random
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import tempfile
import json
from config import Config

class YouTubeService:
    def __init__(self, client_id=None, client_secret=None, token_path=None):
        """Initialize YouTube service with OAuth2 credentials."""
        self.client_id = client_id or Config.YOUTUBE_CLIENT_ID
        self.client_secret = client_secret or Config.YOUTUBE_CLIENT_SECRET
        self.token_path = token_path or f'token_{self.client_id.split("-")[0]}.pickle'
        self.scopes = [
            'https://www.googleapis.com/auth/youtube.upload',
            'https://www.googleapis.com/auth/youtube.readonly'
        ]
        self.service = None
        self.credentials = None
        
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with YouTube API using OAuth2 from .env credentials."""
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no valid credentials, go through OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Create OAuth2 client configuration from instance variables
                client_config = {
                    "installed": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": Config.AUTH_URI,
                        "token_uri": Config.TOKEN_URI,
                        "auth_provider_x509_cert_url": Config.AUTH_PROVIDER_X509_CERT_URL,
                        "redirect_uris": ["http://localhost"]
                    }
                }
                
                # Validate required credentials
                if not self.client_id or not self.client_secret:
                    raise ValueError("YouTube client ID and secret must be provided")
                
                # Create flow from client config
                flow = InstalledAppFlow.from_client_config(
                    client_config,
                    scopes=self.scopes
                )
                
                # Run local server for OAuth
                creds = flow.run_local_server(port=8080, open_browser=True)
            
            # Save credentials for next run
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.credentials = creds
        self.service = build('youtube', 'v3', credentials=creds)
    
    def get_my_channels(self):
        """Get all channels for the authenticated user."""
        try:
            print("Debug: Making API call to get channels...")
            print(f"Debug: Service object: {self.service}")
            print(f"Debug: Credentials valid: {self.credentials and self.credentials.valid}")
            
            response = self.service.channels().list(
                part='snippet,contentDetails',
                mine=True
            ).execute()
            
            print(f"Debug: API response: {response}")
            
            channels = []
            for item in response.get('items', []):
                channel_data = {
                    'id': item['id'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'thumbnail': item['snippet']['thumbnails'].get('default', {}).get('url', ''),
                    'uploads_playlist_id': item['contentDetails']['relatedPlaylists']['uploads']
                }
                channels.append(channel_data)
                print(f"Debug: Added channel: {channel_data['title']} (ID: {channel_data['id']})")
            
            print(f"Debug: Returning {len(channels)} channels")
            return channels
        except HttpError as e:
            print(f"Debug: HttpError getting channels: {e}")
            print(f"Debug: Response status: {e.resp.status}")
            print(f"Debug: Response content: {e.content}")
            return []
        except Exception as e:
            print(f"Debug: General error getting channels: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def upload_video(self, video_path, title, description, tags=None, privacy_status='private', channel_id=None):
        """Upload video to YouTube as a short."""
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        # Log channel information
        if channel_id:
            channels = self.get_my_channels()
            selected_channel = next((ch for ch in channels if ch['id'] == channel_id), None)
            if selected_channel:
                print(f"Uploading to channel: {selected_channel['title']} ({channel_id})")
            else:
                print(f"Warning: Channel ID {channel_id} not found in user's channels")
        
        # Configure video metadata
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': '22'  # People & Blogs category
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Create media upload object
        media = MediaFileUpload(
            video_path,
            chunksize=-1,
            resumable=True,
            mimetype='video/*'
        )
        
        try:
            # Call the API's videos.insert method to create and upload the video
            insert_request = self.service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = self._resumable_upload(insert_request)
            
            if response:
                print(f"Video uploaded successfully! Video ID: {response['id']}")
                return response
            else:
                print("Upload failed")
                return None
                
        except HttpError as e:
            print(f"An HTTP error occurred: {e}")
            return None
    
    def _resumable_upload(self, insert_request):
        """Execute resumable upload with retry logic."""
        response = None
        error = None
        retry = 0
        
        while response is None:
            try:
                print("Uploading file...")
                status, response = insert_request.next_chunk()
                
                if response is not None:
                    if 'id' in response:
                        print(f"Video uploaded successfully! Video ID: {response['id']}")
                        return response
                    else:
                        print(f"The upload failed with an unexpected response: {response}")
                        return None
                        
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    error = f"A retriable HTTP error {e.resp.status} occurred: {e.content}"
                else:
                    raise
                    
            except Exception as e:
                error = f"An error occurred: {e}"
                
            if error is not None:
                print(error)
                retry += 1
                if retry > 3:
                    print("Maximum retries exceeded")
                    return None
                
                max_sleep = 2 ** retry
                sleep_seconds = random.random() * max_sleep
                print(f"Sleeping {sleep_seconds} seconds and then retrying...")
                time.sleep(sleep_seconds)
        
        return response
    
    def set_thumbnail(self, video_id, thumbnail_path):
        """Set custom thumbnail for the video."""
        try:
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            
            print("Thumbnail set successfully")
            return True
            
        except HttpError as e:
            print(f"An error occurred setting thumbnail: {e}")
            return False
    
    def get_video_info(self, video_id):
        """Get video information."""
        try:
            response = self.service.videos().list(
                part='snippet,status',
                id=video_id
            ).execute()
            
            if response['items']:
                return response['items'][0]
            else:
                return None
                
        except HttpError as e:
            print(f"An error occurred: {e}")
            return None
