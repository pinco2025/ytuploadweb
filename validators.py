import re
import os
import mimetypes
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse, parse_qs

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

class InputValidator:
    """Handles validation of all user inputs for uploads, links, and metadata."""
    
    # Supported video formats
    SUPPORTED_VIDEO_FORMATS = {
        '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.m4v'
    }
    
    # Maximum file sizes (in bytes)
    MAX_FILE_SIZE = 15 * 1024 * 1024 * 1024  # 15GB for YouTube
    MAX_TITLE_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 5000
    MAX_HASHTAGS = 20
    MAX_HASHTAG_LENGTH = 30
    
    @staticmethod
    def validate_google_drive_link(drive_link: str) -> Tuple[bool, str, Optional[str]]:
        """Validate a Google Drive link and extract the file ID. Returns (is_valid, error_message, file_id)."""
        if not drive_link:
            return False, "Google Drive link is required", None
        
        if not isinstance(drive_link, str):
            return False, "Google Drive link must be a string", None
        
        # Remove whitespace
        drive_link = drive_link.strip()
        
        # Check if it's a valid URL
        try:
            parsed_url = urlparse(drive_link)
            if parsed_url.scheme not in ['http', 'https']:
                return False, "Invalid URL scheme", None
        except Exception:
            return False, "Invalid URL format", None
        
        # Google Drive link patterns
        patterns = [
            r'/file/d/([a-zA-Z0-9-_]+)',  # Standard file link
            r'id=([a-zA-Z0-9-_]+)',       # Query parameter format
            r'/d/([a-zA-Z0-9-_]+)',       # Short format
            r'/open\?id=([a-zA-Z0-9-_]+)' # Open format
        ]
        
        file_id = None
        for pattern in patterns:
            match = re.search(pattern, drive_link)
            if match:
                file_id = match.group(1)
                break
        
        if not file_id:
            return False, "Invalid Google Drive link format. Please provide a valid sharing link.", None
        
        # Validate file ID format (Google Drive file IDs are typically 33 characters)
        if len(file_id) < 20 or len(file_id) > 50:
            return False, "Invalid file ID format", None
        
        return True, "", file_id
    
    @staticmethod
    def validate_video_title(title: str) -> Tuple[bool, str]:
        """Validate a video title for YouTube upload. Returns (is_valid, error_message)."""
        if not title:
            return False, "Video title is required"
        
        if not isinstance(title, str):
            return False, "Video title must be a string"
        
        title = title.strip()
        
        if len(title) == 0:
            return False, "Video title cannot be empty"
        
        if len(title) > InputValidator.MAX_TITLE_LENGTH:
            return False, f"Video title must be {InputValidator.MAX_TITLE_LENGTH} characters or less"
        
        # Check for potentially problematic characters
        problematic_chars = ['<', '>', '&', '"', "'"]
        for char in problematic_chars:
            if char in title:
                return False, f"Video title contains invalid character: {char}"
        
        return True, ""
    
    @staticmethod
    def validate_description(description: str) -> Tuple[bool, str]:
        """Validate a video description for YouTube upload. Returns (is_valid, error_message)."""
        if not description:
            return True, ""  # Description is optional
        
        if not isinstance(description, str):
            return False, "Description must be a string"
        
        description = description.strip()
        
        if len(description) > InputValidator.MAX_DESCRIPTION_LENGTH:
            return False, f"Description must be {InputValidator.MAX_DESCRIPTION_LENGTH} characters or less"
        
        return True, ""
    
    @staticmethod
    def validate_hashtags(hashtags: str) -> Tuple[bool, str, List[str]]:
        """Validate and parse hashtags. Returns (is_valid, error_message, parsed_hashtags)."""
        if not hashtags:
            return True, "", []
        
        if not isinstance(hashtags, str):
            return False, "Hashtags must be a string", []
        
        hashtags = hashtags.strip()
        
        # Split hashtags by spaces, commas, or newlines
        raw_tags = re.split(r'[,\s\n]+', hashtags)
        parsed_tags = []
        
        for tag in raw_tags:
            tag = tag.strip()
            if not tag:
                continue
            
            # Remove # if present and add it back
            if tag.startswith('#'):
                tag = tag[1:]
            
            # Validate tag length
            if len(tag) > InputValidator.MAX_HASHTAG_LENGTH:
                return False, f"Hashtag '{tag}' is too long (max {InputValidator.MAX_HASHTAG_LENGTH} characters)", []
            
            # Validate tag format (alphanumeric and underscores only)
            if not re.match(r'^[a-zA-Z0-9_]+$', tag):
                return False, f"Hashtag '{tag}' contains invalid characters. Use only letters, numbers, and underscores.", []
            
            parsed_tags.append(tag)
        
        # Check number of hashtags
        if len(parsed_tags) > InputValidator.MAX_HASHTAGS:
            return False, f"Too many hashtags (max {InputValidator.MAX_HASHTAGS})", []
        
        return True, "", parsed_tags
    
    @staticmethod
    def validate_privacy_setting(privacy: str) -> Tuple[bool, str]:
        """Validate the privacy setting for a YouTube video. Returns (is_valid, error_message)."""
        valid_privacy_settings = ['private', 'unlisted', 'public']
        
        if not privacy:
            return False, "Privacy setting is required"
        
        if privacy not in valid_privacy_settings:
            return False, f"Invalid privacy setting. Must be one of: {', '.join(valid_privacy_settings)}"
        
        return True, ""
    
    @staticmethod
    def validate_client_id(client_id: str, available_clients: List[Dict]) -> Tuple[bool, str]:
        """Validate a client ID against the list of available clients. Returns (is_valid, error_message)."""
        if not client_id:
            return False, "Client ID is required"
        
        if not isinstance(client_id, str):
            return False, "Client ID must be a string"
        
        # Check if client exists
        client_exists = any(client['id'] == client_id for client in available_clients)
        if not client_exists:
            return False, f"Client '{client_id}' not found"
        
        return True, ""
    
    @staticmethod
    def validate_channel_id(channel_id: str, available_channels: List[Dict]) -> Tuple[bool, str]:
        """Validate a channel ID against the list of available channels. Returns (is_valid, error_message)."""
        if not channel_id:
            return False, "Channel ID is required"
        
        if not isinstance(channel_id, str):
            return False, "Channel ID must be a string"
        
        # Check if channel exists
        channel_exists = any(channel['id'] == channel_id for channel in available_channels)
        if not channel_exists:
            return False, f"Channel '{channel_id}' not found"
        
        return True, ""
    
    @staticmethod
    def validate_file_path(file_path: str) -> Tuple[bool, str]:
        """Validate a local file path for upload. Returns (is_valid, error_message)."""
        if not file_path:
            return False, "File path is required"
        
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        if not os.path.isfile(file_path):
            return False, f"Path is not a file: {file_path}"
        
        # Check file size
        try:
            file_size = os.path.getsize(file_path)
            if file_size > InputValidator.MAX_FILE_SIZE:
                return False, f"File too large: {file_size} bytes (max {InputValidator.MAX_FILE_SIZE} bytes)"
        except OSError:
            return False, f"Cannot access file: {file_path}"
        
        # Check file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in InputValidator.SUPPORTED_VIDEO_FORMATS:
            return False, f"Unsupported file format: {file_ext}. Supported formats: {', '.join(InputValidator.SUPPORTED_VIDEO_FORMATS)}"
        
        return True, ""
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize text input to prevent XSS and other attacks. Returns cleaned text."""
        if not text:
            return ""
        
        # Remove potentially dangerous HTML tags
        dangerous_tags = ['<script>', '</script>', '<iframe>', '</iframe>', '<object>', '</object>']
        for tag in dangerous_tags:
            text = text.replace(tag, '')
        
        # Remove HTML entities
        text = re.sub(r'&[a-zA-Z0-9#]+;', '', text)
        
        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    @staticmethod
    def validate_upload_form_data(form_data: Dict, available_clients: List[Dict], available_channels: List[Dict]) -> Tuple[bool, str, Dict]:
        """Validate all upload form data at once. Returns (is_valid, error_message, cleaned_data)."""
        cleaned_data = {}
        
        # Validate Google Drive link
        drive_link = form_data.get('drive_link', '')
        is_valid, error_msg, file_id = InputValidator.validate_google_drive_link(drive_link)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['drive_link'] = drive_link
        cleaned_data['file_id'] = file_id
        
        # Validate title
        title = form_data.get('title', '')
        is_valid, error_msg = InputValidator.validate_video_title(title)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['title'] = InputValidator.sanitize_text(title)
        
        # Validate description
        description = form_data.get('description', '')
        is_valid, error_msg = InputValidator.validate_description(description)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['description'] = InputValidator.sanitize_text(description)
        
        # Validate hashtags
        hashtags = form_data.get('hashtags', '')
        is_valid, error_msg, parsed_hashtags = InputValidator.validate_hashtags(hashtags)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['hashtags'] = parsed_hashtags
        
        # Validate privacy setting
        privacy = form_data.get('privacy', 'public')
        is_valid, error_msg = InputValidator.validate_privacy_setting(privacy)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['privacy'] = privacy
        
        # Validate client ID
        client_id = form_data.get('client_id', '')
        is_valid, error_msg = InputValidator.validate_client_id(client_id, available_clients)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['client_id'] = client_id
        
        # Validate channel ID
        channel_id = form_data.get('channel', '')
        is_valid, error_msg = InputValidator.validate_channel_id(channel_id, available_channels)
        if not is_valid:
            return False, error_msg, {}
        cleaned_data['channel_id'] = channel_id
        
        return True, "", cleaned_data 