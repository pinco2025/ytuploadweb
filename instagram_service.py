import os
import random
import time
import logging
import requests
from typing import Dict, List, Optional, Tuple
from auth_manager import AuthManager
from validators import InputValidator

logger = logging.getLogger(__name__)

class InstagramService:
    """Service for uploading videos to Instagram, managing authentication, and handling multi-account logic."""
    
    def __init__(self, auth_manager: AuthManager):
        """Initialize with an AuthManager for client/account switching and credential management."""
        self.auth_manager = auth_manager
        self.current_client_id = None
        self.current_account_id = None
        self.base_url = "https://graph.facebook.com/v18.0"
        
    def _get_access_token(self, client_id: str) -> Optional[str]:
        """Get Instagram access token for a specific client."""
        try:
            # Switch to the specified client
            success, message = self.auth_manager.switch_client(client_id)
            if not success:
                raise Exception(f"Failed to switch to client {client_id}: {message}")
            
            # For Instagram, we need to get the access token from the token file directly
            token_path = os.path.join('tokens', f'instagram_token_{client_id}.json')
            if os.path.exists(token_path):
                import json
                with open(token_path, 'r') as f:
                    token_data = json.load(f)
                    return token_data.get('access_token')
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get access token for client {client_id}: {e}")
            return None
    
    def get_accounts_for_client(self, client_id: str) -> Tuple[List[Dict], str]:
        """Return a list of Instagram accounts for a client."""
        try:
            access_token = self._get_access_token(client_id)
            if not access_token:
                return [], "No valid access token for this client"
            
            # Instagram Graph API endpoint to get user accounts
            url = f"{self.base_url}/me/accounts"
            params = {
                'access_token': access_token,
                'fields': 'id,name,access_token'
            }
            
            response = requests.get(url, params=params)
            if response.status_code != 200:
                return [], f"Failed to get accounts: {response.text}"
            
            data = response.json()
            accounts = []
            
            for account in data.get('data', []):
                # Check if this account has Instagram Business/Creator account
                instagram_accounts = self._get_instagram_accounts(account['access_token'])
                accounts.extend(instagram_accounts)
            
            logger.info(f"Found {len(accounts)} Instagram accounts for client {client_id}")
            return accounts, "Success"
            
        except Exception as e:
            logger.error(f"Error getting accounts for client {client_id}: {e}")
            return [], f"Error getting accounts: {str(e)}"
    
    def _get_instagram_accounts(self, page_access_token: str) -> List[Dict]:
        """Get Instagram accounts associated with a Facebook page."""
        try:
            # First, get the page ID using the page access token
            url = f"{self.base_url}/me"
            params = {
                'access_token': page_access_token,
                'fields': 'id,name'
            }
            
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to get page info: {response.text}")
                return []
            
            page_data = response.json()
            page_id = page_data.get('id')
            page_name = page_data.get('name')
            
            if not page_id:
                logger.error("No page ID found")
                return []
            
            # Now get the Instagram account info for this specific page
            url = f"{self.base_url}/{page_id}"
            params = {
                'access_token': page_access_token,
                'fields': 'instagram_business_account{id,username,name,profile_picture_url}'
            }
            
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to get Instagram account for page {page_id}: {response.text}")
                return []
            
            data = response.json()
            instagram_accounts = []
            
            if 'instagram_business_account' in data:
                ig_account = data['instagram_business_account']
                instagram_accounts.append({
                    'id': ig_account['id'],
                    'username': ig_account.get('username', ''),
                    'name': ig_account.get('name', page_name),
                    'profile_picture_url': ig_account.get('profile_picture_url', ''),
                    'page_access_token': page_access_token,
                    'page_id': page_id,
                    'page_name': page_name
                })
            
            return instagram_accounts
            
        except Exception as e:
            logger.error(f"Error getting Instagram accounts: {e}")
            return []
    
    def switch_to_account(self, client_id: str, account_id: str) -> Tuple[bool, str]:
        """Switch to a specific Instagram account for a client."""
        try:
            # Get accounts for this client
            accounts, message = self.get_accounts_for_client(client_id)
            if message != "Success":
                return False, message
            
            # Check if account exists
            account_exists = any(acc['id'] == account_id for acc in accounts)
            if not account_exists:
                return False, f"Account {account_id} not found for client {client_id}"
            
            self.current_client_id = client_id
            self.current_account_id = account_id
            logger.info(f"Switched to Instagram account {account_id} for client {client_id}")
            return True, f"Switched to account {account_id}"
            
        except Exception as e:
            logger.error(f"Error switching to account {account_id} for client {client_id}: {e}")
            return False, f"Error switching account: {str(e)}"
    
    def upload_video(self, video_path: str, caption: str, hashtags: Optional[List[str]] = None, 
                    location: Optional[str] = None, account_id: Optional[str] = None, 
                    client_id: Optional[str] = None, video_url: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
        """Upload a video to Instagram with error handling and rate limiting. Returns (success, message, response_data)."""
        try:
            # Validate inputs
            if not video_url:
                return False, "No public video URL provided", None
            
            # Validate video URL format
            if not video_url.startswith(('http://', 'https://')):
                return False, "Invalid video URL format. Must be a public HTTP/HTTPS URL", None
            
            is_valid, error_msg = InputValidator.validate_instagram_caption(caption)
            if not is_valid:
                return False, error_msg, None
            # Use current client/account if not specified
            if not client_id:
                client_id = self.current_client_id
            if not account_id:
                account_id = self.current_account_id
            if not client_id:
                return False, "No client ID specified", None
            if not account_id:
                return False, "No account ID specified", None
            # Get access token
            access_token = self._get_access_token(client_id)
            if not access_token:
                return False, "No valid access token for this client", None
            # Switch to the specified account
            if account_id != self.current_account_id:
                success, message = self.switch_to_account(client_id, account_id)
                if not success:
                    return False, message, None
            # Get account details
            accounts, message = self.get_accounts_for_client(client_id)
            if message != "Success":
                return False, f"Failed to get accounts: {message}", None
            account = next((acc for acc in accounts if acc['id'] == account_id), None)
            if not account:
                return False, f"Account {account_id} not accessible with client {client_id}", None
            # Prepare caption with hashtags
            full_caption = caption
            if hashtags:
                hashtag_text = ' '.join([f'#{tag}' for tag in hashtags])
                full_caption += f'\n\n{hashtag_text}'
            
            # Validate caption length for Instagram
            if len(full_caption) > 2200:
                logger.warning(f"Caption too long ({len(full_caption)} chars), truncating to 2200 chars")
                full_caption = full_caption[:2197] + "..."
            
            logger.info(f"Final caption length: {len(full_caption)} characters")
            # Step 1: Create container (using public video_url)
            logger.info(f"Creating container for account {account_id} with video URL: {video_url[:50]}...")
            # Use the user access token for Instagram API calls
            user_access_token = self._get_access_token(client_id)
            container_response = self._create_container(account_id, user_access_token, video_url, full_caption)
            if not container_response:
                logger.error("Container creation failed - no response")
                return False, "Failed to create upload container. Please check that the video URL is accessible and the caption is valid.", None
            
            logger.info(f"Container response: {container_response}")
            container_id = container_response.get('id')
            if not container_id:
                logger.error(f"No container ID in response: {container_response}")
                return False, "No container ID received", None
            
            logger.info(f"Container created successfully with ID: {container_id}")
            
            # Step 2: Publish the container (with retry for processing)
            logger.info(f"Publishing container {container_id}")
            
            # Instagram videos need time to process before publishing
            # Let's poll the status and retry publishing
            max_retries = 10
            retry_delay = 30  # seconds
            
            for attempt in range(max_retries):
                publish_response = self._publish_container(container_id, user_access_token)
                if publish_response:
                    logger.info(f"Publish successful on attempt {attempt + 1}")
                    break
                else:
                    if attempt < max_retries - 1:
                        logger.info(f"Publish failed, video still processing. Retrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                    else:
                        logger.error("Publish failed after all retries")
                        return False, f"Failed to publish video after {max_retries} attempts. Container ID: {container_id}. Video may still be processing.", None
            
            if not publish_response:
                logger.error("Publish failed - no response")
                return False, "Failed to publish video", None
            
            logger.info(f"Publish response: {publish_response}")
            
            # Step 3: Check upload status
            logger.info(f"Checking upload status for container {container_id}")
            status_success, status_message, status_data = self.get_upload_status(container_id, client_id)
            if status_success:
                logger.info(f"Upload status: {status_data}")
                if status_data.get('status_code') == 'FINISHED':
                    logger.info("Upload completed successfully!")
                else:
                    logger.warning(f"Upload still processing. Status: {status_data.get('status_code')}")
            else:
                logger.warning(f"Could not check upload status: {status_message}")
            
            logger.info(f"Instagram upload successful! Container ID: {container_id}")
            
            # Create a detailed success message
            status_code = status_data.get('status_code', 'Unknown') if status_data else 'Unknown'
            if status_code == 'FINISHED':
                success_message = f"Video uploaded successfully! Container ID: {container_id}. Status: {status_code}. Video is now live on Instagram."
            elif status_code == 'ERROR':
                success_message = f"Video upload completed but encountered an error. Container ID: {container_id}. Status: {status_code}. Please check Instagram for details."
            else:
                success_message = f"Video upload completed! Container ID: {container_id}. Status: {status_code}. Video may still be processing."
            
            return True, success_message, publish_response
        except Exception as e:
            error_msg = f"Instagram upload error: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {e}")
            
            # Check if it's a KeyError for 'description'
            if isinstance(e, KeyError) and 'description' in str(e):
                logger.error("KeyError: 'description' field missing from response")
                return False, "Instagram API error: Missing description field in response", None
            
            return False, error_msg, None

    def _create_container(self, account_id: str, access_token: str, video_url: str, caption: str) -> Optional[Dict]:
        """Create a container for video upload using a public video URL."""
        try:
            # For Instagram uploads, we need to use the Instagram Basic Display API
            # This requires using the Instagram Business Account ID with the user access token
            
            logger.info(f"Creating container for Instagram Business Account: {account_id}")
            
            # Use the Instagram Basic Display API endpoint
            url = f"{self.base_url}/{account_id}/media"
            
            # Prepare the data payload
            data = {
                'access_token': access_token,
                'media_type': 'REELS',
                'video_url': video_url,
                'share_to_feed': True,
                'thumb_offset': 0
            }
            
            # Only add caption if it's not empty
            if caption and caption.strip():
                data['caption'] = caption.strip()
            
            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}
            
            logger.info(f"Making request to: {url}")
            logger.info(f"Request data: {data}")
            
            response = requests.post(url, data=data)
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response text: {response.text}")
            
            if response.status_code != 200:
                logger.error(f"Failed to create container: {response.text}")
                logger.error(f"Request data that failed: {data}")
                
                # Check if it's a description-related error
                if 'description' in response.text.lower():
                    logger.error("Instagram API error related to description/caption field")
                    logger.error(f"Caption length: {len(caption) if caption else 0}")
                    logger.error(f"Caption preview: {caption[:100] if caption else 'None'}...")
                    return None
                
                # Log other common errors
                if 'invalid' in response.text.lower():
                    logger.error("Instagram API error: Invalid parameters")
                elif 'permission' in response.text.lower():
                    logger.error("Instagram API error: Permission denied")
                elif 'quota' in response.text.lower():
                    logger.error("Instagram API error: Quota exceeded")
                
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error creating container: {e}")
            return None
    
    def _publish_container(self, container_id: str, access_token: str) -> Optional[Dict]:
        """Publish the container to make the video live."""
        try:
            # For Instagram, we need to use the Instagram Business Account ID for publishing
            # We need to get the Instagram Business Account ID from the user's pages
            
            # First, get the user's pages
            url = f"{self.base_url}/me/accounts"
            params = {
                'access_token': access_token,
                'fields': 'id,name,instagram_business_account{id}'
            }
            
            response = requests.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to get pages: {response.text}")
                return None
            
            pages_data = response.json()
            instagram_account_id = None
            
            # Find the page with Instagram Business Account
            for page in pages_data.get('data', []):
                if 'instagram_business_account' in page:
                    instagram_account_id = page['instagram_business_account']['id']
                    break
            
            if not instagram_account_id:
                logger.error("No Instagram Business Account found")
                return None
            
            logger.info(f"Using Instagram Business Account ID: {instagram_account_id} for publishing")
            
            # Now publish using the Instagram Business Account ID
            url = f"{self.base_url}/{instagram_account_id}/media_publish"
            data = {
                'access_token': access_token,
                'creation_id': container_id
            }
            
            response = requests.post(url, data=data)
            if response.status_code != 200:
                logger.error(f"Failed to publish container: {response.text}")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error publishing container: {e}")
            return None
    
    def get_upload_status(self, container_id: str, client_id: str) -> Tuple[bool, str, Optional[Dict]]:
        """Get the status of an upload."""
        try:
            access_token = self._get_access_token(client_id)
            if not access_token:
                return False, "No valid access token", None
            
            url = f"{self.base_url}/{container_id}"
            params = {'access_token': access_token, 'fields': 'status_code,status'}
            
            response = requests.get(url, params=params)
            if response.status_code != 200:
                return False, f"Failed to get status: {response.text}", None
            
            data = response.json()
            return True, "Success", data
            
        except Exception as e:
            logger.error(f"Error getting upload status: {e}")
            return False, f"Error getting status: {str(e)}", None 