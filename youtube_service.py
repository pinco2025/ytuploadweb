import os
import random
import time
import logging
from typing import Dict, List, Optional, Tuple
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from auth_manager import AuthManager
from validators import InputValidator

logger = logging.getLogger(__name__)

class YouTubeServiceV2:
    """Improved YouTube service with multi-client support and better error handling."""
    
    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.service = None
        self.current_client_id = None
        self.current_channel_id = None
        
    def _get_service(self, client_id: str):
        """Get YouTube service for a specific client."""
        try:
            # Switch to the specified client
            success, message = self.auth_manager.switch_client(client_id)
            if not success:
                raise Exception(f"Failed to switch to client {client_id}: {message}")
            
            # Get credentials for the client
            creds = self.auth_manager.get_active_credentials()
            if not creds:
                raise Exception(f"No valid credentials for client {client_id}")
            
            # Build service
            service = build('youtube', 'v3', credentials=creds)
            self.service = service
            self.current_client_id = client_id
            logger.info(f"Successfully initialized service for client {client_id}")
            return service
            
        except Exception as e:
            logger.error(f"Failed to get service for client {client_id}: {e}")
            raise
    
    def get_channels_for_client(self, client_id: str) -> Tuple[List[Dict], str]:
        """Get channels available for a specific client."""
        try:
            # Check quota before making request
            if not self.auth_manager.can_make_request(client_id, 'channels.list', 1):
                return [], "API quota exceeded for this client"
            
            channels, message = self.auth_manager.get_channels_for_client(client_id)
            if message == "Success":
                # Update quota usage
                self.auth_manager.update_quota(client_id, 'channels.list', 1)
            
            return channels, message
            
        except Exception as e:
            logger.error(f"Error getting channels for client {client_id}: {e}")
            return [], f"Error getting channels: {str(e)}"
    
    def switch_to_channel(self, client_id: str, channel_id: str) -> Tuple[bool, str]:
        """Switch to a specific channel for a client."""
        try:
            success, message = self.auth_manager.switch_channel(client_id, channel_id)
            if success:
                self.current_client_id = client_id
                self.current_channel_id = channel_id
                # Get service for the client
                self._get_service(client_id)
            
            return success, message
            
        except Exception as e:
            logger.error(f"Error switching to channel {channel_id} for client {client_id}: {e}")
            return False, f"Error switching channel: {str(e)}"
    
    def upload_video(self, video_path: str, title: str, description: str, 
                    tags: Optional[List[str]] = None, privacy_status: str = 'public', 
                    channel_id: Optional[str] = None, client_id: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
        """
        Upload video to YouTube with improved error handling and quota management.
        Returns: (success, message, response_data)
        """
        try:
            # Validate inputs
            is_valid, error_msg = InputValidator.validate_file_path(video_path)
            if not is_valid:
                return False, error_msg, None
            
            is_valid, error_msg = InputValidator.validate_video_title(title)
            if not is_valid:
                return False, error_msg, None
            
            # Use current client/channel if not specified
            if not client_id:
                client_id = self.current_client_id
            if not channel_id:
                channel_id = self.current_channel_id
            
            if not client_id:
                return False, "No client ID specified", None
            
            if not channel_id:
                return False, "No channel ID specified", None
            
            # Check quota before upload
            upload_cost = 1600  # YouTube upload costs 1600 quota points
            if not self.auth_manager.can_make_request(client_id, 'videos.insert', upload_cost):
                return False, "API quota exceeded for this client", None
            
            # Switch to the specified client and channel
            if client_id != self.current_client_id or channel_id != self.current_channel_id:
                success, message = self.switch_to_channel(client_id, channel_id)
                if not success:
                    return False, message, None
            
            # Get service
            service = self._get_service(client_id)
            
            # Validate channel access
            channels, message = self.get_channels_for_client(client_id)
            if message != "Success":
                return False, f"Failed to get channels: {message}", None
            
            channel_exists = any(ch['id'] == channel_id for ch in channels)
            if not channel_exists:
                return False, f"Channel {channel_id} not accessible with client {client_id}", None
            
            # Prepare video metadata
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
            
            logger.info(f"Starting upload for client {client_id}, channel {channel_id}")
            
            # Execute upload
            insert_request = service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            response = self._resumable_upload(insert_request, client_id)
            
            if response and 'id' in response:
                # Update quota usage
                self.auth_manager.update_quota(client_id, 'videos.insert', upload_cost)
                
                logger.info(f"Upload successful! Video ID: {response['id']}")
                return True, f"Video uploaded successfully! Video ID: {response['id']}", response
            else:
                return False, "Upload failed - no response received", None
                
        except HttpError as e:
            error_msg = f"YouTube API error: {e.resp.status} - {e.content}"
            logger.error(error_msg)
            return False, error_msg, None
        except Exception as e:
            error_msg = f"Upload error: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def _resumable_upload(self, insert_request, client_id: str, max_retries: int = 3) -> Optional[Dict]:
        """Execute resumable upload with improved retry logic and quota management."""
        response = None
        retry_count = 0
        
        while response is None and retry_count < max_retries:
            try:
                logger.info(f"Uploading file... (attempt {retry_count + 1})")
                status, response = insert_request.next_chunk()
                
                if response is not None:
                    if 'id' in response:
                        logger.info(f"Upload completed successfully! Video ID: {response['id']}")
                        return response
                    else:
                        logger.error(f"Upload failed with unexpected response: {response}")
                        return None
                        
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    # Retriable server errors
                    retry_count += 1
                    if retry_count < max_retries:
                        sleep_time = min(2 ** retry_count + random.random(), 60)
                        logger.warning(f"Server error {e.resp.status}, retrying in {sleep_time:.1f} seconds...")
                        time.sleep(sleep_time)
                        continue
                    else:
                        logger.error(f"Maximum retries exceeded for server errors")
                        return None
                elif e.resp.status == 403:
                    # Quota exceeded or authentication error
                    logger.error(f"Quota exceeded or authentication error: {e.content}")
                    return None
                else:
                    # Non-retriable error
                    logger.error(f"Non-retriable HTTP error {e.resp.status}: {e.content}")
                    return None
                    
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    sleep_time = min(2 ** retry_count + random.random(), 30)
                    logger.warning(f"Upload error, retrying in {sleep_time:.1f} seconds: {e}")
                    time.sleep(sleep_time)
                    continue
                else:
                    logger.error(f"Maximum retries exceeded: {e}")
                    return None
        
        return response
    
    def get_video_info(self, video_id: str, client_id: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
        """Get video information with quota management."""
        try:
            if not client_id:
                client_id = self.current_client_id
            
            if not client_id:
                return False, "No client ID specified", None
            
            # Check quota
            if not self.auth_manager.can_make_request(client_id, 'videos.list', 1):
                return False, "API quota exceeded for this client", None
            
            service = self._get_service(client_id)
            
            response = service.videos().list(
                part='snippet,status,statistics',
                id=video_id
            ).execute()
            
            # Update quota
            self.auth_manager.update_quota(client_id, 'videos.list', 1)
            
            if response['items']:
                return True, "Success", response['items'][0]
            else:
                return False, "Video not found", None
                
        except HttpError as e:
            error_msg = f"YouTube API error: {e.resp.status} - {e.content}"
            logger.error(error_msg)
            return False, error_msg, None
        except Exception as e:
            error_msg = f"Error getting video info: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def set_thumbnail(self, video_id: str, thumbnail_path: str, client_id: Optional[str] = None) -> Tuple[bool, str]:
        """Set custom thumbnail for the video."""
        try:
            if not client_id:
                client_id = self.current_client_id
            
            if not client_id:
                return False, "No client ID specified"
            
            # Validate thumbnail file
            is_valid, error_msg = InputValidator.validate_file_path(thumbnail_path)
            if not is_valid:
                return False, error_msg
            
            # Check quota
            if not self.auth_manager.can_make_request(client_id, 'thumbnails.set', 50):
                return False, "API quota exceeded for this client"
            
            service = self._get_service(client_id)
            
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            
            # Update quota
            self.auth_manager.update_quota(client_id, 'thumbnails.set', 50)
            
            logger.info(f"Thumbnail set successfully for video {video_id}")
            return True, "Thumbnail set successfully"
            
        except HttpError as e:
            error_msg = f"YouTube API error setting thumbnail: {e.resp.status} - {e.content}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error setting thumbnail: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def get_quota_status(self, client_id: Optional[str] = None) -> Dict:
        """Get quota status for a client."""
        if not client_id:
            client_id = self.current_client_id
        
        if not client_id:
            return {"error": "No client ID specified"}
        
        return self.auth_manager.get_quota_status(client_id)
    
    def get_active_client_info(self) -> Optional[Dict]:
        """Get information about the currently active client."""
        return self.auth_manager.get_active_client_info() 