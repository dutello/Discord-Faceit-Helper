# Discord FACEIT Team Balancer Bot

A Discord bot that automatically balances CS2 teams for LAN parties based on live FACEIT ELO ratings. Perfect for organizing fair 5v5 matches with your friends!

## Features

- 🎮 **Automatic Team Balancing**: Distributes 10 players into two balanced teams based on current FACEIT ELO
- 🔄 **Interactive Swapping**: Use dropdown menus to manually swap players between teams
- 📊 **Live ELO Fetching**: Always uses the most current FACEIT stats
- 🎲 **Re-randomization**: Don't like the teams? Rebalance with one click
- 💾 **Account Linking**: Link your Discord account to your FACEIT profile once and you're set
- ✨ **Modern UI**: Beautiful embeds and interactive buttons for a smooth experience

## Prerequisites

- Python 3.8 or higher
- A Discord Bot Token ([Create one here](https://discord.com/developers/applications))
- A FACEIT API Key ([Get one here](https://developers.faceit.com/))

## Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd discord-faceit-helper
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your tokens:
   ```
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   FACEIT_API_KEY=your_faceit_api_key_here
   ```

4. **Set up your Discord Bot**
   
   In the [Discord Developer Portal](https://discord.com/developers/applications):
   - Create a new application
   - Go to the "Bot" section and create a bot
   - Copy the bot token and add it to `.env`
   - Enable "Message Content Intent" and "Server Members Intent" under Privileged Gateway Intents
   - Go to OAuth2 → URL Generator
   - Select scopes: `bot` and `applications.commands`
   - Select bot permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
   - Use the generated URL to invite the bot to your server

5. **Get your FACEIT API Key**
   
   - Go to [FACEIT Developers](https://developers.faceit.com/)
   - Create an account or log in
   - Create a new **Server-Side** API key
   - Copy the key and add it to `.env`

## Usage

1. **Start the bot**
   ```bash
   python bot.py
   ```

2. **Link your FACEIT account**
   ```
   /profile <your_faceit_username_or_url>
   ```
   You can use either your FACEIT username or your full FACEIT profile URL.
   Everyone participating must link their FACEIT account first.

3. **Start a balancing session**
   ```
   /balance
   /start
   /mix
   ```
   Any of these commands creates an interactive session where players can join.

4. **Join the session**
   
   Click the "Join Session" button. Once 10 players have joined, click "Start Balancing".

5. **Adjust teams (optional)**
   
   Use the dropdown menus to select players from each team, then click "Swap Selected Players" to swap them. You can also click "Rebalance" to randomize again.

6. **Finalize and play!**
   
   Click "Finalize Teams" when you're happy with the balance.

## Commands

- `/profile <faceit_username_or_url>` - Link your Discord account to your FACEIT profile (username or URL)
- `/unlink` - Unlink your FACEIT account
- `/myelo` - Check your current FACEIT ELO
- `/balance`, `/start`, `/mix` - Start a team balancing session (requires 10 players)
- `/help` - Show all available commands

## How It Works

### Team Balancing Algorithm

The bot uses a greedy algorithm to balance teams:

1. Fetches current CS2/CS2 ELO for all 10 participants from FACEIT API
2. Sorts players by ELO in descending order
3. Assigns each player to the team with the lower current total ELO
4. This minimizes the absolute ELO difference between teams

The result is two teams with similar total ELO, ensuring fair and competitive matches!

### Data Storage

- User account links are stored in `users.json`
- The file is created automatically on first run
- All data is stored locally (no external database required)

## Troubleshooting

**Bot doesn't respond to commands:**
- Make sure you've enabled the required intents in the Discord Developer Portal
- Wait a few minutes after inviting the bot for slash commands to sync

**Can't link FACEIT account:**
- Verify your FACEIT username is correct (case-sensitive)
- Make sure you have played CS2 or CS2 on FACEIT (the bot needs stats to fetch)

**ELO fetch fails:**
- Ensure your FACEIT API key is valid and correctly added to `.env`
- Check that the player has CS2/CS2 games on their FACEIT profile

**Bot crashes on startup:**
- Verify all environment variables are set in `.env`
- Check that you have all dependencies installed (`pip install -r requirements.txt`)

## Contributing

Feel free to open issues or submit pull requests if you have suggestions or improvements!

## License

MIT License - feel free to use this for your LAN parties and modify as needed!

## Support

If you encounter any issues, please check the troubleshooting section or create an issue on GitHub.

---

**Have fun and enjoy fair matches!** 🎮

