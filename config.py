"""Configuration management for the Discord FACEIT bot."""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class to store API keys and settings."""
    
    # Discord Configuration
    DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    # FACEIT API Configuration
    FACEIT_API_KEY = os.getenv('FACEIT_API_KEY')
    FACEIT_API_BASE_URL = 'https://open.faceit.com/data/v4'
    
    # Bot Settings
    COMMAND_PREFIX = '!'
    REQUIRED_PLAYERS = 10
    TEAM_SIZE = 5
    
    @classmethod
    def validate(cls):
        """Validate that all required configuration is present."""
        if not cls.DISCORD_BOT_TOKEN:
            raise ValueError("DISCORD_BOT_TOKEN not found in environment variables")
        if not cls.FACEIT_API_KEY:
            raise ValueError("FACEIT_API_KEY not found in environment variables")
        return True

