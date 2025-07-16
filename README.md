# YouTube Shorts Uploader Web Application

A Flask web application that allows you to upload videos from Google Drive to YouTube as shorts with custom titles, descriptions, and hashtags. The application now supports multiple YouTube clients and channels for enhanced upload management.

## Features

- Upload videos from Google Drive links
- Automatic YouTube upload as shorts
- Custom title, description, and hashtags
- Privacy settings (Private, Unlisted, Public)
- **Multi-client support** - Manage multiple YouTube OAuth clients
- **Channel selection** - Choose which YouTube channel to upload to
- **Upload statistics** - Track upload counts per client and session
- **API endpoints** - RESTful API for channels, clients, and statistics
- User-friendly web interface
- Error handling and success notifications
- **Testing utilities** - Built-in channel testing functionality

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google API Setup

#### YouTube API:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable YouTube Data API v3
4. Create OAuth 2.0 credentials:
   - Choose "Web application" or "Desktop application"
   - Add redirect URI: `http://localhost:8080/` (for web apps)
5. Download the credentials JSON file

### 3. Credential Configuration

#### Option 1: Automatic Setup (Recommended)
1. Place your downloaded credentials JSON file in the project root as `credentials.json`
2. Run the credential extraction script:
   ```bash
   python extract_credentials.py
   ```
3. This will automatically populate your `.env` file with the correct values

#### Option 2: Manual Setup
1. Open your `.env` file and fill in your credentials manually:
   ```env
   SECRET_KEY=your-secret-key-here
   GOOGLE_PROJECT_ID=your-project-id
   YOUTUBE_CLIENT_ID=your-youtube-client-id.apps.googleusercontent.com
   YOUTUBE_CLIENT_SECRET=your-youtube-client-secret
   REDIRECT_URI=http://localhost:8080/
   ```

### 4. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Usage

### Basic Upload Process
1. Open the web application in your browser
2. Select a YouTube client (if multiple are configured)
3. Choose a YouTube channel to upload to
4. Paste a Google Drive link to your video file
5. Fill in the video title (required)
6. Add description and hashtags (optional)
7. Select privacy setting
8. Click "Upload to YouTube"
9. The first time you'll need to authorize the app with your YouTube account
10. Wait for the upload to complete

### Multi-Client Configuration

The application supports multiple YouTube OAuth clients for better quota management:

1. **Configure clients in `clients.json`**:
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

2. **Benefits of multi-client setup**:
   - Distribute API quota usage across multiple clients
   - Track uploads per client
   - Redundancy in case one client reaches quota limits
   - Better organization for multiple YouTube accounts

### Testing Channels

Use the built-in testing utility to verify your YouTube channel access:

```bash
python test_channels.py
```

This will:
- Test YouTube service initialization
- Verify authentication
- List all accessible YouTube channels
- Provide debugging information for troubleshooting

## Important Notes

### Google Drive Links
- The Google Drive link should be publicly accessible
- Make sure the file is shared with "Anyone with the link can view"
- Supported formats: MP4, MOV, AVI, etc.

### YouTube Shorts Requirements
- Videos should be vertical (9:16 aspect ratio)
- Duration should be 60 seconds or less
- File size should be under 15GB

### Authentication
- On first run, you'll be redirected to Google OAuth for YouTube authorization
- Your credentials will be saved in `token.pickle` for future use

## File Structure

```
Web-Api-Sys/
├── app.py                 # Main Flask application
├── config.py             # Configuration settings
├── google_drive_service.py # Google Drive API service
├── youtube_service.py    # YouTube API service
├── client_manager.py     # Multi-client management system
├── test_channels.py      # Channel testing utility
├── extract_credentials.py # Credential extraction tool
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables
├── credentials.json      # YouTube OAuth credentials (you create this)
├── clients.json          # Multi-client configuration
├── drive_credentials.json # Google Drive service account (optional)
├── token.pickle          # Saved YouTube auth token (auto-generated)
├── templates/
│   ├── index.html        # Main upload form
│   └── success.html      # Success page
├── static/               # Static files (CSS, JS)
└── uploads/              # Temporary file storage
```

## API Endpoints

The application provides RESTful API endpoints for programmatic access:

### GET /api/channels
- **Description**: Retrieve user's YouTube channels
- **Response**: JSON array of channel objects
- **Example**:
  ```json
  {
    "success": true,
    "channels": [
      {
        "id": "UC...",
        "title": "My Channel",
        "description": "Channel description"
      }
    ]
  }
  ```

### GET /api/clients
- **Description**: Get all configured YouTube clients
- **Response**: JSON array of client objects
- **Example**:
  ```json
  {
    "success": true,
    "clients": [
      {
        "id": "client1",
        "name": "YouTube Client 1",
        "upload_count": 5
      }
    ]
  }
  ```

### GET /api/stats
- **Description**: Get upload statistics
- **Response**: JSON object with statistics
- **Example**:
  ```json
  {
    "success": true,
    "stats": {
      "total_clients": 4,
      "total_uploads": 15,
      "session_uploads": 3,
      "client_stats": [
        {
          "id": "client1",
          "name": "YouTube Client 1",
          "upload_count": 5
        }
      ]
    }
  }
  ```

### GET /api/reset-session
- **Description**: Reset the session upload counter
- **Response**: JSON confirmation

## Error Handling

The application includes comprehensive error handling for:
- Invalid Google Drive links
- File download failures
- YouTube upload errors
- Authentication issues
- Network connectivity problems
- Multi-client configuration errors
- Channel access issues

## Security Considerations

- Keep your `credentials.json` and `.env` files secure
- Don't commit sensitive files to version control
- Consider using environment variables in production
- Implement rate limiting for production use

## Troubleshooting

### Common Issues:

1. **"Invalid Google Drive link format"**
   - Ensure the link is in the correct format
   - Make sure the file is publicly accessible

2. **"Failed to download video from Google Drive"**
   - Check if the file is public
   - Verify the file exists and is not corrupted

3. **"OAuth2 credentials file not found"**
   - Make sure `credentials.json` exists in the project root
   - Verify the file contains valid OAuth2 credentials

4. **YouTube upload failures**
   - Check your YouTube API quotas
   - Verify video meets YouTube's requirements
   - Ensure proper authentication

5. **"No channels found" or channel access issues**
   - Run `python test_channels.py` to debug
   - Verify OAuth permissions include YouTube Data API v3
   - Check if the account has created YouTube channels
   - Ensure brand accounts are properly linked

6. **Multi-client configuration errors**
   - Verify `clients.json` has proper JSON format
   - Check that all client IDs and secrets are valid
   - Ensure each client has unique IDs
   - Test individual clients using the web interface

7. **Upload count tracking issues**
   - Check `clients.json` file permissions
   - Verify the file is not corrupted
   - Use `/api/stats` endpoint to check current counts
   - Reset session counts via `/api/reset-session`

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is for educational purposes. Make sure to comply with YouTube's Terms of Service and API usage policies.
