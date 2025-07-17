# Localhost OAuth Setup Guide

This guide will help you configure OAuth to work with localhost only (no ngrok needed).

## 🔧 Google Cloud Console Configuration

### Step 1: Configure OAuth Redirect URI

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **APIs & Services** > **Credentials**
4. Find your **OAuth 2.0 Client ID** and click on it
5. In the **Authorized redirect URIs** section, add:
   ```
   http://localhost:5000/oauth2callback
   ```
6. Click **Save**

### Step 2: Verify Configuration

Your OAuth client should have these redirect URIs:
- ✅ `http://localhost:5000/oauth2callback`

## 🚀 Running the Application

### Step 1: Start the Flask App
```bash
python app.py
```

### Step 2: Access the Application
Open your browser and go to:
```
http://localhost:5000
```

### Step 3: Authenticate
1. Click on the authentication button for your client
2. You'll be redirected to Google's OAuth page
3. Grant permissions to your application
4. You'll be redirected back to `http://localhost:5000/oauth2callback`
5. Authentication will complete successfully

## ✅ Benefits of Localhost-Only Setup

- **Simpler Configuration**: Only one redirect URI to manage
- **No External Dependencies**: No need for ngrok or external tunneling
- **Faster Development**: Direct local access without network delays
- **Better Security**: No exposure to external networks
- **Consistent URLs**: Same URL every time you run the app

## 🔍 Troubleshooting

### Error: "redirect_uri_mismatch"
- Make sure you added `http://localhost:5000/oauth2callback` to Google Cloud Console
- Wait 2-5 minutes for changes to propagate
- Clear browser cache and cookies

### Error: "Connection refused"
- Make sure the Flask app is running on port 5000
- Check that no other application is using port 5000

### Error: "Invalid client"
- Verify your client ID and client secret in `clients.json`
- Make sure the OAuth client is configured for "Desktop application"

## 📝 Configuration Files

### clients.json
```json
[
  {
    "id": "client1",
    "name": "My YouTube Client",
    "client_id": "your-client-id.apps.googleusercontent.com",
    "client_secret": "your-client-secret"
  }
]
```

### config.py
The application is now configured to use:
- **Redirect URI**: `http://localhost:5000/oauth2callback`
- **Port**: 5000
- **Host**: localhost

## 🎯 Next Steps

1. Configure your `clients.json` with your OAuth credentials
2. Start the Flask application
3. Test the OAuth flow
4. Start uploading videos to YouTube!

The application is now optimized for localhost-only usage without any external tunneling services. 