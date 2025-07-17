import os
import re
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

class GoogleDriveService:
    def __init__(self, credentials_path=None):
        """Initialize Google Drive service with service account credentials."""
        self.credentials = None
        self.service = None
        
        if credentials_path and os.path.exists(credentials_path):
            self.credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            self.service = build('drive', 'v3', credentials=self.credentials)
    
    def extract_file_id(self, drive_link):
        """Extract file ID from Google Drive link."""
        patterns = [
            r'/file/d/([a-zA-Z0-9-_]+)',
            r'id=([a-zA-Z0-9-_]+)',
            r'/d/([a-zA-Z0-9-_]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, drive_link)
            if match:
                return match.group(1)
        
        raise ValueError("Invalid Google Drive link format")
    
    def get_file_metadata(self, file_id):
        """Get file metadata from Google Drive."""
        try:
            file_metadata = self.service.files().get(fileId=file_id).execute()
            return file_metadata
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
    
    def download_file(self, file_id, local_path):
        """Download file from Google Drive to local path."""
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
        """Get direct download link for a file using the uc?export=download format, appending the file extension as a query parameter if available."""
        base_link = f"https://drive.google.com/uc?export=download&id={file_id}"
        if file_name and '.' in file_name:
            ext = file_name[file_name.rfind('.'):]
            return f"{base_link}&ext={ext}"
        return base_link
    
    def download_file_direct(self, drive_link, local_path):
        """Download file directly using requests (for public files)."""
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
        """List files in a Google Drive folder, optionally filtering by MIME types and sorting by modifiedTime (oldest first)."""
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
