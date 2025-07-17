from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session
import os
import uuid
import tempfile
import logging
import webbrowser
from typing import Dict, List, Optional
from google_drive_service import GoogleDriveService
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
drive_service = GoogleDriveService()
n8n_service = N8nService()

def load_n8n_config():
    try:
        with open('n8n_config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f'Error loading n8n_config.json: {e}')
        return {}

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main upload page with improved error handling and validation."""
    if request.method == 'POST':
        try:
            # Get form data
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
                return render_template('index.html', clients=[], quota_status={})
            
            # Get channels for the selected client
            selected_client_id = form_data.get('client_id', available_clients[0]['id'] if available_clients else '')
            available_channels, channel_message = youtube_service.get_channels_for_client(selected_client_id)
            
            if channel_message != "Success":
                flash(f'Error loading channels: {channel_message}', 'error')
                clients = auth_manager.get_all_clients()
                quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                return render_template('index.html', clients=clients, quota_status=quota_status)
            
            # Validate all form data
            is_valid, error_msg, cleaned_data = InputValidator.validate_upload_form_data(
                form_data, available_clients, available_channels
            )
            
            if not is_valid:
                flash(error_msg, 'error')
                clients = auth_manager.get_all_clients()
                quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                return render_template('index.html', clients=clients, quota_status=quota_status)
            
            # Check quota before proceeding
            quota_status = youtube_service.get_quota_status(cleaned_data['client_id'])
            if quota_status.get('remaining_quota', 0) < 1600:  # Upload costs 1600 quota points
                flash(f'Insufficient API quota for client {cleaned_data["client_id"]}. Remaining: {quota_status.get("remaining_quota", 0)}', 'error')
                clients = auth_manager.get_all_clients()
                quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                return render_template('index.html', clients=clients, quota_status=quota_status)
            
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
                    return render_template('index.html', clients=clients, quota_status=quota_status)
                
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
                                         client_name=next((c['name'] for c in available_clients if c['id'] == cleaned_data['client_id']), 'Unknown'))
                else:
                    flash(f'Failed to upload video: {message}', 'error')
                    clients = auth_manager.get_all_clients()
                    quota_status = {c['id']: youtube_service.get_quota_status(c['id']) for c in clients}
                    return render_template('index.html', clients=clients, quota_status=quota_status)
                    
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
            return render_template('index.html', clients=clients, quota_status=quota_status)
    
    # GET request - show the form
    try:
        # Get available clients
        clients = auth_manager.get_all_clients()
        if not clients:
            flash('No YouTube clients configured. Please check your clients.json file.', 'error')
            return render_template('index.html', clients=[], quota_status={})
        
        # Get quota status for all clients
        quota_status = {}
        for client in clients:
            quota_status[client['id']] = youtube_service.get_quota_status(client['id'])
        
        return render_template('index.html', clients=clients, quota_status=quota_status)
        
    except Exception as e:
        logger.error(f"Error loading main page: {e}")
        flash(f'Error loading page: {str(e)}', 'error')
        return render_template('index.html', clients=[], quota_status={})

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
        
        # Submit nocap job to Discord webhook
        success, message, status_code = n8n_service.nocap_job(user, images, audios)
        
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 500
            
    except Exception as e:
        logger.error(f"Error in nocap_job: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/n8n')
def n8n_jobs():
    """N8N job submission page."""
    return render_template('n8n.html')

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
    """Update n8n webhook URLs."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        submit_url = data.get('submit_job_url')
        nocap_url = data.get('nocap_job_url')
        if not submit_url or not nocap_url:
            return jsonify({"error": "Both submit_job_url and nocap_job_url are required"}), 400
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

# --- New Route: Drive Job Submission ---
@app.route('/drive-job', methods=['GET', 'POST'])
def drive_job():
    if request.method == 'GET':
        return render_template('drive_job.html')

    # POST: handle job logic
    # Configurations
    GOOGLE_DRIVE_FOLDER_ID = '1P1LGd_9GXYjD4mrksUEcRME4JNZYndxc'
    n8n_config = load_n8n_config()
    WEBHOOK_URLS = n8n_config.get('webhook_urls', {})
    JOB_TYPE = request.form.get('job_type')
    if JOB_TYPE not in WEBHOOK_URLS:
        return jsonify({'success': False, 'message': 'Invalid job type selected or webhook not configured.'}), 400

    # Initialize Google Drive service
    drive_service = GoogleDriveService(credentials_path='credentials.json')
    # MIME types
    AUDIO_MIME_TYPES = [
        'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/x-m4a', 'audio/mp4', 'audio/aac'
    ]
    IMAGE_MIME_TYPES = [
        'image/jpeg', 'image/png', 'image/jpg', 'image/webp'
    ]
    # List files in folder
    files = drive_service.list_files_in_folder(GOOGLE_DRIVE_FOLDER_ID, max_files=20)
    if not files:
        return jsonify({'success': False, 'message': 'No files found in the specified folder.'}), 400
    
    # Separate and sort by type
    audios = [f for f in files if f['mimeType'] in AUDIO_MIME_TYPES]
    images = [f for f in files if f['mimeType'] in IMAGE_MIME_TYPES]
    audios = sorted(audios, key=lambda x: x['modifiedTime'])[:4]
    images = sorted(images, key=lambda x: x['modifiedTime'])[:4]
    if len(audios) < 4 or len(images) < 4:
        return jsonify({'success': False, 'message': 'Not enough audio or image files in the folder.'}), 400
    # Generate public links
    audio_links = [drive_service.get_public_download_link(f['id'], f['name']) for f in audios]
    image_links = [drive_service.get_public_download_link(f['id'], f['name']) for f in images]
    # Construct payload (example structure, adjust as needed)
    payload = {
        'audios': audio_links,
        'images': image_links,
        'job_type': JOB_TYPE
    }
    # Post to webhook
    webhook_url = WEBHOOK_URLS[JOB_TYPE]
    resp = requests.post(webhook_url, json=payload)
    if resp.status_code == 200:
        # Delete files after success
        for f in audios + images:
            try:
                drive_service.service.files().delete(fileId=f['id']).execute()
            except Exception as e:
                print(f'Error deleting file {f["id"]}: {e}')
        return jsonify({
            'success': True, 
            'message': 'Job submitted and files deleted successfully.',
            'audio_links': audio_links,
            'image_links': image_links,
            'webhook_url': webhook_url
        })
    else:
        return jsonify({'success': False, 'message': f'Webhook error: {resp.text}'}), 500

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