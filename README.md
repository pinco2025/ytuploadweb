# Faceless Video Gen Engine

A modern Flask web application for uploading videos to YouTube as Shorts and Instagram Reels, with Discord-based job submission, n8n integration, and robust multi-client support. Features a dark-themed navbar, modular navigation, and secure token handling.

## 🚀 Features

- **Multi-Client & Multi-Channel Authentication**
- **API Quota Management**
- **Comprehensive Input Validation**
- **Enhanced Error Handling**
- **Modern UI**: Dark navbar, bold branding, and app-wide navigation
- **n8n Integration**: Easily manage webhook URLs via a modal in the navbar
- **Discord Job Submission**: Upload files in Discord, submit jobs via message link
- **Gemini AI Integration**: Auto-generate SEO-optimized titles, descriptions, and hashtags based on filenames
- **Google Drive Integration**: Extract filenames from Google Drive links using service account credentials
- **Feature Flags**: Enable/disable modules via `.env` file
- **Secure Token Handling**: All tokens in `tokens/` are gitignored

## 📁 File Structure

```
Web-Api-Sys/
├── app.py                    # Main Flask application
├── auth_manager.py           # Multi-client authentication manager
├── youtube_service.py        # YouTube service with quota management
├── instagram_service.py      # Instagram service with API management
├── gemini_service.py         # Gemini AI service for content generation
├── validators.py             # Comprehensive input validation
├── config.py                 # Configuration settings
├── requirements.txt          # Python dependencies
├── clients.json              # Multi-client configuration
├── tokens/                   # OAuth token storage directory (gitignored)
├── templates/
│   ├── base.html             # App-wide layout with dark navbar and navigation
│   ├── index.html            # YouTube upload interface
│   ├── instagram.html        # Instagram upload interface
│   ├── success.html          # Success page (theme-mapped)
│   ├── discord_job.html      # Discord job submission page
│   ├── n8n.html              # n8n job submission page
│   └── oauth_callback.html   # OAuth callback page
├── static/
│   └── css/
│       └── style.css         # Custom styles
└── uploads/                  # Temporary file storage
├── n8n_config.json           # n8n webhook configuration
```

> **Note:** The main entry point for the application is `app.py`. All navigation is in the dark navbar, and all tokens are excluded from git.

## 🛠️ Feature Flags (Module Control)

You can enable or disable major modules via your `.env` file:

```
ENABLE_N8N_JOBS=true
ENABLE_DISCORD_JOB=true
ENABLE_YOUTUBE_UPLOAD=true
ENABLE_INSTAGRAM_UPLOAD=true
```

Set any to `false` to hide its routes and navigation. The n8n webhook config modal is always available.

## 🧑‍💻 Usage Workflow

- **YouTube Uploader**: Upload videos to YouTube with quota tracking and multi-client support.
- **Instagram Uploader**: Upload videos to Instagram Reels with multi-account support and content publishing.
- **Discord Job Submission**: Upload 8 files in a Discord message, copy the message link, and submit via the app.
- **n8n Jobs**: Submit jobs to n8n webhooks (if enabled).
- **Google Drive Filename Extraction**: The system automatically extracts filenames from Google Drive links. With service account credentials, you get accurate filenames. Without them, the system uses fallback methods.
- **Gemini AI Content Generation**: Enter a Google Drive link, select your platform, and click "AI Generate" to automatically create SEO-optimized titles, descriptions, and hashtags based on the filename.
- **Manage Webhook URLs**: Use the "Edit n8n Webhook URLs" button in the navbar. Enter only your ngrok subdomain (e.g., `abc123` for `https://abc123.ngrok-free.app`).

## 🔒 Security
- All OAuth tokens and quota files are stored in `tokens/` and are gitignored.
- No sensitive data is tracked in git.

## 🛠️ Configuration
- All environment variables (including feature flags) can be set in your `.env` file.
- See `.gitignore` for excluded files and folders.

## 🖼️ UI Highlights
- Dark navbar with bold "Faceless Video Gen Engine" branding
- Navigation links for all enabled modules
- Consistent, modern look across all pages

## ⚡ Performance Optimizations

- **Lazy Loading:** All icon assets and images (where used) are loaded with `loading="lazy"` for faster initial page load.
- **Defer JS Loading:** Bootstrap and other scripts are loaded with `defer` to avoid blocking rendering.
- **JS Optimization:** No custom JS files are present; all scripts are loaded from CDN. If you add custom JS, use a bundler/minifier (e.g., esbuild, Webpack) and place files in `static/js/`.
- **Input Sanitization:** All user input is validated and sanitized server-side using the `InputValidator` class in `validators.py`. This prevents XSS and other injection attacks.

## 🏁 Setup Instructions

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd <your-repo-folder>
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your `.env` file**
   - Copy the example or create a new `.env` file:
     ```bash
     cp .env.example .env  # if available, or create manually
     ```
   - Add your environment variables (see below for feature flags and required secrets).
   
   **Required environment variables:**
   ```
   # YouTube API
   YOUTUBE_CLIENT_ID=your_youtube_client_id
   YOUTUBE_CLIENT_SECRET=your_youtube_client_secret
   
   # Instagram API
   INSTAGRAM_APP_ID=your_instagram_app_id
   INSTAGRAM_APP_SECRET=your_instagram_app_secret
   
   # Gemini AI (for auto content generation)
   GEMINI_API_KEY=your_gemini_api_key
   
   # Feature flags
   ENABLE_YOUTUBE_UPLOAD=true
   ENABLE_INSTAGRAM_UPLOAD=true
   ENABLE_DISCORD_JOB=true
   ENABLE_N8N_JOBS=true
   ```

4. **Configure YouTube OAuth clients**
   - Add your client credentials to `clients.json` (see the example in the repo).
   - Make sure `clients.json` is gitignored.

5. **Set up Instagram Business/Creator accounts**
   - Create a Facebook App in the [Facebook Developer Portal](https://developers.facebook.com/)
   - Add Instagram Basic Display and Instagram Graph API products
   - Configure OAuth redirect URI: `http://localhost:5000/instagram_oauth_callback`
   - Ensure your Instagram accounts are Business or Creator accounts (not personal)
   - Connect your Facebook pages to Instagram accounts

6. **Set up Discord bot (for Discord job module)**
   - Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
   - Invite it to your server with `READ_MESSAGE_HISTORY` and `VIEW_CHANNEL` permissions.
   - Add your bot token to `.env` as `DISCORD_BOT_TOKEN`.

7. **Set up Google Drive Service Account (for better filename extraction)**
   - Run the setup script: `python setup_service_account.py`
   - Follow the guided steps to create and configure service account credentials
   - This enables accurate filename extraction from Google Drive links
   - Without this, the system will use fallback methods for filename extraction

8. **Set up Gemini AI (for auto content generation)**
   - Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Add your API key to `.env` as `GEMINI_API_KEY`
   - The feature will be automatically disabled if no API key is provided

8. **Run the application**
   ```bash
   python app.py
   ```
   The app will be available at [http://localhost:5000](http://localhost:5000)

9. **Feature Flags (optional)**
   - In your `.env`, set any of these to `false` to disable the module:
     ```
     ENABLE_N8N_JOBS=true
     ENABLE_DISCORD_JOB=true
     ENABLE_YOUTUBE_UPLOAD=true
     ENABLE_INSTAGRAM_UPLOAD=true
     ```

10. **Manage n8n Webhook URLs**
   - Use the "Edit n8n Webhook URLs" button in the navbar.
   - Enter only your ngrok subdomain (e.g., `abc123` for `https://abc123.ngrok-free.app`).

---

For more details, see comments in the code and templates. If you have questions or want to contribute, open an issue or PR! 