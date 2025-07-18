# Faceless Video Gen Engine

A modern Flask web application for uploading videos to YouTube as Shorts, with Discord-based job submission, n8n integration, and robust multi-client support. Features a dark-themed navbar, modular navigation, and secure token handling.

## 🚀 Features

- **Multi-Client & Multi-Channel Authentication**
- **API Quota Management**
- **Comprehensive Input Validation**
- **Enhanced Error Handling**
- **Modern UI**: Dark navbar, bold branding, and app-wide navigation
- **n8n Integration**: Easily manage webhook URLs via a modal in the navbar
- **Discord Job Submission**: Upload files in Discord, submit jobs via message link
- **Feature Flags**: Enable/disable modules via `.env` file
- **Secure Token Handling**: All tokens in `tokens/` are gitignored

## 📁 File Structure

```
Web-Api-Sys/
├── app.py                    # Main Flask application
├── auth_manager.py           # Multi-client authentication manager
├── youtube_service.py        # YouTube service with quota management
├── validators.py             # Comprehensive input validation
├── config.py                 # Configuration settings
├── requirements.txt          # Python dependencies
├── clients.json              # Multi-client configuration
├── tokens/                   # OAuth token storage directory (gitignored)
├── templates/
│   ├── base.html             # App-wide layout with dark navbar and navigation
│   ├── index.html            # Main upload interface
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
```

Set any to `false` to hide its routes and navigation. The n8n webhook config modal is always available.

## 🧑‍💻 Usage Workflow

- **YouTube Uploader**: Upload videos to YouTube with quota tracking and multi-client support.
- **Discord Job Submission**: Upload 8 files in a Discord message, copy the message link, and submit via the app.
- **n8n Jobs**: Submit jobs to n8n webhooks (if enabled).
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

4. **Configure YouTube OAuth clients**
   - Add your client credentials to `clients.json` (see the example in the repo).
   - Make sure `clients.json` is gitignored.

5. **Set up Discord bot (for Discord job module)**
   - Create a bot in the [Discord Developer Portal](https://discord.com/developers/applications).
   - Invite it to your server with `READ_MESSAGE_HISTORY` and `VIEW_CHANNEL` permissions.
   - Add your bot token to `.env` as `DISCORD_BOT_TOKEN`.

6. **Run the application**
   ```bash
   python app.py
   ```
   The app will be available at [http://localhost:5000](http://localhost:5000)

7. **Feature Flags (optional)**
   - In your `.env`, set any of these to `false` to disable the module:
     ```
     ENABLE_N8N_JOBS=true
     ENABLE_DISCORD_JOB=true
     ENABLE_YOUTUBE_UPLOAD=true
     ```

8. **Manage n8n Webhook URLs**
   - Use the "Edit n8n Webhook URLs" button in the navbar.
   - Enter only your ngrok subdomain (e.g., `abc123` for `https://abc123.ngrok-free.app`).

---

For more details, see comments in the code and templates. If you have questions or want to contribute, open an issue or PR! 