import os
import json
import pickle
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AuthManager:
    """Manages authentication for multiple YouTube clients and channels."""
    
    def __init__(self, clients_file='clients.json'):
        self.clients_file = clients_file
        self.clients = self._load_clients()
        self.active_client_id = None
        self.active_channel_id = None
        self.tokens_dir = 'tokens'
        self._ensure_tokens_dir()
        
        # API quota tracking
        self.quota_usage = {}
        self.last_quota_reset = datetime.now()
        
    def _ensure_tokens_dir(self):
        """Ensure tokens directory exists."""
        if not os.path.exists(self.tokens_dir):
            os.makedirs(self.tokens_dir)
    
    def _load_clients(self) -> List[Dict]:
        """Load clients from configuration file."""
        try:
            if os.path.exists(self.clients_file):
                with open(self.clients_file, 'r') as f:
                    return json.load(f)
            else:
                logger.warning(f"Client file {self.clients_file} not found")
                return []
        except Exception as e:
            logger.error(f"Error loading clients: {e}")
            return []
    
    def get_client_by_id(self, client_id: str) -> Optional[Dict]:
        """Get client configuration by ID."""
        return next((client for client in self.clients if client['id'] == client_id), None)
    
    def get_all_clients(self) -> List[Dict]:
        """Get all available clients."""
        return self.clients
    
    def _get_token_path(self, client_id: str) -> str:
        """Get token file path for a client."""
        return os.path.join(self.tokens_dir, f'token_{client_id}.pickle')
    
    def _get_quota_path(self, client_id: str) -> str:
        """Get quota tracking file path for a client."""
        return os.path.join(self.tokens_dir, f'quota_{client_id}.json')
    
    def authenticate_client(self, client_id: str) -> Tuple[bool, str]:
        """Authenticate a specific client and return (success, message)."""
        try:
            client = self.get_client_by_id(client_id)
            if not client:
                return False, f"Client {client_id} not found"
            
            token_path = self._get_token_path(client_id)
            scopes = [
                'https://www.googleapis.com/auth/youtube.upload',
                'https://www.googleapis.com/auth/youtube.readonly'
            ]
            
            creds = None
            
            # Load existing token
            if os.path.exists(token_path):
                try:
                    with open(token_path, 'rb') as token:
                        creds = pickle.load(token)
                except Exception as e:
                    logger.warning(f"Failed to load existing token for {client_id}: {e}")
            
            # Check if credentials need refresh
            if creds and not creds.valid:
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        logger.info(f"Refreshed token for client {client_id}")
                    except Exception as e:
                        logger.warning(f"Failed to refresh token for {client_id}: {e}")
                        creds = None
                else:
                    creds = None
            
            # If no valid credentials, authenticate
            if not creds:
                client_config = {
                    "installed": {
                        "client_id": client['client_id'],
                        "client_secret": client['client_secret'],
                        "auth_uri": Config.AUTH_URI,
                        "token_uri": Config.TOKEN_URI,
                        "auth_provider_x509_cert_url": Config.AUTH_PROVIDER_X509_CERT_URL,
                        "redirect_uris": ["http://localhost"]
                    }
                }
                flow = InstalledAppFlow.from_client_config(
                    client_config,
                    scopes=scopes
                )
                # Always force consent and offline access to get refresh token
                auth_url, _ = flow.authorization_url(
                    access_type='offline',
                    prompt='consent',
                    include_granted_scopes='true'
                )
                print(f"Please go to this URL and authorize access: {auth_url}")
                flow.fetch_token(authorization_response=input("Enter the full redirect URL after authorization: "))
                creds = flow.credentials
                # Save credentials
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
                logger.info(f"New authentication completed for client {client_id}")
            # Warn if refresh token is missing
            if creds and not getattr(creds, 'refresh_token', None):
                logger.warning(f"No refresh token present for client {client_id}. You may need to re-authenticate with prompt='consent'.")
            
            self.active_client_id = client_id
            return True, f"Successfully authenticated client {client_id}"
            
        except Exception as e:
            logger.error(f"Authentication failed for client {client_id}: {e}")
            return False, f"Authentication failed: {str(e)}"
    
    def get_channels_for_client(self, client_id: str) -> Tuple[List[Dict], str]:
        """Get channels available for a specific client."""
        try:
            # Authenticate client first
            success, message = self.authenticate_client(client_id)
            if not success:
                return [], message
            
            client = self.get_client_by_id(client_id)
            if not client:
                return [], "Client not found"
            
            # Build service with authenticated credentials
            token_path = self._get_token_path(client_id)
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
            
            service = build('youtube', 'v3', credentials=creds)
            
            # Get channels
            response = service.channels().list(
                part='snippet,contentDetails',
                mine=True
            ).execute()
            
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
            
            logger.info(f"Found {len(channels)} channels for client {client_id}")
            return channels, "Success"
            
        except HttpError as e:
            error_msg = f"YouTube API error: {e.resp.status} - {e.content}"
            logger.error(error_msg)
            return [], error_msg
        except Exception as e:
            error_msg = f"Error getting channels: {str(e)}"
            logger.error(error_msg)
            return [], error_msg
    
    def switch_client(self, client_id: str) -> Tuple[bool, str]:
        """Switch to a different client."""
        try:
            success, message = self.authenticate_client(client_id)
            if success:
                self.active_client_id = client_id
                self.active_channel_id = None  # Reset active channel
                logger.info(f"Switched to client {client_id}")
                return True, f"Switched to client {client_id}"
            else:
                return False, message
        except Exception as e:
            error_msg = f"Failed to switch client: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def switch_channel(self, client_id: str, channel_id: str) -> Tuple[bool, str]:
        """Switch to a specific channel for a client."""
        try:
            # First switch to the client
            success, message = self.switch_client(client_id)
            if not success:
                return False, message
            
            # Get channels for this client
            channels, message = self.get_channels_for_client(client_id)
            if message != "Success":
                return False, message
            
            # Check if channel exists
            channel_exists = any(ch['id'] == channel_id for ch in channels)
            if not channel_exists:
                return False, f"Channel {channel_id} not found for client {client_id}"
            
            self.active_channel_id = channel_id
            logger.info(f"Switched to channel {channel_id} for client {client_id}")
            return True, f"Switched to channel {channel_id}"
            
        except Exception as e:
            error_msg = f"Failed to switch channel: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_active_credentials(self) -> Optional[Credentials]:
        """Get credentials for the currently active client."""
        if not self.active_client_id:
            return None
        
        token_path = self._get_token_path(self.active_client_id)
        if not os.path.exists(token_path):
            return None
        
        try:
            with open(token_path, 'rb') as token:
                return pickle.load(token)
        except Exception as e:
            logger.error(f"Failed to load active credentials: {e}")
            return None
    
    def get_active_client_info(self) -> Optional[Dict]:
        """Get information about the currently active client."""
        if not self.active_client_id:
            return None
        
        client = self.get_client_by_id(self.active_client_id)
        if client:
            return {
                'id': client['id'],
                'name': client['name'],
                'active_channel_id': self.active_channel_id
            }
        return None
    
    def check_quota(self, client_id: str) -> Dict:
        """Check API quota usage for a client."""
        quota_path = self._get_quota_path(client_id)
        
        try:
            if os.path.exists(quota_path):
                with open(quota_path, 'r') as f:
                    quota_data = json.load(f)
            else:
                quota_data = {
                    'daily_quota': 10000,  # Default YouTube API quota
                    'used_quota': 0,
                    'last_reset': datetime.now().isoformat(),
                    'operations': {}
                }
            
            # Check if we need to reset daily quota
            last_reset = datetime.fromisoformat(quota_data['last_reset'])
            if datetime.now().date() > last_reset.date():
                quota_data['used_quota'] = 0
                quota_data['last_reset'] = datetime.now().isoformat()
                quota_data['operations'] = {}
            
            return quota_data
            
        except Exception as e:
            logger.error(f"Error checking quota for {client_id}: {e}")
            return {
                'daily_quota': 10000,
                'used_quota': 0,
                'last_reset': datetime.now().isoformat(),
                'operations': {}
            }
    
    def update_quota(self, client_id: str, operation: str, cost: int = 1):
        """Update quota usage for a client."""
        quota_data = self.check_quota(client_id)
        quota_data['used_quota'] += cost
        
        if operation not in quota_data['operations']:
            quota_data['operations'][operation] = 0
        quota_data['operations'][operation] += cost
        
        quota_path = self._get_quota_path(client_id)
        try:
            with open(quota_path, 'w') as f:
                json.dump(quota_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error updating quota for {client_id}: {e}")
    
    def can_make_request(self, client_id: str, operation: str, cost: int = 1) -> bool:
        """Check if a client can make an API request without exceeding quota."""
        quota_data = self.check_quota(client_id)
        return quota_data['used_quota'] + cost <= quota_data['daily_quota']
    
    def get_quota_status(self, client_id: str) -> Dict:
        """Get detailed quota status for a client."""
        quota_data = self.check_quota(client_id)
        return {
            'client_id': client_id,
            'daily_quota': quota_data['daily_quota'],
            'used_quota': quota_data['used_quota'],
            'remaining_quota': quota_data['daily_quota'] - quota_data['used_quota'],
            'usage_percentage': (quota_data['used_quota'] / quota_data['daily_quota']) * 100,
            'last_reset': quota_data['last_reset'],
            'operations': quota_data['operations']
        } 