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