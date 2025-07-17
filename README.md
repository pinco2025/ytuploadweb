# YouTube Shorts Uploader v2 - Improved Version

A significantly improved Flask web application for uploading videos from Google Drive to YouTube as Shorts with enhanced multi-client support, better error handling, and comprehensive validation.

## 🚀 Major Improvements

### 1. **Multi-Client & Multi-Channel Authentication System**
- **Dynamic Client Switching**: Switch between multiple YouTube OAuth clients on the fly
- **Channel Management**: Each client can access multiple YouTube channels
- **Token Management**: Proper OAuth token storage and refresh handling
- **Authentication State**: Track active client and channel for seamless switching

### 2. **API Quota Management**
- **Real-time Quota Tracking**: Monitor API usage for each client
- **Quota Warnings**: Visual indicators when quota is running low
- **Daily Reset**: Automatic quota reset at midnight
- **Operation Cost Tracking**: Track quota costs for different API operations
- **Smart Client Selection**: Automatically suggest clients with available quota

### 3. **Comprehensive Input Validation**
- **Google Drive Link Validation**: Validate and extract file IDs from various link formats
- **Video Metadata Validation**: Title, description, and hashtag validation
- **File Format Validation**: Support for multiple video formats
- **Size Limits**: Enforce YouTube's file size restrictions
- **XSS Prevention**: Sanitize user inputs to prevent security issues

### 4. **Enhanced Error Handling**
- **Structured Error Messages**: Clear, actionable error messages
- **Logging System**: Comprehensive logging with file and console output
- **Graceful Degradation**: Handle API failures gracefully
- **Retry Logic**: Automatic retry for transient failures
- **User-Friendly Errors**: Convert technical errors to user-friendly messages

### 5. **Improved User Interface**
- **Modern Design**: Bootstrap 5 with Font Awesome icons and tabbed navigation
- **Real-time Validation**: Client-side validation with immediate feedback
- **Quota Visualization**: Visual quota bars with color coding
- **Client Selection Cards**: Intuitive client selection interface
- **Loading States**: Clear loading indicators during operations
- **Responsive Design**: Works on desktop and mobile devices
- **Tabbed Interface**: Switch between YouTube uploader and n8n jobs

### 6. **n8n Integration**
- **Webhook Support**: Submit jobs to n8n webhooks
- **Image & Audio URLs**: Handle 4 image and 4 audio URLs per job
- **Two Job Types**: Submit Job and No Cap Job endpoints
- **Error Handling**: Comprehensive error handling for webhook failures
- **Real-time Feedback**: Immediate response feedback to users

### 7. **Better Code Organization**
- **Separation of Concerns**: Modular architecture with dedicated classes
- **Type Hints**: Full type annotation for better code maintainability
- **Configuration Management**: Centralized configuration handling
- **API Endpoints**: RESTful API design for programmatic access
- **Health Checks**: System health monitoring endpoints

## 📁 New File Structure

```
Web-Api-Sys/
├── app_v2.py                 # Main improved Flask application
├── auth_manager.py           # Multi-client authentication manager
├── youtube_service_v2.py     # Improved YouTube service with quota management
├── validators.py             # Comprehensive input validation
├── config.py                 # Configuration settings
├── google_drive_service.py   # Google Drive integration
├── client_manager.py         # Legacy client manager (deprecated)
├── youtube_service.py        # Legacy YouTube service (deprecated)
├── app.py                    # Legacy main application (deprecated)
├── requirements.txt          # Python dependencies
├── clients.json              # Multi-client configuration
├── tokens/                   # OAuth token storage directory
│   ├── token_client1.pickle  # Tokens for each client
│   ├── token_client2.pickle
│   ├── quota_client1.json    # Quota tracking for each client
│   └── quota_client2.json
├── templates/
│   ├── index_v2.html         # Improved main upload interface
│   ├── success_v2.html       # Enhanced success page
│   ├── index.html            # Legacy template
│   └── success.html          # Legacy template
├── static/
│   └── css/
│       └── style.css         # Custom styles
└── uploads/                  # Temporary file storage
├── n8n_config.json       # n8n webhook configuration
└── update_ngrok_urls.py      # Ngrok URL update script
```

## 🔧 New Features

### Authentication Manager (`auth_manager.py`)
- **Multi-client Support**: Manage multiple YouTube OAuth clients
- **Token Persistence**: Store and refresh OAuth tokens automatically
- **Channel Discovery**: Get available channels for each client
- **Quota Tracking**: Monitor API usage per client
- **Client Switching**: Seamless switching between clients

### Input Validator (`validators.py`)
- **Link Validation**: Validate Google Drive links and extract file IDs
- **Content Validation**: Validate titles, descriptions, and hashtags
- **File Validation**: Check file formats and sizes
- **Security**: Sanitize inputs to prevent XSS attacks
- **Comprehensive Validation**: Validate all form data at once

### YouTube Service v2 (`youtube_service_v2.py`)
- **Quota Management**: Check quota before making API calls
- **Error Handling**: Comprehensive error handling with retry logic
- **Channel Support**: Upload to specific channels
- **Progress Tracking**: Track upload progress and status
- **Resource Cleanup**: Proper cleanup of temporary files

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Clients
Edit `clients.json` to add your YouTube OAuth clients:
```json
[
  {
    "id": "client1",
    "name": "YouTube Client 1",
    "client_id": "your-client-id-1.apps.googleusercontent.com",
    "client_secret": "your-client-secret-1",
    "upload_count": 0
  },
  {
    "id": "client2",
    "name": "YouTube Client 2",
    "client_id": "your-client-id-2.apps.googleusercontent.com",
    "client_secret": "your-client-secret-2",
    "upload_count": 0
  }
]
```

### 3. Run the Application
```bash
python app_v2.py
```

The application will be available at `http://localhost:5000`

## 📊 API Endpoints

### Client Management
- `GET /api/clients` - Get all clients with quota information
- `GET /api/quota/<client_id>` - Get quota status for a specific client
- `GET /api/switch-client/<client_id>` - Switch to a different client

### Channel Management
- `GET /api/channels/<client_id>` - Get channels for a specific client
- `GET /api/switch-channel/<client_id>/<channel_id>` - Switch to a specific channel

### Validation
- `POST /api/validate-link` - Validate Google Drive link

### System
- `GET /health` - Health check endpoint

### n8n Integration
- `POST /submitjob` - Submit a job to n8n webhook
- `POST /nocapjob` - Submit a nocap job to n8n webhook
- `GET /n8n-jobs` - n8n job submission page
- `GET /api/n8n/config` - Get current webhook configuration
- `POST /api/n8n/config` - Update webhook URLs

## 🎯 Usage Workflow

### YouTube Uploader
1. **Select Client**: Choose a YouTube client from the available options
2. **View Quota**: Check API quota status for the selected client
3. **Select Channel**: Choose which YouTube channel to upload to
4. **Enter Video Details**: Fill in title, description, and hashtags
5. **Validate Input**: Real-time validation ensures data quality
6. **Upload**: Click upload and monitor progress
7. **Review Results**: View upload results and updated quota status

### n8n Jobs
1. **Switch to n8n Tab**: Click the "n8n Jobs" tab
2. **Enter User**: Provide the username for the job
3. **Add Images**: Enter 4 image URLs (required)
4. **Add Audio**: Enter 4 audio URLs (required)
5. **Submit Job**: Choose between "Submit Job" or "No Cap Job"
6. **Monitor Response**: View success/error messages from webhook

### Ngrok URL Management
1. **View Current URLs**: Check the webhook configuration section in the n8n tab
2. **Update URLs**: Click "Update URLs" button to open the configuration modal
3. **Enter New Base URL**: Provide your new ngrok base URL (e.g., `https://abc123.ngrok-free.app`)
4. **Auto-Generation**: The system automatically constructs the full webhook URLs
5. **Save Changes**: Click "Update URLs" to save the new configuration
6. **Alternative Method**: Use the command-line script: `python update_ngrok_urls.py`

## 🔒 Security Improvements

## 🔐 OAuth Configuration (Localhost Only)

### Simple Setup
The application is configured to work with localhost only, making OAuth setup straightforward.

### Google Cloud Console Configuration

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Select your project**
3. **Navigate to "APIs & Services" > "Credentials"**
4. **Find your OAuth 2.0 Client ID and click on it**
5. **In "Authorized redirect URIs", add**:
   ```
   http://localhost:5000/oauth2callback
   ```
6. **Click "Save"**

### Running the Application

1. **Start the Flask app**:
   ```bash
   python app.py
   ```

2. **Access the application**:
   ```
   http://localhost:5000
   ```

3. **Authenticate**: Click the authentication button and complete the OAuth flow

### Benefits of Localhost-Only Setup

- ✅ **Simpler Configuration**: Only one redirect URI to manage
- ✅ **No External Dependencies**: No need for ngrok or tunneling
- ✅ **Faster Development**: Direct local access
- ✅ **Better Security**: No exposure to external networks
- ✅ **Consistent URLs**: Same URL every time

### Troubleshooting

**Error: "redirect_uri_mismatch"**
- Verify `http://localhost:5000/oauth2callback` is added to Google Cloud Console
- Wait 2-5 minutes for changes to propagate
- Clear browser cache and cookies

**Error: "Connection refused"**
- Make sure Flask app is running on port 5000
- Check no other app is using port 5000

**Error: "Invalid client"**
- Verify client ID and secret in `clients.json`
- Ensure OAuth client is configured for "Desktop application"

- **Input Sanitization**: Prevent XSS attacks
- **Token Security**: Secure OAuth token storage
- **File Validation**: Validate file types and sizes
- **Error Handling**: Don't expose sensitive information in errors
- **Quota Protection**: Prevent quota exhaustion

## 📈 Monitoring & Logging

- **File Logging**: All operations logged to `app.log`
- **Console Logging**: Real-time console output
- **Quota Monitoring**: Track API usage across all clients
- **Error Tracking**: Comprehensive error logging
- **Performance Metrics**: Upload success rates and timing

## 🛠️ Configuration

### Environment Variables
```env
SECRET_KEY=your-secret-key-here
GOOGLE_PROJECT_ID=your-project-id
YOUTUBE_CLIENT_ID=your-youtube-client-id
YOUTUBE_CLIENT_SECRET=your-youtube-client-secret
REDIRECT_URI=http://localhost:8080/
```

### Quota Settings
- **Daily Quota**: 10,000 points per client (configurable)
- **Upload Cost**: 1,600 points per video upload
- **Channel List Cost**: 1 point per request
- **Video Info Cost**: 1 point per request

### n8n Configuration
The n8n webhook URLs are stored in `n8n_config.json`:
```json
{
  "webhook_urls": {
    "submit_job": "https://your-ngrok-url.ngrok-free.app/webhook/discord-input",
    "nocap_job": "https://your-ngrok-url.ngrok-free.app/webhook/back"
  },
  "timeout_seconds": 30,
  "last_updated": "2024-01-01 12:00:00"
}
```

**Updating Ngrok URLs:**
- **Web Interface**: Use the "Update URLs" button in the n8n tab
- **Command Line**: Run `python update_ngrok_urls.py`
- **Manual**: Edit `n8n_config.json` directly

## 🔄 Migration from v1

To migrate from the original version:

1. **Backup**: Backup your existing `clients.json` and tokens
2. **Update**: Replace old files with new v2 files
3. **Configure**: Update your client configuration if needed
4. **Test**: Test with a small upload first
5. **Deploy**: Deploy the new version

## 🐛 Troubleshooting

### Common Issues

1. **"No clients configured"**
   - Check `clients.json` file exists and is valid JSON
   - Ensure client credentials are correct

2. **"API quota exceeded"**
   - Switch to a different client
   - Wait for daily quota reset
   - Check quota usage in the UI

3. **"Authentication failed"**
   - Delete token files and re-authenticate
   - Check OAuth credentials
   - Ensure redirect URI is correct

4. **"Channel not found"**
   - Verify channel exists for the selected client
   - Check OAuth scopes include channel access
   - Re-authenticate if needed

### Debug Mode
Enable debug logging by setting the log level:
```python
logging.basicConfig(level=logging.DEBUG)
```

## 📝 Changelog

### v2.0.0
- ✨ Multi-client authentication system
- ✨ Real-time quota management
- ✨ Comprehensive input validation
- ✨ Enhanced error handling
- ✨ Modern responsive UI
- ✨ RESTful API endpoints
- ✨ Improved logging system
- ✨ Security enhancements
- ✨ Better code organization

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Check the troubleshooting section
- Review the logs in `app.log`
- Test with the health check endpoint
- Verify your OAuth credentials 