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
import atexit
import shutil
import re

# In-memory store for bulk upload results (cleared on app restart)
BULK_RESULTS = {}

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

# --- Flask Application for YouTube Shorts Uploader and n8n Integration ---
#
# This app provides endpoints for uploading videos to YouTube from Google Drive,
# managing multiple OAuth clients/channels, and submitting jobs to n8n webhooks.
#
# All business logic is handled in service classes. This file wires up the routes.
# --- New Route: Discord Job Submission ---
if app.config['ENABLE_DISCORD_JOB']:
    @app.route('/discord-job', methods=['GET', 'POST'])
    def discord_job():
        """Accept a Discord message link, extract attachment URLs, and send to n8n. Also display payload and n8n response for testing/logging."""
        if request.method == 'GET':
            return render_template('discord_job.html', config=app.config)

        # POST: handle job logic
        message_link = request.form.get('message_link', '').strip()
        job_type = request.form.get('job_type', 'default')
        user = request.form.get('user', '').strip()
        bot_token = os.environ.get('DISCORD_BOT_TOKEN')
        if not message_link or not bot_token:
            return jsonify({'success': False, 'message': 'Missing message link or bot token.'}), 400

        # Accept both discord.com and discordapp.com links
        if 'discordapp.com' in message_link:
            message_link = message_link.replace('discordapp.com', 'discord.com')
        if message_link.startswith('discord://'):
            message_link = message_link.replace('discord://discord', 'https://discord.com')
            message_link = message_link.replace('discord://', 'https://discord.com/')
        message_link = message_link.strip()  # Extra strip after replacements

        parts = message_link.strip('/').split('/')

        channel_id = parts[-2] if len(parts) >= 2 else ''
        message_id = parts[-1] if len(parts) >= 1 else ''

        # Fetch the message from Discord API
        url = f'https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}'
        headers = {'Authorization': f'Bot {bot_token}'}
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            return jsonify({'success': False, 'message': f'Failed to fetch message: {resp.text}'}), 400
        data = resp.json()
        attachments = data.get('attachments', [])
        if len(attachments) != 8:
            return jsonify({'success': False, 'message': 'Message must have exactly 8 attachments.'}), 400

        # Separate audio and image files by extension
        audio_exts = {'.mp3', '.wav', '.m4a', '.aac', '.mp4'}
        image_exts = {'.jpg', '.jpeg', '.png', '.webp'}
        audios_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in audio_exts)]
        images_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in image_exts)]
        audios = [a['url'] for a in audios_full]
        images = [a['url'] for a in images_full]
        audio_filenames = [a['filename'] for a in audios_full]
        image_filenames = [a['filename'] for a in images_full]
        if len(audios) != 4 or len(images) != 4:
            return jsonify({'success': False, 'message': 'Message must have 4 audio and 4 image files.'}), 400

        # Reverse the order of images and audios as they appear in the message
        images = images[::-1]
        image_filenames = image_filenames[::-1]
        audios = audios[::-1]
        audio_filenames = audio_filenames[::-1]

        # Build payload for n8n
        n8n_payload = {
            'audios': audios,
            'images': images,
            'job_type': job_type,
            'user': user
        }
        n8n_config = load_n8n_config()
        WEBHOOK_URLS = n8n_config.get('webhook_urls', {})
        if job_type not in WEBHOOK_URLS:
            return jsonify({'success': False, 'message': 'Invalid job type or webhook not configured.'}), 400
        webhook_url = WEBHOOK_URLS[job_type]
        try:
            n8n_resp = requests.post(webhook_url, json=n8n_payload)
            n8n_resp_json = n8n_resp.json() if n8n_resp.headers.get('Content-Type', '').startswith('application/json') else n8n_resp.text
        except Exception as e:
            return jsonify({'success': False, 'message': f'n8n webhook error: {str(e)}', 'n8n_payload': n8n_payload}), 500
        if n8n_resp.status_code == 200:
            return jsonify({
                'success': True,
                'message': 'Job submitted successfully.',
                'audio_links': audios,
                'image_links': images,
                'audio_filenames': audio_filenames,
                'image_filenames': image_filenames,
                'original_audio_filenames': [a['filename'] for a in audios_full],
                'original_image_filenames': [a['filename'] for a in images_full],
                'original_audio_links': [a['url'] for a in audios_full],
                'original_image_links': [a['url'] for a in images_full],
                'webhook_url': webhook_url,
                'n8n_payload': n8n_payload,
                'n8n_response': n8n_resp_json
            })
        else:
            return jsonify({
                'success': False,
                'message': f'n8n webhook error: {n8n_resp.text}',
                'n8n_payload': n8n_payload,
                'n8n_response': n8n_resp_json
            }), 500

def load_n8n_config():
    """Load n8n webhook configuration from file."""
    try:
        with open('n8n_config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f'Error loading n8n_config.json: {e}')
        return {}

# Unified uploader route
if app.config['ENABLE_YOUTUBE_UPLOAD'] or app.config['ENABLE_INSTAGRAM_UPLOAD']:
    @app.route('/', methods=['GET', 'POST'])
    def unified_upload():
        """Main upload page with improved error handling and validation."""
        if request.method == 'POST':
            try:
                # Get form data from POST request
                form_data = {
                    'drive_link': request.form.get('drive_link', ''),
                    'direct_drive_link': request.form.get('direct_drive_link', ''),  # For Instagram
                    'title': request.form.get('title', ''),
                    'description': request.form.get('description', ''),
                    'hashtags': request.form.get('hashtags', ''),
                    'privacy': request.form.get('privacy', 'public'),
                    'client_id': request.form.get('client_id', ''),
                    'channel_id': request.form.get('channel_id', ''),
                    'platform': request.form.get('platform', '')
                }
                

                
                # Get available clients and channels/accounts for validation
                available_clients = auth_manager.get_all_clients()
                if not available_clients:
                    flash('No clients configured. Please check your clients.json file.', 'error')
                    return render_template('unified_upload.html', clients=[], quota_status={}, config=app.config)
                
                # Determine platform and get appropriate channels/accounts
                platform = form_data.get('platform', '')
                selected_client_id = form_data.get('client_id', '')
                
                if platform == 'youtube':
                    available_channels, channel_message = youtube_service.get_channels_for_client(selected_client_id)
                elif platform == 'instagram':
                    available_channels, channel_message = instagram_service.get_accounts_for_client(selected_client_id)
                else:
                    flash('Invalid platform selected.', 'error')
                    return render_template('unified_upload.html', clients=[], quota_status={}, config=app.config)
                
                if channel_message != "Success":
                    flash(f'Error loading channels: {channel_message}', 'error')
                    clients = auth_manager.get_all_clients()
                    quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                    return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
                
                # Validate all form data based on platform
                if platform == 'youtube':
                    is_valid, error_msg, cleaned_data = InputValidator.validate_upload_form_data(
                        form_data, available_clients, available_channels
                    )
                elif platform == 'instagram':
                    is_valid, error_msg, cleaned_data = InputValidator.validate_instagram_upload_form_data(
                        form_data, available_clients, available_channels
                    )
                else:
                    is_valid, error_msg, cleaned_data = False, 'Invalid platform', {}
                
                if not is_valid:
                    flash(error_msg, 'error')
                    clients = auth_manager.get_all_clients()
                    quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                    return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
                
                # Check quota before proceeding (YouTube only)
                if platform == 'youtube':
                    quota_status = youtube_service.get_quota_status(cleaned_data['client_id'])
                    if quota_status.get('remaining_quota', 0) < 1600:  # Upload costs 1600 quota points
                        flash(f'Insufficient API quota for client {cleaned_data["client_id"]}. Remaining: {quota_status.get("remaining_quota", 0)}', 'error')
                        clients = auth_manager.get_all_clients()
                        quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                        return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
                
                try:
                    # Handle different platforms
                    if platform == 'youtube':
                        # YouTube requires file download
                        unique_filename = f"{platform}_video_{uuid.uuid4().hex}.mp4"
                        local_video_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        
                        # Download video from Google Drive for YouTube
                        logger.info(f"Downloading video from Google Drive for YouTube: {cleaned_data['drive_link']}")
                        download_success = drive_service.download_file_direct(cleaned_data['drive_link'], local_video_path)
                        
                        if not download_success:
                            flash('Failed to download video from Google Drive. Make sure the link is public and accessible.', 'error')
                            clients = auth_manager.get_all_clients()
                            quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                            return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
                    elif platform == 'instagram':
                        # Instagram uses direct URL conversion (no file download needed)
                        local_video_path = None
                    
                    # Upload based on platform
                    if platform == 'youtube':
                        # Prepare description with hashtags
                        description = cleaned_data['description']
                        if cleaned_data['hashtags']:
                            hashtag_text = ' '.join([f'#{tag}' for tag in cleaned_data['hashtags']])
                            description += f'\n\n{hashtag_text}'
                        
                        # Upload to YouTube
                        logger.info(f"Uploading video to YouTube with client {cleaned_data['client_id']}, channel {cleaned_data['channel_id']}")
                        success, message, response = youtube_service.upload_video(
                            video_path=local_video_path,
                            title=cleaned_data['title'],
                            description=description,
                            tags=cleaned_data['hashtags'],
                            privacy_status=cleaned_data['privacy'],
                            channel_id=cleaned_data['channel_id'],
                            client_id=cleaned_data['client_id']
                        )
                    elif platform == 'instagram':
                        # Convert Google Drive link to direct download URL for Instagram
                        logger.info(f"Converting Google Drive link for Instagram: {cleaned_data['drive_link']}")
                        conversion_result = drive_service.convert_to_direct_link(cleaned_data['drive_link'])
                        
                        if not conversion_result['success']:
                            flash(f'Failed to convert Google Drive link: {conversion_result.get("error", "Unknown error")}', 'error')
                            clients = auth_manager.get_all_clients()
                            quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                            return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
                        
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
                    
                    if success and response:
                        if platform == 'youtube':
                            video_id = response['id']
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            
                            # Get updated quota status
                            updated_quota = youtube_service.get_quota_status(cleaned_data['client_id'])
                            
                            flash(f'Video uploaded to YouTube successfully! Video ID: {video_id}', 'success')
                            return render_template('success.html', 
                                                 platform='youtube',
                                                 video_url=video_url, 
                                                 video_id=video_id, 
                                                 quota_status=updated_quota,
                                                 client_name=next((c['name'] for c in available_clients if c['id'] == cleaned_data['client_id']), 'Unknown'),
                                                 config=app.config)
                        elif platform == 'instagram':
                            flash(f'Video uploaded to Instagram successfully! {message}', 'success')
                            return render_template('success.html',
                                                 platform='instagram',
                                                 message=message,
                                                 client_name=next((c['name'] for c in available_clients if c['id'] == cleaned_data['client_id']), 'Unknown'),
                                                 config=app.config)
                    else:
                        flash(f'Failed to upload video: {message}', 'error')
                        clients = auth_manager.get_all_clients()
                        quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                        return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
                        
                finally:
                    # Clean up local file (only for YouTube uploads)
                    if platform == 'youtube' and local_video_path and os.path.exists(local_video_path):
                        try:
                            os.remove(local_video_path)
                            logger.info(f"Cleaned up temporary file: {local_video_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up temporary file {local_video_path}: {e}")
                    
            except Exception as e:
                logger.error(f"Unexpected error during upload: {e}")
                flash(f'An unexpected error occurred: {str(e)}', 'error')
                clients = auth_manager.get_all_clients()
                quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
        
        # GET request - show the form
        try:
            # Get available clients and their quota status for GET request
            clients = auth_manager.get_all_clients()
            if not clients:
                flash('No clients configured. Please check your clients.json file.', 'error')
                return render_template('unified_upload.html', clients=[], quota_status={}, config=app.config)
            quota_status = {}
            for client in clients:
                quota_status[client['id']] = youtube_service.get_quota_status(client['id'])
            return render_template('unified_upload.html', clients=clients, quota_status=quota_status, config=app.config)
            
        except Exception as e:
            logger.error(f"Error loading main page: {e}")
            flash(f'Error loading page: {str(e)}', 'error')
            return render_template('unified_upload.html', clients=[], quota_status={}, config=app.config)

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
    """Update n8n webhook URLs. Accepts a single ngrok_base_url and generates both webhook URLs."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        base_url = data.get('ngrok_base_url')
        if not base_url or not base_url.startswith('http'):
            return jsonify({"error": "A valid ngrok base URL is required."}), 400
        # Remove trailing slash if present
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        submit_url = f"{base_url}/webhook/discord-input"
        nocap_url = f"{base_url}/webhook/back"
        success = n8n_service.update_webhook_urls(submit_url, nocap_url)
        if success:
            return jsonify({
                "success": True,
                "message": "n8n webhook URLs updated successfully"
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
            success, message, status_code = n8n_service.submit_job(user, images, audios)
            
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

@app.route('/bulk-youtube-upload', methods=['GET', 'POST'])
def bulk_youtube_upload():
    """Bulk upload videos to YouTube from multiple Google Drive links (max 10)."""
    if request.method == 'GET':
        clients = [c for c in auth_manager.get_all_clients() if c.get('type') != 'instagram']
        return render_template('bulk_youtube_upload.html', clients=clients, config=app.config)

    # POST: process bulk upload
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[YOUTUBE BULK] Request {request_id} started")
    links_raw = request.form.get('drive_links', '')
    client_id = request.form.get('client_id', '')
    channel_id = request.form.get('channel_id', '')
    links = [l.strip() for l in re.split(r'[\n,]+', links_raw) if l.strip()]
    # Early quota check
    quota_status = youtube_service.get_quota_status(client_id)
    remaining = quota_status.get('remaining_quota', 0)
    total_cost = len(links)*1600
    if remaining < total_cost:
        return render_template('bulk_youtube_upload.html', clients=[c for c in auth_manager.get_all_clients() if c.get('type') != 'instagram'], config=app.config, error=f"Insufficient quota. Needed {total_cost}, remaining {remaining}.")
    if len(links) > 10:
        return render_template('bulk_youtube_upload.html', clients=[c for c in auth_manager.get_all_clients() if c.get('type') != 'instagram'], config=app.config, error='You can only upload up to 10 videos at a time.')
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
        # 3. Download video to local file (skip if testing)
        unique_filename = f"youtube_video_{uuid.uuid4().hex}.mp4"
        local_video_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        if not TESTING_BULK_UPLOAD:
            download_success = drive_service.download_file_direct(link, local_video_path)
            if not download_success:
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
        else:
            success, message, response = youtube_service.upload_video(
                video_path=local_video_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status='public',
                channel_id=channel_id,
                client_id=client_id
            )
        # 6. Clean up local file
        try:
            if not TESTING_BULK_UPLOAD and os.path.exists(local_video_path):
                os.remove(local_video_path)
        except Exception:
            pass
        results.append({'link': link, 'success': success, 'message': message, 'response': response, 'filename': filename})
    BULK_RESULTS[request_id] = results
    return redirect(url_for('bulk_youtube_result', request_id=request_id))

# Result routes for POST-Redirect-GET

@app.route('/bulk-instagram-result/<request_id>')
def bulk_instagram_result(request_id):
    results = BULK_RESULTS.pop(request_id, None)
    if results is None:
        flash('Results expired or not found.', 'error')
        return redirect(url_for('bulk_instagram_upload'))
    return render_template('bulk_instagram_result.html', results=results, config=app.config)


@app.route('/bulk-youtube-result/<request_id>')
def bulk_youtube_result(request_id):
    results = BULK_RESULTS.pop(request_id, None)
    if results is None:
        flash('Results expired or not found.', 'error')
        return redirect(url_for('bulk_youtube_upload'))
    return render_template('bulk_youtube_result.html', results=results, config=app.config)

@app.route('/bulk-uploader', methods=['GET', 'POST'])
def bulk_uploader():
    """Unified bulk uploader for YouTube and Instagram."""
    if request.method == 'GET':
        clients = auth_manager.get_all_clients()
        return render_template('bulk_uploader.html', clients=clients, config=app.config)

    # POST: process bulk upload
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[UNIFIED BULK] Request {request_id} started")
    service = request.form.get('service', '')
    client_id = request.form.get('client_id', '')
    channel_id = request.form.get('channel_id', '')
    account_id = request.form.get('account_id', '')
    links_raw = request.form.get('drive_links', '')
    import re
    links = [l.strip() for l in re.split(r'[\n,]+', links_raw) if l.strip()]
    if service == 'youtube' and len(links) > 10:
        return render_template('bulk_uploader.html', clients=auth_manager.get_all_clients(), config=app.config, error='You can only upload up to 10 videos at a time for YouTube.')
    # Early quota check for youtube
    if service == 'youtube':
        quota_status = youtube_service.get_quota_status(client_id)
        remaining = quota_status.get('remaining_quota',0)
        total_cost = len(links)*1600
        if remaining < total_cost:
            return render_template('bulk_uploader.html', clients=auth_manager.get_all_clients(), config=app.config, error=f"Insufficient quota. Needed {total_cost}, remaining {remaining}.")
    if service == 'instagram' and len(links) > 50:
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
                download_success = drive_service.download_file_direct(link, local_video_path)
                if not download_success:
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
            else:
                success, message, response = youtube_service.upload_video(
                    video_path=local_video_path,
                    title=title,
                    description=description,
                    tags=tags,
                    privacy_status='public',
                    channel_id=channel_id,
                    client_id=client_id
                )
            # 6. Clean up local file
            try:
                if not TESTING_BULK_UPLOAD and os.path.exists(local_video_path):
                    os.remove(local_video_path)
            except Exception:
                pass
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

if __name__ == '__main__':
    logger.info("Starting YouTube Shorts Uploader...")
    app.run(host='0.0.0.0', port=5000) 