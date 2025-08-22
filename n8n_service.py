import requests
import logging
import json
import os
from typing import Dict, List, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class N8nService:
    """Service for handling n8n webhook operations: config, job submission, and error handling."""
    
    def __init__(self):
        """Initialize the n8n service and load webhook configuration from file."""
        self.config_file = "n8n_config.json"
        self.submit_webhook_url = None
        self.nocap_webhook_url = None
        self.timeout = 30
        self.load_config()
    
    def load_config(self):
        """Load webhook URLs and settings from the n8n_config.json file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                
                self.submit_webhook_url = config['webhook_urls']['submit_job']
                self.nocap_webhook_url = config['webhook_urls']['nocap_job']
                self.timeout = config.get('timeout_seconds', 30)
                
                logger.info(f"Loaded n8n config: {config.get('last_updated', 'Unknown date')}")
                logger.info(f"Submit webhook: {self.submit_webhook_url}")
                logger.info(f"Nocap webhook: {self.nocap_webhook_url}")
            else:
                logger.error(f"n8n config file not found: {self.config_file}")
                raise FileNotFoundError(f"n8n config file not found: {self.config_file}")
                
        except Exception as e:
            logger.error(f"Error loading n8n config: {e}")
            raise
    
    def update_webhook_urls(self, submit_url: str, nocap_url: str):
        """Update webhook URLs in the config file and reload settings."""
        try:
            config = {
                "webhook_urls": {
                    "submit_job": submit_url,
                    "nocap_job": nocap_url
                },
                "timeout_seconds": self.timeout,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Reload config
            self.load_config()
            
            logger.info("n8n webhook URLs updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error updating n8n config: {e}")
            return False
    
    def get_current_urls(self) -> Dict[str, Optional[str]]:
        """Return the current webhook URLs as a dict."""
        return {
            "submit_job": self.submit_webhook_url,
            "nocap_job": self.nocap_webhook_url
        }
    
    def submit_job(self, user: str, images: List[str], audios: List[str]) -> Tuple[bool, str, Optional[int]]:
        """Submit a job to the n8n webhook. Returns (success, message, status_code)."""
        if not self.submit_webhook_url:
            return False, "n8n webhook URL not configured", None
            
        try:
            # Validate that we have exactly 4 images and 5 audio files
            if len(images) != 4:
                return False, f"Expected 4 images, got {len(images)}", None
                
            if len(audios) != 5:
                return False, f"Expected 5 audio files, got {len(audios)}", None
            
            # Separate the last audio as background_audio
            background_audio = audios[-1]
            audio_files = audios[:-1]  # First 4 audio files
            
            payload = {
                "user": user,
                "images": images,
                "audios": audio_files,
                "background_audio": background_audio
            }
            
            logger.info(f"Submitting job for user: {user}")
            logger.info(f"Images: {images}")
            logger.info(f"Audios: {audio_files}")
            logger.info(f"Background audio: {background_audio}")
            
            response = requests.post(
                self.submit_webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logger.info(f"Job submitted successfully for user: {user}")
                return True, "All inputs received! CHONAM.", response.status_code
            else:
                logger.error(f"n8n webhook returned status {response.status_code} for user: {user}")
                return False, f"n8n error: {response.status_code}", response.status_code
                
        except requests.exceptions.Timeout:
            error_msg = "Request timeout - n8n webhook took too long to respond"
            logger.error(f"Timeout error for user: {user}")
            return False, error_msg, None
            
        except requests.exceptions.ConnectionError:
            error_msg = "Connection error - unable to reach n8n webhook"
            logger.error(f"Connection error for user: {user}")
            return False, error_msg, None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)}"
            logger.error(f"Request error for user: {user}: {e}")
            return False, error_msg, None
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error for user: {user}: {e}")
            return False, error_msg, None
    
    def nocap_job(self, user: str, images: List[str], audios: List[str]) -> Tuple[bool, str, Optional[int]]:
        """Submit a nocap job to the n8n webhook. Returns (success, message, status_code)."""
        if not self.nocap_webhook_url:
            return False, "n8n webhook URL not configured", None
            
        try:
            payload = {
                "user": user,
                "images": images,
                "audios": audios
            }
            
            logger.info(f"Submitting nocap job for user: {user}")
            logger.info(f"Images: {images}")
            logger.info(f"Audios: {audios}")
            
            response = requests.post(
                self.nocap_webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logger.info(f"Nocap job submitted successfully for user: {user}")
                return True, "All inputs received! CHONAM.", response.status_code
            else:
                logger.error(f"n8n webhook returned status {response.status_code} for user: {user}")
                return False, f"n8n error: {response.status_code}", response.status_code
                
        except requests.exceptions.Timeout:
            error_msg = "Request timeout - n8n webhook took too long to respond"
            logger.error(f"Timeout error for user: {user}")
            return False, error_msg, None
            
        except requests.exceptions.ConnectionError:
            error_msg = "Connection error - unable to reach n8n webhook"
            logger.error(f"Connection error for user: {user}")
            return False, error_msg, None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)}"
            logger.error(f"Request error for user: {user}: {e}")
            return False, error_msg, None
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error for user: {user}: {e}")
            return False, error_msg, None 