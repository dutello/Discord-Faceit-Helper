"""Team balancing algorithm based on FACEIT ELO."""
from typing import List, Dict, Tuple

class TeamBalancer:
    """Handles team balancing based on player ELO ratings."""
    
    @staticmethod
    def balance_teams(players: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Balance players into two teams based on ELO.
        
        Uses a greedy algorithm that assigns each player to the team
        with the lower current total ELO, minimizing the difference.
        
        Args:
            players: List of player dictionaries with 'discord_id', 'name', and 'elo' keys
            
        Returns:
            Tuple of (team_a, team_b) where each is a list of player dictionaries
        """
        if len(players) != 10:
            raise ValueError(f"Expected 10 players, got {len(players)}")
        
        # Sort players by ELO in descending order
        sorted_players = sorted(players, key=lambda p: p['elo'], reverse=True)
        
        team_a = []
        team_b = []
        
        # Greedy assignment: always add to team with lower total ELO
        for player in sorted_players:
            team_a_total = sum(p['elo'] for p in team_a)
            team_b_total = sum(p['elo'] for p in team_b)
            
            # Also ensure we don't exceed team size
            if len(team_a) < 5 and (len(team_b) >= 5 or team_a_total <= team_b_total):
                team_a.append(player)
            else:
                team_b.append(player)
        
        return team_a, team_b
    
    @staticmethod
    def calculate_team_stats(team: List[Dict]) -> Dict:
        """Calculate statistics for a team.
        
        Args:
            team: List of player dictionaries with 'elo' key
            
        Returns:
            Dictionary with 'total_elo', 'average_elo', 'player_count'
        """
        if not team:
            return {'total_elo': 0, 'average_elo': 0, 'player_count': 0}
        
        total_elo = sum(p['elo'] for p in team)
        avg_elo = total_elo / len(team)
        
        return {
            'total_elo': total_elo,
            'average_elo': round(avg_elo, 1),
            'player_count': len(team)
        }
    
    @staticmethod
    def swap_players(team_a: List[Dict], team_b: List[Dict], 
                     player_a_id: str, player_b_id: str) -> Tuple[List[Dict], List[Dict]]:
        """Swap two players between teams.
        
        Args:
            team_a: First team
            team_b: Second team
            player_a_id: Discord ID of player from team_a
            player_b_id: Discord ID of player from team_b
            
        Returns:
            Tuple of updated (team_a, team_b)
        """
        # Find players in their respective teams
        player_a = None
        player_a_index = None
        for i, p in enumerate(team_a):
            if p['discord_id'] == player_a_id:
                player_a = p
                player_a_index = i
                break
        
        player_b = None
        player_b_index = None
        for i, p in enumerate(team_b):
            if p['discord_id'] == player_b_id:
                player_b = p
                player_b_index = i
                break
        
        if player_a is None or player_b is None:
            raise ValueError("One or both players not found in their teams")
        
        # Create new team lists with swapped players
        new_team_a = team_a.copy()
        new_team_b = team_b.copy()
        
        new_team_a[player_a_index] = player_b
        new_team_b[player_b_index] = player_a
        
        return new_team_a, new_team_b

