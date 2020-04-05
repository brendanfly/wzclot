from django.test import TestCase
from wlct.tests.data import PlayerDataHelper, TournamentDataHelper
from wlct.tournaments import TournamentType
from django.test import Client

# Create your tests here.
class DisplayViewTestCases(TestCase):
    def setUp(self):
        # populate a list of players and open tournaments and make sure those tournaments come back in the view appropriately
        pdata_helper = PlayerDataHelper(num_players=10).populate()
        tdata_helper = TournamentDataHelper(type=TournamentType.swiss, num_tournaments=4).populate()

        self.client = Client()

    def test_index_view(self):
        # do not populate the session yet, let's test without being logged in
        response = self.client.get('/index/')