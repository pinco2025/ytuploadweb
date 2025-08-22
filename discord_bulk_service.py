"""
Discord Bulk Job Service for processing JSON files and posting to webhooks with intervals
"""

import json
import time
import threading
import logging
import requests
import os
import signal
import atexit
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)

class DiscordBulkJobService:
    """Service for processing bulk Discord jobs with webhook posting and interval management."""
    
    def __init__(self):
        """Initialize the Discord bulk job service."""
        self.active_jobs = {}  # Store job status and data
        self.job_lock = threading.Lock()
        self.bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        self._shutdown_event = threading.Event()
        
        # Register cleanup handlers
        atexit.register(self._cleanup_on_exit)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down Discord bulk service...")
        self._cleanup_on_exit()
        
    def _cleanup_on_exit(self):
        """Clean up all active jobs when server shuts down."""
        try:
            logger.info("Cleaning up Discord bulk jobs on server shutdown...")
            with self.job_lock:
                # Cancel all running jobs
                for job_id, job_data in self.active_jobs.items():
                    if job_data['status'] in ['pending', 'running']:
                        job_data['status'] = 'cancelled'
                        logger.info(f"Cancelled job {job_id} due to server shutdown")
                
                # Clear all jobs from memory
                self.active_jobs.clear()
                logger.info("All Discord bulk jobs cleaned up")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        # Set shutdown event to stop any running threads
        self._shutdown_event.set()
    
    def create_bulk_job(self, json_data: List[Dict], webhook_url: str, 
                        interval_minutes: int = 5, webhook_type: str = 'submit_job', channel_name: str = None) -> Tuple[bool, str, str]:
        """
        Create a new bulk job with the provided data.
        
        Args:
            json_data: List of dictionaries, each with 'user', 'message_link', and 'background_audio' keys
            webhook_url: n8n webhook URL
            interval_minutes: Minutes between posts (default: 5)
            webhook_type: Type of webhook ('submit_job' or 'nocap_job')
            channel_name: Name of the Discord channel (optional)
        
        Returns:
            Tuple of (success, message, job_id)
        """
        try:
            # Validate JSON data structure
            if not json_data or not isinstance(json_data, list) or len(json_data) == 0:
                return False, "Invalid JSON data format. Expected a non-empty array of video objects.", ""
            
            # Validate each video item in the array
            for i, item in enumerate(json_data):
                if not isinstance(item, dict):
                    return False, f"Video item {i} is not a valid object", ""
                
                if 'user' not in item or 'message_link' not in item or 'background_audio' not in item:
                    return False, f"Video item {i} missing required 'user', 'message_link', or 'background_audio' field", ""
                
                if not item['user'] or not item['message_link'] or not item['background_audio']:
                    return False, f"Video item {i} has empty user, message_link, or background_audio", ""
            
            # Validate webhook URL
            if not webhook_url:
                return False, "Invalid webhook URL", ""
            
            # Check if Discord bot token is available
            if not self.bot_token:
                return False, "Discord bot token not configured", ""
            
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            
            # Create job data
            job_data = {
                'id': job_id,
                'data': json_data,  # Store the entire array
                'webhook_url': webhook_url,
                'webhook_type': webhook_type,
                'interval_minutes': interval_minutes,
                'total_items': len(json_data),
                'completed': 0,
                'failed': 0,
                'status': 'pending',
                'start_time': datetime.now().isoformat(),
                'next_post_time': None,
                'last_post_time': None,
                'errors': [],
                'channel_name': channel_name
            }
            
            # Store job data
            with self.job_lock:
                self.active_jobs[job_id] = job_data
            
            # Start background processing
            thread = threading.Thread(target=self._process_job, args=(job_id,))
            thread.daemon = True
            thread.start()
            
            logger.info(f"Created bulk job {job_id} with {len(json_data)} items")
            return True, f"Bulk job created successfully with {len(json_data)} items", job_id
            
        except Exception as e:
            logger.error(f"Error creating bulk job: {e}")
            return False, f"Error creating bulk job: {str(e)}", ""
    
    def _process_job(self, job_id: str):
        """Background thread to process the bulk job."""
        try:
            with self.job_lock:
                if job_id not in self.active_jobs:
                    return
                job_data = self.active_jobs[job_id]
                job_data['status'] = 'running'
            
            logger.info(f"Starting bulk job {job_id}")
            
            for i, item in enumerate(job_data['data']):
                try:
                    # Check if server is shutting down
                    if self._shutdown_event.is_set():
                        logger.info(f"Server shutting down, stopping job {job_id}")
                        with self.job_lock:
                            if job_id in self.active_jobs:
                                job_data['status'] = 'cancelled'
                        return
                    
                    # Check if job was cancelled
                    with self.job_lock:
                        if job_id not in self.active_jobs or job_data['status'] == 'cancelled':
                            return
                    
                    # Extract attachments from the message link
                    message_link = item['message_link']
                    try:
                        attachments = self._extract_attachments(message_link)
                    except Exception as e:
                        logger.error(f"Failed to extract attachments from message {i+1}: {e}")
                        with self.job_lock:
                            if job_id in self.active_jobs:
                                job_data['failed'] += 1
                                job_data['errors'].append(f"Failed to extract attachments from message {i+1}: {str(e)}")
                        continue
                    
                    # Create payload for n8n webhook with background_audio from each video object
                    n8n_payload = {
                        'audios': attachments['audios'],
                        'images': attachments['images'],
                        'background_audio': item['background_audio'],  # Use background_audio from each video object
                        'job_type': job_data['webhook_type'],
                        'user': item['user'],
                        'channel_name': job_data.get('channel_name')
                    }
                    
                    # Post to n8n webhook
                    success = self._post_to_n8n_webhook(job_data['webhook_url'], n8n_payload, item['name'])
                    
                    with self.job_lock:
                        if job_id in self.active_jobs:
                            job_data['completed'] += 1
                            job_data['last_post_time'] = datetime.now().isoformat()
                            
                            if not success:
                                job_data['failed'] += 1
                                job_data['errors'].append(f"Failed to post item {i+1}: {item['name']}")
                            
                            # Calculate next post time
                            if i < len(job_data['data']) - 1:  # Not the last item
                                next_time = datetime.now() + timedelta(minutes=job_data['interval_minutes'])
                                job_data['next_post_time'] = next_time.isoformat()
                    
                    logger.info(f"Posted item {i+1}/{len(job_data['data'])} for job {job_id}")
                    
                    # Wait for interval (except for the last item)
                    if i < len(job_data['data']) - 1:
                        # Wait in smaller chunks to check for shutdown
                        wait_time = job_data['interval_minutes'] * 60
                        chunk_size = 10  # Check every 10 seconds
                        for _ in range(0, wait_time, chunk_size):
                            if self._shutdown_event.is_set():
                                logger.info(f"Server shutting down during wait, stopping job {job_id}")
                                with self.job_lock:
                                    if job_id in self.active_jobs:
                                        job_data['status'] = 'cancelled'
                                return
                            time.sleep(min(chunk_size, wait_time - _))
                
                except Exception as e:
                    logger.error(f"Error processing item {i+1} for job {job_id}: {e}")
                    with self.job_lock:
                        if job_id in self.active_jobs:
                            job_data['failed'] += 1
                            job_data['errors'].append(f"Error processing item {i+1}: {str(e)}")
            
            # Mark job as completed
            with self.job_lock:
                if job_id in self.active_jobs:
                    job_data['status'] = 'completed'
                    job_data['next_post_time'] = None
            
            logger.info(f"Completed bulk job {job_id}")
            
        except Exception as e:
            logger.error(f"Error in bulk job {job_id}: {e}")
            with self.job_lock:
                if job_id in self.active_jobs:
                    job_data['status'] = 'error'
                    job_data['errors'].append(f"Job processing error: {str(e)}")
    
    def _post_to_n8n_webhook(self, webhook_url: str, payload: Dict, item_name: str) -> bool:
        """Post payload to n8n webhook."""
        try:
            response = requests.post(webhook_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"Successfully posted to n8n webhook: {item_name}")
                return True
            else:
                logger.error(f"Failed to post to n8n webhook. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error posting to n8n webhook: {e}")
            return False
    
    def _extract_attachments(self, message_link: str) -> Dict[str, List[str]]:
        """Extract images and audios from a Discord message link."""
        try:
            # Clean the message link
            if 'discordapp.com' in message_link:
                message_link = message_link.replace('discordapp.com', 'discord.com')
            if message_link.startswith('discord://'):
                message_link = message_link.replace('discord://discord', 'https://discord.com')
                message_link = message_link.replace('discord://', 'https://discord.com/')
            message_link = message_link.strip()
            
            # Parse the message link to extract channel_id and message_id
            parts = message_link.strip('/').split('/')
            channel_id = parts[-2] if len(parts) >= 2 else ''
            message_id = parts[-1] if len(parts) >= 1 else ''
            
            if not channel_id or not message_id:
                raise Exception("Invalid Discord message link format")
            
            # Fetch the message from Discord API
            url = f'https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}'
            headers = {'Authorization': f'Bot {self.bot_token}'}
            resp = requests.get(url, headers=headers)
            
            if resp.status_code != 200:
                raise Exception(f"Failed to fetch message: {resp.text}")
            
            data = resp.json()
            attachments = data.get('attachments', [])
            
            # Require exactly 8 attachments (4 audio + 4 images)
            if len(attachments) != 8:
                raise Exception(f"Message must have exactly 8 attachments (4 audio + 4 images), found {len(attachments)}")
            
            # Separate audio and image files by extension
            audio_exts = {'.mp3', '.wav', '.m4a', '.aac', '.mp4'}
            image_exts = {'.jpg', '.jpeg', '.png', '.webp'}
            
            audios_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in audio_exts)]
            images_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in image_exts)]
            
            audios = [a['url'] for a in audios_full]
            images = [a['url'] for a in images_full]
            
            # Validate we have exactly 4 audio and 4 image files
            if len(audios) != 4 or len(images) != 4:
                raise Exception(f"Message must have exactly 4 audio and 4 image files. Found {len(audios)} audio and {len(images)} images")
            
            # Reverse both arrays for consistency (like standard jobs)
            images = images[::-1]
            audios = audios[::-1]
            
            return {'images': images, 'audios': audios}
            
        except Exception as e:
            logger.error(f"Error extracting attachments from message link {message_link}: {e}")
            raise e
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get the status of a specific job."""
        with self.job_lock:
            return self.active_jobs.get(job_id)
    
    def cancel_job(self, job_id: str) -> Tuple[bool, str]:
        """Cancel a running job."""
        with self.job_lock:
            if job_id not in self.active_jobs:
                return False, "Job not found"
            
            job_data = self.active_jobs[job_id]
            if job_data['status'] in ['completed', 'cancelled', 'error']:
                return False, f"Job is already {job_data['status']}"
            
            job_data['status'] = 'cancelled'
            return True, "Job cancelled successfully"
    
    def get_all_jobs(self) -> Dict[str, Dict]:
        """Get all active jobs (for admin purposes)."""
        with self.job_lock:
            return self.active_jobs.copy()

# Global instance
discord_bulk_service = DiscordBulkJobService() 