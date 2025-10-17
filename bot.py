"""Discord bot for FACEIT team balancing."""
import discord
import time
import logging
import json
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Optional
import asyncio

from config import Config
from database import Database
from faceit_api import FaceitAPI
from team_balancer import TeamBalancer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Active sessions storage
ACTIVE_SESSIONS_FILE = "active_sessions.json"
active_sessions = {}

def load_active_sessions():
    """Load active sessions from file."""
    global active_sessions
    try:
        with open(ACTIVE_SESSIONS_FILE, 'r') as f:
            active_sessions = json.load(f)
        logger.info(f"Loaded {len(active_sessions)} active sessions")
    except FileNotFoundError:
        active_sessions = {}
    except Exception as e:
        logger.error(f"Error loading active sessions: {e}")
        active_sessions = {}

def save_active_sessions():
    """Save active sessions to file."""
    try:
        with open(ACTIVE_SESSIONS_FILE, 'w') as f:
            json.dump(active_sessions, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving active sessions: {e}")

def cleanup_expired_sessions():
    """Remove expired sessions (older than 30 minutes)."""
    current_time = time.time()
    expired_sessions = []
    
    for session_id, session_data in active_sessions.items():
        if current_time - session_data.get('created_at', 0) > 1800:  # 30 minutes
            expired_sessions.append(session_id)
    
    for session_id in expired_sessions:
        del active_sessions[session_id]
        logger.info(f"Cleaned up expired session: {session_id}")
    
    if expired_sessions:
        save_active_sessions()

async def replace_old_sessions():
    """Restore functionality to existing session messages on bot startup."""
    logger.info("Checking for old sessions to restore...")
    
    for session_id, session_data in active_sessions.items():
        try:
            guild_id = session_data.get('guild_id')
            channel_id = session_data.get('channel_id')
            message_id = session_data.get('message_id')
            
            if not guild_id or not channel_id or not message_id:
                continue
                
            guild = bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"Guild {guild_id} not found, skipping session {session_id}")
                continue
                
            channel = guild.get_channel(channel_id)
            if not channel:
                logger.warning(f"Channel {channel_id} not found in guild {guild_id}, skipping session {session_id}")
                continue
            
            # Try to find the existing message
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                logger.warning(f"Message {message_id} not found in channel {channel.name}, skipping session {session_id}")
                # Remove session if message doesn't exist
                del active_sessions[session_id]
                save_active_sessions()
                continue
            
            # Restore the session data
            participants = session_data.get('participants', [])
            teams_created = session_data.get('teams_created', False)
            
            # Create new view with restored session
            new_session_id = f"{guild_id}_{channel_id}_{int(time.time())}"
            
            # Create a mock context for the view
            class MockContext:
                def __init__(self, guild, channel):
                    self.guild = guild
                    self.channel = channel
            
            mock_ctx = MockContext(guild, channel)
            new_view = BalanceSessionView(mock_ctx, new_session_id)
            new_view.participants = set(participants)
            new_view.teams_created = teams_created
            new_view.team_a = session_data.get('team_a', [])
            new_view.team_b = session_data.get('team_b', [])
            new_view.message = message  # Link to existing message
            new_view.save_session()
            
            # Update the existing message with new working buttons
            embed = discord.Embed(
                title="🎮 CS2 Team Balancing Session",
                description=f"Click **Join Session** to participate!\nWe need exactly **{Config.REQUIRED_PLAYERS}** players.",
                color=discord.Color.orange()
            )
            
            embed.add_field(
                name=f"Participants ({len(participants)}/{Config.REQUIRED_PLAYERS})",
                value="\n".join([f"<@{p}>" for p in participants]) if participants else "*No one has joined yet...*",
                inline=False
            )
            
            if teams_created:
                embed.add_field(
                    name="Status",
                    value="✅ Teams have been created",
                    inline=False
                )
            
            # Edit the existing message with new working view
            await message.edit(embed=embed, view=new_view)
            
            # Remove the old session and save the new one
            del active_sessions[session_id]
            save_active_sessions()
            
            logger.info(f"Restored functionality to existing message in channel {channel.name}")
            
        except Exception as e:
            logger.error(f"Error restoring session {session_id}: {e}")
            # Remove problematic session
            if session_id in active_sessions:
                del active_sessions[session_id]
                save_active_sessions()

import re

# Validate configuration
Config.validate()

# Initialize components
db = Database()
faceit = FaceitAPI()
balancer = TeamBalancer()

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents)


def extract_faceit_username(input_text: str) -> str:
    """Extract FACEIT username from either username or profile URL.
    
    Args:
        input_text: Either a FACEIT username or a FACEIT profile URL
        
    Returns:
        Extracted username
    """
    # Check if it's a FACEIT URL
    faceit_url_pattern = r'https?://(?:www\.)?faceit\.com/(?:en/)?players?/([^/?]+)'
    match = re.search(faceit_url_pattern, input_text)
    
    if match:
        return match.group(1)
    
    # If it's not a URL, assume it's a username
    # Clean up any extra characters
    username = input_text.strip()
    
    # Remove any @ symbols that users might add
    if username.startswith('@'):
        username = username[1:]
    
    return username


class BalanceSessionView(discord.ui.View):
    """Interactive view for team balancing session."""
    
    def __init__(self, ctx, session_id: str = None):
        super().__init__(timeout=1800)  # 30 minute timeout
        self.ctx = ctx
        self.participants = set()
        self.message = None
        self.teams_created = False
        self.session_start_time = time.time()
        self.session_id = session_id or f"{ctx.guild.id}_{ctx.channel.id}_{int(time.time())}"
        
        # Load session data if session_id provided (restart scenario)
        if session_id and session_id in active_sessions:
            session_data = active_sessions[session_id]
            self.participants = set(session_data.get('participants', []))
            self.teams_created = session_data.get('teams_created', False)
            self.session_start_time = session_data.get('created_at', time.time())
            logger.info(f"Restored session {session_id} with {len(self.participants)} participants")
        
        # Save session to active sessions
        self.save_session()
    
    def save_session(self):
        """Save current session state to active sessions."""
        active_sessions[self.session_id] = {
            'participants': list(self.participants),
            'teams_created': self.teams_created,
            'team_a': getattr(self, 'team_a', []),
            'team_b': getattr(self, 'team_b', []),
            'created_at': self.session_start_time,
            'guild_id': self.ctx.guild.id,
            'channel_id': self.ctx.channel.id,
            'message_id': self.message.id if self.message else None
        }
        save_active_sessions()
    
    async def auto_recover_session(self, interaction: discord.Interaction):
        """Automatically recover session when interaction is invalid."""
        try:
            # Check if there's a saved session for this channel
            guild_id = interaction.guild.id
            channel_id = interaction.channel.id
            
            # Find the most recent session for this channel
            recent_session = None
            for session_id, session_data in active_sessions.items():
                if (session_data.get('guild_id') == guild_id and 
                    session_data.get('channel_id') == channel_id):
                    if not recent_session or session_data.get('created_at', 0) > recent_session.get('created_at', 0):
                        recent_session = session_data
            
            if recent_session:
                # Try to find and edit the existing message
                message_id = recent_session.get('message_id')
                if message_id:
                    try:
                        message = await interaction.channel.fetch_message(message_id)
                        
                        # Create new view with restored session
                        new_session_id = f"{guild_id}_{channel_id}_{int(time.time())}"
                        
                        # Create a mock context for the view
                        class MockContext:
                            def __init__(self, guild, channel):
                                self.guild = guild
                                self.channel = channel
                        
                        mock_ctx = MockContext(interaction.guild, interaction.channel)
                        new_view = BalanceSessionView(mock_ctx, new_session_id)
                        new_view.participants = set(recent_session.get('participants', []))
                        new_view.teams_created = recent_session.get('teams_created', False)
                        new_view.team_a = recent_session.get('team_a', [])
                        new_view.team_b = recent_session.get('team_b', [])
                        new_view.message = message
                        new_view.save_session()
                        
                        # Update the existing message
                        embed = discord.Embed(
                            title="🎮 CS2 Team Balancing Session",
                            description=f"Click **Join Session** to participate!\nWe need exactly **{Config.REQUIRED_PLAYERS}** players.",
                            color=discord.Color.orange()
                        )
                        
                        participants = recent_session.get('participants', [])
                        embed.add_field(
                            name=f"Participants ({len(participants)}/{Config.REQUIRED_PLAYERS})",
                            value="\n".join([f"<@{p}>" for p in participants]) if participants else "*No one has joined yet...*",
                            inline=False
                        )
                        
                        if recent_session.get('teams_created'):
                            embed.add_field(
                                name="Status",
                                value="✅ Teams have been created",
                                inline=False
                            )
                        
                        await message.edit(embed=embed, view=new_view)
                        
                        if not interaction.response.is_done():
                            await interaction.response.send_message("✅ Session restored! The buttons above are now functional.", ephemeral=True)
                        else:
                            await interaction.followup.send("✅ Session restored! The buttons above are now functional.", ephemeral=True)
                        
                        logger.info(f"Auto-recovered session for user {interaction.user.name}")
                        return
                        
                    except discord.NotFound:
                        logger.warning(f"Original message {message_id} not found, creating new session")
                
                # Fallback: create new session if original message not found
                embed = discord.Embed(
                    title="🔄 Session Recovered",
                    description="This session was restored after a bot restart. The buttons below are now functional!",
                    color=discord.Color.green()
                )
                
                participants = recent_session.get('participants', [])
                embed.add_field(
                    name=f"Participants ({len(participants)}/{Config.REQUIRED_PLAYERS})",
                    value="\n".join([f"<@{p}>" for p in participants]) if participants else "*No participants*",
                    inline=False
                )
                
                if recent_session.get('teams_created'):
                    embed.add_field(
                        name="Status",
                        value="✅ Teams have been created",
                        inline=False
                    )
                
                # Create new view with restored session
                new_view = BalanceSessionView(interaction, f"{guild_id}_{channel_id}_{int(time.time())}")
                new_view.participants = set(participants)
                new_view.teams_created = recent_session.get('teams_created', False)
                new_view.team_a = recent_session.get('team_a', [])
                new_view.team_b = recent_session.get('team_b', [])
                new_view.save_session()
                
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=embed, view=new_view)
                else:
                    await interaction.followup.send(embed=embed, view=new_view)
                
                logger.info(f"Auto-recovered session for user {interaction.user.name}")
            else:
                # No saved session, suggest starting new one
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has expired. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "⏰ **Session Expired**\n\nThis balancing session has expired. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
        except Exception as e:
            logger.error(f"Error in auto-recovery: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has expired. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
            except:
                pass
        
    async def update_embed(self):
        """Update the session embed with current participants."""
        # Check if session is getting close to expiring (10+ minutes old)
        import time
        current_time = time.time()
        session_age = current_time - self.session_start_time
        
        if session_age > 600:  # 10 minutes
            embed = discord.Embed(
                title="🎮 CS2 Team Balancing Session",
                description=f"⚠️ **Session is getting old** - interactions may expire soon!\n\nClick **Join Session** to participate!\nWe need exactly **{Config.REQUIRED_PLAYERS}** players.",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="🎮 CS2 Team Balancing Session",
                description=f"Click **Join Session** to participate!\nWe need exactly **{Config.REQUIRED_PLAYERS}** players.",
                color=discord.Color.orange()
            )
        
        if self.participants:
            participant_list = "\n".join([f"• <@{uid}>" for uid in self.participants])
            embed.add_field(
                name=f"Participants ({len(self.participants)}/{Config.REQUIRED_PLAYERS})",
                value=participant_list,
                inline=False
            )
        else:
            embed.add_field(
                name=f"Participants (0/{Config.REQUIRED_PLAYERS})",
                value="*No one has joined yet...*",
                inline=False
            )
        
        if len(self.participants) == Config.REQUIRED_PLAYERS:
            embed.color = discord.Color.green()
            embed.set_footer(text="✅ Ready! Click 'Start Balancing' to create teams.")
        
        if self.message:
            await self.message.edit(embed=embed, view=self)
    
    @discord.ui.button(label="Join Session", style=discord.ButtonStyle.primary, emoji="✋")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle join button click."""
        try:
            # Check if interaction is still valid
            if not self.is_interaction_valid(interaction):
                # Try to recover the session automatically
                await self.auto_recover_session(interaction)
                return
            
            user_id = str(interaction.user.id)
            
            # Check if user is linked to FACEIT
            if not db.is_user_linked(user_id):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ You need to link your FACEIT account first! Use `/profile <faceit_username>`",
                        ephemeral=True
                    )
                return
            
            if user_id in self.participants:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "ℹ️ You're already in the session!",
                        ephemeral=True
                    )
                return
            
            if len(self.participants) >= Config.REQUIRED_PLAYERS:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Session is full!",
                        ephemeral=True
                    )
                return
            
            self.participants.add(user_id)
            logger.info(f"User {interaction.user.name} ({interaction.user.id}) joined the balancing session")
            self.save_session()  # Save session state
            if not interaction.response.is_done():
                await interaction.response.defer()
            await self.update_embed()
        except Exception as e:
            print(f"Error in join button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
            except:
                pass
    
    @discord.ui.button(label="Leave Session", style=discord.ButtonStyle.secondary, emoji="👋")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle leave button click."""
        try:
            # Check if interaction is still valid
            if not self.is_interaction_valid(interaction):
                # Try to recover the session automatically
                await self.auto_recover_session(interaction)
                return
            
            user_id = str(interaction.user.id)
            
            if user_id not in self.participants:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "ℹ️ You're not in the session!",
                        ephemeral=True
                    )
                return
            
            self.participants.remove(user_id)
            logger.info(f"User {interaction.user.name} ({interaction.user.id}) left the balancing session")
            self.save_session()  # Save session state
            if not interaction.response.is_done():
                await interaction.response.defer()
            await self.update_embed()
        except Exception as e:
            print(f"Error in leave button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
            except:
                pass
    
    @discord.ui.button(label="Start Balancing", style=discord.ButtonStyle.success, emoji="⚖️")
    async def balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle balance button click."""
        try:
            # Check if interaction is still valid
            if not self.is_interaction_valid(interaction):
                # Try to recover the session automatically
                await self.auto_recover_session(interaction)
                return
            
            if len(self.participants) != Config.REQUIRED_PLAYERS:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ Need exactly {Config.REQUIRED_PLAYERS} players! Currently have {len(self.participants)}.",
                        ephemeral=True
                    )
                return
            
            if self.teams_created:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "ℹ️ Teams have already been created!",
                        ephemeral=True
                    )
                return
            
            logger.info(f"User {interaction.user.name} ({interaction.user.id}) initiated team balancing with {len(self.participants)} participants")
            if not interaction.response.is_done():
                await interaction.response.defer()
            await self.create_balanced_teams()
        except Exception as e:
            print(f"Error in balance button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
            except:
                pass
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button click."""
        try:
            # Check if interaction is still valid
            if not self.is_interaction_valid(interaction):
                # Try to recover the session automatically
                await self.auto_recover_session(interaction)
                return
            
            # Remove this session from active sessions
            if hasattr(self, 'session_id') and self.session_id in active_sessions:
                del active_sessions[self.session_id]
                save_active_sessions()
                logger.info(f"Session {self.session_id} cancelled and removed from storage")
            
            if not interaction.response.is_done():
                await interaction.response.send_message("Session cancelled!", ephemeral=True)
            else:
                await interaction.followup.send("Session cancelled!", ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send("Session cancelled!", ephemeral=True)
        except Exception as e:
            print(f"Error in cancel button: {e}")
            # Try to send a followup message
            try:
                await interaction.followup.send(
                    "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                    ephemeral=True
                )
            except:
                pass
        
        self.stop()
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
    
    async def on_timeout(self):
        """Handle view timeout."""
        try:
            # Remove this session from active sessions when it times out
            if hasattr(self, 'session_id') and self.session_id in active_sessions:
                del active_sessions[self.session_id]
                save_active_sessions()
                logger.info(f"Session {self.session_id} timed out and removed from storage")
            
            if self.message:
                embed = discord.Embed(
                    title="⏰ Session Expired",
                    description="This balancing session has expired. Please start a new one with `/balance`, `/start`, or `/mix`.",
                    color=discord.Color.red()
                )
                await self.message.edit(embed=embed, view=None)
        except:
            pass
    
    def is_interaction_valid(self, interaction: discord.Interaction) -> bool:
        """Check if interaction is still valid (not expired)."""
        try:
            # Check if the interaction was created more than 15 minutes ago
            import time
            current_time = time.time()
            interaction_time = interaction.created_at.timestamp()
            time_diff = current_time - interaction_time
            
            # Discord interactions expire after 15 minutes
            return time_diff < 900  # 15 minutes = 900 seconds
        except:
            return False
    
    async def create_balanced_teams(self):
        """Fetch ELOs and create balanced teams."""
        logger.info(f"Starting team balancing process for {len(self.participants)} participants")
        status_embed = discord.Embed(
            title="⏳ Fetching FACEIT ELOs...",
            description="Please wait while I get everyone's current ELO.",
            color=discord.Color.blue()
        )
        await self.message.edit(embed=status_embed, view=None)
        
        # Fetch ELO for all participants
        players = []
        failed_players = []
        
        for discord_id in self.participants:
            faceit_username = db.get_faceit_username(discord_id)
            if not faceit_username:
                failed_players.append(discord_id)
                continue
            
            elo = faceit.get_player_csgo_elo(faceit_username)
            if elo is None:
                failed_players.append(discord_id)
                continue
            
            # Get Discord member for display name
            member = self.ctx.guild.get_member(int(discord_id))
            display_name = member.display_name if member else faceit_username
            
            players.append({
                'discord_id': discord_id,
                'name': display_name,
                'faceit_username': faceit_username,
                'elo': elo
            })
        
        if failed_players:
            error_embed = discord.Embed(
                title="❌ Error Fetching ELOs",
                description=f"Failed to get ELO for some players. They may not have CS2 stats on FACEIT.",
                color=discord.Color.red()
            )
            failed_mentions = "\n".join([f"• <@{uid}>" for uid in failed_players])
            error_embed.add_field(name="Failed Players", value=failed_mentions)
            await self.message.edit(embed=error_embed)
            return
        
        # Balance teams
        team_a, team_b = balancer.balance_teams(players)
        
        # Create team view with swap functionality
        team_view = TeamSwapView(team_a, team_b, self.ctx)
        team_embed = team_view.create_teams_embed()
        
        await self.message.edit(embed=team_embed, view=team_view)
        self.teams_created = True
        self.stop()


class TeamSwapView(discord.ui.View):
    """Interactive view for swapping players between teams."""
    
    def __init__(self, team_a: List[Dict], team_b: List[Dict], ctx):
        super().__init__(timeout=600)  # 10 minute timeout
        self.team_a = team_a
        self.team_b = team_b
        self.ctx = ctx
        self.message = None
        
        # Add select menus
        self.team_a_select = TeamSelect(team_a, "Team A", "team_a")
        self.team_b_select = TeamSelect(team_b, "Team B", "team_b")
        
        self.add_item(self.team_a_select)
        self.add_item(self.team_b_select)
    
    def create_teams_embed(self) -> discord.Embed:
        """Create embed showing balanced teams."""
        embed = discord.Embed(
            title="⚖️ Balanced Teams",
            description="Teams have been created! Use the dropdowns below to swap players if needed.",
            color=discord.Color.green()
        )
        
        # Team A
        team_a_stats = balancer.calculate_team_stats(self.team_a)
        team_a_players = "\n".join([
            f"{i+1}. **{p['name']}** - {p['elo']} ELO" 
            for i, p in enumerate(self.team_a)
        ])
        embed.add_field(
            name=f"🔵 Team A (Avg: {team_a_stats['average_elo']} ELO)",
            value=team_a_players,
            inline=True
        )
        
        # Team B
        team_b_stats = balancer.calculate_team_stats(self.team_b)
        team_b_players = "\n".join([
            f"{i+1}. **{p['name']}** - {p['elo']} ELO" 
            for i, p in enumerate(self.team_b)
        ])
        embed.add_field(
            name=f"🔴 Team B (Avg: {team_b_stats['average_elo']} ELO)",
            value=team_b_players,
            inline=True
        )
        
        # Stats
        elo_diff = abs(team_a_stats['total_elo'] - team_b_stats['total_elo'])
        embed.add_field(
            name="📊 Balance",
            value=f"ELO Difference: **{elo_diff}**",
            inline=False
        )
        
        return embed
    
    @discord.ui.button(label="Swap Selected Players", style=discord.ButtonStyle.primary, emoji="🔄")
    async def swap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Swap the selected players between teams."""
        player_a_id = self.team_a_select.values[0] if self.team_a_select.values else None
        player_b_id = self.team_b_select.values[0] if self.team_b_select.values else None
        
        if not player_a_id or not player_b_id:
            await interaction.response.send_message(
                "❌ Please select one player from each team!",
                ephemeral=True
            )
            return
        
        try:
            self.team_a, self.team_b = balancer.swap_players(
                self.team_a, self.team_b, player_a_id, player_b_id
            )
            
            # Update select menus
            self.team_a_select.update_options(self.team_a)
            self.team_b_select.update_options(self.team_b)
            
            # Update embed
            embed = self.create_teams_embed()
            await interaction.response.edit_message(embed=embed, view=self)
            
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @discord.ui.button(label="Rebalance", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def rebalance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Re-randomize the teams."""
        all_players = self.team_a + self.team_b
        self.team_a, self.team_b = balancer.balance_teams(all_players)
        
        # Update select menus
        self.team_a_select.update_options(self.team_a)
        self.team_b_select.update_options(self.team_b)
        
        embed = self.create_teams_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Finalize Teams", style=discord.ButtonStyle.success, emoji="✅")
    async def finalize_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finalize the teams."""
        embed = self.create_teams_embed()
        embed.title = "✅ Teams Finalized!"
        embed.description = "Good luck and have fun!"
        embed.color = discord.Color.gold()
        
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class TeamSelect(discord.ui.Select):
    """Select menu for choosing a player from a team."""
    
    def __init__(self, team: List[Dict], team_name: str, custom_id: str):
        self.team_data = team
        options = [
            discord.SelectOption(
                label=f"{player['name']} ({player['elo']} ELO)",
                value=player['discord_id'],
                description=f"FACEIT: {player['faceit_username']}"
            )
            for player in team
        ]
        
        super().__init__(
            placeholder=f"Select player from {team_name}",
            options=options,
            custom_id=custom_id
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle selection."""
        await interaction.response.defer()
    
    def update_options(self, team: List[Dict]):
        """Update the select menu options with new team data."""
        self.team_data = team
        self.options = [
            discord.SelectOption(
                label=f"{player['name']} ({player['elo']} ELO)",
                value=player['discord_id'],
                description=f"FACEIT: {player['faceit_username']}"
            )
            for player in team
        ]


@bot.event
async def on_ready():
    """Called when bot is ready."""
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guild(s)')
    
    # Load active sessions and cleanup expired ones
    load_active_sessions()
    cleanup_expired_sessions()
    
    # Proactively replace old sessions with new ones
    await replace_old_sessions()
    
    # Sync commands
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')


@bot.event
async def on_interaction_error(interaction: discord.Interaction, error: Exception):
    """Handle interaction errors globally."""
    logger.error(f"Interaction error: {error}")
    
    # Check if it's an interaction timeout/expired error
    if "interaction" in str(error).lower() and ("failed" in str(error).lower() or "expired" in str(error).lower()):
        try:
            # Try to auto-recover the session
            guild_id = interaction.guild.id
            channel_id = interaction.channel.id
            
            # Find the most recent session for this channel
            recent_session = None
            for session_id, session_data in active_sessions.items():
                if (session_data.get('guild_id') == guild_id and 
                    session_data.get('channel_id') == channel_id):
                    if not recent_session or session_data.get('created_at', 0) > recent_session.get('created_at', 0):
                        recent_session = session_data
            
            if recent_session:
                embed = discord.Embed(
                    title="🔄 Session Recovered",
                    description="This session was restored after a bot restart. The buttons below are now functional!",
                    color=discord.Color.green()
                )
                
                participants = recent_session.get('participants', [])
                embed.add_field(
                    name=f"Participants ({len(participants)}/{Config.REQUIRED_PLAYERS})",
                    value="\n".join([f"<@{p}>" for p in participants]) if participants else "*No participants*",
                    inline=False
                )
                
                if recent_session.get('teams_created'):
                    embed.add_field(
                        name="Status",
                        value="✅ Teams have been created",
                        inline=False
                    )
                
                # Create new view with restored session
                new_view = BalanceSessionView(interaction, f"{guild_id}_{channel_id}_{int(time.time())}")
                new_view.participants = set(participants)
                new_view.teams_created = recent_session.get('teams_created', False)
                new_view.team_a = recent_session.get('team_a', [])
                new_view.team_b = recent_session.get('team_b', [])
                new_view.save_session()
                
                await interaction.followup.send(embed=embed, view=new_view)
                logger.info(f"Auto-recovered session for user {interaction.user.name} via error handler")
            else:
                await interaction.followup.send(
                    "⏰ **Session Expired**\n\nThis balancing session has expired. Please start a new session with `/balance`, `/start`, or `/mix`.",
                    ephemeral=True
                )
        except Exception as recovery_error:
            logger.error(f"Error in global recovery: {recovery_error}")
            try:
                await interaction.followup.send(
                    "⏰ **Session Expired**\n\nThis balancing session has expired. Please start a new session with `/balance`, `/start`, or `/mix`.",
                    ephemeral=True
                )
            except:
                pass


@bot.tree.command(name="profile", description="Link your Discord account to your FACEIT account")
@app_commands.describe(faceit_input="Username or URL")
async def profile(interaction: discord.Interaction, faceit_input: str):
    """Link Discord account to FACEIT username or URL."""
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    
    # Extract username from input (handles both usernames and URLs)
    faceit_username = extract_faceit_username(faceit_input)
    
    # Verify FACEIT account exists
    if not faceit.verify_player_exists(faceit_username):
        await interaction.followup.send(
            f"❌ FACEIT account '{faceit_username}' not found. Please check the username/URL and try again.",
            ephemeral=True
        )
        return
    
    # Check if player has CS2 stats
    stats = faceit.get_player_stats(faceit_username)
    if not stats or not stats.get('has_cs2'):
        await interaction.followup.send(
            f"⚠️ FACEIT account '{faceit_username}' found, but no CS2 stats detected. "
            "Make sure you have played CS2 on FACEIT before linking.",
            ephemeral=True
        )
        return
    
    # Link the account
    db.link_user(str(interaction.user.id), faceit_username)
    logger.info(f"User {interaction.user.name} ({interaction.user.id}) linked FACEIT account: {faceit_username} (ELO: {stats['elo']}, Level: {stats['level']})")
    
    embed = discord.Embed(
        title="✅ Account Linked!",
        description=f"Successfully linked to FACEIT account: **{faceit_username}**",
        color=discord.Color.green()
    )
    embed.add_field(name="Current ELO", value=f"{stats['elo']} ELO", inline=True)
    embed.add_field(name="Level", value=f"Level {stats['level']}", inline=True)
    
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="unlink", description="Unlink your FACEIT account")
async def unlink(interaction: discord.Interaction):
    """Unlink FACEIT account."""
    if db.unlink_user(str(interaction.user.id)):
        logger.info(f"User {interaction.user.name} ({interaction.user.id}) unlinked their FACEIT account")
        await interaction.response.send_message(
            "✅ Your FACEIT account has been unlinked.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "❌ You don't have a linked FACEIT account.",
            ephemeral=True
        )


@bot.tree.command(name="myelo", description="Check your current FACEIT ELO")
async def myelo(interaction: discord.Interaction):
    """Check current FACEIT ELO."""
    await interaction.response.defer(ephemeral=True)
    
    faceit_username = db.get_faceit_username(str(interaction.user.id))
    
    if not faceit_username:
        await interaction.followup.send(
            "❌ You haven't linked your FACEIT account yet! Use `/profile <faceit_username>`",
            ephemeral=True
        )
        return
    
    stats = faceit.get_player_stats(faceit_username)
    
    if not stats or not stats.get('has_cs2'):
        await interaction.followup.send(
            "❌ Could not fetch your CS2 stats. Make sure you have CS2 games on FACEIT.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"📊 {faceit_username}'s Stats",
        color=discord.Color.blue()
    )
    embed.add_field(name="Current ELO", value=f"{stats['elo']} ELO", inline=True)
    embed.add_field(name="Level", value=f"Level {stats['level']}", inline=True)
    
    if stats.get('avatar'):
        embed.set_thumbnail(url=stats['avatar'])
    
    await interaction.followup.send(embed=embed, ephemeral=True)


async def start_balance_session(interaction: discord.Interaction):
    """Start team balancing session."""
    logger.info(f"User {interaction.user.name} ({interaction.user.id}) started a new balancing session")
    view = BalanceSessionView(interaction)
    
    embed = discord.Embed(
        title="🎮 CS2 Team Balancing Session",
        description=f"Click **Join Session** to participate!\nWe need exactly **{Config.REQUIRED_PLAYERS}** players.",
        color=discord.Color.orange()
    )
    embed.add_field(
        name=f"Participants (0/{Config.REQUIRED_PLAYERS})",
        value="*No one has joined yet...*",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed, view=view)
    view.message = await interaction.original_response()


@bot.tree.command(name="balance", description="Start a team balancing session")
async def balance(interaction: discord.Interaction):
    """Start team balancing session."""
    await start_balance_session(interaction)


@bot.tree.command(name="start", description="Start a team balancing session")
async def start(interaction: discord.Interaction):
    """Start team balancing session."""
    await start_balance_session(interaction)


@bot.tree.command(name="mix", description="Mix and balance teams")
async def mix(interaction: discord.Interaction):
    """Mix and balance teams."""
    await start_balance_session(interaction)


@bot.tree.command(name="recover", description="Recover active sessions after bot restart")
async def recover(interaction: discord.Interaction):
    """Recover active sessions after bot restart."""
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    
    # Find sessions for this guild/channel
    recovered_sessions = []
    for session_id, session_data in active_sessions.items():
        if (session_data.get('guild_id') == interaction.guild.id and 
            session_data.get('channel_id') == interaction.channel.id):
            recovered_sessions.append((session_id, session_data))
    
    if not recovered_sessions:
        await interaction.followup.send(
            "ℹ️ No active sessions found for this channel.",
            ephemeral=True
        )
        return
    
    # Create recovery message for the most recent session
    latest_session_id, session_data = max(recovered_sessions, key=lambda x: x[1].get('created_at', 0))
    
    embed = discord.Embed(
        title="🔄 Session Recovered",
        description="This session was restored after a bot restart. The buttons below are now functional!",
        color=discord.Color.green()
    )
    
    participants = session_data.get('participants', [])
    embed.add_field(
        name=f"Participants ({len(participants)}/{Config.REQUIRED_PLAYERS})",
        value="\n".join([f"<@{p}>" for p in participants]) if participants else "*No participants*",
        inline=False
    )
    
    if session_data.get('teams_created'):
        embed.add_field(
            name="Status",
            value="✅ Teams have been created",
            inline=False
        )
    
    # Create new view with restored session
    new_session_id = f"{interaction.guild.id}_{interaction.channel.id}_{int(time.time())}"
    
    # Create a mock context for the view
    class MockContext:
        def __init__(self, guild, channel):
            self.guild = guild
            self.channel = channel
    
    mock_ctx = MockContext(interaction.guild, interaction.channel)
    view = BalanceSessionView(mock_ctx, new_session_id)
    view.participants = set(participants)
    view.teams_created = session_data.get('teams_created', False)
    view.team_a = session_data.get('team_a', [])
    view.team_b = session_data.get('team_b', [])
    view.save_session()
    
    view.message = await interaction.followup.send(embed=embed, view=view)
    
    # Remove the old session
    if latest_session_id in active_sessions:
        del active_sessions[latest_session_id]
        save_active_sessions()
    
    logger.info(f"Recovered session {latest_session_id} for user {interaction.user.name}")


@bot.tree.command(name="clear_sessions", description="Clear all active sessions (admin only)")
async def clear_sessions(interaction: discord.Interaction):
    """Clear all active sessions."""
    # Check if user has admin permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You need administrator permissions to use this command.",
            ephemeral=True
        )
        return
    
    global active_sessions
    session_count = len(active_sessions)
    active_sessions.clear()
    save_active_sessions()
    
    await interaction.response.send_message(
        f"✅ Cleared {session_count} active sessions.",
        ephemeral=True
    )
    logger.info(f"User {interaction.user.name} cleared all {session_count} active sessions")


@bot.tree.command(name="help", description="Show bot commands and usage")
async def help_command(interaction: discord.Interaction):
    """Show help information."""
    embed = discord.Embed(
        title="🤖 FACEIT Team Balancer Bot",
        description="Balance CS2 teams based on FACEIT ELO for fair matches!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="/profile <faceit_username_or_url>",
        value="Link your Discord account to your FACEIT account (username or profile URL)",
        inline=False
    )
    embed.add_field(
        name="/unlink",
        value="Unlink your FACEIT account",
        inline=False
    )
    embed.add_field(
        name="/myelo",
        value="Check your current FACEIT ELO",
        inline=False
    )
    embed.add_field(
        name="/balance, /start, /mix",
        value="Start a team balancing session (needs 10 players)",
        inline=False
    )
    embed.add_field(
        name="/recover",
        value="Recover active sessions after bot restart",
        inline=False
    )
    
    embed.set_footer(text="Made for fair LAN party matches!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


def main():
    """Run the bot."""
    try:
        bot.run(Config.DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"Error running bot: {e}")


if __name__ == "__main__":
    main()

