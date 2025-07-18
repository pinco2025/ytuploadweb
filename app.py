from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session, abort
import os
import uuid
import tempfile
import logging
import webbrowser
from typing import Dict, List, Optional
from youtube_service import YouTubeServiceV2
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

# Allow OAuth2 to work with HTTP for localhost development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize services
auth_manager = AuthManager()
youtube_service = YouTubeServiceV2(auth_manager)
n8n_service = N8nService()
drive_service = GoogleDriveService()

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

        # Extract channel_id and message_id by splitting, no link checking
        parts = message_link.split('/')
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

        # Separate audio and image files by extension, and keep both filename and url for debugging
        audio_exts = {'.mp3', '.wav', '.m4a', '.aac', '.mp4'}
        image_exts = {'.jpg', '.jpeg', '.png', '.webp'}
        audios_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in audio_exts)]
        images_full = [a for a in attachments if any(a['filename'].lower().endswith(ext) for ext in image_exts)]
        audios = [a['url'] for a in audios_full]
        images = [a['url'] for a in images_full]
        audio_filenames = [a['filename'] for a in audios_full]
        image_filenames = [a['filename'] for a in images_full]
        # Log the original order for debugging (remove or comment out)
        # print('Original images:', list(zip(image_filenames, images)))
        # print('Original audios:', list(zip(audio_filenames, audios)))
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

# Main YouTube uploader route
if app.config['ENABLE_YOUTUBE_UPLOAD']:
    @app.route('/', methods=['GET', 'POST'])
    def index():
        """Main upload page with improved error handling and validation."""
        if request.method == 'POST':
            try:
                # Get form data from POST request
                form_data = {
                    'drive_link': request.form.get('drive_link', ''),
                    'title': request.form.get('title', ''),
                    'description': request.form.get('description', ''),
                    'hashtags': request.form.get('hashtags', ''),
                    'privacy': request.form.get('privacy', 'public'),
                    'client_id': request.form.get('client_id', ''),
                    'channel': request.form.get('channel', '')
                }
                
                # Get available clients and channels for validation
                available_clients = auth_manager.get_all_clients()
                if not available_clients:
                    flash('No YouTube clients configured. Please check your clients.json file.', 'error')
                    return render_template('index.html', clients=[], quota_status={}, config=app.config)
                
                # Get channels for the selected client
                selected_client_id = form_data.get('client_id', available_clients[0]['id'] if available_clients else '')
                available_channels, channel_message = youtube_service.get_channels_for_client(selected_client_id)
                
                if channel_message != "Success":
                    flash(f'Error loading channels: {channel_message}', 'error')
                    clients = auth_manager.get_all_clients()
                    quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                    return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
                
                # Validate all form data
                is_valid, error_msg, cleaned_data = InputValidator.validate_upload_form_data(
                    form_data, available_clients, available_channels
                )
                
                if not is_valid:
                    flash(error_msg, 'error')
                    clients = auth_manager.get_all_clients()
                    quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                    return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
                
                # Check quota before proceeding
                quota_status = youtube_service.get_quota_status(cleaned_data['client_id'])
                if quota_status.get('remaining_quota', 0) < 1600:  # Upload costs 1600 quota points
                    flash(f'Insufficient API quota for client {cleaned_data["client_id"]}. Remaining: {quota_status.get("remaining_quota", 0)}', 'error')
                    clients = auth_manager.get_all_clients()
                    quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                    return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
                
                # Generate unique filename
                unique_filename = f"video_{uuid.uuid4().hex}.mp4"
                local_video_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                try:
                    # Download video from Google Drive
                    logger.info(f"Downloading video from Google Drive: {cleaned_data['drive_link']}")
                    download_success = drive_service.download_file_direct(cleaned_data['drive_link'], local_video_path)
                    
                    if not download_success:
                        flash('Failed to download video from Google Drive. Make sure the link is public and accessible.', 'error')
                        clients = auth_manager.get_all_clients()
                        quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                        return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
                    
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
                    
                    if success and response:
                        video_id = response['id']
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        # Get updated quota status
                        updated_quota = youtube_service.get_quota_status(cleaned_data['client_id'])
                        
                        flash(f'Video uploaded successfully! Video ID: {video_id}', 'success')
                        return render_template('success.html', 
                                             video_url=video_url, 
                                             video_id=video_id, 
                                             quota_status=updated_quota,
                                             client_name=next((c['name'] for c in available_clients if c['id'] == cleaned_data['client_id']), 'Unknown'),
                                             config=app.config)
                    else:
                        flash(f'Failed to upload video: {message}', 'error')
                        clients = auth_manager.get_all_clients()
                        quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                        return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
                        
                finally:
                    # Clean up local file
                    try:
                        if os.path.exists(local_video_path):
                            os.remove(local_video_path)
                            logger.info(f"Cleaned up temporary file: {local_video_path}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up temporary file {local_video_path}: {e}")
                    
            except Exception as e:
                logger.error(f"Unexpected error during upload: {e}")
                flash(f'An unexpected error occurred: {str(e)}', 'error')
                clients = auth_manager.get_all_clients()
                quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
        
        # GET request - show the form
        try:
            # Get available clients and their quota status for GET request
            clients = auth_manager.get_all_clients()
            if not clients:
                flash('No YouTube clients configured. Please check your clients.json file.', 'error')
                return render_template('index.html', clients=[], quota_status={}, config=app.config)
            quota_status = {}
            for client in clients:
                quota_status[client['id']] = youtube_service.get_quota_status(client['id'])
            return render_template('index.html', clients=clients, quota_status=quota_status, config=app.config)
            
        except Exception as e:
            logger.error(f"Error loading main page: {e}")
            flash(f'Error loading page: {str(e)}', 'error')
            return render_template('index.html', clients=[], quota_status={}, config=app.config)

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

@app.route('/health')
def health_check():
    """Health check endpoint."""
    try:
        # Check if services are properly initialized
        clients = auth_manager.get_all_clients()
        
        return jsonify({
            "status": "healthy",
            "clients_configured": len(clients),
            "upload_folder_exists": os.path.exists(app.config['UPLOAD_FOLDER'])
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

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
        'include_granted_scopes': 'true'
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
        
        # Log the callback parameters for debugging
        logger.info(f"OAuth callback received - code: {auth_code[:20] if auth_code else 'None'}..., state: {state}, error: {error}")
        
        if error:
            logger.error(f"OAuth error: {error}")
            flash(f'OAuth error: {error}', 'error')
            return redirect(url_for('index'))
        
        if not auth_code:
            logger.error("No authorization code received")
            flash('No authorization code received from Google', 'error')
            return redirect(url_for('index'))
        
        # For now, we need to determine which client this is for
        # Since we don't have state parameter tracking, we'll need to handle this differently
        # Let's create a simple token exchange for the first client
        
        # Get the first client (you can improve this by adding state tracking)
        clients = auth_manager.get_all_clients()
        if not clients:
            flash('No clients configured', 'error')
            return redirect(url_for('index'))
        
        client = clients[0]  # Use first client for now
        client_id = client['id']
        
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
            return redirect(url_for('index'))
        
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

if __name__ == '__main__':
    logger.info("Starting YouTube Shorts Uploader...")
    app.run(debug=True, host='0.0.0.0', port=5000) 