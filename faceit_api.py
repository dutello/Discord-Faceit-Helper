"""FACEIT API integration for fetching player data and ELO."""
import requests
from typing import Optional, Dict
from config import Config

class FaceitAPI:
    """Wrapper for FACEIT API interactions."""
    
    def __init__(self):
        """Initialize the FACEIT API client."""
        self.api_key = Config.FACEIT_API_KEY
        self.base_url = Config.FACEIT_API_BASE_URL
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }
    
    def get_player_by_nickname(self, nickname: str) -> Optional[Dict]:
        """Get player data by nickname.
        
        Args:
            nickname: FACEIT username/nickname
            
        Returns:
            Player data dictionary if found, None otherwise
        """
        try:
            url = f'{self.base_url}/players'
            params = {'nickname': nickname}
            
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                print(f"Error fetching player {nickname}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Exception fetching player {nickname}: {str(e)}")
            return None
    
    def get_player_csgo_elo(self, nickname: str) -> Optional[int]:
        """Get a player's CS:GO ELO.
        
        Args:
            nickname: FACEIT username/nickname
            
        Returns:
            CS:GO ELO as integer if found, None otherwise
        """
        player_data = self.get_player_by_nickname(nickname)
        
        if not player_data:
            return None
        
        # Check if player has CS:GO game data
        games = player_data.get('games', {})
        csgo_data = games.get('cs2') or games.get('csgo')  # Try CS2 first, fallback to CSGO
        
        if not csgo_data:
            return None
        
        # Get ELO from faceit_elo field
        elo = csgo_data.get('faceit_elo', 0)
        return int(elo) if elo else None
    
    def verify_player_exists(self, nickname: str) -> bool:
        """Verify that a FACEIT player exists.
        
        Args:
            nickname: FACEIT username/nickname
            
        Returns:
            True if player exists, False otherwise
        """
        return self.get_player_by_nickname(nickname) is not None
    
    def get_player_stats(self, nickname: str) -> Optional[Dict]:
        """Get comprehensive player stats including ELO, level, etc.
        
        Args:
            nickname: FACEIT username/nickname
            
        Returns:
            Dictionary with player stats or None if not found
        """
        player_data = self.get_player_by_nickname(nickname)
        
        if not player_data:
            return None
        
        games = player_data.get('games', {})
        csgo_data = games.get('cs2') or games.get('csgo')
        
        if not csgo_data:
            return {
                'nickname': nickname,
                'elo': None,
                'level': None,
                'has_csgo': False
            }
        
        return {
            'nickname': nickname,
            'elo': int(csgo_data.get('faceit_elo', 0)),
            'level': int(csgo_data.get('skill_level', 0)),
            'has_csgo': True,
            'player_id': player_data.get('player_id'),
            'avatar': player_data.get('avatar', '')
        }

