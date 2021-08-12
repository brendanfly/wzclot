from django.test import TestCase
from wlct.tests.data import PlayerDataHelper, TournamentDataHelper, get_current_day_str
from wlct.tournaments import TournamentType, ClanLeague, ClanLeagueDivision, ClanLeagueTournament, ClanLeagueTemplate, TournamentGame
from django.test import Client, override_settings
from wlct.management.commands import engine

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

    @override_settings(DEBUG=True)
    def test_clan_league_process_new_games(self):
        # Check to ensure that tournament was created
        self.assertIsNotNone(self.tdata_helper.tournament_id)
        self.assertTrue(len(self.tdata_helper.created_clans) == 4)

        # Start CL... Prepare to load templates with players
        cl = ClanLeague.objects.get(id=self.tdata_helper.tournament_id)
        cl.start("")
        self.assertTrue(cl.has_started)

        # Load players to each template
        self.tdata_helper.load_players_to_cl_templates()
        num_of_tournaments = ClanLeagueTournament.objects.filter(parent_tournament=cl).count()
        self.assertTrue(num_of_tournaments == self.num_templates)

        # Start each template (first round will be made)
        templates = ClanLeagueTemplate.objects.filter(league=cl)
        for template in templates:
            cl.start_template(template.id)

        tournaments = ClanLeagueTournament.objects.filter(parent_tournament=cl)
        rounds_to_process = 1
        for tournament in tournaments:
            self.assertTrue(tournament.has_started)

            # Update tournaments to start games now
            cur_date = get_current_day_str()
            rounds_count = len(tournament.games_start_times.split(";"))
            rounds_to_process = rounds_count + 1
            tournament.games_start_times = ";".join([cur_date] * rounds_count)
            tournament.save()

        # Create & finish all rounds
        for i in range(rounds_to_process):
            for tournament in tournaments:
                tournament.process_new_games()
                tournament.process_all_games()

        # Confirm all games have been completed
        for tournament in tournaments:
            game_count = TournamentGame.objects.filter(tournament=tournament, is_finished=True).count()
            self.assertTrue(game_count == 6)
            print("Total games: {}".format(game_count))