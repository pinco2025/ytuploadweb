# Discord Bulk Job Guide

## 🧙‍♂️ Discord Bulk Job Wizard

The Discord Bulk Job system features a **step-by-step wizard** that guides you through the entire process. This intuitive interface provides better validation and flexibility for creating bulk video jobs.

### Wizard Workflow:
1. **Setup** - Configure number of videos and webhook type
2. **Titles** - Enter video titles (one per line)
3. **Audio Set** - Provide Discord message links with 4 audio files each
4. **Background Audio Set** - Provide direct URLs to background audio files (MP3, WAV, etc.)
5. **Image Set** - Provide Discord message links with 4 image files each + select channel
6. **Optional Second Image Set** - Reuse same audio with different images (optional)
7. **Execute** - Set posting interval and start the job

### Key Benefits:
- ✅ **Real-time validation** at each step
- ✅ **Flexible audio reuse** with multiple image sets
- ✅ **Channel selection** for targeted content
- ✅ **Live counters** to track your progress
- ✅ **Intuitive interface** - no complex file formats required

## 🔧 Requirements

### Discord Message Requirements:
- **Message link format**: Must be a valid Discord message URL
- **Supported formats**:
  - `https://discord.com/channels/guild_id/channel_id/message_id`
  - `https://discordapp.com/channels/guild_id/channel_id/message_id` (auto-converted)
  - `discord://channels/guild_id/channel_id/message_id` (auto-converted)

### Discord Message Content Requirements:
- **Exactly 4 attachments** per message
- **Audio messages**: 4 audio files with extensions: `.mp3`, `.wav`, `.m4a`, `.aac`, `.mp4`
- **Image messages**: 4 image files with extensions: `.jpg`, `.jpeg`, `.png`, `.webp`
- **File order**: Attachments will be processed in reverse order (last attachment first)

### Background Audio Requirements:
- **Direct URLs**: Must be direct links to audio files
- **Supported formats**: MP3, WAV, M4A, AAC, OGG, FLAC
- **Hosting services**: Google Drive, Dropbox, SoundCloud, OneDrive, etc.

## 🚀 How to Use

1. **Go to Discord Bulk Job** in the navigation
2. **Follow the 7-step wizard**:
   - **Step 1**: Set number of videos and webhook type
   - **Step 2**: Enter video titles (one per line)
   - **Step 3**: Add Discord message links with 4 audio files each
   - **Step 4**: Add direct URLs to background audio files (MP3, WAV, etc.)
   - **Step 5**: Add Discord message links with 4 image files each + select channel
   - **Step 6**: Optionally add a second image set with different channel
   - **Step 7**: Set posting interval and start the job

## 🔍 How It Works

### Processing Flow:
1. **Wizard collects** all required information step by step
2. **For each video**:
   - Gets title from step 2
   - Fetches 4 audio files from Discord message (step 3)
   - Gets background audio URL (step 4)
   - Fetches 4 image files from Discord message (step 5)
   - Reverses file order (last attachment first)
   - Creates n8n payload with all components
   - Posts to selected webhook
   - Waits for specified interval
   - Continues to next video

### n8n Payload Format:

```json
{
  "user": "Video Title",
  "audios": ["audio1.mp3", "audio2.mp3", "audio3.mp3", "audio4.mp3"],
  "background_audio": "https://example.com/background-music.mp3", 
  "images": ["image1.jpg", "image2.jpg", "image3.jpg", "image4.jpg"],
  "channel_name": "Channel Name"
}
```

## ⚠️ Common Issues

### Discord Message Errors:
- **Invalid message link**: Must be a valid Discord message URL
- **Wrong attachment count**: Must have exactly 4 attachments per message
- **Wrong file types**: Audio messages need 4 audio files, Image messages need 4 image files
- **Mixed file types**: Each message should contain only one type (all audio OR all images)
- **Access denied**: Bot must have access to the channel

### Background Audio Errors:
- **Invalid URL**: Must be a valid HTTP/HTTPS URL
- **Unsupported format**: Use MP3, WAV, M4A, AAC, OGG, or FLAC
- **Access denied**: URL must be publicly accessible

### Webhook Errors:
- **No webhook configured**: Set up n8n webhook URLs first
- **Invalid webhook URL**: Check webhook URL format
- **Network errors**: Check internet connection

### Wizard Validation Errors:
- **Count mismatch**: Number of titles, audio links, background audio URLs, and image links must all match
- **Empty fields**: All required fields must be filled

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

## 🎨 Dual Image Set Feature (Wizard Only)

The wizard supports creating **two different video sets** using the same audio content:

### Use Case:
- **Set 1**: Gaming highlights with dramatic music → Post to "EpicWisdom" channel
- **Set 2**: Same audio with different visuals → Post to "SynthSaga" channel

### How It Works:
1. Complete steps 1-5 normally (setup through first image set)
2. In **Step 6**, enable "Use Same Audio Set for Different Image Set"
3. Provide a new set of Discord message links with different images
4. Select a different target channel
5. The system will process **both sets** with the same titles and audio

### Result:
- **Total jobs**: Number of videos × 2 (if dual set enabled)
- **Same audio reused**: Titles, audio, and background audio stay identical
- **Different content**: Images and target channels change
- **Sequential processing**: First set completes, then second set begins

## 📝 Example Workflows

### Example Workflow:
1. **Use the step-by-step wizard**
2. **Prepare Discord messages**: Audio (4 files each), Images (4 files each)
3. **Prepare background audio URLs**: Direct links to MP3/WAV files
4. **Follow wizard prompts** for validation and setup
5. **Monitor real-time progress** as jobs execute
6. **Check n8n** for processed jobs

## 🔄 Job Management

- **Cancel running jobs**: Use the cancel button
- **View job status**: Real-time progress updates
- **Error handling**: Failed jobs are logged with details
- **Automatic cleanup**: Old completed jobs are cleaned up automatically 