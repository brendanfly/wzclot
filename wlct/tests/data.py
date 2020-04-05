from wlct.tournaments import *
from wlct.models import Clan, Player
import random, string

# This class handles pre-populating players in the test database
class PlayerDataHelper:
    def __init__(self, **kwargs):
        if 'num_players'in kwargs:
            self.num_players = int(kwargs['num_players'])

    def populate(self):
        tokens = []
        for i in range(0, self.num_players):
            # create a random player, use the iterator as the token and <Player i> as the player's name
            random_string = self.generate_random_token()
            while random_string in tokens:
                random_string = self.generate_random_token()
            name = "Player {}".format(random_string)
            Player.objects.create(token=random_string, name=name)
            tokens.append(random_string)

    def generate_random_token(self):
        return ''.join(random.choice(string.ascii_letters + string.digits) for x in range(6))

    def create_single_player(self):
        random_token = self.generate_random_token()
        player = Player.objects.filter(token=random_token)
        while player:
            random_token = self.generate_random_token()
            player = Player.objects.filter(token=random_token)
        player = Player(token=random_token, name="Player {}".format(random_token))
        player.save()
        return player

class TournamentDataHelper:
    def __init__(self, **kwargs):

        self.num_tournaments = 1
        if 'num_tournaments' in kwargs:
            self.num_tournaments = int(kwargs['num_tournaments'])

        self.num_players = 4
        if 'num_players' in kwargs:
            self.num_players = int(kwargs['num_players'])

        self.type = "Invalid Tournament Type"
        if 'type' in kwargs:
            self.type = kwargs['type']

    def populate(self):
        for i in range(0, self.num_tournaments):
            name = "{} Tournament {}".format(self.type, i)
            description = "{} Tournament Description".format(self.type)

            # need a tournament creator
            creator = Tournament
            if self.type == TournamentType.swiss:
                tournament = SwissTournament(name=name, description=description, created_by=PlayerDataHelper().create_single_player())
                tournament.save()

                for j in range(0, self.num_players):
                    # first check if there are enough already populated
                    players = Player.objects.all()
                    if players.count() < self.num_players:
                        raise Exception("Not enough players populated to add to tournament!")

                    # need a team first
                    team = TournamentTeam(tournament=tournament)
                    team.save()

                    # create a tournament player, and then a team and add that team to the tournament
                    TournamentPlayer.objects.create(tournament=tournament, player=players[i], team=team)

