import os
import re
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleDriveService:
    """Service for interacting with Google Drive: file download, metadata, and folder listing."""
    def __init__(self, credentials_path=None):
        """Initialize Google Drive service with service account credentials if provided."""
        self.credentials = None
        self.service = None
        
        # Try to load service account credentials from common locations
        if credentials_path and os.path.exists(credentials_path):
            self._load_service_account(credentials_path)
        else:
            # Try common service account file locations
            common_paths = [
                'service-account-key.json',
                'google-service-account.json',
                'drive-service-account.json',
                os.path.join('tokens', 'service-account-key.json'),
                os.path.join('config', 'service-account-key.json')
            ]
            
            for path in common_paths:
                if os.path.exists(path):
                    self._load_service_account(path)
                    break
    
    def _load_service_account(self, credentials_path):
        """Load service account credentials from file."""
        try:
            self.credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            self.service = build('drive', 'v3', credentials=self.credentials)
            print(f"Successfully loaded service account credentials from: {credentials_path}")
        except Exception as e:
            print(f"Failed to load service account credentials from {credentials_path}: {e}")
            self.credentials = None
            self.service = None
    
    def extract_file_id(self, drive_link):
        """Extract file ID from a Google Drive sharing link using regex patterns."""
        patterns = [
            r'/file/d/([a-zA-Z0-9-_]+)',
            r'id=([a-zA-Z0-9-_]+)',
            r'/d/([a-zA-Z0-9-_]+)',
            r'/open\?id=([a-zA-Z0-9-_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, drive_link)
            if match:
                return match.group(1)
        
        raise ValueError("Invalid Google Drive link format")
    
    def get_file_metadata(self, file_id):
        """Get file metadata from Google Drive by file ID. Returns dict or None on error."""
        if not self.service:
            print("Google Drive service not initialized with service account credentials.")
            return None
        try:
            file_metadata = self.service.files().get(fileId=file_id).execute()
            return file_metadata
        except HttpError as error:
            print(f"An error occurred while getting file metadata: {error}")
            return None
    
    def download_file(self, file_id, local_path):
        """Download a file from Google Drive to a local path using the Drive API."""
        if not self.service:
            print("Google Drive service not initialized with service account credentials.")
            return False
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            with open(local_path, 'wb') as file:
                downloader = request.execute()
                file.write(downloader)
            
            return True
        except HttpError as error:
            print(f"An error occurred while downloading: {error}")
            return False
    
    def get_public_download_link(self, file_id, file_name=None):
        """Get a direct download link for a file, optionally appending the file extension."""
        base_link = f"https://drive.google.com/uc?export=download&id={file_id}"
        if file_name and '.' in file_name:
            ext = file_name[file_name.rfind('.'):]
            return f"{base_link}&ext={ext}"
        return base_link
    
    def convert_to_direct_link(self, drive_link):
        """Convert a Google Drive view link to a direct download link for Instagram uploads."""
        try:
            file_id = self.extract_file_id(drive_link)
            
            # For Instagram uploads, we need a direct link that Instagram can access
            # Using the uc endpoint with export=download parameter
            direct_link = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            # For MP4 files, we can also try the more direct approach
            # This format works better with Instagram's API
            direct_link_alt = f"https://drive.google.com/file/d/{file_id}/preview"
            
            return {
                'success': True,
                'file_id': file_id,
                'direct_link': direct_link,
                'preview_link': direct_link_alt,
                'message': 'Link converted successfully'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to convert link: {str(e)}',
                'message': 'Invalid Google Drive link format'
            }
    
    def get_file_info(self, drive_link):
        """Get file information from a Google Drive link using service account credentials."""
        try:
            file_id = self.extract_file_id(drive_link)
            
            # If we have service account credentials, use the API to get real metadata
            if self.service:
                metadata = self.get_file_metadata(file_id)
                if metadata:
                    return {
                        'name': metadata.get('name', ''),
                        'id': file_id,
                        'mimeType': metadata.get('mimeType', ''),
                        'size': metadata.get('size', 0),
                        'extracted_with': 'service_account'
                    }
                else:
                    print(f"Failed to get metadata for file ID: {file_id}")
            
            # Fallback for when service account is not available or fails
            # Try to extract filename from the URL if it contains one
            filename_from_url = self._extract_filename_from_url(drive_link)
            if filename_from_url:
                return {
                    'name': filename_from_url,
                    'id': file_id,
                    'mimeType': 'video/mp4',  # Assume video files
                    'size': 0,
                    'extracted_with': 'url_parsing',
                    'note': 'Filename extracted from URL. For more accurate extraction, provide service account credentials.'
                }
            
            # Last resort: create a descriptive name based on the file ID
            return {
                'name': f'video_{file_id[:8]}',  # Use first 8 chars of file ID
                'id': file_id,
                'mimeType': 'video/mp4',  # Assume video files
                'size': 0,
                'extracted_with': 'fallback',
                'note': 'Filename not available. Use filename override field for better AI generation, or provide service account credentials.'
            }
            
        except Exception as e:
            print(f"Error getting file info: {e}")
            return None
    
    def _extract_filename_from_url(self, drive_link):
        """Try to extract filename from Google Drive URL if it contains one."""
        try:
            # Some Google Drive URLs contain the filename in the path
            # Pattern: /file/d/{file_id}/{filename}
            filename_pattern = r'/file/d/[a-zA-Z0-9-_]+/([^/?]+)'
            match = re.search(filename_pattern, drive_link)
            if match:
                filename = match.group(1)
                # URL decode the filename
                import urllib.parse
                filename = urllib.parse.unquote(filename)
                return filename
            
            # Check for filename in query parameters
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(drive_link)
            query_params = parse_qs(parsed_url.query)
            
            # Look for common filename parameters
            for param in ['name', 'filename', 'title']:
                if param in query_params:
                    filename = query_params[param][0]
                    import urllib.parse
                    filename = urllib.parse.unquote(filename)
                    return filename
            
            return None
        except Exception as e:
            print(f"Error extracting filename from URL: {e}")
            return None
    
    def download_file_direct(self, drive_link, local_path):
        """Download a file directly using requests (for public files only)."""
        try:
            file_id = self.extract_file_id(drive_link)
            download_url = f"https://drive.google.com/uc?id={file_id}"
            
            response = requests.get(download_url)
            
            if response.status_code == 200:
                with open(local_path, 'wb') as file:
                    file.write(response.content)
                return True
            else:
                print(f"Failed to download file: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"Error downloading file: {e}")
            return False
    
    def list_files_in_folder(self, folder_id, mime_types=None, max_files=100):
        """List files in a Google Drive folder, optionally filtering by MIME types and sorting by modifiedTime (oldest first). Returns a list of file dicts."""
        if not self.service:
            print("Google Drive service not initialized with service account credentials.")
            return []
        try:
            query = f"'{folder_id}' in parents and trashed = false"
            if mime_types:
                mime_query = ' or '.join([f"mimeType='{mt}'" for mt in mime_types])
                query += f" and ({mime_query})"
            results = self.service.files().list(
                q=query,
                orderBy="modifiedTime",
                pageSize=max_files,
                fields="files(id, name, mimeType, modifiedTime)"
            ).execute()
            return results.get('files', [])
        except HttpError as error:
            print(f"An error occurred while listing files: {error}")
            return []
    
    def is_service_account_available(self):
        """Check if service account credentials are available."""
        return self.service is not None
