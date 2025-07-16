from flask import Flask, request, render_template, jsonify, flash, redirect, url_for, session
import os
import uuid
import tempfile
from google_drive_service import GoogleDriveService
from youtube_service import YouTubeService
from client_manager import ClientManager
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize client manager
client_manager = ClientManager()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            # Get form data
            drive_link = request.form.get('drive_link')
            title = request.form.get('title')
            description = request.form.get('description', '')
            hashtags = request.form.get('hashtags', '')
            privacy = request.form.get('privacy', 'private')
            selected_channel = request.form.get('channel')
            selected_client_id = request.form.get('client_id', 'client1')
            
            # Validate required fields
            if not drive_link or not title:
                flash('Drive link and title are required!', 'error')
                return render_template('index.html')
            
            if not selected_channel:
                flash('Please select a YouTube channel!', 'error')
                return render_template('index.html')
            
            # Get selected client
            selected_client = client_manager.get_client_by_id(selected_client_id)
            if not selected_client:
                flash('Invalid client selected!', 'error')
                return render_template('index.html')
            
            # Process hashtags
            if hashtags:
                if not hashtags.startswith('#'):
                    hashtags = '#' + hashtags
                description += '\n\n' + hashtags
            
            # Initialize services with selected client
            drive_service = GoogleDriveService()
            youtube_service = YouTubeService(
                client_id=selected_client['client_id'],
                client_secret=selected_client['client_secret']
            )
            
            # Extract file ID from Drive link
            file_id = drive_service.extract_file_id(drive_link)
            
            # Generate unique filename
            unique_filename = f"video_{uuid.uuid4().hex}.mp4"
            local_video_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Download video from Google Drive
            print(f"Downloading video from Google Drive...")
            download_success = drive_service.download_file_direct(drive_link, local_video_path)
            
            if not download_success:
                flash('Failed to download video from Google Drive. Make sure the link is public and accessible.', 'error')
                return render_template('index.html')
            
            # Upload to YouTube
            print(f"Uploading video to YouTube...")
            tags = [tag.strip().replace('#', '') for tag in hashtags.split('#') if tag.strip()] if hashtags else []
            
            upload_response = youtube_service.upload_video(
                video_path=local_video_path,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy,
                channel_id=selected_channel
            )
            
            # Clean up local file
            try:
                os.remove(local_video_path)
            except:
                pass
            
            if upload_response:
                # Increment upload counter
                client_manager.increment_upload_count(selected_client_id)
                
                video_id = upload_response['id']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                # Get updated stats
                stats = client_manager.get_client_stats()
                
                flash(f'Video uploaded successfully! Video ID: {video_id}', 'success')
                return render_template('success.html', 
                                     video_url=video_url, 
                                     video_id=video_id, 
                                     stats=stats,
                                     client_name=selected_client['name'])
            else:
                flash('Failed to upload video to YouTube. Please check your credentials and try again.', 'error')
                return render_template('index.html')
                
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
            return render_template('index.html')
    
    # Get stats for the template
    stats = client_manager.get_client_stats()
    clients = client_manager.get_all_clients()
    return render_template('index.html', stats=stats, clients=clients)

@app.route('/api/channels')
def get_channels():
    """API endpoint to get user's YouTube channels."""
    try:
        print("Debug: Getting channels...")
        
        # Check if a specific channel is configured
        if Config.YOUTUBE_CHANNEL_ID:
            print(f"Debug: Using configured channel ID: {Config.YOUTUBE_CHANNEL_ID}")
            # If a specific channel is configured, return just that one
            youtube_service = YouTubeService()
            channels = youtube_service.get_my_channels()
            print(f"Debug: Found {len(channels)} total channels")
            configured_channel = next((ch for ch in channels if ch['id'] == Config.YOUTUBE_CHANNEL_ID), None)
            if configured_channel:
                return jsonify({
                    "success": True,
                    "channels": [configured_channel]
                })
        
        # Otherwise, return all channels
        print("Debug: Getting all channels...")
        youtube_service = YouTubeService()
        channels = youtube_service.get_my_channels()
        print(f"Debug: Found {len(channels)} channels")
        
        if channels:
            for i, channel in enumerate(channels):
                print(f"Debug: Channel {i+1}: {channel['title']} (ID: {channel['id']})")
        
        return jsonify({
            "success": True,
            "channels": channels
        })
    except Exception as e:
        print(f"Debug: Error getting channels: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "channels": []
        })

@app.route('/api/clients')
def get_clients():
    """API endpoint to get all clients."""
    try:
        clients = client_manager.get_all_clients()
        return jsonify({
            "success": True,
            "clients": clients
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "clients": []
        })

@app.route('/api/stats')
def get_stats():
    """API endpoint to get upload statistics."""
    try:
        stats = client_manager.get_client_stats()
        return jsonify({
            "success": True,
            "stats": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "stats": {}
        })

@app.route('/api/reset-session')
def reset_session():
    """API endpoint to reset session upload count."""
    try:
        client_manager.reset_session_count()
        return jsonify({
            "success": True,
            "message": "Session count reset successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "message": "YouTube Shorts Uploader API is running"})

if __name__ == '__main__':
    app.run(debug=True)
