# Discord Bulk Job Guide

## 📋 JSON Format

Your JSON file should contain an array of video objects. Each video object must have a `user`, `message_link`, and `background_audio` field:

```json
[
  {
    "user": "Job 1 - Amazing Video Tutorial",
    "message_link": "https://discord.com/channels/123456789012345678/987654321098765432/111222333444555666",
    "background_audio": "https://example.com/background1.mp3"
  },
  {
    "user": "Job 2 - Incredible Content Episode", 
    "message_link": "https://discord.com/channels/123456789012345678/987654321098765432/777888999000111222",
    "background_audio": "https://example.com/background2.mp3"
  }
]
```

## 🔧 Requirements

### JSON File Requirements:
- **File format**: Must be valid JSON
- **Array structure**: Must be an array of video objects
- **Required fields for each video**: 
  - `user`: Name/title of the video job
  - `message_link`: Discord message link with 8 attachments
  - `background_audio`: URL to the background audio file for this specific video
- **No empty values**: All fields must have content

### Discord Message Requirements:
- **Message link format**: Must be a valid Discord message URL
- **Supported formats**:
  - `https://discord.com/channels/guild_id/channel_id/message_id`
  - `https://discordapp.com/channels/guild_id/channel_id/message_id` (auto-converted)
  - `discord://channels/guild_id/channel_id/message_id` (auto-converted)

### Discord Message Content Requirements:
- **Exactly 8 attachments** per message
- **4 audio files** with extensions: `.mp3`, `.wav`, `.m4a`, `.aac`, `.mp4`
- **4 image files** with extensions: `.jpg`, `.jpeg`, `.png`, `.webp`
- **File order**: Attachments will be processed in reverse order (last attachment first)
- **Background audio**: Will be extracted from each video object in the JSON and used individually for each video

## 🚀 How to Use

### Step 1: Prepare Your Discord Messages
1. **Create Discord messages** with exactly 8 attachments
2. **Upload 4 audio files** (any supported format)
3. **Upload 4 image files** (any supported format)
4. **Copy the message link** (right-click message → Copy Message Link)

### Step 2: Create Your JSON File
```json
[
  {
    "user": "My First Job",
    "message_link": "https://discord.com/channels/YOUR_GUILD_ID/YOUR_CHANNEL_ID/YOUR_MESSAGE_ID",
    "background_audio": "https://example.com/your-background-music1.mp3"
  },
  {
    "user": "My Second Job",
    "message_link": "https://discord.com/channels/YOUR_GUILD_ID/YOUR_CHANNEL_ID/YOUR_MESSAGE_ID_2",
    "background_audio": "https://example.com/your-background-music2.mp3"
  }
]
```

### Step 3: Upload and Configure
1. **Go to Discord Bulk Job** in the navigation
2. **Upload your JSON file**
3. **Select webhook type**:
   - **Submit Job**: Uses n8n submit_job webhook
   - **No Cap Job**: Uses n8n nocap_job webhook
   - **Custom**: Enter your own Discord webhook URL
4. **Set interval** (default: 5 minutes)
5. **Click "Start Bulk Job"**

## 🔍 How It Works

### Processing Flow:
1. **Reads JSON file** and validates format
2. **For each video object in the array**:
   - Extracts `user`, `message_link`, and `background_audio` from JSON
   - Fetches Discord message via Discord API using `message_link`
   - Extracts 8 attachments (4 audio + 4 images)
   - Separates into 4 audio and 4 image files
   - Reverses the order (like single Discord jobs)
   - Creates n8n payload with individual background_audio for each video
   - Posts to selected webhook
   - Waits for specified interval
   - Continues to next video

### n8n Payload Format:
```json
{
  "audios": ["audio1.mp3", "audio2.mp3", "audio3.mp3", "audio4.mp3"],
  "images": ["image1.jpg", "image2.jpg", "image3.jpg", "image4.jpg"],
  "background_audio": "https://example.com/background-music1.mp3",
  "job_type": "submit_job",
  "user": "Job Name",
  "channel_name": "Channel Name"
}
```

## ⚠️ Common Issues

### JSON Format Errors:
- **Missing fields**: Ensure each video object has `user`, `message_link`, and `background_audio`
- **Invalid JSON**: Check for proper JSON syntax
- **Empty values**: All fields must have content

### Discord Message Errors:
- **Invalid message link**: Must be a valid Discord message URL
- **Wrong attachment count**: Must have exactly 8 attachments
- **Wrong file types**: Must have 4 audio + 4 image files
- **Access denied**: Bot must have access to the channel

### Webhook Errors:
- **No webhook configured**: Set up n8n webhook URLs first
- **Invalid webhook URL**: Check webhook URL format
- **Network errors**: Check internet connection

## 📊 Progress Tracking

The system provides real-time progress tracking:
- **Total items**: Number of jobs in JSON file
- **Completed**: Successfully processed jobs
- **Failed**: Jobs that encountered errors
- **Next post time**: When the next job will be processed
- **Error details**: Specific error messages for failed jobs

## 🛠️ Configuration

### Required Environment Variables:
- `DISCORD_BOT_TOKEN`: Your Discord bot token
- `ENABLE_DISCORD_JOB=true`: Enable Discord job features

### n8n Webhook Configuration:
- Configure webhook URLs in the n8n settings
- Use "Edit n8n Webhook URLs" button in navbar
- Set up both "Submit Job" and "No Cap Job" webhooks

## 📝 Example Workflow

1. **Create 5 Discord messages** with 8 attachments each
2. **Copy all message links**
3. **Create JSON file** with the links
4. **Upload to Discord Bulk Job**
5. **Select "Submit Job"** webhook
6. **Set 5-minute interval**
7. **Start the job**
8. **Monitor progress** in real-time
9. **Check n8n** for processed jobs

## 🔄 Job Management

- **Cancel running jobs**: Use the cancel button
- **View job status**: Real-time progress updates
- **Error handling**: Failed jobs are logged with details
- **Automatic cleanup**: Old completed jobs are cleaned up automatically 