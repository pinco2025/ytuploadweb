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
        self.longform_webhook_url = None
        self.compile_webhook_url = None
        self.timeout = 30
        self.load_config()
    
    def load_config(self):
        """Load webhook URLs and settings from the n8n_config.json file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                
                webhooks = config.get('webhook_urls', {})
                self.submit_webhook_url = webhooks.get('submit_job')
                self.nocap_webhook_url = webhooks.get('nocap_job')
                self.longform_webhook_url = webhooks.get('longform_job')
                self.compile_webhook_url = webhooks.get('compile_job')
                self.timeout = config.get('timeout_seconds', 30)
                
                logger.info(f"Loaded n8n config: {config.get('last_updated', 'Unknown date')}")
                logger.info(f"Submit webhook: {self.submit_webhook_url}")
                logger.info(f"Nocap webhook: {self.nocap_webhook_url}")
                logger.info(f"Longform webhook: {self.longform_webhook_url}")
                logger.info(f"Compile webhook: {self.compile_webhook_url}")
            else:
                logger.error(f"n8n config file not found: {self.config_file}")
                raise FileNotFoundError(f"n8n config file not found: {self.config_file}")
                
        except Exception as e:
            logger.error(f"Error loading n8n config: {e}")
            raise
    
    def update_webhook_urls(self, submit_url: str, nocap_url: str, longform_url: str = None, compile_url: str = None):
        """Update webhook URLs in the config file and reload settings."""
        try:
            config = {
                "webhook_urls": {
                    "submit_job": submit_url,
                    "nocap_job": nocap_url,
                    **({"longform_job": longform_url} if longform_url else {}),
                    **({"compile_job": compile_url} if compile_url else {})
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
    
    def update_webhook_urls_from_base(self, base_url: str):
        """Update all webhook URLs from a base ngrok URL. Generates all 4 URLs unanimously."""
        try:
            # Remove trailing slash if present
            if base_url.endswith('/'):
                base_url = base_url[:-1]
            
            # Generate all 4 webhook URLs from the base URL
            webhook_urls = {
                "submit_job": f"{base_url}/webhook/bgaud",
                "nocap_job": f"{base_url}/webhook/back", 
                "longform_job": f"{base_url}/webhook/longform",
                "compile_job": f"{base_url}/webhook/compile"
            }
            
            config = {
                "webhook_urls": webhook_urls,
                "timeout_seconds": self.timeout,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Reload config
            self.load_config()
            
            logger.info("All n8n webhook URLs updated unanimously from base URL")
            logger.info(f"Generated URLs: {webhook_urls}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating n8n config from base URL: {e}")
            return False
    
    def get_current_urls(self) -> Dict[str, Optional[str]]:
        """Return the current webhook URLs as a dict."""
        return {
            "submit_job": self.submit_webhook_url,
            "nocap_job": self.nocap_webhook_url,
            "longform_job": self.longform_webhook_url,
            "compile_job": self.compile_webhook_url
        }
    
    def submit_job(self, user: str, images: List[str], audios: List[str], background_audio: str = None, aud_speed: float = 1.0) -> Tuple[bool, str, Optional[int]]:
        """Submit a job to the n8n webhook. Returns (success, message, status_code)."""
        if not self.submit_webhook_url:
            return False, "n8n webhook URL not configured", None
            
        try:
            # Validate that we have exactly 4 images and 4 audio files
            if len(images) != 4:
                return False, f"Expected 4 images, got {len(images)}", None
                
            if len(audios) != 4:
                return False, f"Expected 4 audio files, got {len(audios)}", None
            
            # Use provided background_audio or default to last audio if not provided
            if background_audio is None:
                background_audio = audios[-1]  # Fallback for backward compatibility
            
            payload = {
                "user": user,
                "images": images,
                "audios": audios,
                "background_audio": background_audio,
                "aud_speed": aud_speed
            }
            
            logger.info(f"Submitting job for user: {user}")
            logger.info(f"Images: {images}")
            logger.info(f"Audios: {audios}")
            logger.info(f"Background audio: {background_audio}")
            logger.info(f"Audio speed: {aud_speed}x")
            
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