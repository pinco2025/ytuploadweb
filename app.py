# --- Flask Application for YouTube Shorts Uploader and n8n Integration ---
#
# This app provides endpoints for uploading videos to YouTube from Google Drive,
# managing multiple OAuth clients/channels, and submitting jobs to n8n webhooks.
#
# All business logic is handled in service classes. This file wires up the routes.

# --- Discord single job functionality has been removed ---
# Only Discord bulk job functionality remains

from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session, abort
import os
import uuid
import tempfile
import logging
import webbrowser
from datetime import datetime
from typing import Dict, List, Optional
from youtube_service import YouTubeServiceV2
from instagram_service import InstagramService
from auth_manager import AuthManager
from validators import InputValidator
from n8n_service import N8nService
from config import Config
import requests
import json
import urllib.parse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
from google_drive_service import GoogleDriveService
from gemini_service import GeminiService
from discord_bulk_service import discord_bulk_service
import atexit
import shutil
import re
import threading
from datetime import timedelta

# --- Long Form Jobs storage ---
LONGFORM_DB_PATH = os.path.join(os.getcwd(), 'long_form_projects.json')
_longform_lock = threading.Lock()
_job_lock = threading.Lock()
LONGFORM_JOB_STATE = {"active": False, "ends_at": None, "reason": ""}

def _load_longform_db():
    try:
        if not os.path.exists(LONGFORM_DB_PATH):
            return {"projects": []}
        with open(LONGFORM_DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load long form DB: {e}")
        return {"projects": []}

def _save_longform_db(data):
    try:
        os.makedirs(os.path.dirname(LONGFORM_DB_PATH), exist_ok=True)
        with open(LONGFORM_DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save long form DB: {e}")
        return False

def _create_empty_rows(num_rows: int = 14):
    rows = []
    for i in range(1, num_rows + 1):
        rows.append({
            "serial_number": i,
            "audio_url": "",
            "image_url": "",
            "status": "incomplete"
        })
    return rows

# In-memory store for bulk upload results (cleared on app restart)
BULK_RESULTS = {}

# In-memory store to track active bulk upload requests (prevents duplicate processing)
ACTIVE_BULK_REQUESTS = set()

# Testing mode permanently disabled in production
TESTING_BULK_UPLOAD = False  # formerly driven by env var

app = Flask(__name__)
app.config.from_object(Config)

# Move these lines AFTER app is defined
UPLOADS_DIR = app.config['UPLOAD_FOLDER']

def clear_uploads_dir():
    if os.path.exists(UPLOADS_DIR):
        for filename in os.listdir(UPLOADS_DIR):
            file_path = os.path.join(UPLOADS_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                logger.warning(f'Failed to delete {file_path}: {e}')

atexit.register(clear_uploads_dir)

# Allow OAuth2 to work with HTTP for localhost development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Console now shows full logs (INFO by default). Use env CONSOLE_LOG_LEVEL to override.
console_level = os.environ.get('CONSOLE_LOG_LEVEL', 'INFO').upper()

console_handler = logging.StreamHandler()
console_handler.setLevel(console_level)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

file_handler = logging.FileHandler('app.log')
file_handler.setLevel(os.environ.get('FILE_LOG_LEVEL', 'INFO').upper())
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(level=getattr(logging, console_level), handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize services
auth_manager = AuthManager()
youtube_service = YouTubeServiceV2(auth_manager)
instagram_service = InstagramService(auth_manager)
n8n_service = N8nService()
drive_service = GoogleDriveService()

# Initialize Gemini service (optional - only if API key is available)
try:
    gemini_service = GeminiService()
    GEMINI_AVAILABLE = True
except Exception as e:
    logger.warning(f"Gemini service not available: {e}")
    gemini_service = None
    GEMINI_AVAILABLE = False

# Register Flask shutdown handler
@atexit.register
def cleanup_on_flask_shutdown():
    """Clean up Discord bulk jobs when Flask app shuts down."""
    try:
        logger.info("Flask app shutting down, cleaning up Discord bulk jobs...")
        discord_bulk_service._cleanup_on_exit()
    except Exception as e:
        logger.error(f"Error during Flask shutdown cleanup: {e}")

# Flask app startup setup
def setup_app():
    """Setup before first request."""
    logger.info("Flask app starting up...")

# Call setup function when app starts
with app.app_context():
    setup_app()

# Flask shutdown event handler
@app.teardown_appcontext
def cleanup_on_request_end(exception=None):
    """Clean up after each request ends."""
    pass  # This is just a placeholder for now

# Register a function to be called when the Flask app context is torn down
def cleanup_on_app_shutdown():
    """Clean up when Flask app shuts down."""
    try:
        logger.info("Flask app context tearing down, cleaning up...")
        discord_bulk_service._cleanup_on_exit()
    except Exception as e:
        logger.error(f"Error during Flask app shutdown cleanup: {e}")

# Register the cleanup function
atexit.register(cleanup_on_app_shutdown)

# --- Discord single job functionality has been removed ---
# Only Discord bulk job functionality remains

def load_n8n_config():
    """Load n8n webhook configuration from file."""
    try:
        with open('n8n_config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f'Error loading n8n_config.json: {e}')
        return {}

# Discord Bulk Job routes
if app.config['ENABLE_DISCORD_JOB']:
    @app.route('/discord-bulk-job', methods=['GET'])
    def discord_bulk_job():
        """Discord bulk job wizard interface."""
        return render_template('discord_bulk_job.html', config=app.config)
    
    @app.route('/api/discord-bulk-job-status/<job_id>')
    def discord_bulk_job_status(job_id):
        """Get the status of a Discord bulk job."""
        try:
            job_data = discord_bulk_service.get_job_status(job_id)
            
            if not job_data:
                return jsonify({'success': False, 'message': 'Job not found.'}), 404
            
            # Format next post time for display
            next_post_time = None
            if job_data.get('next_post_time'):
                try:
                    next_time = datetime.fromisoformat(job_data['next_post_time'])
                    next_post_time = next_time.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
            
            return jsonify({
                'success': True,
                'job_id': job_id,
                'status': job_data['status'],
                'total': job_data['total_items'],
                'completed': job_data['completed'],
                'failed': job_data['failed'],
                'next_post_time': next_post_time,
                'errors': job_data.get('errors', [])
            })
            
        except Exception as e:
            logger.error(f"Error getting job status: {e}")
            return jsonify({'success': False, 'message': f'Error getting job status: {str(e)}'}), 500
    
    @app.route('/api/discord-bulk-job-cancel/<job_id>', methods=['POST'])
    def discord_bulk_job_cancel(job_id):
        """Cancel a running Discord bulk job."""
        try:
            success, message = discord_bulk_service.cancel_job(job_id)
            
            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': message}), 400
                
        except Exception as e:
            logger.error(f"Error cancelling job: {e}")
            return jsonify({'success': False, 'message': f'Error cancelling job: {str(e)}'}), 500
    
    @app.route('/discord-bulk-job-wizard', methods=['POST'])
    def discord_bulk_job_wizard():
        """Handle Discord bulk job submission from wizard interface."""
        try:
            # Get JSON data from request
            data = request.get_json()
            
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400
            
            # Extract wizard data
            num_videos = data.get('numVideos', 0)
            webhook_type = data.get('webhookType', '').strip()
            titles = data.get('titles', [])
            audio_links = data.get('audioLinks', [])
            background_audio_links = data.get('backgroundAudioLinks', [])
            audio_speed = data.get('audioSpeed', 1.0)
            image_links = data.get('imageLinks', [])
            image_set_channel = data.get('imageSetChannel', '').strip()
            use_second_image_set = data.get('useSecondImageSet', False)
            second_image_links = data.get('secondImageLinks', [])
            second_image_set_channel = data.get('secondImageSetChannel', '').strip()
            interval_minutes = data.get('intervalMinutes', 5)
            
            # Validate basic requirements
            if not num_videos or num_videos < 1:
                return jsonify({'success': False, 'message': 'Invalid number of videos'}), 400
            
            if webhook_type not in ['submit_job', 'nocap_job']:
                return jsonify({'success': False, 'message': 'Invalid webhook type'}), 400
            
            # Get webhook URL from n8n config
            n8n_config = load_n8n_config()
            webhook_urls = n8n_config.get('webhook_urls', {})
            webhook_url = webhook_urls.get(webhook_type)
            
            if not webhook_url:
                return jsonify({'success': False, 'message': f'No webhook URL configured for {webhook_type.replace("_", " ")}'}), 400
            
            # Validate counts match
            if len(titles) != num_videos:
                return jsonify({'success': False, 'message': f'Number of titles ({len(titles)}) must match number of videos ({num_videos})'}), 400
            
            if len(audio_links) != num_videos:
                return jsonify({'success': False, 'message': f'Number of audio links ({len(audio_links)}) must match number of videos ({num_videos})'}), 400
            
            if len(background_audio_links) != num_videos:
                return jsonify({'success': False, 'message': f'Number of background audio links ({len(background_audio_links)}) must match number of videos ({num_videos})'}), 400
            
            if len(image_links) != num_videos:
                return jsonify({'success': False, 'message': f'Number of image links ({len(image_links)}) must match number of videos ({num_videos})'}), 400
            
            if not image_set_channel:
                return jsonify({'success': False, 'message': 'Image set channel is required'}), 400
            
            # Validate second image set if enabled
            if use_second_image_set:
                if len(second_image_links) != num_videos:
                    return jsonify({'success': False, 'message': f'Number of second image links ({len(second_image_links)}) must match number of videos ({num_videos})'}), 400
                
                if not second_image_set_channel:
                    return jsonify({'success': False, 'message': 'Second image set channel is required when using second image set'}), 400
            
            # Validate Discord message link formats (for audio and image links)
            discord_links = audio_links + image_links
            if use_second_image_set:
                discord_links += second_image_links
            
            for link in discord_links:
                # Clean the message link
                if 'discordapp.com' in link:
                    link = link.replace('discordapp.com', 'discord.com')
                if link.startswith('discord://'):
                    link = link.replace('discord://discord', 'https://discord.com')
                    link = link.replace('discord://', 'https://discord.com/')
                link = link.strip()
                
                # Validate Discord link format
                import re
                discord_pattern = r'^https://discord\.com/channels/\d+/\d+/\d+$'
                if not re.match(discord_pattern, link):
                    return jsonify({'success': False, 'message': f'Invalid Discord message link format: {link}'}), 400
            
            # Validate background audio URLs (direct links)
            import urllib.parse
            for i, bg_audio_url in enumerate(background_audio_links):
                bg_audio_url = bg_audio_url.strip()
                try:
                    result = urllib.parse.urlparse(bg_audio_url)
                    if not all([result.scheme, result.netloc]):
                        return jsonify({'success': False, 'message': f'Invalid background audio URL {i+1}: {bg_audio_url}'}), 400
                    if result.scheme not in ['http', 'https']:
                        return jsonify({'success': False, 'message': f'Background audio URL {i+1} must use HTTP or HTTPS: {bg_audio_url}'}), 400
                except Exception as e:
                    return jsonify({'success': False, 'message': f'Invalid background audio URL {i+1}: {bg_audio_url}'}), 400
            
            # Validate audio speed
            try:
                audio_speed = float(audio_speed)
                if audio_speed < 1.0 or audio_speed > 2.0:
                    return jsonify({'success': False, 'message': 'Audio speed must be between 1.0 and 2.0'}), 400
            except (ValueError, TypeError):
                return jsonify({'success': False, 'message': 'Invalid audio speed value'}), 400
            
            # Create wizard job using the new wizard service
            success, message, job_id = discord_bulk_service.create_wizard_bulk_job(
                num_videos=num_videos,
                webhook_url=webhook_url,
                webhook_type=webhook_type,
                titles=titles,
                audio_links=audio_links,
                background_audio_links=background_audio_links,
                audio_speed=audio_speed,
                image_links=image_links,
                image_set_channel=image_set_channel,
                use_second_image_set=use_second_image_set,
                second_image_links=second_image_links if use_second_image_set else [],
                second_image_set_channel=second_image_set_channel if use_second_image_set else '',
                interval_minutes=interval_minutes
            )
            
            if success:
                return jsonify({
                    'success': True,
                    'message': message,
                    'job_id': job_id
                })
            else:
                return jsonify({'success': False, 'message': message}), 400
                
        except Exception as e:
            logger.error(f"Error in discord bulk job wizard: {e}")
            return jsonify({'success': False, 'message': f'Error processing wizard job: {str(e)}'}), 500

# Home route - redirects to bulk uploader
@app.route('/', methods=['GET'])
def home():
    """Home page - redirects to bulk uploader."""
    return redirect(url_for('bulk_uploader'))

@app.route('/api/channels/<client_id>')
def get_channels_for_client(client_id):
    """API endpoint to get channels for a specific client."""
    try:
        # Validate client ID
        available_clients = auth_manager.get_all_clients()
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_msg,
                "channels": []
            })
        
        # Get channels for the client
        channels, message = youtube_service.get_channels_for_client(client_id)
        
        if message == "Success":
            return jsonify({
                "success": True,
                "channels": channels
            })
        else:
            return jsonify({
                "success": False,
                "error": message,
                "channels": []
            })
            
    except Exception as e:
        logger.error(f"Error getting channels for client {client_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "channels": []
        })

@app.route('/api/clients')
def get_clients():
    """API endpoint to get all clients with quota information."""
    try:
        clients = auth_manager.get_all_clients()
        quota_status = {}
        
        for client in clients:
            quota_status[client['id']] = youtube_service.get_quota_status(client['id'])
        
        return jsonify({
            "success": True,
            "clients": clients,
            "quota_status": quota_status
        })
    except Exception as e:
        logger.error(f"Error getting clients: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "clients": [],
            "quota_status": {}
        })

@app.route('/api/quota/<client_id>')
def get_quota_status(client_id):
    """API endpoint to get quota status for a specific client."""
    try:
        # Validate client ID
        available_clients = auth_manager.get_all_clients()
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_msg,
                "quota_status": {}
            })
        
        quota_status = youtube_service.get_quota_status(client_id)
        
        return jsonify({
            "success": True,
            "quota_status": quota_status
        })
        
    except Exception as e:
        logger.error(f"Error getting quota status for client {client_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "quota_status": {}
        })

@app.route('/api/switch-client/<client_id>')
def switch_client(client_id):
    """API endpoint to switch to a different client."""
    try:
        # Validate client ID
        available_clients = auth_manager.get_all_clients()
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_msg
            })
        
        success, message = auth_manager.switch_client(client_id)
        
        return jsonify({
            "success": success,
            "message": message
        })
        
    except Exception as e:
        logger.error(f"Error switching to client {client_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/switch-channel/<client_id>/<channel_id>')
def switch_channel(client_id, channel_id):
    """API endpoint to switch to a specific channel for a client."""
    try:
        # Validate client ID
        available_clients = auth_manager.get_all_clients()
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_msg
            })
        
        success, message = youtube_service.switch_to_channel(client_id, channel_id)
        
        return jsonify({
            "success": success,
            "message": message
        })
        
    except Exception as e:
        logger.error(f"Error switching to channel {channel_id} for client {client_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/verify-token/<client_id>')
def verify_token(client_id):
    """API endpoint to verify and refresh token for a client if needed."""
    try:
        # Validate client ID
        available_clients = auth_manager.get_all_clients()
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_msg,
                "needs_auth": False
            })
        
        # Get client info
        client = auth_manager.get_client_by_id(client_id)
        if not client:
            return jsonify({
                "success": False,
                "error": "Client not found",
                "needs_auth": False
            })
        
        # Use the new check_token_status method
        has_token, message, needs_auth = auth_manager.check_token_status(client_id)
        
        return jsonify({
            "success": has_token,
            "message": message,
            "needs_auth": needs_auth,
            "client_type": client.get('type', 'youtube')
        })
        
    except Exception as e:
        logger.error(f"Error verifying token for client {client_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "needs_auth": False
        })

@app.route('/api/generate-oauth-url/<client_id>')
def generate_oauth_url(client_id):
    """API endpoint to generate OAuth URL for client authentication."""
    try:
        # Validate client ID
        available_clients = auth_manager.get_all_clients()
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": error_msg
            })
        
        success, url_or_error = auth_manager.generate_oauth_url(client_id)
        
        return jsonify({
            "success": success,
            "oauth_url": url_or_error if success else None,
            "error": None if success else url_or_error
        })
        
    except Exception as e:
        logger.error(f"Error generating OAuth URL for client {client_id}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/validate-link', methods=['POST'])
def validate_drive_link():
    """API endpoint to validate Google Drive link."""
    try:
        data = request.get_json()
        drive_link = data.get('drive_link', '')
        
        is_valid, error_msg, file_id = InputValidator.validate_google_drive_link(drive_link)
        
        return jsonify({
            "success": is_valid,
            "error": error_msg if not is_valid else "",
            "file_id": file_id
        })
        
    except Exception as e:
        logger.error(f"Error validating drive link: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "file_id": None
        })

@app.route('/api/convert-drive-link', methods=['POST'])
def convert_drive_link():
    """API endpoint to convert Google Drive view link to direct download link."""
    try:
        data = request.get_json()
        drive_link = data.get('drive_link', '')
        
        if not drive_link:
            return jsonify({
                "success": False,
                "error": "No drive link provided",
                "direct_link": None
            })
        
        # Use the Google Drive service to convert the link
        conversion_result = drive_service.convert_to_direct_link(drive_link)
        
        if conversion_result['success']:
            return jsonify({
                "success": True,
                "direct_link": conversion_result['direct_link'],
                "preview_link": conversion_result.get('preview_link'),
                "file_id": conversion_result['file_id'],
                "message": conversion_result['message']
            })
        else:
            return jsonify({
                "success": False,
                "error": conversion_result['error'],
                "direct_link": None
            })
        
    except Exception as e:
        logger.error(f"Error converting drive link: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "direct_link": None
        })

@app.route('/api/generate-content', methods=['POST'])
def generate_content():
    """Generate SEO-optimized content using Gemini AI based on filename from drive link"""
    try:
        if not GEMINI_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "Gemini AI service is not available. Please check your GEMINI_API_KEY configuration."
            }), 400
        
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400
        
        drive_link = data.get('drive_link', '').strip()
        platform = data.get('platform', 'youtube').lower()
        filename_override = data.get('filename_override', '').strip()
        
        if not drive_link:
            return jsonify({
                "success": False,
                "error": "Drive link is required"
            }), 400
        
        if platform not in ['youtube', 'instagram']:
            return jsonify({
                "success": False,
                "error": "Platform must be 'youtube' or 'instagram'"
            }), 400
        
        # Use filename override if provided, otherwise extract from drive link
        if filename_override:
            filename = filename_override
            logger.info(f"Using filename override: {filename}")
        else:
            try:
                file_info = drive_service.get_file_info(drive_link)
                if not file_info or 'name' not in file_info:
                    return jsonify({
                        "success": False,
                        "error": "Could not extract filename from drive link. Please use the filename override field."
                    }), 400
                
                filename = file_info['name']
                extraction_method = file_info.get('extracted_with', 'unknown')
                logger.info(f"Extracted filename from drive link: {filename} (method: {extraction_method})")
                
                # Check if we got a generic filename
                if filename.startswith('video_') and len(filename) < 20:
                    logger.warning(f"Got generic filename: {filename}. Recommend using filename override for better AI generation.")
                    
                # Provide feedback about extraction quality
                if extraction_method == 'fallback':
                    logger.warning("Using fallback filename extraction. Consider providing service account credentials for better results.")
                    
            except Exception as e:
                logger.error(f"Error extracting filename from drive link: {e}")
                return jsonify({
                    "success": False,
                    "error": f"Error extracting filename: {str(e)}"
                }), 400
        
        # Generate content using Gemini
        try:
            content = gemini_service.generate_content(filename, platform)
            
            if not content['success']:
                return jsonify({
                    "success": False,
                    "error": content.get('error', 'Failed to generate content')
                }), 500
            
            return jsonify({
                "success": True,
                "content": {
                    "title": content['title'],
                    "description": content['description'],
                    "hashtags": content['hashtags']
                },
                "filename": filename,
                "platform": platform
            })
            
        except Exception as e:
            logger.error(f"Error generating content with Gemini: {e}")
            return jsonify({
                "success": False,
                "error": f"Error generating content: {str(e)}"
            }), 500
        
    except Exception as e:
        logger.error(f"Error in generate_content endpoint: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/health')
def health_check():
    """Health check endpoint."""
    try:
        # Check if services are properly initialized
        clients = auth_manager.get_all_clients()
        
        return jsonify({
            "status": "healthy",
            "clients_configured": len(clients),
            "upload_folder_exists": os.path.exists(app.config['UPLOAD_FOLDER']),
            "gemini_available": GEMINI_AVAILABLE
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

# Instagram uploader routes
if app.config['ENABLE_INSTAGRAM_UPLOAD']:
    @app.route('/instagram', methods=['GET', 'POST'])
    def instagram_upload():
        """Instagram upload page with improved error handling and validation."""
        if request.method == 'GET':
            try:
                # Get available clients
                clients = auth_manager.get_all_clients()
                return render_template('instagram.html', clients=clients, config=app.config)
            except Exception as e:
                logger.error(f"Error loading Instagram page: {e}")
                flash(f'Error loading page: {str(e)}', 'error')
                return render_template('instagram.html', clients=[], config=app.config)

        # POST: handle upload logic
        try:
            # Get form data from POST request
            form_data = {
                'drive_link': request.form.get('drive_link', ''),
                'caption': request.form.get('caption', ''),
                'hashtags': request.form.get('hashtags', ''),
                'client_id': request.form.get('client_id', ''),
                'account': request.form.get('account', '')
            }
            
            # Get available clients and accounts for validation
            available_clients = auth_manager.get_all_clients()
            if not available_clients:
                flash('No Instagram clients configured. Please check your clients.json file.', 'error')
                return render_template('instagram.html', clients=[], config=app.config)
            
            # Get accounts for the selected client
            selected_client_id = form_data.get('client_id', available_clients[0]['id'] if available_clients else '')
            available_accounts, account_message = instagram_service.get_accounts_for_client(selected_client_id)
            
            if account_message != "Success":
                flash(f'Error loading accounts: {account_message}', 'error')
                clients = auth_manager.get_all_clients()
                return render_template('instagram.html', clients=clients, config=app.config)
            
            # Validate all form data
            is_valid, error_msg, cleaned_data = InputValidator.validate_instagram_upload_form_data(
                form_data, available_clients, available_accounts
            )
            
            if not is_valid:
                flash(error_msg, 'error')
                clients = auth_manager.get_all_clients()
                return render_template('instagram.html', clients=clients, config=app.config)
            
            try:
                # Convert Google Drive link to direct download URL for Instagram
                logger.info(f"Converting Google Drive link for Instagram: {cleaned_data['drive_link']}")
                conversion_result = drive_service.convert_to_direct_link(cleaned_data['drive_link'])
                
                if not conversion_result['success']:
                    flash(f'Failed to convert Google Drive link: {conversion_result.get("error", "Unknown error")}', 'error')
                    clients = auth_manager.get_all_clients()
                    return render_template('instagram.html', clients=clients, config=app.config)
                
                direct_video_url = conversion_result['direct_link']
                logger.info(f"Converted to direct URL: {direct_video_url[:50]}...")
                
                # Prepare caption with hashtags
                caption = cleaned_data['caption']
                if cleaned_data['hashtags']:
                    hashtag_text = ' '.join([f'#{tag}' for tag in cleaned_data['hashtags']])
                    caption += f'\n\n{hashtag_text}'
                
                # Upload to Instagram using direct URL (no file download needed)
                logger.info(f"Uploading video to Instagram with client {cleaned_data['client_id']}, account {cleaned_data['account_id']}")
                success, message, response = instagram_service.upload_video(
                    video_path=None,  # Not needed when using video_url
                    caption=caption,
                    hashtags=cleaned_data['hashtags'],
                    account_id=cleaned_data['account_id'],
                    client_id=cleaned_data['client_id'],
                    video_url=direct_video_url
                )
                
                if success:
                    flash(f'Video uploaded to Instagram successfully! {message}', 'success')
                    return render_template('success.html',
                                         platform='instagram',
                                         message=message,
                                         client_name=next((c['name'] for c in available_clients if c['id'] == cleaned_data['client_id']), 'Unknown'),
                                         config=app.config)
                else:
                    flash(f'Instagram upload failed: {message}', 'error')
                    clients = auth_manager.get_all_clients()
                    return render_template('instagram.html', clients=clients, config=app.config)
                    
            except Exception as e:
                logger.error(f"Error during Instagram upload: {e}")
                flash(f'Upload error: {str(e)}', 'error')
                clients = auth_manager.get_all_clients()
                return render_template('instagram.html', clients=clients, config=app.config)
                
        except Exception as e:
            logger.error(f"Error processing Instagram upload: {e}")
            flash(f'Error processing upload: {str(e)}', 'error')
            clients = auth_manager.get_all_clients()
            return render_template('instagram.html', clients=clients, config=app.config)

    @app.route('/api/instagram/accounts/<client_id>')
    def get_instagram_accounts_for_client(client_id):
        """API endpoint to get Instagram accounts for a specific client."""
        try:
            # Validate client ID
            available_clients = auth_manager.get_all_clients()
            is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
            if not is_valid:
                return jsonify({
                    "success": False,
                    "error": error_msg,
                    "accounts": []
                })
            
            # Get accounts for the client
            accounts, message = instagram_service.get_accounts_for_client(client_id)
            
            if message == "Success":
                return jsonify({
                    "success": True,
                    "accounts": accounts
                })
            else:
                return jsonify({
                    "success": False,
                    "error": message,
                    "accounts": []
                })
                
        except Exception as e:
            logger.error(f"Error getting Instagram accounts for client {client_id}: {e}")
            return jsonify({
                "success": False,
                "error": str(e),
                "accounts": []
            })

    @app.route('/instagram/auth/<client_id>')
    def instagram_auth_redirect(client_id):
        """Redirect to Instagram OAuth for a specific client."""
        try:
            # Validate client ID
            available_clients = auth_manager.get_all_clients()
            is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
            if not is_valid:
                return jsonify({"success": False, "error": error_msg}), 400
            
            # Generate Instagram OAuth URL
            auth_url = f"https://www.facebook.com/v18.0/dialog/oauth?client_id={app.config['INSTAGRAM_APP_ID']}&redirect_uri={app.config['INSTAGRAM_REDIRECT_URI']}&scope=instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,pages_manage_posts,publish_video,instagram_manage_insights&state={client_id}"
            
            return redirect(auth_url)
            
        except Exception as e:
            logger.error(f"Error generating Instagram auth URL for client {client_id}: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/instagram/auth-terminal/<client_id>')
    def instagram_auth_terminal(client_id):
        """Show Instagram OAuth URL in terminal for a specific client."""
        try:
            # Validate client ID
            available_clients = auth_manager.get_all_clients()
            is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
            if not is_valid:
                return jsonify({"success": False, "error": error_msg}), 400
            
            # Generate Instagram OAuth URL
            auth_url = f"https://www.facebook.com/v18.0/dialog/oauth?client_id={app.config['INSTAGRAM_APP_ID']}&redirect_uri={app.config['INSTAGRAM_REDIRECT_URI']}&scope=instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement,pages_manage_posts,publish_video,instagram_manage_insights&state={client_id}"
            
            print(f"\n=== Instagram OAuth URL for client {client_id} ===")
            print(f"URL: {auth_url}")
            print("Copy and paste this URL into your browser to authenticate with Instagram.")
            print("After authentication, you'll be redirected to the callback URL.")
            print("=" * 60)
            
            return jsonify({"success": True, "message": "OAuth URL displayed in terminal"})
            
        except Exception as e:
            logger.error(f"Error generating Instagram auth URL for client {client_id}: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/instagram_oauth_callback')
    def instagram_oauth_callback():
        """Handle Instagram OAuth callback."""
        try:
            code = request.args.get('code')
            state = request.args.get('state')  # This will be the client_id
            
            if not code or not state:
                flash('Instagram authentication failed: Missing authorization code or state', 'error')
                return redirect(url_for('instagram_upload'))
            
            # Exchange code for access token
            token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
            token_data = {
                'client_id': app.config['INSTAGRAM_APP_ID'],
                'client_secret': app.config['INSTAGRAM_APP_SECRET'],
                'redirect_uri': app.config['INSTAGRAM_REDIRECT_URI'],
                'code': code
            }
            
            response = requests.post(token_url, data=token_data)
            if response.status_code != 200:
                flash('Instagram authentication failed: Could not exchange code for token', 'error')
                return redirect(url_for('instagram_upload'))
            
            token_response = response.json()
            access_token = token_response.get('access_token')
            
            if not access_token:
                flash('Instagram authentication failed: No access token received', 'error')
                return redirect(url_for('instagram_upload'))
            
            # Store the token for the client
            token_path = os.path.join('tokens', f'instagram_token_{state}.json')
            os.makedirs('tokens', exist_ok=True)
            
            with open(token_path, 'w') as f:
                json.dump({
                    'access_token': access_token,
                    'client_id': state,
                    'created_at': datetime.now().isoformat()
                }, f, indent=2)
            
            flash('Instagram authentication successful! You can now upload videos.', 'success')
            return redirect(url_for('instagram_upload'))
            
        except Exception as e:
            logger.error(f"Error in Instagram OAuth callback: {e}")
            flash(f'Instagram authentication error: {str(e)}', 'error')
            return redirect(url_for('instagram_upload'))

# n8n jobs routes
if app.config['ENABLE_N8N_JOBS']:
    @app.route('/n8n')
    def n8n_jobs():
        """N8N job submission page."""
        return render_template('n8n.html', config=app.config)

# n8n config endpoints should always be available
@app.route('/api/n8n/config', methods=['GET'])
def get_n8n_config():
    """Get current n8n webhook configuration."""
    try:
        urls = n8n_service.get_current_urls()
        return jsonify({
            "success": True,
            "config": {
                "webhook_urls": urls,
                "timeout": n8n_service.timeout
            }
        })
    except Exception as e:
        logger.error(f"Error getting n8n config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/n8n/config', methods=['POST'])
def update_n8n_config():
    """Update n8n webhook URLs. Accepts a single ngrok_base_url and generates all 4 webhook URLs unanimously."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        base_url = data.get('ngrok_base_url')
        if not base_url or not base_url.startswith('http'):
            return jsonify({"error": "A valid ngrok base URL is required."}), 400
        
        # Use the new unanimous URL generation method
        success = n8n_service.update_webhook_urls_from_base(base_url)
        if success:
            # Get the generated URLs to return them
            urls = n8n_service.get_current_urls()
            return jsonify({
                "success": True,
                "message": "All n8n webhook URLs updated unanimously",
                "generated_urls": urls
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to update n8n webhook URLs"
            }), 500
    except Exception as e:
        logger.error(f"Error updating n8n config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# Discord job submission routes
if app.config['ENABLE_DISCORD_JOB']:
    @app.route('/submitjob', methods=['POST'])
    def submit_job():
        """Submit a job to Discord webhook."""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            
            # Validate required fields
            user = data.get('user')
            images = data.get('images', [])
            audios = data.get('audios', [])
            background_audio = data.get('background_audio')
            
            if not user:
                return jsonify({"error": "User field is required"}), 400
            
            if not isinstance(images, list) or len(images) != 4:
                return jsonify({"error": "Images must be a list of exactly 4 URLs"}), 400
            
            if not isinstance(audios, list) or len(audios) != 4:
                return jsonify({"error": "Audios must be a list of exactly 4 URLs"}), 400
            
            # Reorder images and audios for n8n payload
            images = [images[3], images[2], images[1], images[0]]
            audios = [audios[3], audios[2], audios[1], audios[0]]

            # Submit job to Discord webhook
            success, message, status_code = n8n_service.submit_job(user, images, audios, background_audio, 1.0)
            
            if success:
                return jsonify({"message": message}), 200
            else:
                return jsonify({"error": message}), 500
                
        except Exception as e:
            logger.error(f"Error in submit_job: {e}")
            return jsonify({"error": f"Internal server error: {str(e)}"}), 500

    @app.route('/nocapjob', methods=['POST'])
    def nocap_job():
        """Submit a nocap job to Discord webhook."""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            
            # Validate required fields
            user = data.get('user')
            images = data.get('images', [])
            audios = data.get('audios', [])
            
            if not user:
                return jsonify({"error": "User field is required"}), 400
            
            if not isinstance(images, list) or len(images) != 4:
                return jsonify({"error": "Images must be a list of exactly 4 URLs"}), 400
            
            if not isinstance(audios, list) or len(audios) != 4:
                return jsonify({"error": "Audios must be a list of exactly 4 URLs"}), 400
            
            # Reorder images and audios for n8n payload
            images = [images[3], images[2], images[1], images[0]]
            audios = [audios[3], audios[2], audios[1], audios[0]]

            # Submit nocap job to Discord webhook
            success, message, status_code = n8n_service.nocap_job(user, images, audios)
            
            if success:
                return jsonify({"message": message}), 200
            else:
                return jsonify({"error": message}), 500
                
        except Exception as e:
            logger.error(f"Error in nocap_job: {e}")
            return jsonify({"error": f"Internal server error: {str(e)}"}), 500



@app.route('/auth/<client_id>')
def auth_redirect(client_id):
    am = AuthManager()
    client = am.get_client_by_id(client_id)
    if not client:
        return "Client not found", 404
    scopes = [
        'https://www.googleapis.com/auth/youtube.upload',
        'https://www.googleapis.com/auth/youtube.readonly'
    ]
    base_url = "https://accounts.google.com/o/oauth2/auth"
    
    params = {
        'response_type': 'code',
        'client_id': client['client_id'],
        'redirect_uri': Config.REDIRECT_URI,
        'scope': ' '.join(scopes),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': client_id  # pass through so callback knows which client
    }
    auth_url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    # Print the URL to terminal
    print(f"\n{'='*80}")
    print(f"🔐 OAuth URL for client {client_id}:")
    print(f"{'='*80}")
    print(f"URL: {auth_url}")
    print(f"{'='*80}\n")
    
    return redirect(auth_url)

@app.route('/auth-terminal/<client_id>')
def auth_terminal(client_id):
    """Generate OAuth URL and display it in terminal with browser opening."""
    try:
        success, result = auth_manager.generate_oauth_url(client_id)
        if success:
            return jsonify({
                "success": True,
                "message": "OAuth URL generated and displayed in terminal",
                "url": result
            })
        else:
            return jsonify({
                "success": False,
                "error": result
            }), 400
    except Exception as e:
        logger.error(f"Error in auth_terminal: {e}")
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500

@app.route('/oauth2callback')
def oauth2callback():
    """OAuth2 callback route for Google authentication."""
    try:
        # Get the authorization code from the URL parameters
        auth_code = request.args.get('code')
        state = request.args.get('state')
        error = request.args.get('error')
        

        
        if error:
            logger.error(f"OAuth error: {error}")
            flash(f'OAuth error: {error}', 'error')
            return redirect(url_for('index'))
        
        if not auth_code:
            logger.error("No authorization code received")
            flash('No authorization code received from Google', 'error')
            return redirect('/')
        
        # Determine which client initiated the flow via state param
        if not state:
            flash('Missing state parameter in callback', 'error')
            return redirect('/')

        client = auth_manager.get_client_by_id(state)
        if not client:
            flash(f'Unknown client id {state} in OAuth callback', 'error')
            return redirect('/')
        client_id = state
        
        logger.info(f"Processing OAuth callback for client: {client_id}")
        
        # Exchange the authorization code for tokens using direct requests
        logger.info(f"Exchanging authorization code for tokens...")
        
        token_url = Config.TOKEN_URI
        token_data = {
            'code': auth_code,
            'client_id': client['client_id'],
            'client_secret': client['client_secret'],
            'redirect_uri': Config.REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        
        # Make the token exchange request
        response = requests.post(token_url, data=token_data)
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            flash(f'Token exchange failed: {response.text}', 'error')
            return redirect('/')
        
        token_response = response.json()
        
        # Create credentials object
        credentials = Credentials(
            token=token_response['access_token'],
            refresh_token=token_response.get('refresh_token'),
            token_uri=Config.TOKEN_URI,
            client_id=client['client_id'],
            client_secret=client['client_secret'],
            scopes=['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']
        )
        
        # Save the credentials to a pickle file
        token_path = os.path.join('tokens', f'token_{client_id}.pickle')
        os.makedirs('tokens', exist_ok=True)
        
        with open(token_path, 'wb') as token_file:
            pickle.dump(credentials, token_file)
        
        logger.info(f"✅ Successfully saved tokens for client {client_id} to {token_path}")
        
        flash(f'✅ Successfully authenticated client {client_id}!', 'success')
        return render_template('oauth_callback.html', success=True, client_id=client_id)
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {e}")
        flash(f'OAuth callback error: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

@app.route('/bulk-instagram-upload', methods=['GET', 'POST'])
def bulk_instagram_upload():
    """Bulk upload videos to Instagram from multiple Google Drive links."""
    if request.method == 'GET':
        # Render the bulk upload form/modal
        clients = [c for c in auth_manager.get_all_clients() if c.get('type') == 'instagram']
        return render_template('bulk_instagram_upload.html', clients=clients, config=app.config)

    # POST: process bulk upload
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[INSTAGRAM BULK] Request {request_id} started")
    links_raw = request.form.get('drive_links', '')
    client_id = request.form.get('client_id', '')
    account_id = request.form.get('account_id', '')
    # Split links by line or comma
    links = [l.strip() for l in re.split(r'[\n,]+', links_raw) if l.strip()]
    results = []
    for link in links:
        # 1. Convert to direct link
        conversion_result = drive_service.convert_to_direct_link(link)
        if not conversion_result['success']:
            results.append({'link': link, 'success': False, 'error': f"Drive link conversion failed: {conversion_result.get('error', 'Unknown error')}"})
            continue
        direct_link = conversion_result['direct_link']
        # 2. Extract filename using get_file_info (uses service account if available)
        file_info = drive_service.get_file_info(link)
        filename = None
        extraction_method = None
        if file_info and 'name' in file_info:
            filename = file_info['name']
            extraction_method = file_info.get('extracted_with', 'unknown')
        # Fallback: try to extract from direct link
        if not filename and 'direct_link' in conversion_result:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(conversion_result['direct_link'])
            qs = parse_qs(parsed.query)
            if 'id' in qs:
                filename = f"video_{qs['id'][0][:8]}"
                extraction_method = 'direct_link_fallback'
        if not filename:
            filename = link.split('/')[-1]
            extraction_method = 'url_split_fallback'
        # 3. Generate content with Gemini (skip if testing)
        if TESTING_BULK_UPLOAD:
            caption = f'[TEST MODE] Caption for {filename}'
            hashtags = ['#test', '#bulk', '#upload']
        elif gemini_service:
            gemini_content = gemini_service.generate_content(filename, platform='instagram')
            if not gemini_content.get('success', True):
                results.append({'link': link, 'success': False, 'error': f"Gemini error: {gemini_content.get('error', 'Unknown error')}", 'filename': filename, 'extraction_method': extraction_method})
                continue
            caption = gemini_content.get('description', '')
            hashtags = [h.lstrip('#') for h in gemini_content.get('hashtags', '').split()]
        else:
            caption = filename
            hashtags = []
        # 4. Upload to Instagram (skip if testing)
        if TESTING_BULK_UPLOAD:
            success, message, response = True, '[TEST MODE] Upload skipped', None
        else:
            success, message, response = instagram_service.upload_video(
                video_path=None,
                caption=caption,
                hashtags=hashtags,
                account_id=account_id,
                client_id=client_id,
                video_url=direct_link
            )
        results.append({'link': link, 'success': success, 'message': message, 'response': response, 'filename': filename, 'extraction_method': extraction_method})
    # Store results and redirect (POST-Redirect-GET)
    BULK_RESULTS[request_id] = results
    return redirect(url_for('bulk_instagram_result', request_id=request_id))

@app.route('/clear-bulk-instagram-uploads', methods=['POST'])
def clear_bulk_instagram_uploads():
    """Clear all current bulk Instagram uploads (delete all files in uploads dir)."""
    try:
        clear_uploads_dir()
        return jsonify({'success': True, 'message': 'All bulk Instagram uploads cleared.'})
    except Exception as e:
        logger.error(f'Error clearing bulk uploads: {e}')
        return jsonify({'success': False, 'error': str(e)})

# Legacy bulk-youtube-upload route removed to prevent duplicate uploads
# All YouTube bulk uploads now handled by the unified /bulk-uploader endpoint

# Result routes for POST-Redirect-GET

@app.route('/bulk-instagram-result/<request_id>')
def bulk_instagram_result(request_id):
    results = BULK_RESULTS.pop(request_id, None)
    if results is None:
        flash('Results expired or not found.', 'error')
        return redirect(url_for('bulk_instagram_upload'))
    return render_template('bulk_instagram_result.html', results=results, config=app.config)


# Legacy bulk-youtube-result route removed - now handled by bulk_uploader_result

@app.route('/bulk-uploader', methods=['GET', 'POST'])
def bulk_uploader():
    """Unified bulk uploader for YouTube and Instagram."""
    if request.method == 'GET':
        clients = auth_manager.get_all_clients()
        return render_template('bulk_uploader.html', clients=clients, config=app.config)

    # POST: process bulk upload
    request_id = uuid.uuid4().hex[:8]
    
    # Safeguard against duplicate processing
    if request_id in ACTIVE_BULK_REQUESTS:
        logger.warning(f"[UNIFIED BULK] Request {request_id} already in progress, rejecting duplicate")
        return render_template('bulk_uploader.html', clients=auth_manager.get_all_clients(), config=app.config, error='A bulk upload is already in progress. Please wait for it to complete.')
    
    ACTIVE_BULK_REQUESTS.add(request_id)
    logger.info(f"[UNIFIED BULK] Request {request_id} started")
    service = request.form.get('service', '')
    client_id = request.form.get('client_id', '')
    channel_id = request.form.get('channel_id', '')
    account_id = request.form.get('account_id', '')
    links_raw = request.form.get('drive_links', '')
    
    # Improved link parsing with deduplication
    raw_links = [l.strip() for l in re.split(r'[\n,]+', links_raw) if l.strip()]
    # Remove duplicates while preserving order
    seen = set()
    links = []
    for link in raw_links:
        if link not in seen:
            seen.add(link)
            links.append(link)
    
    logger.info(f"[UNIFIED BULK] Request {request_id}: Service={service}, Parsed {len(raw_links)} raw links, {len(links)} unique links")
    logger.info(f"[UNIFIED BULK] Request {request_id}: Links: {links}")
    if service == 'youtube' and len(links) > 10:
        ACTIVE_BULK_REQUESTS.discard(request_id)
        return render_template('bulk_uploader.html', clients=auth_manager.get_all_clients(), config=app.config, error='You can only upload up to 10 videos at a time for YouTube.')
    # Early quota check for youtube
    if service == 'youtube':
        quota_status = youtube_service.get_quota_status(client_id)
        remaining = quota_status.get('remaining_quota',0)
        total_cost = len(links)*1600
        if remaining < total_cost:
            ACTIVE_BULK_REQUESTS.discard(request_id)
            return render_template('bulk_uploader.html', clients=auth_manager.get_all_clients(), config=app.config, error=f"Insufficient quota. Needed {total_cost}, remaining {remaining}.")
    if service == 'instagram' and len(links) > 50:
        ACTIVE_BULK_REQUESTS.discard(request_id)
        return render_template('bulk_uploader.html', clients=auth_manager.get_all_clients(), config=app.config, error='You can only upload up to 50 videos at a time for Instagram.')
    results = []
    for link in links:
        # 1. Convert to direct link
        conversion_result = drive_service.convert_to_direct_link(link)
        if not conversion_result['success']:
            results.append({'link': link, 'success': False, 'error': f"Drive link conversion failed: {conversion_result.get('error', 'Unknown error')}"})
            continue
        direct_link = conversion_result['direct_link']
        # 2. Extract filename for Gemini
        file_info = drive_service.get_file_info(link)
        filename = file_info['name'] if file_info and 'name' in file_info else link.split('/')[-1]
        if service == 'youtube':
            # 3. Download video to local file (skip if testing)
            unique_filename = f"youtube_video_{uuid.uuid4().hex}.mp4"
            local_video_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            if not TESTING_BULK_UPLOAD:
                logger.info(f"[UNIFIED BULK] Request {request_id}: YouTube link downloading to {local_video_path}")
                download_success = drive_service.download_file_direct(link, local_video_path)
                if not download_success:
                    logger.error(f"[UNIFIED BULK] Request {request_id}: YouTube link download failed")
                    results.append({'link': link, 'success': False, 'error': 'Failed to download video from Google Drive. Make sure the link is public and accessible.', 'filename': filename})
                    continue
            # 4. Generate content with Gemini (skip if testing)
            if TESTING_BULK_UPLOAD:
                title = f'[TEST MODE] Title for {filename}'
                description = f'[TEST MODE] Description for {filename}'
                hashtags = ['#test', '#bulk', '#upload']
            elif gemini_service:
                gemini_content = gemini_service.generate_content(filename, platform='youtube')
                if not gemini_content.get('success', True):
                    results.append({'link': link, 'success': False, 'error': f"Gemini error: {gemini_content.get('error', 'Unknown error')}", 'filename': filename})
                    try:
                        if os.path.exists(local_video_path):
                            os.remove(local_video_path)
                    except Exception:
                        pass
                    continue
                title = gemini_content.get('title', '')
                description = gemini_content.get('description', '')
                hashtags = gemini_content.get('hashtags', '').split()
            else:
                title = filename
                description = filename
                hashtags = []
            # Fix: Strip '#' for tags, add hashtags to description
            tags = [tag.lstrip('#') for tag in hashtags]
            if tags:
                hashtag_text = ' '.join([f'#{tag}' for tag in tags])
                description += f'\n\n{hashtag_text}'
            # 5. Upload to YouTube (skip if testing)
            if TESTING_BULK_UPLOAD:
                success, message, response = True, '[TEST MODE] Upload skipped', None
                logger.info(f"[UNIFIED BULK] Request {request_id}: YouTube TEST MODE - upload skipped")
            else:
                logger.info(f"[UNIFIED BULK] Request {request_id}: YouTube starting upload with title: {title}")
                success, message, response = youtube_service.upload_video(
                    video_path=local_video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    privacy_status='public',
                    channel_id=channel_id,
                    client_id=client_id
                )
                logger.info(f"[UNIFIED BULK] Request {request_id}: YouTube upload result - success: {success}, message: {message}")
            # 6. Clean up local file
            try:
                if not TESTING_BULK_UPLOAD and os.path.exists(local_video_path):
                    os.remove(local_video_path)
                    logger.info(f"[UNIFIED BULK] Request {request_id}: YouTube cleaned up local file")
            except Exception as e:
                logger.warning(f"[UNIFIED BULK] Request {request_id}: YouTube failed to clean up local file: {e}")
            results.append({'link': link, 'success': success, 'message': message, 'response': response, 'filename': filename})
        elif service == 'instagram':
            # 3. Generate content with Gemini (skip if testing)
            if TESTING_BULK_UPLOAD:
                caption = f'[TEST MODE] Caption for {filename}'
                hashtags = ['#test', '#bulk', '#upload']
            elif gemini_service:
                gemini_content = gemini_service.generate_content(filename, platform='instagram')
                if not gemini_content.get('success', True):
                    results.append({'link': link, 'success': False, 'error': f"Gemini error: {gemini_content.get('error', 'Unknown error')}", 'filename': filename})
                    continue
                caption = gemini_content.get('description', '')
                hashtags = [h.lstrip('#') for h in gemini_content.get('hashtags', '').split()]
            else:
                caption = filename
                hashtags = []
            # 4. Upload to Instagram (skip if testing)
            if TESTING_BULK_UPLOAD:
                success, message, response = True, '[TEST MODE] Upload skipped', None
            else:
                success, message, response = instagram_service.upload_video(
                    video_path=None,
                    caption=caption,
                    hashtags=hashtags,
                    account_id=account_id,
                    client_id=client_id,
                    video_url=direct_link
                )
            results.append({'link': link, 'success': success, 'message': message, 'response': response, 'filename': filename})
        else:
            results.append({'link': link, 'success': False, 'error': 'Invalid service selected.', 'filename': filename})
    
    # Clean up active request tracking
    ACTIVE_BULK_REQUESTS.discard(request_id)
    logger.info(f"[UNIFIED BULK] Request {request_id} completed, processed {len(links)} links for service: {service}")
    
    BULK_RESULTS[request_id] = results
    return redirect(url_for('bulk_uploader_result', request_id=request_id, service=service))

@app.route('/bulk-uploader-result/<request_id>')
def bulk_uploader_result(request_id):
    service = request.args.get('service','')
    results = BULK_RESULTS.pop(request_id, None)
    if results is None:
        flash('Results expired or not found.', 'error')
        return redirect(url_for('bulk_uploader'))
    return render_template('bulk_uploader_result.html', results=results, config=app.config, service=service)

# ---------------- Long Form Jobs UI and APIs ----------------
@app.route('/long-form-jobs', methods=['GET'])
def long_form_jobs_page():
    try:
        return render_template('long_form_jobs.html', config=app.config)
    except Exception as e:
        logger.error(f"Error loading long form jobs page: {e}")
        abort(500)

@app.route('/api/longform/projects', methods=['GET', 'POST'])
def longform_projects():
    try:
        with _longform_lock:
            db = _load_longform_db()
            if request.method == 'GET':
                return jsonify({"success": True, "projects": db.get('projects', [])})
            data = request.get_json() or {}
            name = (data.get('name') or '').strip()
            if not name:
                return jsonify({"success": False, "error": "Project name is required"}), 400
            # prevent duplicates (case-insensitive)
            if any(p.get('name', '').lower() == name.lower() for p in db.get('projects', [])):
                return jsonify({"success": False, "error": "Project with this name already exists"}), 400
            project_id = uuid.uuid4().hex
            project = {"id": project_id, "name": name, "rows": _create_empty_rows()}
            db.setdefault('projects', []).append(project)
            if not _save_longform_db(db):
                return jsonify({"success": False, "error": "Failed to save project"}), 500
            return jsonify({"success": True, "project": project})
    except Exception as e:
        logger.error(f"Error in longform_projects: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/longform/projects/<project_id>', methods=['DELETE'])
def delete_longform_project(project_id):
    try:
        with _longform_lock:
            db = _load_longform_db()
            projects = db.get('projects', [])
            new_projects = [p for p in projects if p.get('id') != project_id]
            if len(new_projects) == len(projects):
                return jsonify({"success": False, "error": "Project not found"}), 404
            db['projects'] = new_projects
            if not _save_longform_db(db):
                return jsonify({"success": False, "error": "Failed to delete project"}), 500
            return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting longform project: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/longform/projects/<project_id>/rows', methods=['GET', 'PUT'])
def longform_project_rows(project_id):
    try:
        with _longform_lock:
            db = _load_longform_db()
            project = next((p for p in db.get('projects', []) if p.get('id') == project_id), None)
            if not project:
                return jsonify({"success": False, "error": "Project not found"}), 404
            if request.method == 'GET':
                # Backward-compat: convert any legacy image_urls[5] to image_url
                rows = project.get('rows', [])
                normalized = []
                for idx, row in enumerate(rows, start=1):
                    if isinstance(row, dict):
                        image_url = row.get('image_url')
                        if not image_url:
                            imgs = row.get('image_urls') if isinstance(row.get('image_urls'), list) else []
                            image_url = imgs[0] if imgs else ''
                        normalized.append({
                            "serial_number": row.get('serial_number', idx),
                            "audio_url": (row.get('audio_url') or '').strip(),
                            "image_url": (image_url or '').strip(),
                            "status": (row.get('status') or 'incomplete').strip().lower()
                        })
                    else:
                        normalized.append({
                            "serial_number": idx,
                            "audio_url": "",
                            "image_url": "",
                            "status": "incomplete"
                        })
                return jsonify({"success": True, "rows": normalized})
            data = request.get_json() or {}
            rows = data.get('rows')
            if not isinstance(rows, list) or len(rows) != 14:
                return jsonify({"success": False, "error": "Rows must be a list of 14 row objects"}), 400
            # Validate and normalize rows
            normalized = []
            for idx, row in enumerate(rows, start=1):
                audio = (row.get('audio_url') or '').strip()
                image_url = (row.get('image_url') or '').strip()
                status = (row.get('status') or 'incomplete').strip().lower()
                normalized.append({
                    "serial_number": idx,
                    "audio_url": audio,
                    "image_url": image_url,
                    "status": status if status in ["incomplete", "complete"] else "incomplete"
                })
            project['rows'] = normalized
            if not _save_longform_db(db):
                return jsonify({"success": False, "error": "Failed to save rows"}), 500
            return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error in longform_project_rows: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/longform/dispatch', methods=['POST'])
def longform_dispatch():
    """Dispatch a single longform row: extract images from Discord link and forward to n8n longform webhook.
    Expects JSON: { project_name, serial_number, audio_url, image_url }
    Sends to n8n: { project_name, serial_number, audio_url, images: [5->1 reordered to 1->5] }
    """
    try:
        data = request.get_json() or {}
        project_name = (data.get('project_name') or '').strip()
        serial_number = data.get('serial_number')
        audio_url = (data.get('audio_url') or '').strip()
        image_message_link = (data.get('image_url') or '').strip()

        if not project_name or not serial_number or not audio_url or not image_message_link:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Extract images from Discord message link using existing wizard logic
        try:
            attachments = discord_bulk_service._extract_attachments(image_message_link)
            images = attachments.get('images', [])
        except Exception as e:
            return jsonify({"success": False, "error": f"Failed to extract images: {str(e)}"}), 400

        if not images or len(images) not in (4, 5):
            return jsonify({"success": False, "error": f"Expected 5 image attachments, found {len(images) if images else 0}"}), 400

        # If 4 provided for some reason, still forward but prefer 5. Ensure order 1..5 already via extractor reverse.
        # Prepare n8n payload
        urls = n8n_service.get_current_urls()
        longform_url = urls.get('longform_job')
        if not longform_url:
            return jsonify({"success": False, "error": "Longform webhook URL not configured"}), 500

        payload = {
            'project_name': project_name,
            'serial_number': serial_number,
            'audio_url': audio_url,
            'images': images
        }

        try:
            resp = requests.post(longform_url, json=payload, timeout=n8n_service.timeout)
            if resp.status_code != 200:
                return jsonify({"success": False, "error": f"n8n returned {resp.status_code}"}), 502
        except Exception as e:
            return jsonify({"success": False, "error": f"Dispatch error: {str(e)}"}), 502

        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error in longform dispatch: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/longform/job-status', methods=['GET'])
def longform_job_status():
    try:
        with _job_lock:
            active = LONGFORM_JOB_STATE.get('active', False)
            ends_at = LONGFORM_JOB_STATE.get('ends_at')
            reason = LONGFORM_JOB_STATE.get('reason', '')
            # Auto-expire
            if active and ends_at:
                try:
                    end_dt = datetime.fromisoformat(ends_at)
                    if datetime.utcnow() >= end_dt:
                        LONGFORM_JOB_STATE.update({"active": False, "ends_at": None, "reason": ""})
                        active = False
                        ends_at = None
                        reason = ''
                except Exception:
                    pass
        return jsonify({"success": True, "active": active, "ends_at": ends_at, "reason": reason})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/longform/start-job', methods=['POST'])
def longform_start_job():
    try:
        data = request.get_json() or {}
        seconds = int(data.get('seconds', 0))
        reason = (data.get('reason') or '').strip()
        if seconds <= 0:
            return jsonify({"success": False, "error": "seconds must be > 0"}), 400
        with _job_lock:
            # Check existing
            if LONGFORM_JOB_STATE.get('active') and LONGFORM_JOB_STATE.get('ends_at'):
                try:
                    end_dt = datetime.fromisoformat(LONGFORM_JOB_STATE['ends_at'])
                    if datetime.utcnow() < end_dt:
                        return jsonify({"success": False, "error": "Job already in progress", "ends_at": LONGFORM_JOB_STATE['ends_at']}), 409
                except Exception:
                    pass
            # Start new
            ends_at_dt = datetime.utcnow() + timedelta(seconds=seconds)
            LONGFORM_JOB_STATE.update({
                "active": True,
                "ends_at": ends_at_dt.isoformat(),
                "reason": reason or 'longform'
            })
        return jsonify({"success": True, "ends_at": LONGFORM_JOB_STATE['ends_at']})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/longform/compile', methods=['POST'])
def longform_compile():
    """Compile job: send project_name to compile webhook."""
    try:
        data = request.get_json() or {}
        project_name = (data.get('project_name') or '').strip()
        if not project_name:
            return jsonify({"success": False, "error": "project_name is required"}), 400
        
        urls = n8n_service.get_current_urls()
        compile_url = urls.get('compile_job')
        if not compile_url:
            return jsonify({"success": False, "error": "Compile webhook URL not configured"}), 500
        
        payload = {"project_name": project_name}
        
        try:
            resp = requests.post(compile_url, json=payload, timeout=n8n_service.timeout)
            if resp.status_code != 200:
                return jsonify({"success": False, "error": f"n8n returned {resp.status_code}"}), 502
        except Exception as e:
            return jsonify({"success": False, "error": f"Compile error: {str(e)}"}), 502
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error in longform compile: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    import signal
    import sys
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        
        # Clean up Discord bulk jobs
        try:
            discord_bulk_service._cleanup_on_exit()
        except Exception as e:
            logger.error(f"Error cleaning up Discord bulk jobs: {e}")
        
        # Clear uploads directory
        try:
            clear_uploads_dir()
        except Exception as e:
            logger.error(f"Error clearing uploads directory: {e}")
        
        logger.info("Shutdown complete. Exiting...")
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
    
    logger.info("Starting YouTube Shorts Uploader...")
    try:
        app.run(host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        signal_handler(signal.SIGTERM, None) 