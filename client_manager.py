import json
import os
from typing import List, Dict, Optional
from datetime import datetime

class ClientManager:
    def __init__(self, clients_file='clients.json'):
        """Initialize the client manager with a clients configuration file."""
        self.clients_file = clients_file
        self.clients = []
        self.session_upload_count = 0
        self.load_clients()
    
    def load_clients(self):
        """Load clients from the configuration file."""
        try:
            if os.path.exists(self.clients_file):
                with open(self.clients_file, 'r') as f:
                    self.clients = json.load(f)
            else:
                # Create default clients file if it doesn't exist
                self.clients = [
                    {
                        "id": "client1",
                        "name": "YouTube Client 1",
                        "client_id": "your-client-id-1.apps.googleusercontent.com",
                        "client_secret": "your-client-secret-1",
                        "upload_count": 0
                    }
                ]
                self.save_clients()
        except Exception as e:
            print(f"Error loading clients: {e}")
            self.clients = []
    
    def save_clients(self):
        """Save clients to the configuration file."""
        try:
            with open(self.clients_file, 'w') as f:
                json.dump(self.clients, f, indent=2)
        except Exception as e:
            print(f"Error saving clients: {e}")
    
    def get_all_clients(self) -> List[Dict]:
        """Get all clients."""
        return self.clients
    
    def get_client_by_id(self, client_id: str) -> Optional[Dict]:
        """Get a specific client by ID."""
        for client in self.clients:
            if client['id'] == client_id:
                return client
        return None
    
    def increment_upload_count(self, client_id: str):
        """Increment the upload count for a specific client."""
        for client in self.clients:
            if client['id'] == client_id:
                client['upload_count'] += 1
                self.session_upload_count += 1
                self.save_clients()
                return
        print(f"Warning: Client {client_id} not found")
    
    def get_session_upload_count(self) -> int:
        """Get the number of uploads in this session."""
        return self.session_upload_count
    
    def get_total_upload_count(self) -> int:
        """Get the total number of uploads across all clients."""
        return sum(client['upload_count'] for client in self.clients)
    
    def get_client_upload_count(self, client_id: str) -> int:
        """Get the upload count for a specific client."""
        client = self.get_client_by_id(client_id)
        return client['upload_count'] if client else 0
    
    def reset_session_count(self):
        """Reset the session upload count."""
        self.session_upload_count = 0
    
    def add_client(self, client_data: Dict):
        """Add a new client."""
        self.clients.append(client_data)
        self.save_clients()
    
    def update_client(self, client_id: str, client_data: Dict):
        """Update an existing client."""
        for i, client in enumerate(self.clients):
            if client['id'] == client_id:
                self.clients[i] = client_data
                self.save_clients()
                return True
        return False
    
    def delete_client(self, client_id: str):
        """Delete a client."""
        self.clients = [client for client in self.clients if client['id'] != client_id]
        self.save_clients()
    
    def get_client_stats(self) -> Dict:
        """Get statistics for all clients."""
        stats = {
            'total_clients': len(self.clients),
            'total_uploads': self.get_total_upload_count(),
            'session_uploads': self.session_upload_count,
            'client_stats': []
        }
        
        for client in self.clients:
            stats['client_stats'].append({
                'id': client['id'],
                'name': client['name'],
                'upload_count': client['upload_count']
            })
        
        return stats
