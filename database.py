"""Simple JSON-based database for storing Discord to FACEIT username mappings."""
import json
import os
from datetime import datetime
from typing import Optional, Dict

class Database:
    """Manages user data persistence in JSON format."""
    
    def __init__(self, db_file: str = 'users.json'):
        """Initialize the database.
        
        Args:
            db_file: Path to the JSON database file
        """
        self.db_file = db_file
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Create the database file if it doesn't exist."""
        if not os.path.exists(self.db_file):
            with open(self.db_file, 'w') as f:
                json.dump({}, f)
    
    def _load(self) -> Dict:
        """Load data from the database file."""
        with open(self.db_file, 'r') as f:
            return json.load(f)
    
    def _save(self, data: Dict):
        """Save data to the database file."""
        with open(self.db_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def link_user(self, discord_id: str, faceit_username: str) -> bool:
        """Link a Discord user to a FACEIT username.
        
        Args:
            discord_id: Discord user ID
            faceit_username: FACEIT username
            
        Returns:
            True if successful
        """
        data = self._load()
        data[str(discord_id)] = {
            'faceit_username': faceit_username,
            'last_updated': datetime.now().isoformat()
        }
        self._save(data)
        return True
    
    def unlink_user(self, discord_id: str) -> bool:
        """Unlink a Discord user from their FACEIT account.
        
        Args:
            discord_id: Discord user ID
            
        Returns:
            True if user was found and removed, False otherwise
        """
        data = self._load()
        discord_id = str(discord_id)
        
        if discord_id in data:
            del data[discord_id]
            self._save(data)
            return True
        return False
    
    def get_faceit_username(self, discord_id: str) -> Optional[str]:
        """Get the FACEIT username for a Discord user.
        
        Args:
            discord_id: Discord user ID
            
        Returns:
            FACEIT username if found, None otherwise
        """
        data = self._load()
        user_data = data.get(str(discord_id))
        
        if user_data:
            return user_data.get('faceit_username')
        return None
    
    def is_user_linked(self, discord_id: str) -> bool:
        """Check if a Discord user is linked to a FACEIT account.
        
        Args:
            discord_id: Discord user ID
            
        Returns:
            True if linked, False otherwise
        """
        return self.get_faceit_username(discord_id) is not None
    
    def get_all_users(self) -> Dict:
        """Get all user data.
        
        Returns:
            Dictionary of all user mappings
        """
        return self._load()

