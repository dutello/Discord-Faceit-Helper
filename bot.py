"""Discord bot for FACEIT team balancing."""
import discord
import time
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Optional
import asyncio

from config import Config
from database import Database
from faceit_api import FaceitAPI
from team_balancer import TeamBalancer
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
    
    def __init__(self, ctx):
        super().__init__(timeout=1800)  # 30 minute timeout
        self.ctx = ctx
        self.participants = set()
        self.message = None
        self.teams_created = False
        self.session_start_time = time.time()
        
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
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
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
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
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
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
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
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏰ **Session Expired**\n\nThis balancing session has been running for too long and is no longer interactive. Please start a new session with `/balance`, `/start`, or `/mix`.",
                        ephemeral=True
                    )
                return
            
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
    
    # Sync commands
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')


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

