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
        self._active_threads = set()  # Track active threads
        
        # Register cleanup handlers
        atexit.register(self._cleanup_on_exit)
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except Exception as e:
            logger.warning(f"Could not register signal handlers: {e}")
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down Discord bulk service...")
        self._cleanup_on_exit()
        
    def _cleanup_on_exit(self):
        """Clean up all active jobs when server shuts down."""
        try:
            logger.info("Cleaning up Discord bulk jobs on server shutdown...")
            
            # Set shutdown event to stop any running threads
            self._shutdown_event.set()
            
            with self.job_lock:
                # Cancel all running jobs
                for job_id, job_data in self.active_jobs.items():
                    if job_data['status'] in ['pending', 'running']:
                        job_data['status'] = 'cancelled'
                        logger.info(f"Cancelled job {job_id} due to server shutdown")
                
                # Clear all jobs from memory
                self.active_jobs.clear()
                logger.info("All Discord bulk jobs cleaned up")
            
            # Wait for active threads to finish (with timeout)
            if self._active_threads:
                logger.info(f"Waiting for {len(self._active_threads)} active threads to finish...")
                for thread in list(self._active_threads):
                    if thread.is_alive():
                        thread.join(timeout=5.0)  # Wait up to 5 seconds per thread
                        if thread.is_alive():
                            logger.warning(f"Thread {thread.name} did not finish within timeout")
                
                self._active_threads.clear()
                logger.info("All threads cleaned up")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    


    def create_wizard_bulk_job(self, num_videos: int, webhook_url: str, webhook_type: str, 
                              titles: List[str], audio_links: List[str], background_audio_links: List[str],
                              audio_speed: float, image_links: List[str], image_set_channel: str, 
                              use_second_image_set: bool = False, second_image_links: List[str] = None, 
                              second_image_set_channel: str = '', interval_minutes: int = 5) -> Tuple[bool, str, str]:
        """
        Create a new wizard-based bulk job with separate audio and image sets.
        
        Args:
            num_videos: Number of videos to create
            webhook_url: n8n webhook URL
            webhook_type: Type of webhook ('submit_job' or 'nocap_job')
            titles: List of video titles
            audio_links: List of Discord message links containing audio files
            background_audio_links: List of Discord message links containing background audio files
            audio_speed: Audio playback speed (1.0 to 2.0)
            image_links: List of Discord message links containing image files
            image_set_channel: Channel name for first image set
            use_second_image_set: Whether to create a second image set with same audio
            second_image_links: List of Discord message links for second image set
            second_image_set_channel: Channel name for second image set
            interval_minutes: Minutes between posts
        
        Returns:
            Tuple of (success, message, job_id)
        """
        try:
            # Validate inputs
            if not all([num_videos, webhook_url, webhook_type, titles, audio_links, 
                       background_audio_links, image_links, image_set_channel]):
                return False, "Missing required parameters", ""
            
            if not self.bot_token:
                return False, "Discord bot token not configured", ""
            
            # Generate unique job ID
            job_id = str(uuid.uuid4())
            
            # Calculate total jobs (include second image set if enabled)
            total_jobs = num_videos * (2 if use_second_image_set else 1)
            
            # Create job data
            job_data = {
                'id': job_id,
                'job_type': 'wizard',  # Mark as wizard job
                'num_videos': num_videos,
                'webhook_url': webhook_url,
                'webhook_type': webhook_type,
                'titles': titles,
                'audio_links': audio_links,
                'background_audio_links': background_audio_links,
                'audio_speed': audio_speed,
                'image_links': image_links,
                'image_set_channel': image_set_channel,
                'use_second_image_set': use_second_image_set,
                'second_image_links': second_image_links or [],
                'second_image_set_channel': second_image_set_channel,
                'interval_minutes': interval_minutes,
                'total_items': total_jobs,
                'completed': 0,
                'failed': 0,
                'status': 'pending',
                'start_time': datetime.now().isoformat(),
                'next_post_time': None,
                'last_post_time': None,
                'errors': []
            }
            
            # Store job data
            with self.job_lock:
                self.active_jobs[job_id] = job_data
            
            # Start background processing
            thread = threading.Thread(target=self._process_wizard_job, args=(job_id,), name=f"discord_wizard_job_{job_id}")
            thread.daemon = True
            self._active_threads.add(thread)
            thread.start()
            
            logger.info(f"Created wizard bulk job {job_id} with {total_jobs} total jobs ({num_videos} videos)")
            return True, f"Wizard bulk job created successfully with {total_jobs} total jobs", job_id
            
        except Exception as e:
            logger.error(f"Error creating wizard bulk job: {e}")
            return False, f"Error creating wizard bulk job: {str(e)}", ""
    

    
    def _process_wizard_job(self, job_id: str):
        """Background thread to process the wizard bulk job."""
        try:
            with self.job_lock:
                if job_id not in self.active_jobs:
                    return
                job_data = self.active_jobs[job_id]
                job_data['status'] = 'running'
            
            logger.info(f"Starting wizard bulk job {job_id}")
            
            # Process first image set
            self._process_image_set(job_id, job_data, 1)
            
            # Process second image set if enabled
            if job_data.get('use_second_image_set', False):
                self._process_image_set(job_id, job_data, 2)
            
            # Mark job as completed
            with self.job_lock:
                if job_id in self.active_jobs:
                    job_data['status'] = 'completed'
                    job_data['next_post_time'] = None
            
            logger.info(f"Completed wizard bulk job {job_id}")
            
        except Exception as e:
            logger.error(f"Error in wizard bulk job {job_id}: {e}")
            with self.job_lock:
                if job_id in self.active_jobs:
                    job_data['status'] = 'error'
                    job_data['errors'].append(f"Job processing error: {str(e)}")
        finally:
            # Clean up thread reference
            current_thread = threading.current_thread()
            if current_thread in self._active_threads:
                self._active_threads.remove(current_thread)
    
    def _process_image_set(self, job_id: str, job_data: Dict, image_set_number: int):
        """Process a single image set (1 or 2) for all videos."""
        try:
            num_videos = job_data['num_videos']
            
            # Determine which image set to use
            if image_set_number == 1:
                image_links = job_data['image_links']
                channel_name = job_data['image_set_channel']
            else:
                image_links = job_data['second_image_links']
                channel_name = job_data['second_image_set_channel']
            
            for video_index in range(num_videos):
                try:
                    # Check if server is shutting down or job was cancelled
                    if self._shutdown_event.is_set():
                        logger.info(f"Server shutting down, stopping wizard job {job_id}")
                        with self.job_lock:
                            if job_id in self.active_jobs:
                                job_data['status'] = 'cancelled'
                        return
                    
                    with self.job_lock:
                        if job_id not in self.active_jobs or job_data['status'] == 'cancelled':
                            return
                    
                    # Get data for this video
                    title = job_data['titles'][video_index]
                    audio_link = job_data['audio_links'][video_index]
                    background_audio_link = job_data['background_audio_links'][video_index]
                    image_link = image_links[video_index]
                    
                    # Extract attachments from Discord messages
                    try:
                        audio_attachments = self._extract_attachments(audio_link)
                        # Background audio is now a direct URL, not a Discord message link
                        background_audio_url = background_audio_link.strip()
                        image_attachments = self._extract_attachments(image_link)
                    except Exception as e:
                        error_msg = f"Failed to extract attachments for video {video_index + 1} (image set {image_set_number}): {str(e)}"
                        logger.error(error_msg)
                        with self.job_lock:
                            if job_id in self.active_jobs:
                                job_data['failed'] += 1
                                job_data['errors'].append(error_msg)
                        continue
                    
                    # Create payload for n8n webhook
                    n8n_payload = {
                        'user': title,
                        'images': image_attachments['images'],  # 4 images from Discord (reversed)
                        'audios': audio_attachments['audios'],  # 4 audios from Discord (reversed)
                        'background_audio': background_audio_url,  # Single background audio URL
                        'aud_speed': job_data['audio_speed'],  # Audio speed multiplier
                        'channel_name': channel_name
                    }
                    
                    # Post to n8n webhook
                    success = self._post_to_n8n_webhook(job_data['webhook_url'], n8n_payload, 
                                                      f"{title} (Set {image_set_number})")
                    
                    with self.job_lock:
                        if job_id in self.active_jobs:
                            job_data['completed'] += 1
                            job_data['last_post_time'] = datetime.now().isoformat()
                            
                            if not success:
                                job_data['failed'] += 1
                                job_data['errors'].append(f"Failed to post video {video_index + 1} (image set {image_set_number}): {title}")
                            
                            # Calculate next post time if not the last item
                            current_job_number = job_data['completed']
                            if current_job_number < job_data['total_items']:
                                next_time = datetime.now() + timedelta(minutes=job_data['interval_minutes'])
                                job_data['next_post_time'] = next_time.isoformat()
                    
                    logger.info(f"Posted video {video_index + 1}/{num_videos} (image set {image_set_number}) for wizard job {job_id}")
                    
                    # Wait for interval (except for the last item of the last set)
                    current_job_number = job_data['completed']
                    if current_job_number < job_data['total_items']:
                        # Wait in smaller chunks to check for shutdown
                        wait_time_seconds = job_data['interval_minutes'] * 60
                        chunk_size = 10  # Check every 10 seconds
                        for wait_elapsed in range(0, wait_time_seconds, chunk_size):
                            if self._shutdown_event.is_set():
                                logger.info(f"Server shutting down during wait, stopping wizard job {job_id}")
                                with self.job_lock:
                                    if job_id in self.active_jobs:
                                        job_data['status'] = 'cancelled'
                                return
                            time.sleep(min(chunk_size, wait_time_seconds - wait_elapsed))
                
                except Exception as e:
                    error_msg = f"Error processing video {video_index + 1} (image set {image_set_number}) for wizard job {job_id}: {str(e)}"
                    logger.error(error_msg)
                    with self.job_lock:
                        if job_id in self.active_jobs:
                            job_data['failed'] += 1
                            job_data['errors'].append(error_msg)
            
        except Exception as e:
            error_msg = f"Error processing image set {image_set_number} for wizard job {job_id}: {str(e)}"
            logger.error(error_msg)
            with self.job_lock:
                if job_id in self.active_jobs:
                    job_data['errors'].append(error_msg)
    
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
        """Extract images and audios from a Discord message link (Wizard mode: 4 attachments)."""
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
            
            # Wizard mode: exactly 4 attachments (either all audio or all images)
            if len(attachments) != 4:
                raise Exception(f"Message must have exactly 4 attachments, found {len(attachments)}")
            
            # Separate audio and image files by extension
            audio_exts = {'.mp3', '.wav', '.m4a', '.aac', '.mp4'}
            image_exts = {'.jpg', '.jpeg', '.png', '.webp'}
            
            audios_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in audio_exts)]
            images_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in image_exts)]
            
            audios = [a['url'] for a in audios_full]
            images = [a['url'] for a in images_full]
            
            # Determine what type of attachments we have
            if len(audios) == 4 and len(images) == 0:
                # All audio files
                pass
            elif len(images) == 4 and len(audios) == 0:
                # All image files  
                pass
            else:
                raise Exception(f"Message must have exactly 4 files of the same type. Found {len(audios)} audio and {len(images)} images")
            
            # Reverse both arrays for consistency (last attachment first)
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