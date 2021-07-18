from wlct.tournaments import *
from wlct.models import Clan, Player
import random, string
from copy import deepcopy


def generate_random_token():
    return ''.join(random.choice(string.ascii_letters + string.digits) for x in range(6))

def generate_random_template():
    return ''.join(random.choice(string.digits) for x in range(6))


# This class handles pre-populating players in the test database
class PlayerDataHelper:
    def __init__(self, **kwargs):
        if 'num_players'in kwargs:
            self.num_players = int(kwargs['num_players'])
        if 'clan_id' in kwargs:
            self.clan_id = int(kwargs['clan_id'])
        self.created_players = []

    def populate(self):
        tokens = []
        for i in range(0, self.num_players):
            # create a random player, use the iterator as the token and <Player i> as the player's name
            random_string = generate_random_token()
            while random_string in tokens:
                print("creating new string for players")
                random_string = generate_random_token()
            name = "Player {}".format(random_string)
            if hasattr(self, 'clan_id'):
                clan = Clan.objects.get(id=self.clan_id)
                player = Player.objects.create(token=random_string, name=name, clan=clan)
            else:
                player = Player.objects.create(token=random_string, name=name)
            self.created_players.append(player.id)
            tokens.append(random_string)

        # Return self to allow chaining
        return self

    def copy_player_list(self):
        return self.created_players.copy()

    def create_single_player(self):
        random_token = generate_random_token()
        player = Player.objects.filter(token=random_token)
        while player:
            random_token = generate_random_token()
            player = Player.objects.filter(token=random_token)
        player = Player(token=random_token, name="Player {}".format(random_token))
        player.save()
        return player

class ClanDataHelper:
    def __init__(self, **kwargs):
        if 'num_clans' in kwargs:
            self.num_clans = int(kwargs['num_clans'])
        if 'num_players'in kwargs:
            self.num_players = int(kwargs['num_players'])
        self.created_clans = {}

    def populate(self):
        tokens = []
        for i in range(0, self.num_clans):
            # create a random player, use the iterator as the token and <Player i> as the player's name
            random_string = generate_random_token()
            while random_string in tokens:
                print("creating new string for clans")
                random_string = generate_random_token()
            name = "Clan {}".format(random_string)

            clan = Clan.objects.create(name=name)
            self.created_clans[clan.id] = PlayerDataHelper(num_players=self.num_players, clan_id=clan.id).populate().copy_player_list()

            tokens.append(random_string)

        # Return self to allow chaining
        return self

    def copy_clan_list(self):
        return deepcopy(self.created_clans)

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

        # CL tests - # of 1v1s, 2v2s, 3v3s
        self.cl_templates = '1.1.1'
        if 'cl_templates' in kwargs:
            self.cl_templates = kwargs['cl_templates']

        # CL tests - number of clans in a division
        self.num_clans = 2
        if 'num_clans'in kwargs:
            self.num_clans = int(kwargs['num_clans'])

        self.created_clans = {}
        self.tournament_id = 0
        print("after tdata ctor")


    def populate(self):
        for i in range(0, self.num_tournaments):
            name = "{} Tournament {}".format(self.type, i)
            description = "{} Tournament Description".format(self.type)

            # need a tournament creator
            creator = PlayerDataHelper().create_single_player()
            if self.type == TournamentType.swiss:
                tournament = SwissTournament(name=name, description=description, created_by=creator)
                self.tournament_id = tournament.id
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
            elif self.type == TournamentType.clan_league:
                cl = ClanLeague.objects.create(name=name, multi_day=True, teams_per_game=2, created_by=creator, players_per_team=0, number_players=0, max_players=0, template=0, template_settings="")
                self.tournament_id = cl.id
                cl_division = ClanLeagueDivision.objects.create(title="{} - Division".format(name), league=cl)

                [num_1v1s, num_2v2s, num_3v3s] = self.cl_templates.split('.')

                # Create clans & players
                self.created_clans = ClanDataHelper(num_clans=self.num_clans, num_players=int(num_1v1s) + int(num_2v2s) * 2 + int(num_3v3s) * 3).populate().copy_clan_list()

                # Create CL clans from the newly created clans
                for clan_id in self.created_clans.keys():
                    clan = Clan.objects.get(id=clan_id)
                    ClanLeagueDivisionClan.objects.create(clan=clan, division=cl_division)

                # Create templates for cl division
                unique_template_ids = []
                for i in range(int(num_1v1s)):
                    template_id = generate_random_template()
                    while template_id in unique_template_ids:
                        print("creating new string for 1v1s")
                        template_id = generate_random_template()
                    unique_template_ids.append(template_id)

                    ClanLeagueTemplate(templateid=int(template_id), league=cl, players_per_team=1, name="Template {} - 1v1".format(template_id))

                for i in range(int(num_2v2s)):
                    template_id = generate_random_template()
                    while template_id in unique_template_ids:
                        print("creating new string for 2v2s")
                        template_id = generate_random_template()
                    unique_template_ids.append(template_id)

                    ClanLeagueTemplate(templateid=int(template_id), league=cl, players_per_team=2, name="Template {} - 2v2".format(template_id))

                for i in range(int(num_3v3s)):
                    template_id = generate_random_template()
                    while template_id in unique_template_ids:
                        print("creating new string for 3v3s")
                        template_id = generate_random_template()
                    unique_template_ids.append(template_id)

                    ClanLeagueTemplate(templateid=int(template_id), league=cl, players_per_team=3, name="Template {} - 3v3".format(template_id))

        # Return self to allow chaining
        print("after tdata populate")
        return self

    # Pre: CL has been started (divisions/templates added)
    # Post: Players will be added to each division/template
    def load_players_to_cl_templates(self):
        if self.type == TournamentType.clan_league:
            cl = ClanLeague.objects.get(id=self.tournament_id)
            if self.tournament_id == 0 or not cl or not cl.has_started:
                raise Exception("Tournament does not exist or was not started")

            divisions = ClanLeagueDivision.objects.filter(league=cl)
            templates = ClanLeagueTemplate.objects.filter(league=cl)

            for division in divisions:

                # Keep track of index of players used... Use unique player on each slot
                player_idx = 0
                clans_in_div = ClanLeagueDivisionClan.objects.filter(division=division)
                for template in templates:
                    # create a tournament here
                    tournament_name = "{} - {}".format(division.title, template.name)
                    cl_tourney = ClanLeagueTournament(multi_day=True, division=division, created_by=cl.created_by,
                                                      template=template.templateid,
                                                      players_per_team=template.players_per_team,
                                                      max_players=clans_in_div.count() * template.players_per_team,
                                                      private=True, parent_tournament=self, name=tournament_name,
                                                      teams_per_game=2, clan_league_template=template)
                    cl_tourney.save()

                    # each tournament should already have teams able to be set up here (for round robin)
                    # create the empty teams in the the rr_tourney, size of teams in division as all teams will play the template
                    for clan in clans_in_div:
                        team = TournamentTeam(clan_league_clan=clan, clan_league_division=division,
                                              players=cl_tourney.players_per_team, tournament=self,
                                              round_robin_tournament=cl_tourney,
                                              max_games_at_once=clans_in_div.count())
                        team.save()

                        for i in range(0, cl_tourney.players_per_team):
                            player = Player.objects.get(id=self.created_clans[clan.id][player_idx+i])
                            tplayer = TournamentPlayer(player=player, tournament=self, team=team)
                            tplayer.save()
                    player_idx += template.players_per_team