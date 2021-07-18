from django.test import TestCase
from wlct.tests.data import PlayerDataHelper, TournamentDataHelper
from wlct.tournaments import TournamentType
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
    def setUp(self):
        # CL tests will use 6 clans... 2 1v1s, 1 2v2, 1 3v3 (7 players from each clan)
        print("running test setup for CL")
        tdata_helper = TournamentDataHelper(type=TournamentType.clan_league, cl_templates='2.1.1', num_clans=4).populate()
        self.tdata_helper = tdata_helper
        print("after tdata")

    def test_league_is_created(self):
        self.assertIsNotNone(self.tdata_helper.tournament_id)
        self.assertTrue(len(self.tdata_helper.created_clans) == 4)
