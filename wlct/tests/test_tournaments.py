from unittest.mock import patch

from django.test import TestCase

from wlct.api import API_TEST, TestResponse
from wlct.tests.data import PlayerDataHelper, TournamentDataHelper, get_current_day_str
from wlct.models import Player
from wlct.tournaments import TournamentType, ClanLeague, ClanLeagueDivision, ClanLeagueTournament, ClanLeagueTemplate, \
    TournamentGame, RealTimeLadder, TournamentTeam
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

class RealTimeLadderTests(TestCase):
    def setUp(self):
        self.pdata_helper = PlayerDataHelper(num_players=2).populate()
        self.tdata_helper = TournamentDataHelper(type=TournamentType.real_time_ladder, num_templates=4).populate()

    def api_validate_template_locked(self, token, templateid):
        response = TestResponse()
        response.response_dict['tokenIsValid'] = 'true'
        template_key = "template{}".format(templateid)
        response.response_dict[template_key] = {
            "result": "CannotUseTemplate",
            "reasonCode": "MultiAttackAndAttackByPercentageLocked"
        }
        return response

    @override_settings(DEBUG=True)
    @patch.object(API_TEST, 'api_validate_token_for_template', api_validate_template_locked)
    def test_real_time_ladder_ineligible_player(self):
        playerid = self.pdata_helper.created_players[0]
        player = Player.objects.get(id=playerid)
        self.assertIsNotNone(player)

        rtl = RealTimeLadder.objects.get(id=self.tdata_helper.tournament_id)

        # Triggers new TournamentTeam path
        self.assertRaises(RealTimeLadder.LockedTemplatesException, rtl.join_leave_player, player, True, True)
        # Triggers existing TournamentTeam path
        self.assertRaises(RealTimeLadder.LockedTemplatesException, rtl.join_leave_player, player, True, True)

        # No player should have joined
        self.assertFalse(TournamentTeam.objects.filter(active=True, tournament=rtl).exists())

    @override_settings(DEBUG=True)
    def test_real_time_ladder_eligible_player(self):
        rtl = RealTimeLadder.objects.get(id=self.tdata_helper.tournament_id)

        # Have both players join (successfully)
        for playerid in self.pdata_helper.created_players:
            player = Player.objects.get(id=playerid)
            self.assertEquals(rtl.join_leave_player(player, True, False), "Looks like you're new to the **{}**. Welcome, and best of luck!".format(rtl.name))

        # 2 players should have joined
        self.assertTrue(TournamentTeam.objects.filter(active=True, tournament=rtl).count() == 2)

        # Create new game
        rtl.process_new_games()
        self.assertTrue(TournamentGame.objects.filter(tournament=rtl).exists())

        for playerid in self.pdata_helper.created_players:
            player = Player.objects.get(id=playerid)
            # Test double leaving (successful on first attempt, unsuccessful on second
            self.assertEquals(rtl.join_leave_player(player, False, False), "You've left the ladder. Come back again soon.")
            self.assertEquals(rtl.join_leave_player(player, False, False), "You're currently not on the ladder.")

        # 0 players should be remaining
        self.assertFalse(TournamentTeam.objects.filter(active=True, tournament=rtl).exists())
