# YouTube Shorts Uploader Web Application

A Flask web application that allows you to upload videos from Google Drive to YouTube as shorts with custom titles, descriptions, and hashtags.

## Features

- Upload videos from Google Drive links
- Automatic YouTube upload as shorts
- Custom title, description, and hashtags
- Privacy settings (Private, Unlisted, Public)
- User-friendly web interface
- Error handling and success notifications

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

1. Open the web application in your browser
2. Paste a Google Drive link to your video file
3. Fill in the video title (required)
4. Add description and hashtags (optional)
5. Select privacy setting
6. Click "Upload to YouTube"
7. The first time you'll need to authorize the app with your YouTube account
8. Wait for the upload to complete

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
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables
├── credentials.json      # YouTube OAuth credentials (you create this)
├── drive_credentials.json # Google Drive service account (optional)
├── token.pickle          # Saved YouTube auth token (auto-generated)
├── templates/
│   ├── index.html        # Main upload form
│   └── success.html      # Success page
├── static/               # Static files (CSS, JS)
└── uploads/              # Temporary file storage
```

## Error Handling

The application includes comprehensive error handling for:
- Invalid Google Drive links
- File download failures
- YouTube upload errors
- Authentication issues
- Network connectivity problems

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

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is for educational purposes. Make sure to comply with YouTube's Terms of Service and API usage policies.
