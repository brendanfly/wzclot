from django.test import TestCase
from wlct.tests.data import PlayerDataHelper, TournamentDataHelper
from wlct.tournaments import TournamentType, ClanLeague, ClanLeagueDivision, ClanLeagueTournament, ClanLeagueTemplate
from django.test import Client

# Create your tests here.
class SwissTournamentTests(TestCase):
    def setUp(self):
        # populate a list of players and open tournaments and make sure those tournaments come back in the view appropriately
        pdata_helper = PlayerDataHelper(num_players=10).populate()
        tdata_helper = TournamentDataHelper(type=TournamentType.swiss, num_tournaments=4).populate()

        self.client = Client()

    def test_swiss_process_new_games(self):
        self.assertTrue(True)


class ClanLeagueTests(TestCase):
    num_templates = 4

    def setUp(self):
        # CL tests will use 6 clans... 2 1v1s, 1 2v2, 1 3v3 (7 players from each clan)
        tdata_helper = TournamentDataHelper(type=TournamentType.clan_league, cl_templates='2.1.1', num_clans=4).populate()
        self.tdata_helper = tdata_helper

    def test_clan_league_process_new_games(self):
        # Check to ensure that tournament was created
        self.assertIsNotNone(self.tdata_helper.tournament_id)
        self.assertTrue(len(self.tdata_helper.created_clans) == 4)

        # Start tournament
        cl = ClanLeague.objects.get(id=self.tdata_helper.tournament_id)
        cl.start("")
        self.assertTrue(cl.has_started)

        # Load players to each template... Bypasses start function
        self.tdata_helper.load_players_to_cl_templates()

        num_of_tournaments = ClanLeagueTournament.objects.filter(parent_tournament=cl).count()
        self.assertTrue(num_of_tournaments == self.num_templates)
