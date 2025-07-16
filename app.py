from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session
import os
import uuid
import tempfile
import logging
from typing import Dict, List, Optional
from google_drive_service import GoogleDriveService
from youtube_service import YouTubeServiceV2
from auth_manager import AuthManager
from validators import InputValidator
from discord_service import DiscordService
from config import Config

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
discord_service = DiscordService()

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
                return render_template('index.html')
            
            # Get channels for the selected client
            selected_client_id = form_data.get('client_id', available_clients[0]['id'] if available_clients else '')
            available_channels, channel_message = youtube_service.get_channels_for_client(selected_client_id)
            
            if channel_message != "Success":
                flash(f'Error loading channels: {channel_message}', 'error')
                return render_template('index.html')
            
            # Validate all form data
            is_valid, error_msg, cleaned_data = InputValidator.validate_upload_form_data(
                form_data, available_clients, available_channels
            )
            
            if not is_valid:
                flash(error_msg, 'error')
                return render_template('index.html')
            
            # Check quota before proceeding
            quota_status = youtube_service.get_quota_status(cleaned_data['client_id'])
            if quota_status.get('remaining_quota', 0) < 1600:  # Upload costs 1600 quota points
                flash(f'Insufficient API quota for client {cleaned_data["client_id"]}. Remaining: {quota_status.get("remaining_quota", 0)}', 'error')
                return render_template('index.html')
            
            # Generate unique filename
            unique_filename = f"video_{uuid.uuid4().hex}.mp4"
            local_video_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            try:
                # Download video from Google Drive
                logger.info(f"Downloading video from Google Drive: {cleaned_data['drive_link']}")
                download_success = drive_service.download_file_direct(cleaned_data['drive_link'], local_video_path)
                
                if not download_success:
                    flash('Failed to download video from Google Drive. Make sure the link is public and accessible.', 'error')
                    return render_template('index.html')
                
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
                    return render_template('index.html')
                    
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
            return render_template('index.html')
    
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
        success, message, status_code = discord_service.submit_job(user, images, audios)
        
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
        success, message, status_code = discord_service.nocap_job(user, images, audios)
        
        if success:
            return jsonify({"message": message}), 200
        else:
            return jsonify({"error": message}), 500
            
    except Exception as e:
        logger.error(f"Error in nocap_job: {e}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/discord')
def discord_jobs():
    """Discord job submission page."""
    return render_template('discord.html')

@app.route('/api/discord/config', methods=['GET'])
def get_discord_config():
    """Get current Discord webhook configuration."""
    try:
        urls = discord_service.get_current_urls()
        return jsonify({
            "success": True,
            "config": {
                "webhook_urls": urls,
                "timeout": discord_service.timeout
            }
        })
    except Exception as e:
        logger.error(f"Error getting Discord config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/discord/config', methods=['POST'])
def update_discord_config():
    """Update Discord webhook URLs."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        submit_url = data.get('submit_job_url')
        nocap_url = data.get('nocap_job_url')
        
        if not submit_url or not nocap_url:
            return jsonify({"error": "Both submit_job_url and nocap_job_url are required"}), 400
        
        success = discord_service.update_webhook_urls(submit_url, nocap_url)
        
        if success:
            return jsonify({
                "success": True,
                "message": "Discord webhook URLs updated successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to update Discord webhook URLs"
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating Discord config: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

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