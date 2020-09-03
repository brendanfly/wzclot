# the main classes for the tournaments
# they all effectively implement a Tournament in the models file
from django.db import models
from django.contrib import admin
import datetime
from dateutil import tz
from wlct.logging import log_exception, log, LogLevel, log_tournament, log_game, log_game_status, ProcessGameLog, ProcessNewGamesLog
from wlct.models import Player, Clan
from django.conf import settings
import random
from random import shuffle
from wlct.api import API
from collections import defaultdict
import json
import math
import itertools
from copy import copy
import pickle
from dateutil.relativedelta import relativedelta as rd
from django.utils import timezone
import pytz
from django.core.exceptions import ObjectDoesNotExist
import traceback
import urllib.request
from urllib.error import HTTPError
from wlct.cogs.common import embed_list_special_delimiter
from wlct.clotbook import get_clotbook

def is_player_allowed_join_by_token(token, templateid):
    allowed_join = False
    api = API()
    apirequest = api.api_validate_token_for_template(token, templateid)
    try:
        apirequestJson = apirequest.json()
    except:
        log("IsPlayerAllowedJoinByToken EXCEPTION: {}, {}, {}, {}".format(token, templateid, apirequest.text,
                                                                apirequest.status_code), LogLevel.critical)
        return False

    if "tokenIsValid" not in apirequestJson:
        log("Invalid token in is_player_allowed_join token: {}".format(token), LogLevel.informational)
        return False

    # now we need to look at the template status here, the key is templateXXXXXX
    template_key = "template{}".format(templateid)

    if template_key in apirequestJson:
        # do we have access?
        if 'result' in apirequestJson[template_key]:
            result = apirequestJson[template_key]['result']
            allowed_join = result == "CanUseTemplate"

    return allowed_join

def is_player_allowed_join(request_player, templateid):
    # get the api to check to see if we can display join buttons
    if not request_player:
        return False

    return is_player_allowed_join_by_token(request_player.token, templateid)

def get_current_month_year():
    tuple_return = (datetime.datetime.now().month, datetime.datetime.now().year)
    return tuple_return

def get_current_day_month_year():
    tuple_return = (datetime.datetime.now().day, datetime.datetime.now().month, datetime.datetime.now().year)
    return tuple_return

def get_team_by_id(tournament, id):
    team = TournamentTeam.objects.filter(tournament=tournament.id, pk=int(id))
    return team

def calculate_new_elo_rating(win, rating1, rating2):
    expected_elo = expected(rating1, rating2)
    print("Expected Elo with {} and {} is {}".format(rating1, rating2, expected_elo))
    if win:
        new_elo = elo(rating1, expected_elo, 1)
        print("[WIN]: Elo for {} is {}".format(rating1, new_elo))
        return new_elo
    else:
        new_elo = elo(rating1, expected_elo, 0)
        print("[LOSS]: Elo for {} is {}".format(rating1, new_elo))
        return new_elo


def expected(A, B):
    """
    Calculate expected score of A in a match against B
    :param A: Elo rating for player A
    :param B: Elo rating for player B
    """
    return 1 / (1 + 10 ** ((B - A) / 400))

def elo(old, exp, score, k=32):
    """
    Calculate the new Elo rating for a player
    :param old: The previous Elo rating
    :param exp: The expected score for this match
    :param score: The actual score for this match
    :param k: The k-factor for Elo (default: 32)
    """
    return old + k * (score - exp)

def get_round_title(round, total_rounds, use_round_num_only):
    if use_round_num_only:
        return "Round: {}".format(round)
    elif total_rounds - round == 0:
        return "Championship Round"
    elif total_rounds - round == 1:
        return "Semifinals"
    elif total_rounds - round == 2:
        return "Quarterfinals"
    else:
        return "Round: {}".format(round)

def get_seed_list(num_players):
    ol = [1]
    for i in range(math.ceil(math.log(num_players) / math.log(2) ) ):

        l = 2*len(ol) + 1
        ol = [e if e <= num_players else 0 for s in [[el, l-el] for el in ol] for e in s]
    return ol

def add_open_slot(team_index, player_index, players_per_team, allow_buttons, logged_in, in_tournament):
    table = ""
    if players_per_team > 1:
        table += '<tr><td>Open Slot {} &nbsp;'.format(player_index)
    else:
        table += '<tr><td>Open Slot {} &nbsp;'.format(team_index)

    if allow_buttons and logged_in and not in_tournament:
        table += '<button class ="btn btn-primary" name="slot" id="join{}-{}">Join Slot</button>'.format(team_index,
                                                                                                         player_index)
    elif not logged_in:
        table += 'You must be logged in to join tournaments'
    elif in_tournament and allow_buttons:
        table += '<button class ="btn btn-primary" name="slot" id="join{}-{}" disabled>Join Slot</button>'.format(
            team_index, player_index)
    else:
        table += 'You either do not meet the requirements for this template, the host has locked it for starting, or there is another issue. :)'

    table += '</td></tr>'

    return table

def get_team_data_no_clan(team):
    team_data = ""
    tournament_players = TournamentPlayer.objects.filter(team=team)
    for tournament_player in tournament_players:
        team_data += '{} '.format(tournament_player.player.name)
    return team_data

def get_team_data_no_clan_player_list(list):
    team_data = ""
    for player_token in list:
        players = Player.objects.filter(token=player_token)
        for player in players:
            team_data += '{} '.format(player.name)
    return team_data

def get_team_data_player_list(list):
    team_data = ""
    for player_token in list:
        player = Player.objects.filter(token=player_token)
        if player:
            player = player[0]
            team_data += get_player_data(player)
    return team_data

def get_matchup_data_player_list(players1, players2):
    data = '<table><tr><td>{}</td><td>{}</td></tr></table>'.format(get_team_data_player_list(players1), get_team_data_player_list(players2))
    return data

def get_matchup_data(team1, team2):
    data = '<table><tr><td>{}</td><td>{}</td></tr></table>'.format(get_team_data(team1), get_team_data(team2))
    return data

def get_team_data_impl(team, sameline):
    team_data = ""
    tournament_players = TournamentPlayer.objects.filter(team=team)
    for tournament_player in tournament_players:
        team_data += get_tournament_player_data(tournament_player)
        if not sameline:
            team_data += "<br/>"
    return team_data

def get_team_data_sameline(team):
    return get_team_data_impl(team, True)

def get_team_data(team):
    return get_team_data_impl(team, False)

def get_tournament_player_data(player):
    table = ''
    if player.player.clan is not None:
        table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
            player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

    table += '&nbsp;<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
        player.player.token, player.player.name)

    return table

def get_player_data(player):
    table = ''
    if player.clan is not None:
        table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
            player.clan.icon_link, player.clan.image_path, player.clan.name)

    table += '&nbsp;<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
        player.token, player.name)

    return table

def get_clan_data(clan):
    data = ''
    data += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>&nbsp;{}'.format(
        clan.icon_link, clan.image_path, clan.name, clan.name)

    return data

# used to determine for a given tournament how many games since team1 has played team2
# returns True if the teams have played in the last "games_since" games.
# the list is ordered by game finish date
def did_play_games_against_since_finished(team1, team2, tournament, games_since):
    games_played = TournamentGameEntry.objects.filter(team=team1, tournament=tournament).order_by('-game__game_finished_time')
    if games_played:
        current_game = 0
        for gameEntry in games_played:
            if gameEntry.team_opp == team2.id:
                # they've played in the game
                return True
            current_game += 1
            if current_game == games_since:
                break
    return False

def did_teams_play_in_round(teamid1, teamid2, round):
    game_played = TournamentGameEntry.objects.filter(team=teamid1, team_opp=teamid2, game__round=round)
    if game_played:
        return True
    return False

def did_play_games_against_since_created(teamid1, teamid2, num_games_since):
    games1 = TournamentGameEntry.objects.filter(team=teamid1, team_opp=teamid2).order_by('-created_date')[:num_games_since]
    if games1.count() > 0:
        # teams played each other in the last 3
        return True
    return False

def get_games_for_team(teamid, tournament):
    games_played = TournamentGameEntry.objects.filter(team=teamid, tournament=tournament)
    if games_played:
        return games_played.count()

    return 0

def get_games_unfinished_for_team(teamid, tournament):
    games_played = TournamentGameEntry.objects.filter(team=teamid, tournament=tournament, is_finished=False)
    if games_played:
        return games_played.count()

    return 0

def get_games_finished_for_team(teamid, tournament):
    games_played = TournamentGameEntry.objects.filter(team=teamid, tournament=tournament, is_finished=True)
    if games_played:
        return games_played.count()

    return 0

def get_games_against_since_hours(team1, team2, tournament, hours):
    nowdate = datetime.datetime.now(tz=pytz.UTC)
    enddate = nowdate - datetime.timedelta(hours=hours)
    games_finished_since = TournamentGameEntry.objects.filter(is_finished=True, team=team1, team_opp=team2, tournament=tournament,
                                                              created_date__gt=enddate)
    if games_finished_since:
        return games_finished_since.count()
    return 0


def get_games_finished_for_team_since(teamid, tournament, days):
    nowdate = datetime.datetime.now(tz=pytz.UTC)
    enddate = nowdate - datetime.timedelta(days=days)
    games_finished_since = TournamentGameEntry.objects.filter(is_finished=True, team=teamid, tournament=tournament, created_date__gt=enddate)
    if games_finished_since:
        return games_finished_since.count()

    return 0


def find_league_by_id(id):
    try:
        child_tourney = PromotionalRelegationLeagueSeason.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_league = PromotionalRelegationLeague.objects.filter(pk=id)
        if child_league:
            return child_league[0]

        child_league = MonthlyTemplateRotation.objects.filter(pk=id)
        if child_league:
            return child_league[0]

        child_league = ClanLeague.objects.filter(pk=id)
        if child_league:
            return child_league[0]

        child_league = RealTimeLadder.objects.filter(pk=id)
        if child_league:
            return child_league[0]

        child_league = MultiDayLadder.objects.filter(pk=id)
        if child_league:
            return child_league[0]

    except:
        # league wasn't found
        log_exception()
        log("League wasn't found: {}".format(id), LogLevel.informational)

def find_tournaments_by_division_id(id):
    try:
        division = ClanLeagueDivision.objects.filter(pk=id)
        if division:
            return ClanLeagueTournament.objects.filter(division=division[0])

    except:
        # tournament wasn't found
        log_exception()
        log("Tournament wasn't found: {}".format(id), LogLevel.informational)

    return []

def find_tournament_by_id(id, query_all=False):
    try:
        # try to get the tournament that has this id
        child_tourney = SwissTournament.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_tourney = SeededTournament.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_tourney = GroupStageTournament.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_tourney = ClanLeagueTournament.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_tourney = PromotionalRelegationLeagueTournament.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_tourney = RoundRobinRandomTeams.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        child_tourney = RoundRobinTournament.objects.filter(pk=id)
        if child_tourney:
            return child_tourney[0]

        if query_all:
            child_tourney = find_league_by_id(id)
            if child_tourney:
                return child_tourney
    except:
        # tournament wasn't found
        log_exception()
        log("Tournament wasn't found: {}".format(id), LogLevel.informational)

    return None


def find_tournament_public(id):
    try:
        # try to get the tournament that has this id
        child_tourney = SwissTournament.objects.filter(pk=id, private=False)
        if child_tourney:
            return child_tourney

        child_tourney = SeededTournament.objects.filter(pk=id, private=False)
        if child_tourney:
            return child_tourney

        child_tourney = GroupStageTournament.objects.filter(pk=id, private=False)
        if child_tourney:
            return child_tourney
    except:
        # tournament wasn't found
        log("Tournament wasn't found: {}".format(id), LogLevel.informational)

    return None


class Tournament(models.Model):
    name = models.CharField(max_length=128, null=True)
    description = models.CharField(max_length=2000, null=True, blank=True)
    number_players = models.IntegerField(default=-1)
    teams_per_game = models.IntegerField(default=-1)
    template = models.IntegerField(default=-1)
    created_by = models.ForeignKey('Player', on_delete=models.DO_NOTHING)
    created_date = models.DateTimeField(auto_now_add=True)
    number_rounds = models.IntegerField(default=-1)
    is_finished = models.BooleanField(default=False, db_index=True)
    has_started = models.BooleanField(default=False, db_index=True)
    players_per_team = models.IntegerField(default=1)
    private = models.BooleanField(default=False, db_index=True)
    start_option_when_full = models.BooleanField(default=True)
    host_sets_tourney = models.BooleanField(default=False)
    start_locked = models.BooleanField(default=False)  # used by tournament that are locked to join, but haven't started
    max_players = models.IntegerField(default=-1)
    template_settings = models.TextField(default="", null=True, blank=True)
    multi_day = models.BooleanField(default=False)
    winning_team = models.ForeignKey('TournamentTeam', on_delete=models.DO_NOTHING, null=True, related_name='winning_team', blank=True)
    update_in_progress = models.BooleanField(default=False)
    game_creation_allowed = models.BooleanField(default=True)
    is_league = models.BooleanField(default=False, blank=True, null=True)
    bracket_game_data = models.TextField(blank=True, null=True, default="")
    game_log = models.TextField(blank=True, null=True, default="")
    tournament_logs = models.TextField(blank=True, null=True, default="")
    is_official = models.BooleanField(default=False)
    vacation_force_interval = 20

    def is_player_allowed_join(self, player):
        return is_player_allowed_join(player, self.template)

    def get_full_public_link(self):
        if self.is_league:
            return "http://wzclot.eastus.cloudapp.azure.com/leagues/{}/".format(self.id)
        return "http://wzclot.eastus.cloudapp.azure.com/tournaments/{}/".format(self.id)

    def should_process_in_engine(self):
        return True

    def player_data_in_name(self):
        return False

    def get_max_games_at_once(self):
        return 6

    def should_show_max_games_option(self):
        return False

    def show_tournament_details(self):
        return False

    def has_force_vacation_interval(self):
        return False

    def update_game_creation_allowed(self, allowed):
        self.game_creation_allowed = allowed
        self.save()

    def get_game_log(self):
        if self.game_log == "":
            self.update_game_log()
        return self.game_log

    def cache_data(self):
        # cache the data here for fast reads on the page load for clients
        self.update_bracket_game_data()
        self.update_game_log()

    def get_pause_resume(self, player):
        if player and player.id == self.created_by.id:
            if self.game_creation_allowed:
                pause_resume = '<button type="button" class="btn btn-danger" name="pause" id="pause"><i class="fa fa-pause"></i>&nbsp;Pause {}</button>'.format(self.type)
            else:
                # resume case
                pause_resume = '<button type="button" class="btn btn-success" name="resume" id="resume"><i class="fa fa-play"></i>&nbsp;Resume {}</button>'.format(self.type)
            return pause_resume
        return ""

    @property
    def bracket_seeded_async(self):
        return False

    @property
    def winning_team_data(self):
        ret = ""
        players = TournamentPlayer.objects.filter(team=self.winning_team, tournament=self.id)
        if players:
            ret += "Winning Team: "
            for player in players:
                player = player.player
                if player.clan is not None:
                    ret += '&nbsp;<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                        player.clan.icon_link, player.clan.image_path, player.clan.name)

                ret += '&nbsp;<a href="/stats/{}" target="_blank">{}</a>'.format(
                    player.token, player.name)

        return ret

    def start(self):
        if self.has_started:
            # can't start twice, just log here so we can keep track of how often this happens
            log("Tournament ID {} Name {} already started, and trying to start again!".format(self.name, self.id), LogLevel.critical)
            return

        self.number_players = self.current_filled_teams * self.players_per_team

        self.has_started = True
        self.remove_partial_teams()
        self.save()

    def create_game_with_template_and_data(self, tournament_round, game, tid, extra_data):
        if not self.game_creation_allowed:
            log_tournament("Game creation is not allowed. Returning...", self)
            return  # don't actually create the games but allow the logging for each tournament to go through

        # create the game
        api = API()
        data = {}
        data['templateID'] = tid

        game_name = "{}".format(self.get_game_name())
        log_tournament("Game Name Created: {}".format(game_name), self)
        game_name = game_name[:50]
        data['gameName'] = game_name
        data['players'] = []

        if extra_data is not None:
            data.update({'settings': extra_data})

        teams = game.split('.')
        team_id = 1
        tournament_team_ids = []
        player_names = []
        ratings = []
        for team in teams:
            current_rating = 0
            teamid = int(team)
            tournament_team = TournamentTeam.objects.filter(pk=teamid)
            if tournament_team:
                team_player_ids = []
                tournament_team = tournament_team[0]
                tournament_players = TournamentPlayer.objects.filter(team=tournament_team)
                for tournament_player in tournament_players:
                    data['players'].append({"token": tournament_player.player.token, 'team': '{}'.format(team_id)})
                    team_player_ids.append(tournament_player.player.token)
                    current_rating += tournament_player.player.rating
                    if self.player_data_in_name():
                        player_names.append(tournament_player.player.name)
                        # append the player names to the game name
                tournament_team_ids.append(".".join(team_player_ids))
                tournament_team.process_games_since_created = 0
                tournament_team.save()
                current_rating = current_rating / tournament_players.count()
                ratings.append(current_rating)
            team_id += 1

        player_ids = "-".join(tournament_team_ids)
        print("Rating {} vs. {}".format(ratings[0], ratings[1]))
        if len(player_names) == 2:
            try:
                game_name += " {} vs. {}".format(player_names[0], player_names[1])
                game_name = game_name[:50]
                data['gameName'] = game_name
            except:
                log_exception()
        gameInfo = api.api_create_tournament_game(data)
        gameInfo = gameInfo.json()

        log_tournament("Game info created: {}".format(gameInfo), self)

        # the game has been posted, make sure we have a game id and then query the settings
        if 'gameID' in gameInfo:
            # great, query the settings
            gameID = gameInfo['gameID']

            game_link = 'https://www.warzone.com/MultiPlayer?GameID={}'.format(gameID)
            team_game = self.players_per_team > 1
            tournament_game = TournamentGame(game_link=game_link, gameid=gameID,
                                             players_per_team=self.players_per_team,
                                             team_game=team_game, tournament=self, round=tournament_round,
                                             teams=game, players=player_ids, templateid=tid)
            tournament_game.save_with_entry()
            log_game(
                "Game {} created in tournament {}. Teams: {}, gameID: {}, round: {}".format(gameID, self.id,
                                                                                            game, gameID,
                                                                                            tournament_round.round_number),
                self, tournament_game)

            # we need to create the initial lines for the match-up
            self.post_create_games()
            tournament_game.create_initial_lines_ratings(ratings[0], ratings[1])
            return tournament_game
        else:
            # not good, error, TODO: Log???
            print("Error in creating game: {}".format(gameInfo))
            log("Error in creating tournament game response {}:, data: {}".format(gameInfo, data), LogLevel.critical)
            return None

    def post_create_games(self):
        pass

    def create_game(self, tournament_round, game):
        self.create_game_with_template_and_data(tournament_round, game, self.template, None)

    def get_game_name(self):
        if self.name:
            return self.name
        else:
            return "WZClot Tournament Game"

    def get_invited_players_inverse_table(self, creator_token, request_data, viewer_token):
        # get all the players, and only add the players we care about (excluding invited players) to the html
        table = '<table class="table table-hover table-condensed compact stripe" id="invite-filter">'
        table += '<thead><tr><th>Player Name</th><th> </th></tr></thead><tbody id="invite-filter-table">'

        is_player_available = False
        players = Player.objects.all()
        # list of player names associated with the rows so that we can do easy filtering on the client
        # side
        for player in players:
            invite = TournamentInvite.objects.filter(tournament=self.id, player=player, joined=False)
            tournament_player = TournamentPlayer.objects.filter(tournament=self.id, player=player)
            if not invite and not tournament_player:
                is_player_available = True
                # player wasn't invited to this tournament
                # check if it's us, if it is, skip
                if player.token != viewer_token and player.token != creator_token:
                    clan_name = ""
                    if player.clan:
                        clan_name = '{}'.format(player.clan.name)
                    table += '<tr><td data-search="{} {}">'.format(clan_name, player.name)
                    if player.clan is not None:
                        table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                            player.clan.icon_link, player.clan.image_path, player.clan.name)

                    table += '<a href="/stats/{}" target="_blank"><span class="invite_name">{}</span></a>'.format(
                        player.token, player.name)
                    table += '</td>'
                    table += '<td><button class="btn btn-primary" name="slot" id="invite-{}">+</button></td>'.format(
                        player.token)
                    table += '</tr>'

        if not is_player_available:
            table += 'There are no players to invite.'

        table += '</tbody></table>'

        return table

    def get_invited_players_table(self):
        # get all the players, and only add the players we care about (excluding invited players) to the html
        table = '<p>A list of invited players will be displayed here</p>'
        invites = TournamentInvite.objects.filter(tournament=self.id, joined=False)
        current_player = 0
        if invites:
            table = '<table class="table table-hover">'
            for invite in invites:
                if current_player is 0:
                    table += '<tr>'
                if current_player is 4:
                    table += '</tr><tr>'
                    current_player = 0

                # player wasn't invited to this tournament
                # check if it's us, if it is, skip
                player = invite.player
                table += '<td>'
                if player.clan is not None:
                    table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                        player.clan.icon_link, player.clan.image_path, player.clan.name)

                table += '<a href="/stats/{}" target="_blank">{}</a>'.format(
                    player.token, player.name)

                # the player viewing the page is the one in this row, so we need to give the player the option to leave their slot
                table += '</td>'

                current_player += 1

            table += '</table>'
        return table


    def get_template_settings_dict(self):
        if self.template_settings is not None and len(self.template_settings) > 0:
            try:
                settings_dict = json.loads('''{}'''.format(self.template_settings))
                return settings_dict
            except Exception:
                log_tournament("Template error: {}".format(traceback.format_exc()), self)
        return None


    def get_template_settings_table(self):
        template_settings_table = ""
        try:
            template_settings_table += '<br/><div class="card gedf-card span12">'
            template_settings_table += '<div class="card-header h7">Template Settings</div>'
            template_settings_table += '<div class="card-body">'
            template_settings_table += '<div class="container">'
            template_settings_table += '<div class="row">'
            template_settings_table += '<table class="table table-hover" style="font:12px;">'
            settings_dict = self.get_template_settings_dict()
            if settings_dict is not None:
                for k, v in settings_dict.items():
                    template_settings_table += "<tr><td>{}</td>".format(k)
                    template_settings_table += "<td>{}</td></tr>".format(v)

            template_settings_table += '</table></div></div></div></div>'
        except Exception:
            log_exception()
            return ""

        return template_settings_table

    def handle_finish_game_with_info(self, game_info):
        pass

    # the button id's for this are as follows
    # join button id = "join{team id}-{team slot id}"
    # decline button id = "decline" as we can look up the slot and free up the space
    # by removing the record and reloading the team table
    def get_team_table(self, allow_buttons, logged_in, request_player):
        table = ''

        # a few overrides on the pass in values
        if self.has_started:
            allow_buttons = False  # hard override
        elif self.start_locked:
            allow_buttons = False  # hard override

        in_tournament = False
        tournament_player = TournamentPlayer.objects.filter(player=request_player, tournament=self.id)
        if tournament_player:
            in_tournament = True

        tournamentteams = TournamentTeam.objects.filter(tournament=self.id).order_by('-wins', 'team_index')
        if tournamentteams:
            table += '<table class="table table-hover">'
            team_indent = ''
            if self.has_started:
                if self.players_per_team > 1:
                    team_indent = 'style="margin-left:1em"'
                    table += '<tr><th>Team</th><th>Record</th></tr>'
                else:
                    table += '<tr><th>Player</th><th>Record</th></tr>'
            for team in tournamentteams:
                if self.players_per_team > 1:
                    table += "<tr><td><b>Team {} </b></td>".format(team.team_index)
                    if self.has_started:
                        table += "<td>{}-{}</td>".format(team.wins, team.losses)
                    else:
                        table += "<td></td>"
                    table += "</tr>"
                total_players = 0
                team_players = TournamentPlayer.objects.filter(team=team)
                if team_players:
                    for player in team_players:
                        table += '<tr><td>'
                        if player.player.clan is not None:
                            table += '<a href="https://warzone.com{}" target="_blank" {}><img src="{}" alt="{}" /></a>'.format(
                                player.player.clan.icon_link, team_indent, player.player.clan.image_path, player.player.clan.name)
                            table += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                                player.player.token, player.player.name)
                        else:
                            table += '<a href="/stats/{}" target="_blank" {}>{}</a>&nbsp;'.format(
                                player.player.token, team_indent, player.player.name)
                        if self.players_per_team == 1 and self.has_started:
                            table += "<td>{}-{}</td>".format(team.wins, team.losses)

                        if logged_in and player is not None and player.player.token == request_player.token and not self.has_started and not self.start_locked:
                            # the player viewing the page is the one in this row, so we need to give the player the option to leave their slot
                            if self.has_started:
                                table += '<td>'
                            table += '<button class="btn btn-primary" name="slot" id="decline">Leave Slot</button>'

                        table += '</tr>'

                        total_players += 1

                # if we get here, we need to add an open slot
                while total_players < self.players_per_team:
                    table += add_open_slot(team.team_index, total_players + 1, self.players_per_team, allow_buttons,
                                           logged_in, in_tournament)
                    total_players += 1

            table += "</table>"

        return table

    def is_player_on_vacation(self, player):
        api = API()
        apirequest = api.api_validate_invite_token(player.token)
        apirequestJson = apirequest.json()
        log("IsPlayerOnVacation: {}".format(apirequestJson), LogLevel.informational)
        if 'onVacationUntil' in apirequestJson:
            return True

        return False

    def is_team_on_vacation(self, team):
        players = TournamentPlayer.objects.filter(team=team)
        api = API()
        for player in players:
            apirequest = api.api_validate_invite_token(player.player.token)
            apirequestJson = apirequest.json()
            if 'onVacationUntil' in apirequestJson:
                return True

        return False

    def get_url(self):
        if self.is_league:
            return "/leagues/{}/".format(self.id)
        elif hasattr(self, "season_template"):
            return "/pr/season/{}/".format(self.id)
        return "/tournaments/{}/".format(self.id)

    def are_vacations_supported(self):
        settings_dict = self.get_template_settings_dict()
        if settings_dict is not None:
            log("TemplateSettings: {}".format(settings_dict), LogLevel.informational)
            if 'AllowVacations' in settings_dict and settings_dict['AllowVacations']:
                return True

        return False

    def process_game(self, game):
        try:
            processGameLog = ""
            processGameLog += "Process Game {} in tournament {}: ".format(game.id, self.name)
            teams = game.teams.split('.')
            test_content = TestContent()
            game_info = test_content.team_game(teams[0], teams[1])
            api = API()
            game_status = api.api_query_game_feed(game.gameid, game_info)
            if game_status is not None:
                game_status = game_status.json()
            else:
                processGameLog += "\nGame Status is None for tournament {}, game {}".format(self.id, game.id)

            if game_status:
                if 'map' in game_status:
                    del game_status['map']
                log_game_status("Checking game status for game {}: {} ".format(game.gameid, game_status), self, game)

            players_data = None
            # process the game here
            # first we need to look-up the winner and parse the player data
            if 'numberOfTurns' in game_status:
                number_of_turns = int(game_status['numberOfTurns'])
                if number_of_turns >= 0:
                    game.betting_open = False
                    game.save()
            if 'players' in game_status:
                players_data = game_status['players']
            if 'state' in game_status:
                game.current_state = game_status['state']
                game.save()

            if 'error' in game_status:
                processGameLog += "Error in getting the data for game {}: {} ".format(game.gameid, game_status['error'])
                if game_status['error'] == "Loading the game produced an error: ServerGameKeyNotFound":
                    # game was deleted, mark the game as completed and move on
                    game.finish_game_with_info(game_status)
                    game.game_link = "invalid_link"
                    game.save()
                # we return regardless
                return

            # calculate the difference in times from last turn time to now, and if more than the game turn time
            # let's force a loss
            teams_won = []
            teams_lost = []

            # put each player into a defaultdict(int) where the team id is the key
            # at the end, loop through all the players, and make sure the statuses match up
            # here's how we count games lost
            # any one of the team didn't join within the allotted time - loss, continue
            # any one of the team declined - loss, continue
            # if game is finished, then we will have 1 winner/1 loser
            # if every declines, we pick a random winner

            teams_in_game = []

            for i in range(0, 2):  # make sure we loop twice
                for player_data in players_data:
                    player = Player.objects.filter(token=player_data['id'])
                    if player:
                        tournament_player = TournamentPlayer.objects.filter(player=player[0], tournament=self.id)
                        player_to_use = None
                        if not tournament_player:
                            # we might have a parent tournament we belong to, check that next
                            if hasattr(self, 'parent_tournament'):
                                tournament_player = TournamentPlayer.objects.filter(player=player[0], tournament=self.parent_tournament)
                        if game.players or tournament_player:
                            if game.players:
                                # If players value exists in TournamentGame, use this to find any player on team
                                team_players_list = game.players.split("-")
                                for j in range(len(team_players_list)):
                                    if player_data.get("id") in team_players_list[j].split("."):
                                        processGameLog += "\nFound team this player is/was a part of, using first player found on team"
                                        player_to_use_team = TournamentTeam.objects.filter(id=teams[j])[0]
                                        player_to_use = TournamentPlayer.objects.filter(team=player_to_use_team)[0]
                                        break
                            elif tournament_player.count() > 1 or (tournament_player[0].team.round_robin_tournament is not None and tournament_player[0].team.round_robin_tournament.id is not self.id):
                                # in some cases, the tournament doing the games is parented, and for clan league there can be more than
                                # one time the same player comes up, in different tournaments. Work around that by looping through all players here
                                for tplayer in tournament_player:
                                    processGameLog += "\nTournaments this player is in: {}, team: {}, current player round robin: {}, current round robin processing: {}".format(
                                        tournament_player.count(), tplayer.team.id, self.id,
                                        tplayer.team.round_robin_tournament.id)
                                    if tplayer.team.round_robin_tournament.id == self.id:
                                        processGameLog += "\nFound round robin tournament this player is a part of, using that"
                                        player_to_use = tplayer
                                        break
                            else:
                                processGameLog += "\nThis player {} on team {} is either only in one tournament, or the parent tournament is the one we care about.".format(tournament_player[0].player.token, tournament_player[0].team.id)
                                player_to_use = tournament_player[0]

                            if player_to_use is None:
                                processGameLog += "\nCannot find player to use, continuing on"
                                continue

                            if player_to_use.team.id not in teams_in_game:
                                teams_in_game.append(player_to_use.team.id)

                            if "state" in game_status and game_status["state"] == 'Finished':
                                if player_data['state'] == 'Won':
                                    if player_to_use.team.id not in teams_won and len(teams_won) == 0:
                                        teams_won.append(player_to_use.team.id)
                                        processGameLog += "\nGame Finished, team {} won ".format(player_to_use.team.id)
                                else:
                                    if player_to_use.team.id not in teams_lost and len(teams_lost) == 0:
                                        teams_lost.append(player_to_use.team.id)
                                        processGameLog += "\nGame Finished, team {} lost ".format(player_to_use.team.id)

                                game.finish_game_with_info(game_status)
                                game.save()
                                # the tournament knows how to handle moving players from round to round, so call into that
                            elif "state" in game_status and game_status["state"] == 'WaitingForPlayers':
                                # special handling
                                # we need to calculate how long these players have been waiting, and if that's longer
                                # than the turn time, we give both players a loss and mark the game as finished
                                if player_data['state'] == 'Declined':
                                    if len(teams_lost) == 0:
                                        if player_to_use.team.id not in teams_lost:
                                            teams_lost.append(player_to_use.team.id)
                                            processGameLog += "\n{} declined game".format(player[0].name)
                                    else:
                                        if player_to_use.team.id not in teams_lost and len(teams_won) == 0:
                                            teams_won.append(player_to_use.team.id)
                                            processGameLog += "\nGame never started, but team {} won ".format(player_to_use.team.id)

                                    # regardless of who won/lost, delete the game, we still have the data in memory
                                    # so this is ok
                                    processGameLog += "\n{} failed to join (DECLINED), forcing loss and deleting game ".format(
                                        player[0].name)

                                    # delete the game
                                    if 'id' in game_status:
                                        delete_status = api.api_delete_game(game_status['id'])
                                    else:
                                        processGameLog += "\nGame Status did not contain the game id: {} ".format(game_status)

                                    game.finish_game_with_info(game_status)
                                    game.save()
                                elif player_data['state'] == 'Invited':
                                    # player is invited and hasn't joined, if we've been waiting too long we've lost
                                    last_turn_time = datetime.datetime.strptime(game_status['lastTurnTime'], '%m/%d/%Y %H:%M:%S')
                                    td = datetime.datetime.utcnow() - last_turn_time
                                    seconds_since_created = int(td.total_seconds())

                                    # grab the settings from this game, and convert the turn time to minutes
                                    settings = game_status['settings']
                                    turn_time_in_minutes = 0
                                    if 'AutoBoot' in settings or 'DirectBoot' in settings:
                                        if settings['AutoBoot'] is not None and settings['AutoBoot'] != 'none':
                                            turn_time_in_minutes = settings['AutoBoot']
                                        elif settings['DirectBoot'] is not None and settings['DirectBoot'] != 'none':
                                            turn_time_in_minutes = settings['DirectBoot']

                                    processGameLog += "{} invited to game ".format(player_to_use.player.name)


                                    boot_time = last_turn_time + datetime.timedelta(minutes=turn_time_in_minutes)
                                    game.game_boot_time = boot_time.replace(tzinfo=pytz.UTC)
                                    game.save()

                                    # Check if loser has been assigned first
                                    if len(teams_lost) and player_to_use.team.id not in teams_lost and len(teams_won) == 0:
                                        teams_won.append(player_to_use.team.id)
                                        processGameLog += "\nTeam {} won due to team {} already losing ".format(player_to_use.team.id, teams_lost[0])

                                    processGameLog += "\nSeconds since created: {}, turn time in minutes: {} ".format(
                                        seconds_since_created, turn_time_in_minutes)
                                    seconds_in_turn = int(float(turn_time_in_minutes)) * 60
                                    if seconds_since_created > seconds_in_turn:
                                        processGameLog += "\nGame has reached past the boot time...checking vacation status"
                                        # check for vacation status for any of the players on the team
                                        # and if they are on vacation, then do not give them the lost
                                        # mark this game as is_finished=False so it gets looked at again
                                        # and continue on
                                        player_on_vacation = self.is_player_on_vacation(player[0])
                                        processGameLog += "\nPlayer {} is on vacation: {}.".format(player[0].name, player_on_vacation)
                                        if player_on_vacation and self.are_vacations_supported():
                                            # continue on case, no result for the game yet
                                            # do we have an interval in which we force a loss (i.e. clan league is 10 days without joining)
                                            if self.has_force_vacation_interval():
                                                processGameLog += "\nForce Vacation Hard Interval: Team {} is on vacation due to player {} so the game should not start".format(player_to_use.team.id, player[0].name)
                                                seconds_since_created = int(td.total_seconds())
                                                seconds_to_wait = 60*60*24*self.vacation_force_interval
                                                if seconds_since_created < seconds_to_wait:  # # of days
                                                    processGameLog += "\nForce vacation interval is at {} seconds and we have until {} seconds".format(seconds_since_created, seconds_to_wait)
                                                    game.is_finished = False
                                                    game.save()
                                                    return
                                            else:
                                                game.is_finished = False
                                                game.save()
                                                return

                                        # no join/decline, so the team loses
                                        if len(teams_lost) == 0:
                                            if player_to_use.team.id not in teams_lost:
                                                teams_lost.append(player_to_use.team.id)
                                        else:
                                            # there is already a team that lost, so just give us the win
                                            if player_to_use.team.id not in teams_lost and len(teams_won) == 0:
                                                teams_won.append(player_to_use.team.id)

                                        processGameLog += "\n{} failed to join, forcing loss and deleting game ".format(player_to_use.player.name)
                                        game.finish_game_with_info(game_status)
                                        game.save()

                                        # delete the game
                                        if 'id' in game_status:
                                            api.api_delete_game(game_status['id'])
                                        else:
                                            processGameLog += "\nGame Status did not contain the game id: {} ".format(game_status)
                                else:
                                    # if any player in this team has joined, make sure no one else declined
                                    # there's an edge case where if you're the last player looked at but you've already lost
                                    # we add the winning team as the losing team below.
                                    if len(teams_lost) > 0 and len(teams_won) == 0:
                                        for team_id in teams_in_game:
                                            if team_id not in teams_lost:
                                                teams_won.append(team_id)
                                                processGameLog += "\nTeam {} won due to team {} already losing ".format(team_id, teams_lost[0])
                        else:
                            processGameLog += "\nCan't find player {} in tournament {} ".format(player_data['id'], self.id)
                    else:
                        processGameLog += "\nCouldn't find player {} ".format(player_data['id'])
            game.save()

            if not len(teams_won) and len(teams_lost):
                processGameLog += "\nPatching up teams won list, with team {} already lost.".format(teams_lost[0])
                for team_id in teams_in_game:
                    if team_id not in teams_lost:
                        processGameLog += "\nTeam {} not in teams_lost, adding to teams won".format(team_id)
                        teams_won.append(team_id)

            # now loop through the winners and losers and update their ratings accordingly
            for team in teams_won:
                tourney_team = TournamentTeam.objects.filter(pk=int(team))
                if tourney_team:
                    tourney_team = tourney_team[0]
                    game.winning_team = tourney_team
                    game.finish_game_with_info(game_status)
                    game.save()
                    processGameLog += "\nWinning team: {}, len(teams_won): {}".format(tourney_team.id, len(teams_won))
                    # there has to be a team that lost
                    if teams_lost[0] is not None:
                        tourney_team_lost = TournamentTeam.objects.filter(pk=int(teams_lost[0]))
                        if tourney_team_lost:
                            tourney_team_lost = tourney_team_lost[0]
                            current_win_rating = tourney_team.rating
                            tourney_team.rating = calculate_new_elo_rating(True, tourney_team.rating, tourney_team_lost.rating)
                            tourney_team.wins += 1
                            tourney_team.buchholz += tourney_team_lost.buchholz
                            tourney_team.save()
                            tourney_team_lost.rating = calculate_new_elo_rating(False, tourney_team_lost.rating, current_win_rating)
                            tourney_team_lost.losses += 1
                            tourney_team_lost.buchholz += tourney_team.buchholz
                            tourney_team_lost.save()
                            processGameLog += "\nWinning team: {}, len(teams_won): {}".format(tourney_team_lost.id,
                                                                                            len(teams_lost))
                    else:
                        processGameLog += "Could not find a losing team when processing game...??"
        except Exception:
            log_exception()
            processGameLog += "Tournament {}/{} found exception: {}".format(self.name, self.id, traceback.format_exc())
        finally:
            pgl = ProcessGameLog(game=game, msg=processGameLog, level=LogLevel.process_game)
            pgl.save()

    def get_tournament_logs(self):
        return self.tournament_logs

    def update_tournament_logs(self):
        # format the tournament logs in a nice table for us to see
        self.tournament_logs = ""

    def decline_tournament(self, token):
        # is the player in the tournament?
        player = Player.objects.filter(token=token)
        if not player:
            raise Exception("Player with token {} not found".format(token))

        # if we're start locked or have started, we must bail
        if self.start_locked or self.has_started:
            raise Exception("The host is trying to start the tournament or it has already started.")

        # make sure this player is already in the tournament
        tournament_player = TournamentPlayer.objects.filter(player=player[0], tournament=self.id)
        if not tournament_player:
            raise Exception("Player {} is not in the tournament!".format(token))

        # remove the TournamentPlayer object
        tournament_player[0].delete()

    @property
    def current_rounds(self):
        # based off of number of rounds calculate from max_rounds which will change when we actually
        # start the tournament, let's try to calculate it on the fly based on the max_players here
        rounds = 0
        if self.current_filled_teams != 0:
            rounds = math.ceil(math.log(self.current_filled_teams, 2))
        return rounds

    @property
    def multi_day_str(self):
        if self.multi_day:
            return "Multi-Day"
        else:
            return "Real-Time"

    @property
    def max_rounds(self):
        # based off of number of rounds calculate from max_rounds which will change when we actually
        # start the tournament, let's try to calculate it on the fly based on the max_players here
        rounds = 0
        if self.max_teams > 0:
            rounds = math.ceil(math.log(self.max_teams, 2))
        return rounds

    @property
    def max_teams(self):
        return self.max_players // self.players_per_team

    @property
    def current_filled_teams(self):
        teams_complete = 0
        tournament_teams = TournamentTeam.objects.filter(tournament=self.id)
        if tournament_teams:
            for team in tournament_teams:
                tournament_players = TournamentPlayer.objects.filter(tournament=self.id, team=team)
                if tournament_players and tournament_players.count() == self.players_per_team:
                    teams_complete += 1

        return teams_complete

    def remove_partial_teams(self):
        # this method deletes all empty teams
        tournament_teams = TournamentTeam.objects.filter(tournament=self.id)
        for team in tournament_teams:
            empty_team = True
            tournament_players = TournamentPlayer.objects.filter(team=team)
            if tournament_players and tournament_players.count() > 0:
                empty_team = False

            if empty_team:
                team.delete()

    @property
    def partial_filled_teams(self):
        partial_teams = 0
        tournament_teams = TournamentTeam.objects.filter(tournament=self.id)
        if tournament_teams:
            for team in tournament_teams:
                tournament_players = TournamentPlayer.objects.filter(team=team)
                if tournament_players and tournament_players.count() < self.players_per_team:
                    partial_teams += 1

        return partial_teams

    # really a test method only
    def fill_teams(self):
        print("Filling teams for {}".format(self.name))
        current_players_used = []
        tournament_teams = TournamentTeam.objects.filter(tournament=self.id)
        if tournament_teams:
            current_teams_filled = 0
            for team in tournament_teams:
                tournament_players = TournamentPlayer.objects.filter(team=team)

                current_players_on_team = tournament_players.count()
                print("Current players on team: {}".format(current_players_on_team))
                for num in random.sample(range(1, 100), self.players_per_team - current_players_on_team):

                    existing_player = Player.objects.filter(token=num)
                    while num in current_players_used or existing_player:
                        num = random.sample(range(1, 1000000), self.players_per_team - current_players_on_team)[0]
                        existing_player = Player.objects.filter(token=num)

                    name = "Player {}".format(num)
                    player = Player(token=num, name=name)
                    player.save()
                    tournament_player = TournamentPlayer(tournament=self, team=team, player=player)
                    tournament_player.save()

                    current_players_used.append(num)

                current_teams_filled += 1

    @property
    def can_start_tourney(self):
        # can start tourney walks the list of teams calculating how many we need based on
        # min_teams to start

        # if debugging we can always start it unless there are partial teams
        if settings.DEBUG and (self.partial_filled_teams is 0):
            return True

        return (self.current_filled_teams >= self.min_teams) and (self.partial_filled_teams is 0)

    @property
    def time_since_created(self):
        naive_now = datetime.datetime.now().replace(tzinfo=None)
        naive_then = self.created_date.replace(tzinfo=None)
        td = naive_now - naive_then

        seconds = int(td.total_seconds())
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60

        remaining_hours = (hours % 24)
        days = int(hours // 24)
        if hours > 0:
            if remaining_hours > 0:
                if days > 1 and ((remaining_hours > 1) or (hours > 24)):
                    return "{} days, {} hours ago".format(days, remaining_hours)
                elif days > 1:
                    return "{} days, {} hour ago".format(days, remaining_hours)
                elif remaining_hours > 1:
                    return " {} hours ago".format(remaining_hours)
                else:
                    return "{} day, {} hour ago".format(days, remaining_hours)
            else:
                if hours > 1:
                    return "{} hours ago".format(hours)
                else:
                    return "{} hour ago".format(hours)
        if minutes > 0:
            if minutes > 1:
                return "{} minutes ago".format(minutes)
            else:
                return "{} minute ago".format(minutes)
        if seconds > 0:
            if minutes > 1:
                return "{} seconds ago".format(seconds)
            else:
                return "{} second ago".format(seconds)

    @property
    def spots_left_count(self):
        try:
            players_in_tournament = TournamentPlayer.objects.filter(tournament=self)
            if players_in_tournament:
                return self.max_players - players_in_tournament.count()
            else:
                return self.max_players
        except:
            log_exception()
        finally:
            return 0

    @property
    def spots_left(self):
        # how many players are currently in the tournament
        return_text = ""
        try:
            if self.has_started:
                return_text = "In Progress"
            else:
                players_in_tournament = TournamentPlayer.objects.filter(tournament=self)
                if players_in_tournament:
                    return_text = self.max_players - players_in_tournament.count()
                else:
                    return_text = self.max_players

            return "<h3>{}</h3><h5>spots left</h5>".format(return_text)
        except:
            log_exception()
            return 0

    def __str__(self):
        if self.name:
            name = "Tournament: {}, id: {}".format(self.name, self.id)
        else:
            name = "Tournament id: {}".format(self.id)
        return name

    def invite_player(self, request_data):
        if 'buttonid' in request_data:
            buttonid = request_data['buttonid']
            token_split = buttonid.split('-')
            token = token_split[1]
            player = None
            print("Inviting {}  to tournament {} ".format(token, self.id))
            if token.isnumeric():
                token = int(token)
                player = Player.objects.filter(token=token)
                if player:
                    player = player[0]

                    invite = TournamentInvite.objects.filter(player=player, tournament=self)
                    if invite:
                        # you can't be invited multiple times
                        # so just return
                        return

                    # now create the invite record
                    tournament_player = TournamentPlayer.objects.filter(tournament=self, player=player)
                    joined = False
                    if tournament_player:
                        joined = True

                    invited_player = TournamentInvite(player=player, tournament=self, joined=joined)
                    invited_player.save()

    def join_tournament(self, token, buttonid):
        # if we get called we're definitely already logged in
        # parse the join button, and join the slot
        digits = buttonid[4:len(buttonid)]
        digits = digits.split('-')

        teamnum = digits[0]
        playernum = digits[1]
        player = None
        if teamnum.isnumeric() and playernum.isnumeric():
            teamnum = int(teamnum)
            playernum = int(playernum)

            player = Player.objects.filter(token=token)
            if not player:
                raise Exception("Player with token {} not found".format(token))

            # if we're start locked or have started, we must bail
            if self.start_locked or self.has_started:
                raise Exception("The host is trying to start the tournament or it has already started.")

            # make sure this player isn't already in the tournament
            tournament_player = TournamentPlayer.objects.filter(player=player[0], tournament=self.id)
            if tournament_player:
                raise Exception("Player {} is already in the tournament!".format(token))

            # lookup the team and make sure there is a slot
            tournament_team = TournamentTeam.objects.filter(team_index=teamnum, tournament=self.id)
            if tournament_team:
                # found the team, is there an opening
                tournament_player = TournamentPlayer.objects.filter(tournament=self.id, team=tournament_team[0])
                if tournament_player and tournament_player.count() == self.players_per_team:
                    # there is already a player here
                    raise Exception("Team {} is already filled.".format(teamnum))
                else:
                    # create the player and move on
                    player = Player.objects.filter(token=token)
                    if player:
                        tournament_player = TournamentPlayer(tournament=self, team=tournament_team[0], player=player[0])
                        tournament_player.save()

                        # now, if there is an invite for this player, go ahead and delete it as well (since they've now joined)
                        tournament_invite = TournamentInvite.objects.filter(player=player[0], tournament=self, joined=False)
                        if tournament_invite:
                            tournament_invite[0].joined = True
                            tournament_invite[0].save()
                    else:
                        raise Exception("Player with token {} not found".format(token))
        else:
            raise Exception("Invalid team or player number")


    def setPlayerInvited(self, invited):
        self.player_invited = invited


class SwissTournament(Tournament):
    type = models.CharField(max_length=255, default="Swiss")
    max_rating = models.IntegerField(default=0)
    min_rating = models.IntegerField(default=0)
    best_record = models.CharField(max_length=10, default="0-0")
    extra_rounds = models.IntegerField(default=0, null=True, blank=True)

    min_teams = 4

    def show_tournament_details(self):
        return True

    def tournament_details(self):
        return "Extra Rounds: {}".format(self.extra_rounds)

    def process_new_games(self):
        # now that we have the team data committed, we mark the game as finished and continue on to the next round
        # and let the child class continue to handle the match-ups to the next round

        # first, put in memory all the round match-ups
        team_matchups = defaultdict(list)  # dictionary of lists of teams that cannot play each other
        team_wins = defaultdict(list)  # dictionary of lists of each teams wins, the key is the number of wins
        team_losses = defaultdict(list) # dictionary of lists of each teams losses, the key is the number of losses
        teams_look_for_games = defaultdict(int)  # dictionary of rounds for each eligible teams next game

        tournament_rounds_finished = TournamentRound.objects.filter(tournament=self, is_finished=True)
        if tournament_rounds_finished and tournament_rounds_finished.count() == (self.current_rounds + self.extra_rounds):
            # all round have been completed
            # mark the tournament finished, we're done
            log_tournament("Tournament is finished, ending", self)
            # who has the winning-est records?
            tournament_team = TournamentTeam.objects.filter(tournament=self.id).order_by('-wins')
            if tournament_team:
                team = tournament_team[0]  # team with the most wins
                self.winning_team = team
            self.is_finished = True
            self.save()
            return

        # we aren't done and have at least 1 round left to go, walk through each round computing
        # match-ups and total wins arrays, to schedule the next games only when all the games of the previous
        # round is completed
        tournament_rounds = TournamentRound.objects.filter(tournament=self).order_by('round_number')
        for round in tournament_rounds:
            games_in_progress = TournamentGame.objects.filter(round=round, is_finished=False)
            if games_in_progress:
                # round is in progress, return
                return

            # We loop through all games in the tournament building a list of wins/losses/match-ups/who needs a game
            round_finished = True
            games = TournamentGame.objects.filter(round=round)
            if not games:
                round_finished = False
            for game in games.iterator():
                # parse into two
                teams = game.teams.split('.')
                for team in teams:
                    # if the game is completed, this team is available to get a new game created
                    # if this game is not completed, remove them from the list if they are already there
                    # this allows the list of teams
                    if game.is_finished:
                        if round.round_number < (self.current_rounds + self.extra_rounds):
                            teams_look_for_games[team] = round.round_number + 1

                    # this next piece is only done a single time
                    if team.isnumeric() and (round.round_number == 1):
                        tournament_team = TournamentTeam.objects.filter(tournament=self, pk=int(team))
                        if tournament_team:
                            tournament_team = tournament_team[0]
                            # add this teams wins/losses to our ongoing list
                            team_wins[tournament_team.wins].append(team)
                            team_losses[tournament_team.losses].append(team)
                    for teams_played in teams:
                        # add all opponents to the current team list, including ourselves (since we can't play ourselves)
                        if teams_played not in team_matchups[int(team)]:  # only do this once
                            team_matchups[team].append(teams_played)

                if not game.is_finished:
                    round_finished = False
            if round_finished:
                round.is_finished = True
                round.save()
            elif len(teams_look_for_games) == self.max_teams:
                # now that we've built the round data, we need to try to create games for any team
                # that is in our potential team list, against all others in that list with the same number of wins
                # this main loop loops from the reverse sorted list of winners, best at the top
                # since the keys aren't
                # we're ready to create the next round of games, but only if there aren't games in the round already
                print("Running algorithm to create games for round {}, as {} teams need games and total games per round = {}".format(round.round_number, len(teams_look_for_games), self.max_teams))
                times_run_algo = 0
                while True:
                    game_data_grid = ""
                    games_created_for = []
                    if times_run_algo == 10:
                        break
                    times_run_algo += 1

                    if round.round_number > self.number_rounds:
                        # we're in extra rounds...handle this differently by creating two lists of
                        # all the teams in reverse ranking order
                        # clear team_bucket2 and team_bucket1 and instead make them the list of teams descending
                        log_tournament("Processing extra round {} games".format(round.round_number), self)
                        # have both bucket, loop through the first and try to make pairs
                        tournament_teams = TournamentTeam.objects.filter(tournament=self.id).order_by('-rating')
                        team_list = []
                        for team in tournament_teams:
                            team_list.append(str(team.id))

                        if times_run_algo >= 1:
                            team_list.reverse()
                            team_list2 = team_list.copy()
                        elif times_run_algo >= 2:
                            # it's unfortunate, but we need to shuffle the teams
                            shuffle(team_list)
                            team_list2 = team_list.copy()
                            shuffle(team_list2)
                        else:
                            team_list2 = team_list.copy()

                        for team in team_list:
                            for team2 in team_list2:
                                # first condition is they can't have played this team before, and we need to be looking for a game
                                if team not in team_matchups[team2]:
                                    if team not in games_created_for:
                                        if team2 not in games_created_for:
                                            if team2 not in team_matchups[team]:
                                                if teams_look_for_games[team2] == teams_look_for_games[team]:
                                                    log_tournament("Creating game {} in round {} for {} and {}".format(
                                                        (len(games_created_for) / 2) + 1, teams_look_for_games[team],
                                                        team, team2), self)

                                                    game = "{}.{};".format(team, team2)
                                                    game_data_grid += game
                                                    games_created_for.append(team)
                                                    games_created_for.append(team2)
                                if len(games_created_for) == len(teams_look_for_games):
                                    break
                            if len(games_created_for) == len(teams_look_for_games):
                                break
                    else:
                        # we have a list of buckets determined by teams_wins[x] where x is the list of teams with
                        # that number of wins. What we want to do is copy that list, and run through them
                        # trying to match-up players who haven't played each other.
                        # if all buckets succeed, we're done.
                        team_wins2 = copy(team_wins)
                        for key, bucket in team_wins.items():
                            team_bucket1 = team_wins[key]
                            team_bucket2 = team_wins2[key]
                            shuffle(team_bucket2)  # why not
                            shuffle(team_bucket1)  # why not

                            log_tournament("Processing bucket {} of {} teams".format(bucket, len(team_bucket1)), self)
                            # have both bucket, loop through the first and try to make pairs
                            for team in team_bucket1:
                                for team2 in team_bucket2:
                                    # first condition is they can't have played this team before, and we need to be looking for a game
                                    if team not in team_matchups[team2]:
                                        if team not in games_created_for:
                                            if team2 not in games_created_for:
                                                if team2 not in team_matchups[team]:
                                                    if teams_look_for_games[team2] == teams_look_for_games[team]:
                                                        log_tournament("Creating game {} in round {} for {} and {}".format((len(games_created_for)/2)+1, teams_look_for_games[team], team, team2), self)

                                                        game = "{}.{};".format(team, team2)
                                                        game_data_grid += game
                                                        games_created_for.append(team)
                                                        games_created_for.append(team2)
                                    if len(games_created_for) == len(teams_look_for_games):
                                        break
                                if len(games_created_for) == len(teams_look_for_games):
                                    break

                    # we've built a list of the games we've "created", now, we need to see if this matches the total
                    # number of games we'd expect
                    log_tournament("After iteration {}, games_created = {} and teams who need games = {}".format(times_run_algo, len(games_created_for), len(teams_look_for_games)), self)
                    if len(games_created_for) == len(teams_look_for_games):
                        # remove the last character from the game data grid
                        game_data_grid = game_data_grid[:-1]
                        round.games = game_data_grid
                        game_data = game_data_grid.split(';')
                        for game in game_data:
                            self.create_game(round, game)
                            print("Creating game: {}".format(game))
                        round.save()
                        log_tournament("Calculated all match-ups for round {}: Game Data: {}".format(round.round_number, round.games), self)
                        return

    def update_game_log(self):
        self.game_log = ""

    def get_bracket_game_data(self):
        return self.bracket_game_data

    def update_bracket_game_data(self):
        # returns a list of all the games for the swiss tournament in reverse order of when it was created
        bracket_game_data = ""

        if not self.is_finished and not self.has_started:
            bracket_game_data = '<p>List of created games will be displayed here</p>'
            return bracket_game_data
        else:
            # bracket game data for swiss tournament is a table of all the rounds, we only put 4 on a line. so if the tournament
            # has more that's ok
            # build the table
            max_games_per_row = 4
            tournament_rounds = TournamentRound.objects.filter(tournament=self.id).order_by('round_number')
            for round in tournament_rounds:
                bracket_game_data += '<br/><div class="card gedf-card span12">'
                bracket_game_data += '<div class="card-header h7">'
                bracket_game_data += 'Round {}'.format(round.round_number)
                bracket_game_data += '</div>'  # close card header
                bracket_game_data += '<div class="card-body">'
                bracket_game_data += '<div class="container">'
                bracket_game_data += '<div class="row">'
                # grab the games in this round, we don't care about the status
                tournament_games = TournamentGame.objects.filter(round=round, tournament=self.id)
                num_games = 1
                for game in tournament_games:
                    bracket_game_data += '<div class="col-md-3 col-lg-3 col-xl-3 col-xs-3"><table class="table table-hover table-bordered" style="font-size:12px;">'
                    # add the game link with rowspan = 2
                    teams = game.teams.split('.')
                    num_teams = 1
                    for team in teams:
                        bracket_game_data += '<tr>'
                        if num_teams == 1:
                            bracket_game_data += '<td rowspan="2" class="align-middle"><a href="{}" target="_blank">Game Link</a></td>'.format(game.game_link)
                            num_teams = 0  # just so we don't do this again
                        bracket_game_data += '<td class="col-md-9 col-lg-9 col-xl-9 col-xs-9">'
                        tournament_players = TournamentPlayer.objects.filter(team=int(team))
                        for tournament_player in tournament_players:
                            if tournament_player.player.clan is not None:
                                bracket_game_data += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a> '.format(
                                    tournament_player.player.clan.icon_link, tournament_player.player.clan.image_path, tournament_player.player.clan.name)

                            bracket_game_data += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                            tournament_player.player.token, tournament_player.player.name)
                            if game.is_finished and game.winning_team is not None:
                                if team == str(game.winning_team.id):
                                    bracket_game_data += '<span class="text-success">W</span>'
                                else:
                                    bracket_game_data += '<span class="text-danger">L</span>'

                        bracket_game_data += '</td></tr>'

                    bracket_game_data += '</table></div>'
                    num_games += 1

                while num_games < (max_games_per_row + 1):
                    bracket_game_data += '<div class="col-md-3 col-lg-3 col-xl-3 col-xs-3"></div>'
                    num_games += 1

                bracket_game_data += '</div></div></div></div>'  # well closing div + row closing div

        self.bracket_game_data = bracket_game_data
        self.save()

    def get_start_locked_data(self):
        # returns the html for the tournament
        if self.current_filled_teams >= self.min_teams:
            return "<p>Are you sure you want to start this tournament?</p>"
        else:
            return "<p>You cannot start this tournament until the minimum number of players have joined</p>"

    def start(self, tournament_data):
        # start the tournament calculating the max_rounds again based on the number of players
        # in the tournament
        #
        # the tournament can be started once the minimum # of players have joined, so recalculate
        # set the common parent settings
        super(SwissTournament, self).start()

        self.number_rounds = self.current_rounds
        log("Starting Swiss tournament id: {} name: {} players: {} rounds: {}".format(self.id, self.name,
                                                                                      self.number_players,
                                                                                      self.current_rounds),
            LogLevel.informational)
        for i in range(1, self.number_rounds + self.extra_rounds + 1):
            # create a new round
            # construct the game list by looping through all the players and putting the first two together, second two, and so forth
            # we only know the games on the very first go at it
            game_data = ""
            print("Tournament Round {} created".format(i))
            if i == 1:
                tournament_teams = TournamentTeam.objects.filter(tournament=self)
                teams_added = 0
                for tournament_team in tournament_teams:
                    if teams_added == self.teams_per_game:
                        # we're done, reset
                        game_data += ";"
                        teams_added = 0

                    if teams_added == (self.teams_per_game - 1):
                        game_data += "{}".format(tournament_team.id)
                    else:
                        game_data += "{}.".format(tournament_team.id)

                    teams_added += 1

                print("Game data for tournament: {} ".format(game_data))
                games_in_round = len(game_data.split(';'))

            tournament_round = TournamentRound(round_number=i, tournament=self, is_finished=False, games=game_data, number_games=games_in_round)
            tournament_round.save()

        # we need to create initial games here, as the engine might not run for a while (we just missed it)
        # get the game data back and parse it
        tournament_round = TournamentRound.objects.filter(round_number=1, tournament=self)
        if tournament_round:
            tournament_round = tournament_round[0]

            # get the games and deserialize
            game_data_grid = tournament_round.games.split(';')
            for game in game_data_grid:
                self.create_game(tournament_round, game)

        # once we've done everything else, mark has_started and save the tournament
        self.has_started = True
        self.save()

class SeededTournament(Tournament):
    type = models.CharField(max_length=255, default="Seeded")
    min_teams = 4

    @property
    def bracket_seeded_async(self):
        return True

    def start(self, tournament_data):
        try:
            # start the tournament calculating the max_rounds again based on the number of players
            # in the tournament
            #
            # the tournament can be started once the minimum # of players have joined, so recalculate
            # set the common parent settings
            super(SeededTournament, self).start()

            self.number_rounds = self.current_rounds
            log("Starting Seeded tournament id: {} name: {} players: {} rounds: {}".format(self.id, self.name,
                                                                                          self.number_players,
                                                                                          self.current_rounds),
                LogLevel.informational)

            seed_team_list = tournament_data.split(';')
            team_list = []
            for seeded_team in seed_team_list:
                split_data = seeded_team.split('.')
                team_list.append(split_data[1])
                tournament_team1 = TournamentTeam.objects.filter(tournament=self, pk=split_data[1])
                if tournament_team1:
                    tournament_team1[0].seed = int(split_data[0])
                    tournament_team1[0].save()

            total_teams = int(self.number_players / self.players_per_team)

            # build the seed list, which is the order in which games are created and saved,
            # so subsequent rounds will match-up the correct teams together
            seed_list = get_seed_list(self.max_teams)

            print("Seed list: {}".format(seed_list))
            print("Team list: {}".format(team_list))
            # now, loop through the seed list, pairing up the teams in this order
            game_data_grid = ""
            game_data = ""
            team_to_add = 1  # can only be 1 or two, we're either adding the first team or the second
            for i in range(0, len(seed_list)):
                index = seed_list[i] - 1
                if team_to_add % 2 == 0:
                    # second team
                    game_data += ".{};".format(team_list[index])
                    game_data_grid += game_data
                    game_data = ""  # reset
                else:
                    # first team
                    game_data += "{}".format(team_list[index])

                team_to_add += 1

            print("Starting game data grid: {}".format(game_data_grid))

            # create the rounds
            games_in_round = total_teams
            for i in range(1, self.number_rounds + 1):
                # create a new round
                # construct the game list by looping through all the players and putting the first two together, second two, and so forth
                # we only know the games on the very first go at it
                game_data = ""
                game_data_grid = game_data_grid[:-1]
                game_data = game_data_grid
                games_in_round = games_in_round / 2
                if i > 1:
                    game_data_grid = ""
                    print("Processing neutral data for round {}".format(i))
                    game_data = ""
                    for j in range(0, int(games_in_round)):
                        game_data += "{}.{};".format(0, 0)
                    game_data = game_data[:-1]
                print("Creating round {} with game data: {}".format(i, game_data))
                tournament_round = TournamentRound(round_number=i, tournament=self, is_finished=False,
                                                   games=game_data, number_games=games_in_round)
                tournament_round.save()

            # we need to create initial games here, as the engine might not run for a while (we just missed it)
            # get the game data back and parse it
            tournament_round = TournamentRound.objects.filter(round_number=1, tournament=self)
            if tournament_round:
                tournament_round = tournament_round[0]
                game_data = tournament_round.games.split(';')
                for game in game_data:
                    print("[StartGame]: Creating game {} in round {}".format(game, tournament_round.round_number))
                    self.create_game(tournament_round, game)
        except Exception:
            log_exception()

    def process_new_games(self):
        # loop through the rounds, computing any new matchups for the next round if possible
        # game_data starts from the #1 seed against the lowest, so we can work through
        # the tree from there

        tournament_rounds_finished = TournamentRound.objects.filter(tournament=self, is_finished=True)
        if tournament_rounds_finished and tournament_rounds_finished.count() == self.current_rounds:
            # all round have been completed
            # mark the tournament finished, we're done
            log_tournament("Tournament is finished, ending", self)
            # who has the winning-est records?
            tournament_team = TournamentTeam.objects.filter(tournament=self.id).order_by('-wins')
            if tournament_team:
                team = tournament_team[0]  # team with the most wins
                self.winning_team = team
            self.is_finished = True
            self.save()
            print("Tournament is finished, returning")
            return

        if tournament_rounds_finished:
            log_tournament("Total rounds finished are {}".format(tournament_rounds_finished.count()), self)
        # we aren't done and have at least 1 round left to go, walk through each round computing
        # match-ups and total wins arrays, to schedule the next games only when all the games of the previous
        # round is completed
        tournament_rounds = TournamentRound.objects.filter(tournament=self).order_by('round_number')
        for round in tournament_rounds.iterator():
            games_created = []
            # dump the data into buckets
            # if we're on round 1, do nothing
            # on successive rounds, look up the previous rounds game list, parse into buckets
            # and move players accordingly
            games_finished = TournamentGame.objects.filter(round=round, tournament=self, is_finished=True)
            if games_finished and games_finished.count() == round.number_games:
                print("Round {} has {} games finished".format(round.round_number, round.number_games))
                round.is_finished = True
                round.save()
                if round.round_number == self.max_rounds:
                    tournament_team = TournamentTeam.objects.filter(tournament=self.id).order_by('-wins')
                    if tournament_team:
                        team = tournament_team[0]  # team with the most wins
                        self.winning_team = team
                    self.is_finished = True
                    self.save()
                    print("Tournament is finished, returning")
                    return
                else:
                    continue

            games_in_round = TournamentGame.objects.filter(round=round, tournament=self)
            if games_in_round and games_in_round.count() == round.number_games:
                # we've got the games in this round done, move on
                print("All game have been created in round {}, continuing on".format(round.round_number))
                continue

            game_buckets_current_round = {}
            current_round_game_data = round.games.split(';')

            log_tournament("Round {} game_data: {}".format(round.round_number, round.games), self)
            if round.round_number > 1:
                previous_round = TournamentRound.objects.filter(tournament=self, round_number=round.round_number-1)
                previous_round_games = []
                if previous_round:
                    log_tournament("Previous Round Game Data: {}".format(previous_round[0].games.split(';')), self)
                    previous_round_games = previous_round[0].games.split(';')
                current_game_idx = 0
                for game in previous_round_games:
                    # lookup the game, and see if it's finished, if not, continue
                    # regardless if the game is finished or not, we set game_buckets_current_round to the default here
                    game_obj = TournamentGame.objects.filter(tournament=self, teams=game, is_finished=True)
                    if game_obj and game_obj[0].is_finished:
                        index = int(current_game_idx / 2)
                        dec_index = current_game_idx / 2

                        current_game_team1 = 0
                        current_game_team2 = 0
                        if index in current_round_game_data:
                            current_game_team1 = current_round_game_data[index].split('.')[0]
                            current_game_team2 = current_round_game_data[index].split('.')[1]
                        if index not in game_buckets_current_round:
                            # initialize
                            game_buckets_current_round[index] = "{}.{}".format(current_game_team1, current_game_team2)

                        log_tournament("Round [{}]: looking at bucket[{}]: {}".format(round.round_number, index, game_buckets_current_round[index]), self)
                        if dec_index == index:
                            # team1 in the bucket advances
                            log_tournament("Team {} advances to bucket {} in round {}".format(game_obj[0].winning_team.id, index, round.round_number), self)
                            if game_buckets_current_round[index].split('.')[1] != '0':
                                other_team = game_buckets_current_round[index].split('.')[1]
                                game_buckets_current_round[index] = "{}.{}".format(game_obj[0].winning_team.id,
                                                                                   other_team)
                            else:
                                game_buckets_current_round[index] = "{}.{}".format(game_obj[0].winning_team.id, current_game_team2)
                        else:
                            # team2 is set
                            log_tournament("Team {} advances to bucket {} in round {}".format(game_obj[0].winning_team.id, index,
                                                                                   round.round_number), self)
                            if game_buckets_current_round[index].split('.')[0] != '0':
                                other_team = game_buckets_current_round[index].split('.')[0]
                                game_buckets_current_round[index] = "{}.{}".format(other_team,
                                                                               game_obj[0].winning_team.id)
                            else:
                                game_buckets_current_round[index] = "{}.{}".format(current_game_team1, game_obj[0].winning_team.id)
                        # put the bucket back on the object
                        game_data = game_buckets_current_round[index].split('.')
                        log_tournament("Round [{}], Bucket [{}]: {}".format(round.round_number, index, game_data), self)
                        team1 = game_data[0]
                        team2 = game_data[1]
                        if team1 is not '0' and team2 is not '0':
                            game_data = "{}.{}".format(team1, team2)
                            game_buckets_current_round[index] = game_data

                            if team1 not in games_created and team2 not in games_created:
                                if not self.game_exists_between(team1, team2):
                                    log_tournament("Creating game in round {} between {} and {}".format(round.round_number, team1, team2), self)
                                    self.create_game(round, game_data)
                                    games_created.append(team1)
                                    games_created.append(team2)

                    current_game_idx += 1

                round_data_save = ""
                for index, game in game_buckets_current_round.items():
                    round_data_save += "{};".format(game)

                if round_data_save != "":
                    round_data_save = round_data_save[:-1]
                    print("Saving game data for round {}: {}".format(round.round_number, round_data_save))
                    round.games = round_data_save
                    round.save()
            game_buckets_current_round.clear()


    def game_exists_between(self, team1, team2):
        teams = "{}.{}".format(team1, team2)
        game = TournamentGame.objects.filter(tournament=self, teams=teams)
        if game:
            return True
        else:
            teams = "{}.{}".format(team2, team1)
            game = TournamentGame.objects.filter(tournament=self, teams=teams)
            if game:
                return True

        return False

    def get_bracket_game_data(self):
        if self.bracket_game_data == "" or len(self.bracket_game_data) == 0:
            self.update_bracket_game_data()
        return self.bracket_game_data

    def update_bracket_game_data(self):
        bracket_data = {}
        bracket_data['bracket_data'] = {}
        bracket_data['bracket_data']['results'] = []
        bracket_data['bracket_data']['teams'] = []
        bracket_data['game_links'] = []
        # the way we design the bracket is we have a massive table, with one row
        # each column in the row is a 'round' in the tournament, which is made of up
        # single tables per round
        total_games = 0
        rounds = TournamentRound.objects.filter(tournament=self).order_by('round_number')

        for round in rounds:
            # create the lists
            '''             
             Example of the minimal data
             
             var minimalData = {
                teams : [
                  ["Team 1", "Team 2"], /* first matchup */
                  ["Team 3", "Team 4"]  /* second matchup */
                ],
                results : [
                  [[1,2], [3,4]],       /* first round */
                  [[4,6], [2,1]]        /* second round */
                ]
              }
            '''
            game_data = round.games.split(';')
            if round.round_number == 1:
                # loop through all the teams in order from the round to create the team list
                for game in game_data:
                    current_game_list = []
                    teams = game.split('.')
                    for team in teams:
                        player_obj = TournamentPlayer.objects.filter(tournament=self, team=int(team))
                        if player_obj:
                            team_player = ""
                            if player_obj.count() == 1:
                                # store the player data as if we were to output, cause if this is a partial team
                                # then we want to just continue on
                                player_data = ""
                                if player_obj[0].player.clan is not None:
                                    player_data += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                                        player_obj[0].player.clan.icon_link, player_obj[0].player.clan.image_path, player_obj[0].player.clan.name)

                                player_data += '<a href="/stats/{}" target="_blank">{}</a></a>&nbsp;'.format(
                                    player_obj[0].player.token, player_obj[0].player.name)

                                team_player = "<span class='badge badge-light' style='display:inline-block;width:25px;'>{}</span> {}".format(player_obj[0].team.seed,
                                                                                           player_data)
                            else:
                                # use the team #
                                team_player = "<span class='seed'>{}</span> Team {}".format(player_obj[0].team.seed, player_obj[0].team.id)
                            current_game_list.append(team_player)
                    bracket_data['bracket_data']['teams'].append(current_game_list)

            # now build the result list
            current_round_results = []
            for game in game_data:
                current_game_result = []
                game_obj = TournamentGame.objects.filter(tournament=self, round=round, teams=game)
                if game_obj and game_obj[0].is_finished:
                    # the game is finished, so add the resulting data
                    teams = game.split('.')
                    if game_obj[0].winning_team.id == int(teams[0]):
                        current_game_result.append(1)
                        current_game_result.append(0)

                    else:
                        current_game_result.append(0)
                        current_game_result.append(1)
                    bracket_data['game_links'].append(game_obj[0].game_link)
                else:
                    current_game_result.append(None)
                    current_game_result.append(None)
                    if game_obj:
                        bracket_data['game_links'].append(game_obj[0].game_link)
                    else:
                        bracket_data['game_links'].append("javascript:void(0);")

                # regardless if the game is finished or not, we must have an entry here for the
                # potential game link
                current_game_result.append(str(total_games))
                total_games += 1
                current_round_results.append(current_game_result)
            bracket_data['bracket_data']['results'].append(current_round_results)

        self.bracket_game_data = json.dumps(bracket_data)
        self.save()

    def get_game_log(self):
        return self.game_log

    def update_game_log(self):
        game_log = '<table class="table table-bordered table-condensed clot_table compact stripe cell-border" id="game_log_data_table">'
        game_log += '<thead><tr><th>Match-Up</th><th>Game Link</th><th>State</th><th>Winning Team</th><th>Start Time</th><th>End Time</th></tr></thead>'
        game_log += '<tbody>'
        games = TournamentGame.objects.filter(tournament=self)
        for game in games:
            game_log += '<tr>'
            # create the match-up text for the game
            game_data = game.teams.split('.')
            team1 = game_data[0]
            team2 = game_data[1]
            team_1 = TournamentTeam.objects.filter(id=int(team1))
            if team_1:
                team_2 = TournamentTeam.objects.filter(id=int(team2))
                if team_2:
                    game_log += '<td data-search="{} {}">{}</td>'.format(get_team_data_no_clan(team_1[0]),
                                                                         get_team_data_no_clan(team_2[0]),
                                                                         get_matchup_data(team_1[0],
                                                                                          team_2[0]))
            game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(game.game_link)
            if game.is_finished:
                finished_text = '<span class="text-success"><b>Finished</b></span>'
            else:
                finished_text = '<span class="text-info">{}</span>'.format(game.current_state)
            game_log += '<td>{}</td>'.format(finished_text)

            if game.is_finished:
                winning_team = '{}'.format(get_team_data(game.winning_team))
            else:
                winning_team = ''
            game_log += '<td>{}</td>'.format(winning_team)
            time_to_boot_calculate = 0

            start_time = game.game_start_time.strftime("%b %d, %Y %H:%M:%S %p")

            # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
            end_time = game.game_finished_time.strftime(
                "%b %d, %Y %H:%M:%S %p") if game.is_finished and game.game_finished_time else 'N/A'

            game_log += '<td>{}</td>'.format(start_time)
            game_log += '<td>{}</td>'.format(end_time)
            game_log += '</tr>'

        game_log += '</tbody></table>'
        self.game_log = game_log
        self.save()

    def get_start_locked_data(self):
        # if we set the tourney (currently always) and we can start (minimum # of full teams, and 0 partial teams)
        draggable_data = ""
        if self.host_sets_tourney and self.can_start_tourney:
            # lookup the entire list of players, and display them as a seeded list for the user to sort
            draggable_data = 'Please set the seeds for the teams in the tournament before you begin<br/>'
            draggable_data += '<div class="dd" id="seed_list">'
            draggable_data += '<ol class="dd-list" id="seed_ordered_list">'

            tournament_teams = TournamentTeam.objects.filter(tournament=self.id).order_by('team_index')
            if tournament_teams:
                # first, build the seed list based off the filled up teams
                for team in tournament_teams:
                    tournament_players = TournamentPlayer.objects.filter(tournament=self.id, team=team)
                    if tournament_players and tournament_players.count() == self.players_per_team:
                        draggable_data += '<li class="dd-item" data-id="{}">'.format(team.team_index)
                        draggable_data += '<div class="dd-handle" id="{}"><span class="seed_text">Seed {}: </span><span class="player_text">'.format(team.id, team.team_index)
                        for player in tournament_players:
                            # store the player data as if we were to output, cause if this is a partial team
                            # then we want to just continue on

                            if player.player.clan is not None:
                                draggable_data += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                                    player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

                            draggable_data += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                                player.player.token, player.player.name)
                        draggable_data += "</span></div>"
                        draggable_data += '</li>'
                draggable_data += "</ol>"
                draggable_data += '</div>'

            return draggable_data

class GroupStageTournament(Tournament):
    type = models.CharField(max_length=255, default="Group Stage")
    groups = models.IntegerField(default=4)
    player_per_group = models.IntegerField(default=4)
    knockout_rounds = models.IntegerField(default=2)
    knockout_teams = models.IntegerField(default=0)
    champion1 = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='first_place')
    champion2 = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='second_place')
    champion3 = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='third_place')
    third_place_game = models.BooleanField(default=False)
    knockout_tournament = models.ForeignKey('SeededTournament', on_delete=models.SET_NULL, blank=True, null=True)

    min_teams = 4

    def start(self, tournament_data):
        super(GroupStageTournament, self).start()

        log("Starting Group Stage tournament id: {} name: {} players: {} rounds: {}".format(self.id, self.name,
                                                                                      self.number_players,
                                                                                      self.current_rounds),
            LogLevel.informational)

        # create the respective groups, and add all the appropriate teams to it
        group_buckets = {}
        for data in tournament_data.split(';'):
            group_number = data.split('.')[0]
            team_number = data.split('.')[1]
            print("Team {} is in Group {}".format(team_number, group_number))

            if group_number not in group_buckets:
                # initialize
                group_buckets[group_number] = []

            group_buckets[group_number].append(team_number)

        print("Bucket Length: {}".format(len(group_buckets)))
        self.groups = int(self.max_teams / self.player_per_group)
        self.save()

        games_at_once = 1
        if self.multi_day:
            games_at_once = 2

        # now create the groups, and for each group add the teams to them
        for i in range(1, self.groups+1):
            index = str(i)
            print("Creating group {} with {} games at once".format(index, games_at_once))
            # create the round robin tournament for this group first
            number_teams = len(group_buckets[index])
            tournament_name = "{}: Group {} Round Robin".format(self.name, i)
            rr_tourney = RoundRobinTournament(name=tournament_name, games_at_once=games_at_once, max_players=number_teams*self.players_per_team, number_rounds=number_teams-1, multi_day=self.multi_day,start_option_when_full=False,private=True,description=self.description,template=self.template,template_settings=self.template_settings, teams_per_game=self.teams_per_game,created_by=self.created_by,players_per_team=self.players_per_team, parent_tournament=self)
            rr_tourney.save()
            group = GroupStageTournamentGroup(tournament=self, group_number=i, round_robin_tournament=rr_tourney)
            group.save()

            # now add all the teams to this group
            for team in group_buckets[index]:
                tournament_team = TournamentTeam.objects.filter(pk=int(team))
                if tournament_team:
                    tournament_team[0].round_robin_tournament = rr_tourney
                    tournament_team[0].group = group
                    tournament_team[0].save()
            # start the tournament...
            rr_tourney.start()

    def get_bracket_game_data(self):
        if self.bracket_game_data == "" or len(self.bracket_game_data) == 0:
            self.update_bracket_game_data()
        return self.bracket_game_data

    def update_bracket_game_data(self):
        # update the tournament game log here, which is a collection of all round robin games
        groups = GroupStageTournamentGroup.objects.filter(tournament=self).order_by('group_number')
        log_tournament("Updating {} bracket_game_data for {} groups.".format(self.name, groups.count()), self)
        game_data = ""
        if self.knockout_tournament is not None and self.knockout_tournament.id > 0:
            game_data += '<br/><a href="{}" class="btn btn-primary btn-lg" role="button" target="_blank">Knockout Tournament</a><br/>'.format(self.knockout_tournament.get_url())
        for group in groups:
            log_tournament("Updating bracket_game_data for group: {}".format(group.get_name()), self)
            game_data += '<br/><h5>{}</h5>'.format(group.get_name())
            child_tournament = find_tournament_by_id(group.round_robin_tournament, True)
            if child_tournament:
                child_tournament.update_bracket_game_data()
                game_data += child_tournament.get_bracket_game_data()
            game_data += '<br/><br/>'
        self.bracket_game_data = game_data
        self.save()


    def get_start_locked_data(self):
        # if we set the tourney (currently always) and we can start (minimum # of full teams, and 0 partial teams)
        draggable_data = ""
        if self.host_sets_tourney and self.can_start_tourney:
            # lookup the entire list of players, and display them as a seeded list for the user to sort
            draggable_data = 'Please determine the groups for this tournament before it begins. There will be exactly 4 teams per group.<br/>'
            draggable_data += '<div class="dd" id="seed_list">'
            draggable_data += '<ol class="dd-list" id="group_ordered_list">'

            current_group = 1
            tournament_teams = TournamentTeam.objects.filter(tournament=self.id).order_by('team_index')
            if tournament_teams:
                teams_in_group = 1
                for team in tournament_teams:
                    # first, build the seed list based off the filled up teams
                    tournament_players = TournamentPlayer.objects.filter(tournament=self.id, team=team)
                    if tournament_players and tournament_players.count() == self.players_per_team:
                        draggable_data += '<li class="dd-item" data-id="{}">'.format(team.team_index)
                        draggable_data += '<div class="dd-handle" id="{}"><span class="group_text">Group {}: </span><span class="player_text">'.format(team.id, current_group)
                        for player in tournament_players:
                            # store the player data as if we were to output, cause if this is a partial team
                            # then we want to just continue on

                            if player.player.clan is not None:
                                draggable_data += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}"/></a>'.format(
                                    player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

                            draggable_data += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                                player.player.token, player.player.name)
                        draggable_data += "</span></div>"
                        draggable_data += '</li>'
                    teams_in_group += 1
                    if teams_in_group % 4 == 0:
                        current_group += 1
                        teams_in_group = 1
                draggable_data += "</ol>"
                draggable_data += '</div>'

            return draggable_data

    def process_new_games(self):
        # we only process new games for the group stage if all round robin
        # tournaments have finished, at that point we then take the appropriate
        # players from each group and seed them accordingly and create
        # the knockout tournament
        round_robin_tournaments = RoundRobinTournament.objects.filter(parent_tournament=self, is_finished=True)
        print("Round robin tournaments finished: {}, groups: {}".format(round_robin_tournaments.count(), self.groups))
        if round_robin_tournaments.count() == self.groups:
            log_tournament("Finished with all round robin tournaments, proceeding to create the knockout tournament", self)

            if self.knockout_tournament is not None and self.knockout_tournament.id > 0:
                if self.knockout_tournament.is_finished:
                    self.is_finished = True
                    self.save()
                return

            # seeded data fed into the tournament needs to be in the following format
            # [seed1].[team];[seed2].[team];....
            # teams do not need to have a seed

            # go ahead and loop through all round_robin tournaments and determine the order
            # in which each team finished

            # first_place always matches against a second_place in a group in the seeded, but order doesn't necessarily
            # matter here
            first = []
            second = []

            for t in round_robin_tournaments:
                teams = TournamentTeam.objects.filter(group=t.get_group()).order_by('place', '-rating')
                if teams and teams[0] and teams[1]:
                    first.append(teams[0])
                    second.append(teams[1])

            # now we loop through all the first/second place teams and assign them seeds
            # a first seed always plays a second, and they cannot be from the same group

            # create the seeded tournament
            tourney_name = "{} Knockout Tournament".format(self.name)

            # num players is num groups * 2
            num_players =  round_robin_tournaments.count() * 2
            num_rounds = int(math.log(num_players) / math.log(2))
            log_tournament("Creating Knockout tournament with {} players and {} rounds".format(num_players, num_rounds), self)
            seeded_tournament = SeededTournament(name=tourney_name, multi_day=self.multi_day, start_option_when_full=False, private=True, description=self.description, template=self.template, template_settings=self.template_settings, max_players=num_players, teams_per_game=self.teams_per_game, created_by=self.created_by, players_per_team=self.players_per_team, number_rounds=num_rounds, number_players=num_players, host_sets_tourney=True)
            seeded_tournament.save()

            teams = first + second
            seed_list = ""
            team_index = 1
            for t in teams:
                players = TournamentPlayer.objects.filter(team=t)
                t.pk = None
                t.team_index = team_index
                t.tournament = seeded_tournament
                t.wins = 0
                t.losses = 0
                t.round_robin_tournament = None
                t.group = None
                t.save()
                for player in players:
                    player.pk = None
                    player.tournament = seeded_tournament
                    player.team = t
                    player.save()
                # need to create new tournament players + teams for the seeded tournament
                # do that here, and store the seed list as well.
                seed_list += '{}.{};'.format(team_index, t.id)
                team_index += 1

            log_tournament("Seeded tournament seed_list: {}".format(seed_list), self)
            seeded_tournament.start(seed_list[:-1])
            self.knockout_tournament = seeded_tournament
            self.save()

    def update_game_log(self):
        # update the tournament game log here, which is a collection of all round robin games
        round_robin_tournaments = RoundRobinTournament.objects.filter(parent_tournament=self)
        game_log = '<br/><table class="table table-bordered table-condensed clot_table compact stripe cell-border" id="game_log_data_table">'
        game_log += '<thead><tr><th>Group</th><th>Match-Up</th><th>Game Link</th><th>State</th><th>Winning Team</th><th>Start Time</th><th>End Time</th></tr></thead>'
        game_log += '<tbody>'
        for t in round_robin_tournaments:
            games = TournamentGame.objects.filter(tournament=t)
            for game in games:
                game_log += '<tr>'
                game_log += '<td>{}</td>'.format(t.get_group().get_name())
                # create the match-up text for the game
                game_data = game.teams.split('.')
                team1 = game_data[0]
                team2 = game_data[1]
                team_1 = TournamentTeam.objects.filter(id=int(team1))
                if team_1:
                    team_2 = TournamentTeam.objects.filter(id=int(team2))
                    if team_2:
                        game_log += '<td data-search="{} {}">{}</td>'.format(get_team_data_no_clan(team_1[0]),
                                                                             get_team_data_no_clan(team_2[0]),
                                                                             get_matchup_data(team_1[0],
                                                                                              team_2[0]))
                game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(game.game_link)
                if game.is_finished:
                    finished_text = '<span class="text-success"><b>Finished</b></span>'
                else:
                    finished_text = '<span class="text-info">{}</span>'.format(game.current_state)
                game_log += '<td>{}</td>'.format(finished_text)

                if game.is_finished:
                    winning_team = '{}'.format(get_team_data(game.winning_team))
                else:
                    winning_team = ''
                game_log += '<td>{}</td>'.format(winning_team)
                time_to_boot_calculate = 0

                start_time = game.game_start_time.strftime("%b %d, %Y %H:%M:%S %p")

                # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
                end_time = game.game_finished_time.strftime(
                    "%b %d, %Y %H:%M:%S %p") if game.is_finished and game.game_finished_time else 'N/A'

                game_log += '<td>{}</td>'.format(start_time)
                game_log += '<td>{}</td>'.format(end_time)
                game_log += '</tr>'

        game_log += '</tbody></table>'
        self.game_log = game_log
        self.save()

class GroupStageTournamentGroup(models.Model):
    tournament = models.ForeignKey('GroupStageTournament', on_delete=models.CASCADE, blank=True, null=True, related_name='group_stage_tournament')
    first_place = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='first_place_group')
    second_place = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='second_place_group')
    group_number = models.IntegerField(default=0)
    round_robin_tournament = models.ForeignKey('RoundRobinTournament', on_delete=models.CASCADE, blank=True, null=True, related_name='round_robin_tournament')

    def get_name(self):
        return "Group {}".format(chr(64+self.group_number))


class RoundRobinTournament(Tournament):
    type = models.CharField(max_length=255, default="Round Robin")
    games_at_once = models.IntegerField(default=2)
    first_place = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='rr_first_place')
    second_place = models.ForeignKey('TournamentTeam', on_delete=models.SET_NULL, null=True, blank=True, related_name='rr_second_place')
    total_games = models.IntegerField(default=0)
    parent_tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, null=True, blank=True, related_name='rr_parent')
    games_left = models.TextField(default="", blank=True, null=True)
    random_teams = models.BooleanField(default=False)

    min_teams = 4

    def uses_byes(self):
        return False

    def games_created_at_once(self):
        return 2

    @property
    def current_rounds(self):
        return self.number_teams - 1

    @property
    def number_teams(self):
        return int(self.max_players / self.players_per_team)

    def get_group(self):
        tournament_group = GroupStageTournamentGroup.objects.filter(round_robin_tournament=self)
        if tournament_group:
            return tournament_group[0]

    def get_bracket_game_data(self):
        if self.bracket_game_data == "" or len(self.bracket_game_data) == 0:
            self.update_bracket_game_data()
        return self.bracket_game_data

    def update_bracket_game_data(self):
        # table should be all teams on the top and all teams on the bottom
        # the games are from the teams on the left matched up with the teams on the right
        teamsCol = TournamentTeam.objects.filter(round_robin_tournament=self).order_by('-wins')
        teamsRow = teamsCol
        log = '<div style="padding-top:25px;">'.format(self.id)
        log += '<table class="table table-bordered table-condensed clot_table"><tr><td>{}</td>'.format(self.name)
        for team in teamsRow:
            log += '<td>{}</td>'.format(get_team_data(team))
        log += '</tr>'
        teams_left_log = ""
        for team_left in teamsCol:
            teams_left_log += "TeamLeft: {}".format(get_team_data(team_left))
            log += '<tr>'
            log += '<td>{}</td>'.format(get_team_data(team_left))
            for team_top in teamsRow:
                teams_left_log += "TeamTop: {}".format(get_team_data(team_top))
                bg_color = ""
                # now we create the rows, where each row loops through team and compares
                # and looks up all games between then and team2
                game = TournamentGameEntry.objects.filter(team=team_top, team_opp=team_left, tournament=self)
                if game:
                    game = game[0]
                    if game.game.is_finished:
                        if game.game.winning_team is not None and game.game.winning_team.id == team_left.id:
                            bg_color = "#cde5b6;"  # light green - win
                        else:
                            bg_color = "#FBDFDF;"  # light red - lose
                    else:
                        bg_color = "#ffe7a3;"  # light yellow - in progress
                    log += '<td style="background-color:{}"><a href="{}" target="_blank">Game Link</a></td>'.format(bg_color, game.game.game_link)
                else:
                    # empty cell
                    log += '<td></td>'
            log += '</tr>'
        log += '</table></div><hr>'

        if not self.has_started:
            log_tournament(teams_left_log, self)
        self.bracket_game_data = log
        self.save()

    def process_new_games(self):
        # we need to create two lists of players
        teams_list = []
        group = self.get_group()
        tournament_teams = TournamentTeam.objects.filter(round_robin_tournament=self)
        found_bye = False
        shuffled_team_list_read_only = []
        if self.uses_byes():
            for team in tournament_teams:
                shuffled_team_list_read_only.append(team)

            shuffle(shuffled_team_list_read_only)

            # remove one team from the shuffled list before proceeding to create games
            for i in range(0, len(shuffled_team_list_read_only)):
                log_tournament("Looking at team: {}, with bye: {}".format(shuffled_team_list_read_only[i].id, shuffled_team_list_read_only[i].has_had_bye), self)
                if not shuffled_team_list_read_only[i].has_had_bye and not found_bye:
                    bye_team = shuffled_team_list_read_only[i]
                    bye_team.has_had_bye = True
                    bye_team.save()
                    found_bye = True
                    log_tournament("Team with bye: {}".format(shuffled_team_list_read_only[i].id), self)

                    # check to see if this is the last team that needs a bye. We include this team
                    # because there could be a chance that they do not get a game in the last two rounds due to
                    # the games they needed are for teams with byes
                    teams_with_byes = TournamentTeam.objects.filter(round_robin_tournament=self, has_had_bye=True)
                    if teams_with_byes.count() == len(shuffled_team_list_read_only):
                        # all teams have byes now, so include them all to make sure all games get created
                        log_tournament("Last team to get a bye: {}, add it to the list and make sure all games are created".format(shuffled_team_list_read_only[i].id), self)
                        teams_list.append(shuffled_team_list_read_only[i].id)
                else:
                    teams_list.append(shuffled_team_list_read_only[i].id)
        else:
            for team in tournament_teams:
                teams_list.append(team.id)
        matchups = list(itertools.combinations(teams_list, 2))
        shuffle(matchups)

        log_tournament("Teams to find matchups for: {}".format(teams_list), self)
        # first, are we finished?
        games = TournamentGame.objects.filter(tournament=self, is_finished=True)
        if games.count() == self.total_games and not self.is_finished:
            log_tournament("Found {} finished games with {} total in the RR, ending".format(games.count(), self.total_games), self)

            # we need to figure out the buchholz for every team in case there are ties
            # this will be used as the tie breaker

            # this process is expensive but it will only be run one time
            # first, lookup all teams and cache their wins/losses
            team_wins = {}
            team_losses = {}
            log_tournament("Total teams to iterate for caching wins/losses: {}".format(tournament_teams.count()), self)
            for team in tournament_teams:
                team_wins[team.id] = team.wins
                team_losses[team.id] = team.losses
                print("Team {} went {}-{}".format(team.id, team.wins, team.losses))

            # print("Team wins: {} and losses {}".format(team_wins, team_losses))
            team_buchholz = defaultdict(int)
            log_tournament("Total games in tournament: {}".format(games.count()), self)
            for game in games.iterator():
                team1 = game.teams.split('.')[0]
                team2 = game.teams.split('.')[1]

                # initialize
                if team1 not in team_buchholz:
                    team_buchholz[team1] = 0
                if team2 not in team_buchholz:
                    team_buchholz[team2] = 0

                team_buchholz[team1] += team_wins[int(team2)]
                team_buchholz[team2] += team_wins[int(team1)]

                team_buchholz[team1] -= team_losses[int(team2)]
                team_buchholz[team2] -= team_losses[int(team1)]


            # now loop through all the teams and print out their buchholz
            log_tournament("Team buccholz: {} entries: {}".format(len(team_buchholz), team_buchholz), self)
            for team, buchholz in team_buchholz.items():
                tournament_team = TournamentTeam.objects.filter(id=int(team))
                if tournament_team:
                    log_tournament("Updating buchholz for team {}: Buchholz {}".format(team, buchholz), self)
                    tournament_team[0].buchholz = buchholz
                    tournament_team[0].save()


            # now get the teams in order of wins...and see if there are any ties we need
            # to break
            teams = TournamentTeam.objects.filter(round_robin_tournament=self, group=group).order_by('-wins')
            team_buckets = defaultdict(list)
            log_tournament("Looping through {} teams in this group: ".format(teams.count()), self)
            for team in teams.iterator():
                if team.wins not in team_buckets:
                    team_buckets[team.wins] = []

                team_buckets[team.wins].append(team.id)

            # make a list of the wins
            current_place = 1
            team_buckets_wins = list(team_buckets)
            for wins, teams in team_buckets.items():
                if len(teams) == 1:
                    # base easy case, give them the place
                    tournament_team = TournamentTeam.objects.filter(id=int(teams[0]))
                    if tournament_team:
                        log_tournament("Team {} got {} place".format(teams[0], current_place), self)
                        tournament_team[0].place = current_place
                        tournament_team[0].save()
                        current_place += 1
                elif len(teams) == 2:
                    # two way tie, someone get this place, and someone gets the next one
                    # lookup their match-up and figure out who is first/second
                    tournament_game = TournamentGame.objects.filter(teams="{}.{}".format(teams[0], teams[1]))
                    if not tournament_game:
                        tournament_game = TournamentGame.objects.filter(teams="{}.{}".format(teams[1], teams[0]))
                        if not tournament_game:
                            log("Cannot find game between {} and {} in round-robin tie breaking".format(teams[0], teams[1]), self)

                    if tournament_game:
                        if tournament_game[0].winning_team.id == int(teams[0]):
                            first_team = int(teams[0])
                            second_team = int(teams[1])
                        else:
                            first_team = int(teams[1])
                            second_team = int(teams[0])
                            # first team won, give them the next place

                        # lookup both teams
                        first_tournament_team = TournamentTeam.objects.filter(id=first_team)
                        if first_tournament_team:
                            log_tournament("Team {} got {} place".format(first_team, current_place), self)
                            first_tournament_team[0].place = current_place
                            first_tournament_team[0].save()
                            current_place += 1

                        second_tournament_team = TournamentTeam.objects.filter(id=second_team)
                        if second_tournament_team:
                            log_tournament("Team {} got {} place".format(second_team, current_place), self)
                            second_tournament_team[0].place = current_place
                            second_tournament_team[0].save()
                            current_place += 1

                else:
                    log_tournament("3 or more teams tied...figure this out later", self)
                    # 3 or more teams tied...
                    # figure out who had the most wins between the games between these teams
                    # recursively break ties between them falling back to buchholz if there
                    # are still more than 2 teams
                    for team1 in teams:
                        for team2 in teams:
                            # lookup the game with team1 and team2, keep track of the total
                            # of wins between the games between these players
                            pass
                    pass

            # comment these next two lines out in order to test more tie-breakers
            self.is_finished = True
            self.save()
            return

        # cache all the games we know about so far that are in progress
        team_game_data = defaultdict(list)
        games = TournamentGame.objects.filter(tournament=self, is_finished=False)
        for game in games:
            team1 = int(game.teams.split('.')[0])
            team2 = int(game.teams.split('.')[1])

            team_game_data[team1].append(team2)
            team_game_data[team2].append(team1)

        # we need to remove all matchups from our list that cannot happen again
        # finished or in progress both count here
        possible_matchups = []
        log_tournament("Matchups before removing: {}".format(matchups), self)
        for matchup in matchups:
            game_data = "{}.{}".format(matchup[0], matchup[1])
            game = TournamentGame.objects.filter(tournament=self, teams=game_data)
            if game:
                continue
            else:
                # try again, reverting the match-up data
                game_data = "{}.{}".format(matchup[1], matchup[0])
                game = TournamentGame.objects.filter(tournament=self, teams=game_data)
                if game:
                    continue
            possible_matchups.append(matchup)

        log_tournament("Possible matchups in RR: {}".format(possible_matchups), self)
        # lookup the round for the round robin tournament
        # if there are an odd number of teams in the tournament, give out byes to a different team each round
        log_tournament(
            "Before grabbing round team_game_data: {}".format(team_game_data), self)
        games_created = []
        game_data1 = []
        game_data2 = []
        round = TournamentRound.objects.filter(tournament=self, round_number=1)
        # while current_iteration < iterations and iterations < 50:
        for matchup in possible_matchups:
            if round:
                team1 = matchup[0]
                team2 = matchup[1]
            else:
                log("No round found for round robin tournament {}!".format(self.id), LogLevel.critical)

            # see if both opponents have an available slot to play
            log_tournament("Current games team {}: {}, team {}: {}".format(team1, len(team_game_data[team1]), team2, len(team_game_data[team2])), self)
            if len(team_game_data[team1]) < self.games_at_once and len(team_game_data[team2]) < self.games_at_once:
                # go ahead and create the new game
                log_tournament("Games created for team {}: {}, team {}: {}".format(team1, games_created.count(team1), team2, games_created.count(team2)), self)
                if games_created.count(team1) < self.games_created_at_once() and games_created.count(team2) < self.games_created_at_once():
                    # need to update game lists with newly created games
                    # otherwise teams will get too many games
                    team_game_data[team1].append(team2)
                    team_game_data[team2].append(team1)
                    games_created.append(team1)
                    games_created.append(team2)
                    game_data1.append(team1)
                    game_data2.append(team2)
                    log_tournament("After game was validated, following teams have games created: {}".format(games_created), self)

        log_tournament("Teams with games created so far: {}, teams in division: {}, byes: {}".format(len(games_created), self.number_teams, self.uses_byes()), self)
        if self.uses_byes():
            # we always try to create the games as sometimes there will not be a fixed # due to the way byes
            # and match-ups happen
            self.create_games(game_data1, game_data2, round[0])
        else:
            self.create_games(game_data1, game_data2, round[0])

    def get_team_table(self, allow_buttons, logged_in, request_player):
        if not self.has_started:
            return super(Tournament, self).get_team_table(allow_buttons, logged_in, request_player)
        else:
            table = '<table class="table table-hover"><tr><th>Player</th><th>Record</th></tr>'
            teams = TournamentTeam.objects.filter(round_robin_tournament=self).order_by('-wins')
            for team in teams:
                team_players = TournamentPlayer.objects.filter(team=team)
                for player in team_players:
                    table += '<tr><td>'
                    if player.player.clan is not None:
                        table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                            player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

                    table += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                        player.player.token, player.player.name)

                    table += '<td>{}-{}</td>'.format(team.wins, team.losses)

                    table += '</tr>'
            table += "</table>"
            return table

    def create_games(self, game_data1, game_data2, round):
        # we have reached the point where we have enough games to create...create them, whatever we have
        for i in range(0, len(game_data1)):
            log_tournament(
                "Creating Round Robin game for tournament {} between {}  and {}".format(self.id, game_data1[i], game_data2[i]),
                self)
            game_data = "{}.{}".format(game_data1[i], game_data2[i])
            self.create_game(round, game_data)

    def start(self):
        # start the round robin tournament
        super(RoundRobinTournament, self).start()

        # There should be number_teams-1 games which is stored in self.number_rounds as well
        # based off of this start pairing up giving players no more than 2 games
        self.total_games = int((self.number_teams * (self.number_teams - 1)) / 2)
        log_tournament("Starting {}. Total games: {}, number_teams: {}".format(self.name, self.total_games, self.number_teams), self)
        self.save()

        # create the round
        tournament_round = TournamentRound(round_number=1, tournament=self, is_finished=False,
                                           number_games=self.number_teams)
        tournament_round.save()

        # now just process the games, which will in turn create them
        self.process_new_games()

    def should_create_game(self):
        return True

    def get_game_log(self):
        if self.game_log == "" or self.game_log is None:
            self.update_game_log()
        return self.game_log

    def update_game_log(self):
        if self.number_players == 0:
            players = TournamentPlayer.objects.filter(tournament=self)
            self.number_players = players.count()
            self.save()
        game_log = '<table class="table table-bordered table-condensed clot_table compact stripe cell-border" id="game_log_data_table">'
        game_log += '<thead><tr><th>Match-Up</th><th>Game Link</th><th>State</th><th>Winning Team</th><th>Start Time</th><th>End Time</th></tr></thead>'
        game_log += '<tbody>'
        games = TournamentGame.objects.filter(tournament=self)
        for game in games:
            game_log += '<tr>'
            # create the match-up text for the game
            game_data = game.teams.split('.')
            team1 = game_data[0]
            team2 = game_data[1]
            team_1 = TournamentTeam.objects.filter(id=int(team1))
            if team_1:
                team_2 = TournamentTeam.objects.filter(id=int(team2))
                if team_2:
                    if team_1[0].clan_league_clan is not None:
                        game_log += '<td data-search="{} {} {} {}">{}</td>'.format(team_1[0].clan_league_clan.clan.name,
                                                                                   team_2[0].clan_league_clan.clan.name,
                                                                                   get_team_data_no_clan(team_1[0]),
                                                                                   get_team_data_no_clan(team_2[0]),
                                                                                   get_matchup_data(team_1[0],
                                                                                                    team_2[0]))
                    else:
                        game_log += '<td data-search="{} {}">{}</td>'.format(get_team_data_no_clan(team_1[0]),
                                                                                   get_team_data_no_clan(team_2[0]),
                                                                                   get_matchup_data(team_1[0],
                                                                                                    team_2[0]))

            game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(game.game_link)

            if game.is_finished:
                finished_text = '<span class="text-success"><b>Finished</b></span>'
            else:
                finished_text = '<span class="text-info">{}</span>'.format(game.current_state)
            game_log += '<td>{}</td>'.format(finished_text)

            if game.is_finished:
                winning_team = '{}'.format(get_team_data(game.winning_team))
            else:
                winning_team = ''
            game_log += '<td>{}</td>'.format(winning_team)
            time_to_boot_calculate = 0

            start_time = game.game_start_time.strftime("%b %d, %Y %H:%M:%S %p")

            # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
            end_time = game.game_finished_time.strftime(
                "%b %d, %Y %H:%M:%S %p") if game.is_finished and game.game_finished_time else 'N/A'

            game_log += '<td>{}</td>'.format(start_time)
            game_log += '<td>{}</td>'.format(end_time)
            game_log += '</tr>'

        game_log += '</tbody></table>'
        self.game_log = game_log
        self.save()


class RoundRobinRandomTeams(RoundRobinTournament):

    def fill_teams(self):
        odd_number = False
        super(RoundRobinRandomTeams, self).fill_teams()

        # delete the first player if odd number
        if odd_number:
            player = TournamentPlayer.objects.filter(tournament=self)[0]
            player.delete()

    def get_game_log(self):
        if self.game_log == "" or len(self.game_log) == 0:
            self.update_game_log()
        return self.game_log

    def process_new_games(self):
        try:

            round = TournamentRound.objects.filter(tournament=self, round_number=1)
            if not round:
                log("Error finding round for RoundRobinRandomTeams...bailing from process_new_games", LogLevel.critical)
                return
            round = round[0]

            # custom random team logic
            # calculate the following before creating new teams/games
            # 1) Current games played per player
            # 2) Current teammates so far per player

            # cache all current player pairings
            player_previous_matchups = {}
            games = TournamentGame.objects.filter(tournament=self)

            # get the list of player ids
            players = []
            tplayers = TournamentPlayer.objects.filter(tournament=self)
            for p in tplayers:
                  players.append(p.player.token)

            if games.count() == 0:
                # tournament start, assign players to teams and delete the extras
                teams = TournamentTeam.objects.filter(tournament=self)
                for t in teams:
                    team_players = TournamentPlayer.objects.filter(team=t)
                    if not team_players.count():
                        log_tournament("Removing team {} due to insufficient players.".format(t.id), self)
                        t.delete()
                        continue
                    if team_players.count() == 1:
                        log_tournament("Player {} gets a bye in the first set of games.".format(player.player.token), self)
                    elif team_players.count() == 2:
                        player = team_players[0]
                        player2 = team_players[1]
                        log_tournament(
                            "Players {}, {} are on team {} to start".format(player.player.token, player2.player.token,
                                                                            t.id), self)

                teams = TournamentTeam.objects.filter(tournament=self)
                log_tournament("There are {} initial teams to create games for".format(teams.count()), self)
                game_data = ""
                for t in teams:
                    if len(game_data) == 0:
                        game_data += "{}.".format(t.id)
                    else:
                        game_data += str(t.id)
                        self.create_game(round, game_data)
                        game_data = ""

            # at this point, player_previous_matchups is the entire list of players who have played with who
            # we use this to decide how to randomly pair players moving forward

            # to create games, we first see which players need games
            # this number needs to be more than 4 in order to make games
            # we create brand new teams, place the players with teammates they have not received so far and create that
            # game
            # walk through and place players on the appropriate teams
            players_need_games = []
            games = TournamentGame.objects.filter(tournament=self)
            for game in games:
                if game.players is not None and len(game.players) > 0:
                    log_tournament("Players in game {}: ".format(game.players), self)
                    team1 = game.players.split('-')[0]
                    team2 = game.players.split('-')[1]

                    if team1.split('.')[0] not in player_previous_matchups:
                        player_previous_matchups[team1.split('.')[0]] = []
                    if team1.split('.')[1] not in player_previous_matchups:
                        player_previous_matchups[team1.split('.')[1]] = []
                    if team2.split('.')[0] not in player_previous_matchups:
                        player_previous_matchups[team2.split('.')[0]] = []
                    if team2.split('.')[1] not in player_previous_matchups:
                        player_previous_matchups[team2.split('.')[1]] = []

                    player_previous_matchups[team1.split('.')[0]].append(team1.split('.')[1])
                    player_previous_matchups[team1.split('.')[1]].append(team1.split('.')[0])
                    player_previous_matchups[team2.split('.')[0]].append(team2.split('.')[1])
                    player_previous_matchups[team2.split('.')[1]].append(team2.split('.')[0])

            # we need to remove all match-ups from our list that cannot happen again
            # finished or in progress both count here
            matchups = list(itertools.combinations(players, 2))
            possible_matchups = []
            log_tournament("Match-ups before removing: {}".format(len(matchups)), self)
            for matchup in matchups:
                player = matchup[0]
                player2 = matchup[1]
                if player2 in player_previous_matchups[str(player)] or player in player_previous_matchups[str(player2)]:
                    continue
                possible_matchups.append(matchup)

            log_tournament("Possible match-ups in RR: {}".format(len(possible_matchups)), self)

            # now that we have the possible list of match-ups let's go ahead and run our algorithm
            # we need at least 4 teams that need games, and there needs to be a valid combination of teams within these 4
            players_need_games = []
            unfinished_dict = defaultdict(int)
            for player in players:
                tplayers = TournamentPlayer.objects.filter(tournament=self, player__token=player)
                unfinished_games = 0
                for player in tplayers:
                    unfinished_games += get_games_unfinished_for_team(player.team.id, self)
                if player.id not in unfinished_dict:
                    unfinished_dict[player.id] = 0
                unfinished_dict[player.id] = unfinished_games
                if unfinished_games < self.games_at_once:
                    players_need_games.append(player)

            # sort by players with the least amount of games so they can try to get a game first


            log_tournament("{} players need games.".format(len(players_need_games)), self)

            if len(players_need_games) > (2*self.players_per_team):
                log_tournament("Enough players to try to create a new game. Running full algorithm.", self)

                players_create_teams = []
                for p in players_need_games:
                    for popp in players_need_games:
                        if p.id != popp.id and p.player.token not in player_previous_matchups[popp.player.token]:
                            players_create_teams.append((p, popp))
                            print("Possible team: {}.{}".format(p.player.token, popp.player.token))

                while len(players_create_teams) > 2:
                    if unfinished_dict[players_create_teams[0][0].id] >= self.games_at_once or unfinished_dict[players_create_teams[0][1].id] >= self.games_at_once:
                        players_create_teams.pop(0)
                        continue

                    # if either player in the first tuple is in the second, pop and continue
                    player1_id = players_create_teams[0][0].id
                    player2_id = players_create_teams[0][1].id
                    if player1_id == players_create_teams[1][0].id or player1_id == players_create_teams[1][1].id:
                        players_create_teams.pop(0)
                        continue
                    elif player2_id == players_create_teams[1][0].id or player2_id == players_create_teams[1][1].id:
                        players_create_teams.pop(0)
                        continue

                    if unfinished_dict[players_create_teams[1][0].id] >= self.games_at_once or unfinished_dict[players_create_teams[1][1].id] >= self.games_at_once:
                        players_create_teams.pop(1)
                        continue

                    log_tournament("Player sets needing games: {}".format(len(players_create_teams)), self)
                    # get the first two teams
                    team1 = players_create_teams[0]
                    team = TournamentTeam(tournament=self, max_games_at_once=self.games_at_once)
                    team.save()
                    team1_id = team.id
                    team1[0].team = team
                    team1[0].save()
                    print("Player {} on team1 {}".format(team1[0].player.token, team1[0].team.id))
                    team1[1].team = team
                    team1[1].save()
                    print("Player {} on team1 {}".format(team1[1].player.token, team1[1].team.id))

                    team2 = players_create_teams[1]
                    team = TournamentTeam(tournament=self, max_games_at_once=self.games_at_once)
                    team.save()
                    team2_id = team.id
                    team2[0].team = team
                    team2[0].save()
                    print("Player {} on team2 {}".format(team2[0].player.token, team2[0].team.id))
                    team2[1].team = team
                    team2[1].save()
                    print("Player {} on team2 {}".format(team2[1].player.token, team2[1].team.id))

                    game_data = '{}.{}'.format(team1_id, team2_id)
                    self.create_game(round, game_data)

                    unfinished_dict[players_create_teams[0][0].id] += 1
                    unfinished_dict[players_create_teams[0][1].id] += 1
                    unfinished_dict[players_create_teams[1][0].id] += 1
                    unfinished_dict[players_create_teams[1][1].id] += 1

                    players_create_teams.pop(0)
                    players_create_teams.pop(1)

        except:
            log_exception()

    def start(self, tournament_data):
        tplayers = TournamentPlayer.objects.filter(tournament=self)
        self.max_players = tplayers.count()
        self.save()

        super(RoundRobinRandomTeams, self).start()


    def get_bracket_game_data(self):
        return "There is no bracket or game data for this. Please see the game log tab for a history of the games."

    def get_start_locked_data(self):
        # returns the html for the tournament
        if self.current_filled_teams >= self.min_teams:
            return "<p>Are you sure you want to start this tournament?</p>"
        else:
            return "<p>You cannot start this tournament until the minimum number of players have joined</p>"

    @property
    def max_rounds(self):
        # based off of number of rounds calculate from max_rounds which will change when we actually
        # start the tournament, let's try to calculate it on the fly based on the max_players here
        return self.current_rounds

    @property
    def current_rounds(self):
        # based off of number of rounds calculate from max_rounds which will change when we actually
        # start the tournament, let's try to calculate it on the fly based on the max_players here
        return (TournamentPlayer.objects.filter(tournament=self).count() - 1)

    @property
    def current_filled_teams(self):
        return self.number_teams

    @property
    def can_start_tourney(self):
        # can start tourney walks the list of teams calculating how many we need based on
        # min_teams to start

        # if debugging we can always start it unless there are partial teams
        if settings.DEBUG:
            return True

        return (self.current_filled_teams >= self.min_teams)


    def get_team_table(self, allow_buttons, logged_in, request_player):
        if not self.has_started:
            return super(RoundRobinRandomTeams, self).get_team_table(allow_buttons, logged_in, request_player)
        else:
            table = '<table class="table table-hover"><tr><th>Player</th><th>Record</th><th>Rating</th></tr>'
            team_players = TournamentPlayer.objects.filter(tournament=self).order_by('-wins')
            for player in team_players:
                table += '<tr><td>'
                if player.player.clan is not None:
                    table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                        player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

                table += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                    player.player.token, player.player.name)

                table += '<td>{}-{}</td>'.format(player.wins, player.losses)
                table += '<td>{}</td>'.format(player.rating)

                table += '</tr>'
            table += "</table>"
            return table

    def update_game_log(self):
        game_log = '<table class="table table-bordered table-condensed clot_table compact stripe cell-border" id="game_log_data_table">'
        game_log += '<thead><tr><th>Match-Up</th><th>Game Link</th><th>State</th><th>Winning Team</th><th>Start Time</th><th>End Time</th></tr></thead>'
        game_log += '<tbody>'
        games = TournamentGame.objects.filter(tournament=self)
        for game in games:
            game_log += '<tr>'
            # create the match-up text for the game
            players = game.players.split('-')
            players1 = players[0].split('.')
            players2 = players[1].split('.')
            game_data = game.teams.split('.')
            team1 = game_data[0]
            team2 = game_data[1]
            winning_team_id = 0
            if game.winning_team:
                if game.winning_team.id == int(team1):
                    winning_team_id = int(team1)
                    winning_player_list = players1
                else:
                    winning_team_id = int(team2)
                    winning_player_list = players2

            game_log += '<td data-search="{} {}">{}</td>'.format(get_team_data_no_clan_player_list(players1),
                                                                 get_team_data_no_clan_player_list(players2),
                                                                 get_matchup_data_player_list(players1,
                                                                                  players2))

            game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(game.game_link)

            if game.is_finished:
                finished_text = '<span class="text-success"><b>Finished</b></span>'
            else:
                finished_text = '<span class="text-info">{}</span>'.format(game.current_state)
            game_log += '<td>{}</td>'.format(finished_text)

            if game.is_finished and winning_team_id != 0:
                winning_team = '{}'.format(get_team_data_player_list(winning_player_list))
            else:
                winning_team = ''
            game_log += '<td>{}</td>'.format(winning_team)
            time_to_boot_calculate = 0

            start_time = game.game_start_time.strftime("%b %d, %Y %H:%M:%S %p")

            # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
            end_time = game.game_finished_time.strftime(
                "%b %d, %Y %H:%M:%S %p") if game.is_finished and game.game_finished_time else 'N/A'

            game_log += '<td>{}</td>'.format(start_time)
            game_log += '<td>{}</td>'.format(end_time)
            game_log += '</tr>'

        game_log += '</tbody></table>'
        self.game_log = game_log
        self.save()


# Tournament round
# represents a round in the tournament
class TournamentRound(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    games = models.TextField(blank=True, null=True)
    round_number = models.IntegerField(default=0)
    is_finished = models.BooleanField(default=False)
    number_games = models.IntegerField(default=0)

    def get_round_number(self):
        print("Getting round #: tournament name {}, round #: {}".format(self.tournament.name, self.round_number))
        return self.round_number

    def __str__(self):
        return "Tournament {}, round {}, is_finished? {}, number_games {}".format(self.tournament.name, self.round_number, self.is_finished, self.number_games)


# Tournament Team
# Each tournament team belongs to a tournament
class TournamentTeam(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    rating = models.IntegerField(default=1500)
    buchholz = models.IntegerField(default=0)
    players = models.IntegerField(default=1)
    team_index = models.IntegerField(default=0, db_index=True)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    seed = models.IntegerField(default=0)
    group = models.ForeignKey('GroupStageTournamentGroup', on_delete=models.DO_NOTHING, blank=True, null=True)
    round_robin_tournament = models.ForeignKey('RoundRobinTournament', on_delete=models.DO_NOTHING, blank=True, null=True, related_name='rr_tournament')
    clan_league_clan = models.ForeignKey('ClanLeagueDivisionClan', on_delete=models.DO_NOTHING, blank=True, null=True, related_name='clan_league_clan')
    clan_league_division = models.ForeignKey('ClanLeagueDivision', on_delete=models.CASCADE, blank=True, null=True, related_name='clan_league_division')
    place = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    max_games_at_once = models.IntegerField(default=2, blank=True, null=True)
    has_had_bye = models.BooleanField(default=False)
    joined_time = models.DateTimeField(default=timezone.now)
    leave_after_game = models.BooleanField(default=False, blank=True, null=True)
    last_boot_time = models.DateTimeField(blank=True, null=True)
    on_vacation = models.BooleanField(default=False)
    ranked = models.BooleanField(default=False)
    process_games_since_created = models.IntegerField(default=0, blank=True, null=True)

    def update_max_games_at_once(self, games):
        print("Updating max games to {}".format(games))
        if games.isnumeric() and int(games) <= self.tournament.get_max_games_at_once() and int(games) >= 1:
            self.max_games_at_once = int(games)
            self.save()

    def get_max_games_at_once_option(self):
        data = '<select id="max_games">'
        for i in range(1, self.tournament.get_max_games_at_once()+1):
            if i == self.max_games_at_once:
                data += '<option value="{}" data-games="{}" data-team="{}" selected>{} games</option>'.format(i, i, self.id, i)
            else:
                data += '<option value="{}" data-games="{}" data-team="{}">{} games</option>'.format(i, i, self.id, i)

        data += '</select>'
        return data

    def __str__(self):
        players = TournamentPlayer.objects.filter(team=self)
        player_str = ""
        for player in players:
            player_str += "{},".format(player.player.name)
        return "Team {}: {}".format(self.id, player_str)


    def __str__(self):
        players = TournamentPlayer.objects.filter(team=self)
        team_str = ""
        for player in players:
            team_str += "{}".format(player.player.name)
        return "{} Team {}, {}-{}: {}".format(self.tournament.name, self.id, self.wins, self.losses, team_str)


class TournamentGameEntry(models.Model):
    team = models.ForeignKey('TournamentTeam', on_delete=models.CASCADE, related_name='team')
    team_opp = models.ForeignKey('TournamentTeam', on_delete=models.DO_NOTHING, related_name='team_opp')
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, related_name='game', blank=True, null=True)
    is_finished = models.BooleanField(default=False, db_index=True)
    created_date = models.DateTimeField(default=timezone.now, db_index=True)
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, related_name='tournament', blank=True, null=True)
    round = models.ForeignKey('TournamentRound', on_delete=models.CASCADE, related_name='tournament_round', blank=True, null=True)

    def __str__(self):
        return "Game Entry in Tournament {}, between {} and {}, is_finished: {}, round id: {}".format(self.tournament.name, self.team.id, self.team_opp.id, self.is_finished, self.game.round.id)

# Tournament Game Implementation
# Each tournament game belongs to a tournament, and a round
# tournament round
class TournamentGame(models.Model):
    team_game = models.BooleanField(default=False)
    players_per_team = models.IntegerField(default=1)
    game_link = models.CharField(max_length=255, null=True)
    gameid = models.CharField(max_length=255, default="Invalid game id", db_index=True)
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    teams = models.CharField(max_length=255, null=True, db_index=True)
    players = models.CharField(max_length=255, null=True, blank=True)
    round = models.ForeignKey('TournamentRound', on_delete=models.DO_NOTHING)
    is_finished = models.BooleanField(default=False, db_index=True)
    outcome = models.CharField(max_length=255, null=True, blank=True)
    winning_team = models.ForeignKey('TournamentTeam', null=True, on_delete=models.DO_NOTHING, blank=True)
    game_finished_time = models.DateTimeField(blank=True, null=True, db_index=True)
    game_boot_time = models.DateTimeField(blank=True, null=True)
    current_state = models.CharField(max_length=255, null=True, blank=True)
    needs_recreation = models.BooleanField(default=False, blank=True, null=True)
    game_start_time = models.DateTimeField(default=timezone.now, db_index=True)
    mentioned = models.BooleanField(default=False, blank=True, null=True)
    game_log_sent = models.BooleanField(default=False, blank=True, null=True, db_index=True)
    no_winning_team_log_sent = models.BooleanField(default=False, blank=True, null=True)
    betting_open = models.BooleanField(default=True)
    templateid = models.IntegerField(default=0, blank=True, null=True)

    def __str__(self):
        return "Round {} game in {} between {}. Game ID ({}) Finished? {}".format(self.round.round_number, self.tournament.name, self.teams, self.gameid, self.is_finished)

    def create_initial_lines_ratings(self, ratings1, ratings2):
        cb = get_clotbook()
        cb.create_initial_odds_for_game(self, ratings1, ratings2)

    def create_initial_lines(self):
        players1 = self.players.split('-')[0]
        players2 = self.players.split('-')[1]

        ratings1 = 0
        players1 = players1.split('.')
        for p in players1:
            player = Player.objects.filter(token=p)
            if player:
                ratings1 += player[0].rating
        ratings1 = ratings1 / len(players1)

        ratings2 = 0
        players2 = players2.split('.')
        for p in players2:
            player = Player.objects.filter(token=p)
            if player:
                ratings2 += player[0].rating
        ratings2 = ratings2 / len(players2)

        cb = get_clotbook()
        cb.create_initial_odds_for_game(self, ratings1, ratings2)

    def finish_game_with_info(self, game_info):
        self.finish_game()

        # get the child tournament object and see if there is some post processing needed for games with specific
        # game info
        child_tournament = find_tournament_by_id(self.tournament, True)
        if child_tournament:
            child_tournament.handle_finish_game_with_info(game_info)

    def finish_game(self):
        self.is_finished = True

        self.current_state = "Finished"
        log_tournament("Finish Game/Game Entry: {}".format(self.teams), self.tournament)
        team1 = self.teams.split('.')[0]
        team2 = self.teams.split('.')[1]

        tournament_team1 = get_team_by_id(self.tournament, int(team1))
        tournament_team2 = get_team_by_id(self.tournament, int(team2))

        # if tournament is actually a sub-tournament, look for TournamentTeam in parent tournament
        if not tournament_team1:
            child_tournament = find_tournament_by_id(self.tournament, True)
            tournament_team1 = get_team_by_id(child_tournament.parent_tournament, int(team1))
        if not tournament_team2:
            child_tournament = find_tournament_by_id(self.tournament, True)
            tournament_team2 = get_team_by_id(child_tournament.parent_tournament, int(team2))

        if tournament_team1 and tournament_team2:
            team1Entry = TournamentGameEntry.objects.filter(team=tournament_team1[0], team_opp=tournament_team2[0], game=self.pk,
                                             tournament=self.tournament)
            if team1Entry:
                team1Entry[0].is_finished = True
                team1Entry[0].save()
            else:
                log_tournament("finish_game(): Cannot find game entry #1 or team {}".format(team1), self.tournament)

            team2Entry = TournamentGameEntry.objects.filter(team=tournament_team2[0], team_opp=tournament_team1[0], game=self.pk,
                                             tournament=self.tournament)
            if team2Entry:
                team2Entry[0].is_finished = True
                team2Entry[0].save()
            else:
                log_tournament("finish_game(): Cannot find game entry #2 for team {}".format(team2), self.tournament)

            # handle any clotbook updates
            cb = get_clotbook()
            cb.finish_game(self)

            self.game_finished_time = timezone.now()
            self.save()
            self.handle_tournament_player_updates()
        else:
            log_tournament("Could not find tournament teams with ids: {} {} in tournament {}".format(team1, team2, self.tournament.id), self.tournament)

    def create_entry(self, team1, team2):
        team1Entry = TournamentGameEntry(team=team1, team_opp=team2, game=self,
                                         tournament=self.tournament, round=self.round)
        team1Entry.save()

        team2Entry = TournamentGameEntry(team=team2, team_opp=team1, game=self,
                                         tournament=self.tournament, round=self.round)
        team2Entry.save()

    def save_with_entry(self):
        log_tournament("Save Internal for: {}".format(self.teams), self.tournament)
        team1 = self.teams.split('.')[0]
        team2 = self.teams.split('.')[1]

        self.save()

        tournament_team1 = get_team_by_id(self.tournament, int(team1))
        tournament_team2 = get_team_by_id(self.tournament, int(team2))
        if tournament_team1 and tournament_team2:
            self.create_entry(tournament_team1[0], tournament_team2[0])
        else:
            # try to lookup the teams based on rr tournament
            tournament_team1 = get_team_by_id(self.tournament.parent_tournament, int(team1))
            tournament_team2 = get_team_by_id(self.tournament.parent_tournament, int(team2))
            if tournament_team1 and tournament_team2:
                self.create_entry(tournament_team1[0], tournament_team2[0])
            else:
                log("Cannot find teams {} or {} in tournament {}-{}".format(team1, team2, self.tournament.id, self.tournament.name), LogLevel.critical)

    def handle_tournament_player_updates(self):
        # grab all players on both teams...increase their win/loss counts respectively...but also their rating
        if self.is_finished and self.winning_team is not None:
            winning_team_id = self.winning_team.id
            if int(self.teams.split('.')[0]) == winning_team_id:
                losing_team_id = int(self.teams.split('.')[1])
                losing_players = self.players.split('-')[1].split('.')
                winning_players = self.players.split('-')[0].split('.')
            else:
                losing_team_id = int(self.teams.split('.')[0])
                losing_players = self.players.split('-')[0].split('.')
                winning_players = self.players.split('-')[1].split('.')

            log("Team {} won, {} lost. Updating individual TournamentPlayer ratings".format(winning_team_id, losing_team_id), LogLevel.game)
            average_tplayer_win_rating = 0
            average_tplayer_loss_rating = 0

            average_player_win_rating = 0
            average_player_loss_rating = 0

            for id in winning_players:
                tplayer = TournamentPlayer.objects.filter(player__token=int(id))
                if tplayer:
                    tplayer = tplayer[0]
                    average_tplayer_win_rating += tplayer.rating
                    average_player_win_rating += tplayer.player.rating

            for id in losing_players:
                tplayer = TournamentPlayer.objects.filter(player__token=int(id))
                if tplayer:
                    tplayer = tplayer[0]
                    average_tplayer_loss_rating += tplayer.rating
                    average_player_loss_rating += tplayer.player.rating

            average_tplayer_loss_rating /= len(winning_players)
            average_tplayer_win_rating /= len(winning_players)
            average_player_win_rating /= len(winning_players)
            average_player_loss_rating /= len(winning_players)

            for id in winning_players:
                tplayer = TournamentPlayer.objects.filter(player__token=int(id))
                if tplayer:
                    player = tplayer[0]
                    player.wins += 1
                    player.rating = calculate_new_elo_rating(True, player.rating, average_tplayer_loss_rating)
                    player.save()

                    player.player.wins += 1
                    player.player.rating = calculate_new_elo_rating(True, player.player.rating, average_player_loss_rating)
                    player.player.save()
            for id in losing_players:
                tplayer = TournamentPlayer.objects.filter(player__token=int(id))
                if tplayer:
                    player = tplayer[0]
                    player.rating = calculate_new_elo_rating(False, player.rating, average_tplayer_win_rating)
                    player.losses += 1
                    player.save()

                    player.player.losses += 1
                    player.player.rating = calculate_new_elo_rating(False, player.player.rating, average_player_win_rating)
                    player.player.save()
        else:
            log("Skipping game {} as there is no winning team".format(self.id), LogLevel.game)

    # Returns a list of lists of player tokens
    # Each sublist pertains to team in same order as game.players/game.teams
    def get_player_tokens(self):
        if self.players:
            team_tokens = self.players.split("-")
            players = []

            for team in team_tokens:
                players.append(team.split("."))
        else:
            teams = self.teams.split(".")
            players = []

            for team in teams:
                tplayers = TournamentPlayer.objects.filter(team__id=int(team))

                team_players = []
                for tplayer in tplayers:
                    team_players.append(tplayer.player.token)
                players.append(team_players)
        return players

# Object to represent a tournament player
# A tournament player is a single entity in a tournament team, and included in a team size=1
# Each player belongs to a tournament and a corresponding WZ player
class TournamentPlayer(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    team = models.ForeignKey('TournamentTeam', on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.DO_NOTHING)
    rating = models.IntegerField(default=1500)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)

    def __str__(self):
        return "Tournament {}, Team {}, Player {}".format(self.tournament.name, self.team.id, self.player.token)

    def get_max_games_at_once_option(self):
        return self.team.get_max_games_at_once_option()

class TournamentInvite(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.DO_NOTHING)
    joined = models.BooleanField(default=False)
    notified = models.BooleanField(default=False)
    created_date = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return "Tournament {}, player {}, joined? {}".format(self.tournament.name, self.player.name, self.joined)


class MonthlyTemplateRotationMonth(TournamentRound):
    template = models.IntegerField(default=0)
    month = models.IntegerField(default=0)
    year = models.IntegerField(default=0)

    month_str = ["Unknown",
                  "January",
                  "Febuary",
                  "March",
                  "April",
                  "May",
                  "June",
                  "July",
                  "August",
                  "September",
                  "October",
                  "November",
                  "December"]

    def get_round_number(self):
        return "MTC: {}, {}".format(self.month_str[self.month], self.year)

    def __str__(self):
        return "pk: {}, MTC Month in {}, Month: {}, Year: {}, Template: {}".format(self.id, self.tournament.name, self.month, self.year, self.template)

class MonthlyTemplateRotation(Tournament):
    type = models.CharField(max_length=255, blank=True, null=True, default="Monthly Template Circuit")
    current_template = models.IntegerField(default=0)

    min_teams = 2
    month_str = ["Unknown",
                  "January",
                  "Febuary",
                  "March",
                  "April",
                  "May",
                  "June",
                  "July",
                  "August",
                  "September",
                  "October",
                  "November",
                  "December"]

    def __str__(self):
        return "MTC: {}, id: {}, first template: {}".format(self.name, self.id, self.template)

    def get_game_name(self):
        current_month = self.get_current_month()
        return "MTC | {}, {} - {}".format(self.month_str[current_month.month], current_month.year, self.name)

    def should_show_max_games_option(self):
        return True

    def get_template_settings_table(self):
        template_settings = '<div class="row"><div class="container">'
        template_settings += '<table class="table table-hover"><tr><th>Month</th><th>Year</th><th>Template</th></tr>'

        months = MonthlyTemplateRotationMonth.objects.filter(tournament=self).order_by('pk')
        for month in months:
            template = month.template
            if template == 0:
                template = "The host has not set the template for this month yet."
            else:
                template = '<a href="https://warzone.com/MultiPlayer?TemplateID={}" target="_blank">View Template</a>'.format(month.template)

            template_settings += '<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(self.month_str[month.month], month.year, template)

        template_settings += '</table></div></div>'
        return template_settings

    @property
    def show_invite_button(self):
        return True

    def get_month_index(self, month_text):
        for month_index, month in enumerate(self.month_str):
            if month == month_text:
                return month_index

    def league_editor_button_text(self):
        return "Open {} editor".format(self.type)

    def handle_finish_game_with_info(self, game_info):
        # handle the game info here
        log_tournament("[MTC] {}: Finished game_info: {}".format(self.name, game_info), self)
        if 'players' in game_info:
            players_data = game_info['players']
            for data in players_data:
                if 'state' in data and (data['state'] == 'Invited' or data['state'] == 'Booted' or data['state'] == 'Declined'):
                    if 'id' in data:
                        token = data['id']
                        player = TournamentPlayer.objects.filter(player__token=token)
                        if player:
                            # did we boot this past week?
                            if player[0].team.last_boot_time is not None:
                                if player[0].team.last_boot_time.replace(tzinfo=pytz.UTC) > (datetime.datetime.utcnow().replace(tzinfo=pytz.UTC) - datetime.timedelta(days=7)):
                                    # last boot time was in this past week..remove player
                                    log_tournament("Removing player {} ({}) from MTC {}".format(player[0].player.name, player[0].player.token, self.name), self)
                                    player[0].team.active = False

                                    # also set joined=False on the invite
                                    invite = TournamentInvite.objects.filter(player=player[0].player, tournament=self)
                                    if invite:
                                        invite[0].joined = False
                                        invite[0].save()

                            # regardless we need to log the current time
                            player[0].team.last_boot_time = datetime.datetime.utcnow()
                            player[0].team.save()

    def is_player_allowed_join(self, player):
        return is_player_allowed_join(player, self.current_template)

    def update_league_editing(self, data):
        # data is a dict of the values we must save
        # parse that and save to the DB
        # load the json
        ret = {}
        data_json = json.loads(data)

        # loop through the data, checking the template settings and returning error if ALL
        # month templates are invalid
        # we know how the data comes back, let's now grab each row (up to 6) and see if the templates are
        # valid and we can save them
        for key, month in data_json.items():
               if 'mtc-month' in month and 'mtc-year' in month and 'mtc-template' in month:
                   month_index = self.get_month_index(month['mtc-month'])

                   # load the month, and update the values
                   month_obj = MonthlyTemplateRotationMonth.objects.filter(tournament=self, month=month_index, year=int(month['mtc-year']))
                   if month_obj:
                       print("Updating month {} with template {}".format(month['mtc-month'], month['mtc-template']))
                       month_obj[0].template = month['mtc-template']
                       month_obj[0].save()
        ret.update({'editing_window_status_text': "Monthly Template Circuit data updated successfully! <br/> Remember, the next month won't start unless there's a valid template set for it."})

        return ret

    def get_league_editor(self):
        # we are only allowed to edit months that have not started yet, so any month that is
        # greater than the current month in the current year, and all months in the next year
        month_data = []
        current_month = get_current_month_year()[0]
        current_year = get_current_month_year()[1]
        months = MonthlyTemplateRotationMonth.objects.filter(tournament=self).order_by('pk')
        for month in months:
            if month.year >= current_year:
                # we're good, include it
                if month.month >= current_month:
                    # also good, include it
                    month_data.append(month)

        api = API()
        editor = '<table class="table table-hover" id="league-editing-data-table">'
        editor += '<tr><th>Circuit Month</th><th>Circuit Year</th><th>Template ID</th></tr>'
        for month in month_data:
            invalid_template = (month.template == 0)
            # create the input fields to allow the user to change the template for the month
            ret = {}
            if not invalid_template:
                ret = api.api_create_fake_game_and_get_settings(month.template)

            if 'Pace' not in ret:
                invalid_template = True

            if not invalid_template:
                if ret['Pace'] == 'RealTime':
                    fmt = '{0.minutes} minutes {0.seconds} seconds'
                else:
                    fmt = '{0.days} days {0.hours} hours'

                directbootTimeMinutes = ret['settings']['DirectBoot']
                autobootTimeMinutes = ret['settings']['AutoBoot']

                pace = ""
                if 'directBoot' in ret:
                    directBoot = ret['directBoot']
                    pace += "Direct Boot: {}".format(directBoot)
                if 'autoBoot' in ret:
                    autoBoot = ret['autoBoot']
                    pace += " Auto Boot: {}".format(autoBoot)

                class_style = "border border-success"
            else:
                class_style = "border border-danger"
                month.template = 0  # overwrite the users option
                month.save()
                pace = "Unknown! Please enter a valid template"

            print("Pace: {}".format(pace))
            editor += '<tr><td id="mtc-month">{}</td><td id="mtc-year">{}</td><td><input type="number" class="{}" size="15" id="mtc-template" name="mtc-template" value="{}" /><br />Pace: {}</td></tr>'.format(self.month_str[month.month], month.year, class_style, month.template, pace)

        editor += '</table>'
        return editor

    def get_current_template_id(self):
        # for now simply return the current one
        return self.current_template

    def get_join_leave(self, allow_buttons, logged_in, request_player):
        # get's the join/leave buttons based on the player wanting to join
        join = ''
        if logged_in:
            # is the player currently active in the tournament?
            tournament_player = TournamentPlayer.objects.filter(player=request_player, tournament=self)
            if tournament_player and not tournament_player[0].team.active and allow_buttons:
                join += '<button type="button" class="btn btn-info" name="slot" id="join">Join Circuit</button>&nbsp;<button type="button" class="btn btn-info" name="slot" id="decline" disabled="disabled">Leave Circuit</button>'
            elif tournament_player and tournament_player[0].team.active:
                join += '<button type="button" class="btn btn-info" name="slot" id="join" disabled="disabled">Join Circuit</button>&nbsp;<button type="button" class="btn btn-info" name="slot" id="decline">Leave Circuit</button>'
            elif not tournament_player and allow_buttons:
                join += '<button type="button" class="btn btn-info" name="slot" id="join">Join Circuit</button>&nbsp;<button type="button" class="btn btn-info" name="slot" id="decline" disabled="disabled">Leave Circuit</button>'

        if logged_in and not is_player_allowed_join(request_player, self.get_current_template_id()):
            join += "&nbsp;Sorry, you do not meet the template requirements for this month. You will not get any games until you meet the requirements."

        return join

    def create_new_month(self, month, year, template):
        # creates a new month with the specified month/year/template
        #print("Try creating new month with template: {}, month: {}, year: {}".format(template, month, year))
        existing_month = MonthlyTemplateRotationMonth.objects.filter(month=month, year=year, tournament=self)
        if not existing_month:
            #print("Creating new month with template: {}, month: {}, year: {}".format(template, month, year))
            circuit_month = MonthlyTemplateRotationMonth(tournament=self, month=month, year=year, template=template)
            circuit_month.save()

    def get_next_month(self):
        current_month = get_current_month_year()[0]
        current_year = get_current_month_year()[1]
        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

        print("Looking for next month: {} {}".format(current_month, current_year))
        next_month = MonthlyTemplateRotationMonth.objects.filter(tournament=self, month=current_month, year=current_year)
        if next_month:
            return next_month[0]

        return None

    def get_current_month(self):
        current_month = MonthlyTemplateRotationMonth.objects.filter(tournament=self, month=get_current_month_year()[0], year=get_current_month_year()[1])
        return current_month[0]

    def get_template_data_text(self):
        return ""

    def process_new_games(self):
        print("Handling process new games for {}".format(self.name))
        self.ensure_6_months()
        # process new games for the circuit
        # max games by default is 2
        #
        # here's the algorithm in a nutshell
        # Loop through all players
        # See how many games each player currently has, if less than 2, find an opponent
        # also with less than 2 games that they haven't played in this circuit...
        processNewGamesLog = ""
        current_circuit_month = self.get_current_month()
        if current_circuit_month:
            self.current_template = current_circuit_month.template
            self.template = current_circuit_month.template
            self.save()

        processNewGamesLog += "MTC {} Process New Games, current template = {} ".format(self.name, self.current_template)
        # the main loop
        # check the template id, if it's not 0 we've validated that it's a valid template
        if self.current_template != 0:
            team_list = []
            tournament_teams = TournamentTeam.objects.filter(tournament=self, active=True).order_by('-rating') # order by rating descending
            for team in tournament_teams.iterator():
                # only add teams that aren't on vacation
                if not self.is_team_on_vacation(team):
                    team_list.append(team)
                # look up how many match-ups this team has currently that are not finished
                # if less then 2 find a player closest in rating
            team_list_opp = team_list.copy()
            for team in team_list:
                shuffle(team_list_opp)  # so team comparisons are random

                # can we get a game created?
                tournament_player = TournamentPlayer.objects.filter(team=team, tournament=self)
                if tournament_player and not is_player_allowed_join(tournament_player[0].player, self.get_current_template_id()):
                    processNewGamesLog += "Player {} cannot get a game created on template {} due to restrictions".format(tournament_player[0].player.name, self.get_current_template_id())
                    continue  # we cannot have games on this template....whoooops!!!!

                # this is the highest rated team, how many games do they have?
                num_games = get_games_unfinished_for_team(team.id, current_circuit_month.tournament)
                while num_games < team.max_games_at_once:
                    processNewGamesLog += "Found {} unfinished games for team {} ".format(num_games, team.id)
                    # create as many games as we can
                    for team_opp in team_list_opp:
                        if num_games == team.max_games_at_once:
                            break

                        # requirements are the opposing team cannot have 2 games, and these opponents cannot
                        # already be in a game together
                        if team.id != team_opp.id:
                            # can the opponent get a game created
                            tournament_player_opp = TournamentPlayer.objects.filter(team=team_opp, tournament=self)
                            if tournament_player_opp and not is_player_allowed_join(tournament_player_opp[0].player, self.get_current_template_id()):
                                processNewGamesLog += "Player {} cannot get a game created on template {} due to restrictions".format(tournament_player[0].player.name, self.get_current_template_id())
                                continue  # we cannot get any games created

                            processNewGamesLog += "Trying to match team {} and team {} ".format(team.id, team_opp.id)
                            game_together = TournamentGameEntry.objects.filter(team=team.id, team_opp=team_opp.id, game__round=current_circuit_month)
                            if game_together:
                                processNewGamesLog += "Teams already have a game together!"
                                continue

                            # check the opp for 2 games, and make sure we didn't already play this player in this round
                            num_games_opp = get_games_unfinished_for_team(team_opp.id, current_circuit_month.tournament)
                            processNewGamesLog += "Team_opp {} has {} games currently ".format(team_opp.id, num_games_opp)
                            # need to keep track of how many times we've "tried" to match up against a player...maybe loop twice with this condition?
                            if num_games_opp < team_opp.max_games_at_once and not did_teams_play_in_round(team.id, team_opp.id, current_circuit_month) and not did_play_games_against_since_finished(team, team_opp, self, 3):
                                # create the game, increase num_games so we bail out of the while loop for this team
                                processNewGamesLog += "Teams {} and {} did not play in round {} ".format(team.id, team_opp.id, current_circuit_month.id)
                                game_data = "{}.{}".format(team.id, team_opp.id)
                                self.create_game(current_circuit_month, game_data)
                                processNewGamesLog += "Creating game between: {} and {} ".format(team.id, team_opp.id)
                                num_games = get_games_unfinished_for_team(team.id, current_circuit_month.tournament)
                        else:
                            continue  # comparing the same teams, move on

                    if num_games < team.max_games_at_once:  # break if we have less than what we want that is fine, we will try again
                        break
        pngl = ProcessNewGamesLog(tournament=self, msg=processNewGamesLog, level=LogLevel.process_new_games)
        pngl.save()

    def get_team_table(self, allow_buttons, logged_in, request_player):
        # override the parent method to return the buttons to join the MTC or leave if already
        # joined
        table = ''

        # a few overrides on the pass in values
        in_tournament = False
        tournament_player = TournamentPlayer.objects.filter(player=request_player, tournament=self.id)
        if tournament_player:
            in_tournament = True

        tournamentteams = TournamentTeam.objects.filter(tournament=self.id, active=True).order_by('-rating', '-wins')
        if tournamentteams:
            table += '<table class="table table-hover">'
            table += '<tr><th>Rank</th><th>Player</th><th>Rating</th>'
            if request_player and (request_player.id == self.created_by.id):
                table += '<th>Manage</th>'
            table += '</tr>'
            team_index = 1
            ordered_team_data = []

            # for good measure
            self.number_players = tournamentteams.count()
            self.save()
            unranked_data = []
            ranked_data = []
            for team in tournamentteams:
                if self.players_per_team > 1:
                    table += "<tr><td><b>Team {} </b></td></tr>".format(team.team_index)

                team_players = TournamentPlayer.objects.filter(team=team)
                if team_players:

                    for player in team_players:
                        pass  # do we want multiple teams in MTC? who knows...

                    ranked = False
                    team_data_internal = ""
                    rating = team.rating
                    # lookup how many games this team has completed in the last 3 months
                    # if 10 or more, then display their rating
                    games_completed_3_months = get_games_finished_for_team_since(team.id, self,
                                                                                 90)  # all games completed within last 90 days
                    if games_completed_3_months >= 12 and not team.on_vacation:
                        team_data_internal = '<tr><td>#{}</td><td>'.format(team_index)
                        team_index += 1
                        ranked = True
                    else:
                        team_data_internal = '<tr><td>Unranked</td><td>'

                    team_data_internal += get_tournament_player_data(team_players[0])
                    team_data_internal += '</td>'
                    team_data_internal += '<td>{}</td>'.format(rating)

                    if request_player and (request_player.id == self.created_by.id):
                        team_data_internal += '<td><button type="button" class="btn btn-info btn-sm player_status_change" data-action="decline" data-team="{}" name="slot" id="decline-{}">Remove From Circuit</button></td>'.format(team.id, team.id)
                    team_data_internal += '</tr>'

                    if ranked:
                        ranked_data.append(team_data_internal)
                    else:
                        unranked_data.append(team_data_internal)

            # combine the ranked + unranked lists
            ordered_data = ranked_data + unranked_data
            for team_data in ordered_data:
                table += team_data
            table += "</table>"

        return table

    def join_tournament(self, token, buttonid):
        # if we get called we're definitely already logged in
        # parse the join button, and join the slot
        log("Player {} joining MTC {}".format(token, self.name), LogLevel.informational)
        player = Player.objects.filter(token=token)
        if not player:
            raise Exception("Player with token {} not found".format(token))

        # if we're start locked we must bail, but you can join the
        if self.start_locked:
            raise Exception("The host is trying to start the tournament or it has already started.")

        # make sure this player isn't already in the tournament
        tournament_player = TournamentPlayer.objects.filter(player=player[0], tournament=self.id)
        if tournament_player:
            if not tournament_player[0].team.active:
                # set active to true and move on
                log_tournament("Team {} has become active".format(tournament_player[0].team.id), self)
                tournament_player[0].team.active = True
                tournament_player[0].team.save()
                self.number_players += 1
                self.save()
                return
            return

        # create a new team object for them
        teams = TournamentTeam.objects.filter(tournament=self).order_by('-team_index')
        if teams:
            for team in teams:
                team_index = team.team_index + 1
        else:
            team_index = 1

        new_team = TournamentTeam(tournament=self, team_index=team_index, players=self.players_per_team)
        new_team.save()
        self.number_players += 1
        self.save()

        # if we get here, we're a new player entirely
        # there is no limit to the total MTR players, so just add a new one
        # create the player and move on
        tournament_player = TournamentPlayer(tournament=self, team=new_team, player=player[0])
        tournament_player.save()

        # now, if there is an invite for this player
        tournament_invite = TournamentInvite.objects.filter(player=player[0], tournament=self)
        if tournament_invite:
            tournament_invite[0].joined = True
            tournament_invite[0].save()

    def decline_tournament(self, token):
        # is the player in the tournament?
        player = Player.objects.filter(token=token)
        if not player:
            raise Exception("Player with token {} not found".format(token))

        # if we're start locked we must bail, but the player should still be able to join
        # after it starts
        if self.start_locked:
            raise Exception("The host is trying to start the tournament or it has already started.")

        # make sure this player is already in the tournament
        tournament_player = TournamentPlayer.objects.filter(player=player[0], tournament=self.id)
        if not tournament_player:
            raise Exception("Player {} is not in the tournament!".format(token))

        # de-activate the tournament player
        tournament_player[0].team.active = False
        tournament_player[0].team.save()
        self.number_players -= 1
        self.save()

        # also, deactivate any invited player so that they can join again
        invite = TournamentInvite.objects.filter(player=player[0], tournament=self)
        if invite:
            invite[0].joined = False
            invite[0].save()

    def ensure_6_months(self):
        current_month = get_current_month_year()[0] + 1
        current_year = get_current_month_year()[1]
        months_created = 0
        while current_month <= 12 and months_created < 6:
            self.create_new_month(current_month, current_year, 0)
            months_created += 1
            current_month += 1

        # do we need to return?
        if months_created == 6:
            return

        # reset to the next year
        current_month = 1
        current_year += 1
        while current_month <= 12 and months_created < 6:
            self.create_new_month(current_month, current_year, 0)
            months_created += 1
            current_month += 1

        # we've got 6 months created at this point...

    def start(self):
        # create the initial month with the template chosen
        self.create_new_month(get_current_month_year()[0], get_current_month_year()[1], self.template)

        # now create 6 more months accordingly to players fill in templates in advance on
        self.ensure_6_months()

        if settings.DEBUG:
            self.fill_teams()

    def update_game_log(self):
        game_log = '<div class="row"><div class="container">'
        game_log += '<table class="table table-hover table_condensed clot_table compact stripe cell-border" id="game_log_data_table">'
        game_log += '<thead><tr>'
        game_log += '<th>Template</th><th>Match-up</th><th>Link</th><th>State</th><th>Winner</th><th>End-Time</th>'
        game_log += '</tr></thead>'
        game_log += '<tbody>'

        games_output = []
        tournament_game_entries = TournamentGameEntry.objects.filter(tournament=self).order_by('-created_date')
        for entry in tournament_game_entries:
            if entry.game.id in games_output:
                continue

            game_log += '<tr>'

            # template link
            start_time = entry.game.game_start_time
            month = start_time.month
            year = start_time.year
            game_log += '<td><a href = "https://warzone.com/MultiPlayer?TemplateID={}" target="_blank" class="badge badge-primary">{}, {} Template</a>'.format(self.get_current_template_id, self.month_str[month], year)

            # Match-Up
            game_log += '<td>{} vs. {}</td>'.format(get_team_data_sameline(entry.team), get_team_data_sameline(entry.team_opp))

            # link to the game
            game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(entry.game.game_link)

            # Game State
            if entry.game.is_finished:
                finished_text = '<span class="text-success"><b>Finished</b></span>'
            else:
                finished_text = '<span class="text-info">{}</span>'.format(entry.game.current_state)
            game_log += '<td>{}</td>'.format(finished_text)

            # Winner
            winner = ""
            if entry.game.winning_team is not None:
                if entry.team.id == entry.game.winning_team.id:
                    winner = get_team_data(entry.team)
                else:
                    winner = get_team_data(entry.team_opp)
            game_log += '<td>{}</td>'.format(winner)

            # End-Time
            # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
            end_time = entry.game.game_finished_time.strftime(
                "%b %d, %Y %H:%M:%S %p") if entry.game.is_finished and entry.game.game_finished_time else 'N/A'
            game_log += '<td>{}</td>'.format(end_time)

            game_log += '</tr>'

            games_output.append(entry.game.id)
        game_log += '</tbody></table></div></div>'
        self.game_log = game_log
        self.save()

    def get_bracket_game_data(self):
        return self.bracket_game_data

    def update_bracket_game_data(self):
        bracket_data = '<div class="row"><div class="container">'

        bracket_data += '<table class="table table-hover"><tr>'
        bracket_data += '<th>Team</th><th>Overall Record</th></tr>'
        # we want to only display the overall wins/losses, with the current month wins/losses next to it
        tournament_teams = TournamentTeam.objects.filter(tournament=self).order_by('-wins', '-rating')
        for team in tournament_teams:
            bracket_data += '<tr>'
            bracket_data += '<td>'

            tournament_player = TournamentPlayer.objects.filter(team=team)
            if tournament_player:
                bracket_data += get_tournament_player_data(tournament_player[0])

            bracket_data += '</td>'
            bracket_data += '<td>'
            bracket_data += '{}-{}'.format(team.wins, team.losses)
            bracket_data += '</td></tr>'

        bracket_data += '</table>'
        bracket_data += "</div></div>"
        self.bracket_game_data = bracket_data
        self.save()

    def get_start_delete_buttons(self):
        return ""

class PromotionalRelegationLeague(Tournament):
    type = models.CharField(max_length=255, blank=True, null=True, default="Promotion/Relegation League")
    seasons = models.IntegerField(default=0)
    current_season = models.ForeignKey('PromotionalRelegationLeagueSeason', blank=True, null=True, on_delete=models.DO_NOTHING)
    min_teams = 2

    @property
    def season_in_progress(self):
        return False

    def create_season(self, season_name, games_at_once):
        if len(season_name) < 3 or len(season_name) > 251:
            raise ValueError("Season name must be between 3-250 characters.")
        if not games_at_once.isnumeric() or int(games_at_once) < 1 or int(games_at_once) > 100:
            raise ValueError("Games at once must be 1-100 inclusive.")
        season = PromotionalRelegationLeagueSeason(pr_tournament=self, name=season_name, created_by=self.created_by, private=True, games_at_once=int(games_at_once))
        season.save()

    def copy_season(self, season_name, copy_season_id):
        # Get original season to copy
        orig_season = PromotionalRelegationLeagueSeason.objects.filter(id=int(copy_season_id))
        # Ensure parameters are correct before copying
        if not orig_season:
            raise ValueError("Seasonal with id {} could not be found".format(copy_season_id))
        # Get the # of games and template from original season
        games_at_once = orig_season[0].games_at_once
        template = orig_season[0].season_template
        description = orig_season[0].description

        # Create a new season given original season
        season = PromotionalRelegationLeagueSeason(pr_tournament=self, name=season_name, created_by=self.created_by, private=True, games_at_once=games_at_once, season_template=template, game_creation_allowed=False, description=description)
        season.save()
        
        # Iterate through original season divisions and copy to new season
        divisions = ClanLeagueDivision.objects.filter(pr_season=orig_season[0])
        for div in divisions:
            new_division = ClanLeagueDivision(title=div.title, pr_season=season)
            new_division.save()

            # Iterate through original season teams and copy TT and TP to new season
            teams = TournamentTeam.objects.filter(clan_league_division=div)
            for team in teams:
                new_team = TournamentTeam(clan_league_division=new_division, max_games_at_once=games_at_once, players=team.players, tournament=season)
                new_team.save()
                players = TournamentPlayer.objects.filter(team=team)
                for player in players:
                    new_player = TournamentPlayer(team=new_team, tournament=season, player=player.player)
                    new_player.save()
        # Set player count for season
        players = TournamentPlayer.objects.filter(tournament=season)
        if players:
            season.numbers_players = players.count()
        season.save()

    def get_seasons_editable(self):
        return self.get_seasons_impl(True)

    def get_seasons_impl(self, editable):
        seasons = PromotionalRelegationLeagueSeason.objects.filter(pr_tournament=self)
        if seasons.count() == 0:
            return ""
        season_data = '<div class="container"><div class="row">'
        season_data += '<table class="table table-hover table-condensed">'
        season_data += '<tr><th>Season Name</th><th>Management</th></tr>'
        for season in seasons:
            if not editable:
                mgmt_text = "View Season"
            else:
                mgmt_text = "Manage/View Season"
            mgmt_data = '<a role="button" class="btn btn-md btn-primary" href="/pr/season/{}">{}</a>'.format(season.id, mgmt_text)
            if editable:
                disabled = ""
                if not season.is_finished and season.has_started:
                    disabled = "disabled"
                mgmt_data += '&nbsp;<button type="button" class="btn btn-md btn-danger remove-pr-season" id="remove-pr-season-{}" data-id="{}" {}>Delete Season</button>'.format(season.id, season.id, disabled)
                mgmt_data += '&nbsp;<button type="button" class="btn btn-md btn-success copy-pr-season" id="copy-pr-season-{}" data-id="{}">Copy Season</button>'.format(season.id, season.id)
            season_data += '<tr><td id="season-{}">{}</td><td>{}</td></tr>'.format(season.id, season.name, mgmt_data)
        season_data += '</table></div></div>'

        return season_data

    def get_seasons(self):
        return self.get_seasons_impl(False)

    def remove_season(self, season_id):
        # cannot remove season when in progress
        season = PromotionalRelegationLeagueSeason.objects.filter(id=int(season_id))
        if not season:
            raise ValueError("Season could not be found.")
        season.delete()

class PromotionalRelegationLeagueSeason(Tournament):
    pr_tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, related_name='pr_parent_tournament')
    season_template = models.ForeignKey('ClanLeagueTemplate', on_delete=models.CASCADE, related_name='pr_season_template', blank=True, null=True, default=None)
    games_at_once = models.IntegerField(default=2)

    def start(self, tournament_data):
        log_tournament("Starting {}".format(self.name), self)
        tournaments = PromotionalRelegationLeagueTournament.objects.filter(parent_tournament=self)
        if tournaments.count() > 0 or self.has_started:
            log_tournament("Cannot start {}, tournament count: {}, and self.has_started: {}".format(self.name, tournaments.count(), self.has_started), self)
            return

        self.has_started = True
        self.save()

        log_tournament("{}.has_started = True...creating RR for divisions".format(self.name), self)

        divisions = ClanLeagueDivision.objects.filter(pr_season=self)
        for div in divisions:
            teams = TournamentTeam.objects.filter(clan_league_division=div, tournament=self)
            tournament = PromotionalRelegationLeagueTournament(parent_tournament=self, template=self.season_template.templateid, name=div.title, division=div, created_by=self.created_by, number_players=teams.count()*self.season_template.players_per_team, max_players=teams.count()*self.season_template.players_per_team, number_rounds=teams.count()-1, players_per_team=self.season_template.players_per_team, teams_per_game=2, private=True, games_at_once=self.games_at_once)
            tournament.save()
            log_tournament("Created P/R RR Tournament {}".format(tournament.name), self)
            for team in teams:
                team.round_robin_tournament = tournament
                team.save()
            tournament.start()

        self.game_creation_allowed = True
        self.save()

    def get_pause_resume(self, player):
        if player and player.id == self.created_by.id:
            if self.game_creation_allowed:
                pause_resume = '<button type="button" class="btn btn-danger" name="pause" id="pause"><i class="fa fa-pause"></i>&nbsp;Pause Season</button>'
            else:
                # resume case
                pause_resume = '<button type="button" class="btn btn-success" name="resume" id="resume"><i class="fa fa-play"></i>&nbsp;Resume Season</button>'
            return pause_resume
        return ""

    def update_game_creation_allowed(self, allowed):
        self.game_creation_allowed = allowed

        tournaments = PromotionalRelegationLeagueTournament.objects.filter(parent_tournament=self)
        for tournament in tournaments:
            tournament.game_creation_allowed = allowed
            tournament.save()
        self.save()


    def update_game_log(self):
        pass

    def update_bracket_game_data(self):
        pass

    def process_new_games(self):
        # loop through all divisions, creating games for those divisions
        pass

    def get_start_locked_data(self):
        # returns the html for the tournament
        return "<p>Are you sure you want to start Season {}? Once you've started the season you can pause/resume it you cannot alter divisions, players, or templates.</p>".format(self.name)

    def get_bracket_game_data(self):
        return self.bracket_game_data

    @property
    def can_start_tourney(self):
        # we must have exactly 1 template and atleast 1 division, all divisions must have at least 4 teams
        if self.season_template is None:
            return False
        divisions = ClanLeagueDivision.objects.filter(pr_season=self)
        if divisions.count() == 0:
            return False
        for div in divisions:
            teams = TournamentTeam.objects.filter(tournament=self, clan_league_division=div)
            if teams.count() < 4:
                return False
        players = TournamentPlayer.objects.filter(player__token=1, tournament=self)
        if players.count() != 0:
            return False

        # set the proper fields on this tournament which is looked at before creating the underlying round robin ones
        self.players_per_team = self.season_template.players_per_team
        self.save()

        return True


    def add_team_to_division(self, request):
        if 'tournamentid' in request.POST and 'divisionid' in request.POST:
            # create the team in the division
            division = ClanLeagueDivision.objects.filter(id=int(request.POST['divisionid']))
            if division:
                self.create_empty_team(division[0])
                players = TournamentPlayer.objects.filter(tournament=self)
                if players:
                    self.numbers_players = players.count()
                    self.save()

    def remove_team_from_division(self, request):
        if 'teamid' in request.POST:
            team = TournamentTeam.objects.filter(pk=int(request.POST['teamid']))
            team.delete()

    def invite_player(self, request_data):
        # update the slot based on the request data. We override the parent
        if 'data_attrib[player]' in request_data:
            playerid = request_data['data_attrib[player]']

        # look up the associated clan/division/template/team and add this player to the team in the correct slot
        # if the playerid == 0 then this means it was an empty slot
        try:
            if 'data_attrib[swapid]' in request_data:
                # add the player to the team
                tplayer = TournamentPlayer.objects.get(id=int(playerid))
                templateid = self.season_template.templateid
                player = Player.objects.get(id=int(request_data['data_attrib[swapid]']))

                # Check if the player is already in the tournament (only applies if not empty seat -- ie token != "1")
                if player.token != "1" and TournamentPlayer.objects.filter(player=player, tournament=self):
                    raise Exception("{} is already invited.".format(player.name))

                if is_player_allowed_join(player, templateid):
                    log_tournament(
                        "Swapped {} [{}] with {} [{}]".format(tplayer.player.name, tplayer.player.token, player.name,
                                                              player.token), self)
                    tplayer.player = player
                    tplayer.save()
                else:
                    raise Exception("{} is not allowed to play this template.".format(player.name))

        except ObjectDoesNotExist:
            log_exception()

    def add_template(self, request):
        # check the parameters
        if 'templateid' in request.POST and 'templatesettings' in request.POST and 'players_per_team' in request.POST and 'templatename' in request.POST:
            templateid = request.POST['templateid']
            templatesettings = request.POST['templatesettings']
            players_per_team = int(request.POST['players_per_team'])
            templatename = request.POST['templatename']
            if players_per_team < 1 or players_per_team > 3:
                raise Exception("You many only have 1, 2, or 3 players per team for Clan Leagues")
            elif len(templateid) < 4:
                raise Exception("You must enter in a valid template id.")
            elif len(templatename) < 3 or len(templatename) > 250:
                raise Exception("Template name must be between 3-250 characters")
            # if the template gets modified with # of players different then blow away divisions
            if self.season_template is not None and self.season_template.players_per_team != players_per_team:
                # remove all divisions, and teams in those divisions
                divisions = ClanLeagueDivision.objects.filter(pr_season=self)
                for div in divisions:
                    teams = TournamentTeam.objects.filter(clan_league_division=div)
                    for t in teams:
                        t.delete()
                    div.delete()
            template = self.season_template
            if template:
                template.delete()
            template = ClanLeagueTemplate(templateid=int(templateid), template_settings=templatesettings, players_per_team=players_per_team, name=templatename)
            template.save()
            self.season_template = template
            self.save()
        else:
            raise Exception("Invalid arguments provided!")

    def get_editable_template_data(self):
        return self.get_template_data_impl(True)

    def get_template_data(self):
        return self.get_template_data_impl(False)

    def get_template_data_impl(self, editable):
        print("GetTemplate Data Editable: {}".format(editable))
        data = ""
        template = self.season_template
        if template is not None:
            if editable:
                data += '<p class="text-danger" id="template_start_error"></p>'
            data += '<table class="table table-hover table-condensed clot_table compact stripe cell-border" id="template_table">'
            data += '<tr>'
            data += '<th>Template ID</th>'
            data += '<th>Template Name</th>'
            data += '<th>Template Link</th>'
            data += '<th>Players Per Team</th>'
            data += '</tr>'

            data += '<tr>'
            data += '<td>{}</td>'.format(template.templateid)
            data += '<td>{}</td>'.format(template.name)
            data += '<td><a href="https://warzone.com/MultiPlayer?TemplateID={}" target="_blank" class="badge badge-primary">Template</a></td>'.format(template.templateid)
            data += '<td>{}</td>'.format(template.players_per_team)
            data += '</table>'
        return data

    def get_editable_roster_data(self, id):
        division_data = ""
        division = ClanLeagueDivision.objects.filter(pr_season=self.id, pk=int(id))
        if division:
            division = division[0]
            division_data += division.get_pr_division_card(True)
        return division_data


    def create_empty_team(self, division):
        team = TournamentTeam(clan_league_division=division,
                              players=self.season_template.players_per_team, tournament=self)
        team.save()

        for j in range(0, self.season_template.players_per_team):
            empty_slot = Player.objects.filter(token=1)
            if not empty_slot:
                empty_slot = Player(token=1, name="Empty Slot")
                empty_slot.save()
            else:
                empty_slot = empty_slot[0]
            player = TournamentPlayer(player=empty_slot, tournament=self, team=team)
            player.save()

    def get_editable_divisions_data(self):
        return self.get_divisions_data_impl(True)

    def get_divisions_data(self):
        return self.get_divisions_data_impl(False)

    def get_divisions_data_impl(self, editable):
        division_data = ""
        divisions = ClanLeagueDivision.objects.filter(pr_season=self.id)
        current_division = 1
        for division in divisions:
            # use cards, and outline the divisions here only allowing editable teams for 4 or more teams
            division_data += division.get_pr_division_card(editable)
            current_division += 1
        return division_data

    def add_new_division(self, request):
        if self.season_template is None:
            raise Exception("Please add a template first!")
        if 'division-name' in request.POST:
            division_name = request.POST['division-name']
            if len(division_name) > 3 and len(division_name) <= 100:
                division = ClanLeagueDivision(title=division_name, pr_season=self)
                division.save()

                # always default to create 4 slots per team in the division
                for i in range(0, 4):
                    self.create_empty_team(division)

                players = TournamentPlayer.objects.filter(tournament=self)
                if players:
                    self.numbers_players = players.count()
                # the creator will get to assign players to these team slots now
                self.game_creation_allowed = False
                self.save()
                return division
        raise Exception("Division name must be between 3-100 characters.")

    def remove_division(self, request):
        if 'divisionid' in request.POST:
            divisionid = request.POST['divisionid']
            division = ClanLeagueDivision.objects.filter(pr_season=self, pk=int(divisionid))
            division[0].delete()
        else:
            raise Exception("Division not found to remove!")

    def get_invited_players_inverse_table(self, creator_token, request_data, viewer_token):
        # get all the players, and only add the players we care about (excluding invited players) to the html
        table = '<table class="table table-hover table-condensed compact stripe" id="invite-filter">'
        table += '<thead><tr><th>Player Name</th><th> </th></tr></thead><tbody id="invite-filter-table">'

        is_player_available = False
        players = Player.objects.all()
        # list of player names associated with the rows so that we can do easy filtering on the client
        # side
        for player in players:
            is_player_available = True
            # player wasn't invited to this tournament
            # check if it's us, if it is, skip
            clan_name = ""
            if player.clan:
                clan_name = '{}'.format(player.clan.name)
            table += '<tr><td data-search="{} {}">'.format(clan_name, player.name)
            table += get_player_data(player)

            table += '</td>'
            table += '<td><button class="btn btn-info btn-sm" id="cl-update-player-{}" name="slot" data-swapid="{}" data-player="{}">Swap</button></td>'.format(
                player.id, player.id, request_data['data_attrib[player]'])
            table += '</tr>'

        if not is_player_available:
            table += 'There are no players to invite.'

        table += '</tbody></table>'

        return table

class PromotionalRelegationLeagueTournament(RoundRobinTournament):
    division = models.ForeignKey('ClanLeagueDivision', on_delete=models.CASCADE, null=True, blank=True)

    def are_vacations_supported(self):
        return True

    def get_game_name(self):
        # get the current number of games
        log_tournament("PR Game Name: {} | {}".format(self.division.pr_season.name, self.division.title), self)
        return "{} | {}".format(self.division.pr_season.name, self.division.title)

    def has_force_vacation_interval(self):
        return False

    def uses_byes(self):
        return False

    def process_new_games(self):
        # just call into the parent to create games
        try:
            super(PromotionalRelegationLeagueTournament, self).process_new_games()
        except Exception:
            log_exception()

    def start(self):
        print("Starting Promotional Relegation League Tournament")

        super(PromotionalRelegationLeagueTournament, self).start()
        # just call into the parent and start it


class ClanLeagueTemplate(models.Model):
    templateid = models.IntegerField(default=0, blank=True, null=True, db_index=True)
    template_settings = models.TextField(default="", blank=True, null=True)
    players_per_team = models.IntegerField(default=1, blank=True, null=True)
    league = models.ForeignKey('ClanLeague', on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, default="", null=True)

    def get_template_settings_dict(self):
        if self.template_settings is not None:
            try:
                settings_dict = json.loads('''{}'''.format(self.template_settings))
                return settings_dict
            except Exception:
                log_exception()
        return None

class ClanLeagueDivisionClan(models.Model):
    division = models.ForeignKey('ClanLeagueDivision', on_delete=models.CASCADE, null=True, blank=True)
    clan = models.ForeignKey('Clan', on_delete=models.CASCADE, null=True, blank=True)
    max_points_possible = models.IntegerField(default=0, blank=True, null=True)
    total_points = models.IntegerField(default=0, blank=True, null=True)

class ClanLeagueDivision(models.Model):
    title = models.CharField(default="", blank=True, null=True, max_length=255)
    league = models.ForeignKey('ClanLeague', on_delete=models.CASCADE, null=True, blank=True)
    pr_season = models.ForeignKey('PromotionalRelegationLeagueSeason', on_delete=models.CASCADE, null=True, blank=True)

    @staticmethod
    def has_duplicate_clans(clans):
        set_of_clans = set()
        for clan in clans:
            if clan.clan.id in set_of_clans:
                return True
            set_of_clans.add(clan.clan.id)
        return False

    def get_division_card(self, type, editable):
        division_data = '<br/><div class ="card gedf-card span6">'
        division_data += '<div class ="card-header">'
        division_data += '<div class ="d-flex justify-content-between align-items-center">'
        division_data += '<div>'
        division_data += '<h6>{}</h6>'.format(self.title)
        if not self.league.has_started and editable:
            division_data += '<button class="btn btn-sm btn-danger" type="button" id="division-remove-{}" data-division="{}">Remove Division</button>'.format(self.id, self.id)
        division_data += '</div>'
        division_data += '</div>'
        division_data += '</div>'

        division_data += '<div class="card-body">'

        clans = ClanLeagueDivisionClan.objects.filter(division=self)
        if type == "add-clans":
            if not self.league.has_started:
                # load the clan information, including all clans at the top to add to this division
                if editable:
                    # check for duplicate clans and return warning
                    if ClanLeagueDivision.has_duplicate_clans(clans):
                        division_data += '<div class="alert alert-warning">'
                        division_data += '<span type="button" class="close" aria-label="Close" data-dismiss="alert"><span aria-hidden="true">&times;</span></span>'
                        division_data += '<span>Warning: duplicate clans in the division</span>'
                        division_data += '</div>'
                    all_clans = Clan.objects.all().order_by("name")
                    division_data += '<select name="div-clans-{}" multiple>'
                    for clan in all_clans:
                        division_data += '<option class="text-sm" value="{}">{}</option>'.format(clan.id, clan.name)

                    division_data += '</select>'
                    division_data += '<br/><br/><button class="btn btn-sm btn-info" type="button" id="division-update-clans-{}" data-division="{}">+ Add Clans to {}</button><br/><br/>'.format(self.id, self.id, self.title)
                division_data += "Clans currently in {}:<br/>".format(self.title)

            # now we need to put all clans in the division at the bottom regardless of what card we're showing
            if clans.count() > 0:
                if self.league.has_started:
                    division_data += '<b>Clans</b><hr>'
                for clan in clans:
                    division_data += '{}'.format(get_clan_data(clan.clan))
                    if not self.league.has_started and editable:
                        division_data += '&nbsp;<a href="javascript:void(0);" class="badge badge-danger" id="remove-clan" data-clan="{}" data-division="{}">Remove</a>'.format(clan.clan.id, self.id)
                    division_data += '&nbsp;&nbsp;&nbsp;'

                if self.league.has_started:
                    division_data += '<br/><br/><b>Tournaments</b><hr>'
                    tournaments = ClanLeagueTournament.objects.filter(division=self)
                    for tournament in tournaments:
                        if tournament.has_started:
                            division_data += '<div class="row" style="padding-bottom:25px;">'
                            division_data += '<button class="btn btn-info" onclick="toggle_div(\'toggle-data-{}\');">{} Games</button>'.format(
                                tournament.id, tournament.name)
                            division_data += '<div id="toggle-data-{}" style="display:none;padding-top:25px;">'.format(tournament.id)
                            division_data += '<a href="/tournaments/{}/" class="btn btn-primary btn-sm" role="button">View {} Details</a>'.format(tournament.id, tournament.name)
                            division_data += '<br/>{}'.format(tournament.get_bracket_game_data())
                            division_data += '</div>'
                            division_data += '</div>'

                    # loop through the tournaments again asking for the current game results
        elif type == "add-players":
            # loop through clans, and for each clan loop through templates
            player_data = '<table class="table table-hover">'
            player_data += '<tr><th>Template</th><th>Clan</th><th>Players</th></tr>'

            # now loop through the templates, and each clan in the division
            for clan in clans:
                tournaments = ClanLeagueTournament.objects.filter(division=self)
                for tournament in tournaments:
                    player_data += '<tr>'
                    team = TournamentTeam.objects.filter(clan_league_division=self, tournament=self.league, clan_league_clan=clan, round_robin_tournament=tournament)
                    if team:
                        player_data += '<td>{}</td>'.format(tournament.clan_league_template.name)
                        player_data += '<td>{}</td>'.format(get_clan_data(clan.clan))
                        player_data += '<td>'
                        players = TournamentPlayer.objects.filter(team=team[0])
                        for player in players:
                            player_data += '{}'.format(get_tournament_player_data(player))
                            if editable:
                                player_data += '<a href="javascript:void(0);" class="badge badge-info invite_players" data-player="{}">Change Player</a>&nbsp;'.format(player.id)
                        player_data += '</td>'
                    player_data += '</tr>'
            player_data += '</table>'
            division_data += player_data
        division_data += '</div></div>'
        return division_data

    def get_pr_division_card(self, editable):
        division_data = '<br/><div class="editable-division" id="division-data-{}">'.format(self.id)
        division_data += '<div class ="card gedf-card span6">'
        division_data += '<div class ="card-header">'
        division_data += '<div class ="d-flex justify-content-between align-items-center">'
        division_data += '<div>'
        division_data += '<h6>{}</h6>'.format(self.title)
        if not self.pr_season.has_started and editable:
            division_data += '<button class="btn btn-sm btn-danger" type="button" id="division-remove-{}" data-division="{}">Remove Division</button>'.format(self.id, self.id)
            division_data += '&nbsp;<button class="btn btn-sm btn-info" type="button" id="division-add-team" data-division="{}">+ Add Team</button>'.format(self.id)
        elif self.pr_season.has_started:
            tournament = PromotionalRelegationLeagueTournament.objects.filter(division=self)
            if tournament:
                tournament = tournament[0]
                division_data += '<a href="/tournaments/{}/" class="btn btn-primary" role="button">View Division Results</a>'.format(
                        tournament.id)

        division_data += '</div>'
        division_data += '</div>'
        division_data += '</div>'

        division_data += '<div class="card-body">'
        division_data += '<table class="table table-sm table-hover">'
        teams = TournamentTeam.objects.filter(clan_league_division=self).order_by('id')
        template = self.pr_season.season_template
        if template:
            current_team = 1
            for t in teams:
                division_data += '<tr><td>'
                players = TournamentPlayer.objects.filter(team=t)
                for player in players:
                    division_data += '{}'.format(get_tournament_player_data(player))
                    if editable:
                        division_data += '<a href="javascript:void(0);" class="badge badge-info invite_players" data-player="{}">Change Player</a>&nbsp;'.format(player.id)
                if current_team > 4 and editable:
                    division_data += '<a href="javascript:void(0);" class="badge badge-danger" id="division-remove-team-{}" data-division="{}" data-team="{}">Remove Team</button>'.format(
                        self.id, self.id, t.id)
                current_team += 1

                division_data += '</td></tr>'

        division_data += '</table>'
        division_data += '</div></div></div>'
        return division_data


class ClanLeagueTournament(RoundRobinTournament):
    creation_interval = models.CharField(default="", blank=True, null=True, max_length=255)
    division = models.ForeignKey('ClanLeagueDivision', on_delete=models.CASCADE, null=True, blank=True)
    games_start_times = models.TextField(default="", blank=True, null=True)
    clan_league_template = models.ForeignKey('ClanLeagueTemplate', on_delete=models.DO_NOTHING, null=True, blank=True)
    vacation_force_interval = 20

    def are_vacations_supported(self):
        return True

    def get_game_name(self):
        return "{} | {} - {}".format(self.division.league.name, self.division.title, self.clan_league_template.name)

    def has_force_vacation_interval(self):
        return True

    def uses_byes(self):
        if self.number_teams % 2 != 0:
            return True
        return False

    def games_created_at_once(self):
        return 1

    def get_next_game_interval(self):
        start_times = self.games_start_times.split(';')

        # always take the next (first) one
        if len(start_times[0]) >= 8:  # every start time is a day/month/year, and we need at least 8 characters
            next_start = start_times[0].split('.')
            return "{}/{}/{}".format(next_start[0], next_start[1], next_start[2])
        return ""

    def process_new_games(self):
        # just call into the parent to create games
        if self.should_create_game():  # remove the date as well, so if we fail in create game we are screwed and manually need to re-add the date
            super(ClanLeagueTournament, self).process_new_games()
        try:
            # are there any games that need recreation?
            recreation_games = TournamentGame.objects.filter(tournament=self, needs_recreation=True)
            for game in recreation_games:
                print("Recreating game: {}".format(game.id))
                # delete the current game entry first
                entry = TournamentGameEntry.objects.filter(game=game, tournament=self)
                if entry:
                    entry[0].delete()
                round = TournamentRound.objects.filter(tournament=self, round_number=1)
                if round:
                    self.create_game(round[0], game.teams)
                    # a brand new game object is created so we need to delete this one
                    game.delete()
                    print("Game {} recreated".format(game.id))
        except Exception:
            log_exception()

    def get_team_table(self, allow_buttons, logged_in, request_player):
        if not self.has_started:
            return super(RoundRobinTournament, self).get_team_table(allow_buttons, logged_in, request_player)
        else:
            table = '<table class="table table-hover"><tr><th>Clan</th><th>Record</th></tr>'
            teams = TournamentTeam.objects.filter(round_robin_tournament=self).order_by('-wins')
            for team in teams:
                table += '<tr><td>'
                if team.clan_league_clan is not None and team.clan_league_clan.clan is not None:
                    table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                        team.clan_league_clan.clan.icon_link, team.clan_league_clan.clan.image_path,
                        team.clan_league_clan.clan.name)

                table += ' {}&nbsp;'.format(team.clan_league_clan.clan.name)

                table += '<td>{}-{}</td>'.format(team.wins, team.losses)

                table += '</tr>'
            table += "</table>"
            return table

    def start(self):
        print("Starting Clan League Tournament, with template {}".format(self.clan_league_template.name))
        self.games_at_once = 100

        # now we must create date intervals for each of the games. first games start now, with the following logic
        # Team games: 10/25/35/50/60/75/85/100 etc...
        # 1v1 games: 7/14/21/28/35/42 etc...

        # today is
        today = datetime.datetime.now()
        today_str = "{}.{}.{}".format(today.day, today.month, today.year)

        log_tournament("Starting tournament on: {}/{}/{}".format(today.month, today.day, today.year), self)

        creation_dates = "{}.{}.{};".format(today.month, today.day, today.year)
        if self.players_per_team == 1:
            # hook up logic so that games are created every 7 days for as many teams as there are (everyone get a bye)
            for i in range(1, self.number_teams):
                next_date = today + datetime.timedelta(days=10)
                creation_dates += "{}.{}.{};".format(next_date.month, next_date.day, next_date.year)
                log_tournament("Creation dates after iteration {}: {}".format(i, creation_dates), self)
                today = next_date
        else:
            for i in range(1, self.number_teams):
                if i % 2 == 1:
                    # increment 10 for odd numbers
                    next_date = today + datetime.timedelta(days=10)
                else:
                    # increment 15
                    next_date = today + datetime.timedelta(days=15)
                creation_dates += "{}.{}.{};".format(next_date.month, next_date.day, next_date.year)
                log_tournament("Creation dates after iteration {}: {}".format(i, creation_dates), self)
                today = next_date

        creation_dates = creation_dates[:-1]
        self.games_start_times = creation_dates
        log_tournament("Game Start times: {}".format(self.games_start_times), self)
        self.save()

        super(ClanLeagueTournament, self).start()
        # just call into the parent and start it

    def post_create_games(self):
        start_times = self.games_start_times.split(';')
        # always take the next (first) one
        if len(start_times[0]) >= 8:  # every start time is a day/month/year, and we need at least 8 characters
            # also, we only want to remove the date if it is today (meaning games should have gotten created)
            today = datetime.datetime.now()
            if len(start_times[0].split('.')) == 3:
                start_month = start_times[0].split('.')[0]
                start_day = start_times[0].split('.')[1]
                start_year = start_times[0].split('.')[2]
                if (int(today.day) == int(start_day)) and (int(today.month) == int(start_month)) and (int(today.year) == int(start_year)):
                    log_tournament("Removing start time for: {}/{}/{}".format(today.month, today.day, today.year), self)
                    start_times.pop(0)
                    new_start_times = ""
                    for time in start_times:
                        new_start_times += "{};".format(time)

                    # remove the last character, and save
                    new_start_times = new_start_times[:-1]
                    self.games_start_times = new_start_times
                    self.save()

    def should_create_game(self):
        start_times = self.games_start_times.split(';')

        if settings.DEBUG:
            return True

        # always take the next (first) one
        if len(start_times[0]) >= 8:  # every start time is a day/month/year, and we need at least 8 characters
            today = get_current_day_month_year()
            day = today[0]
            month = today[1]
            year = today[2]
            next_start = start_times[0].split('.')
            log_tournament("Today is {}/{}/{} and next game creation is on {}/{}/{}".format(month, day, year, next_start[0], next_start[1], next_start[2]), self)
            if int(next_start[0]) == month and int(next_start[1]) == day and int(next_start[2]) == year:
                # we can start the game now...but before returning true, store the start times again
                # with the first element missing
                return True
            return False
        else:
            return False

class ClanLeague(Tournament):
    type = models.CharField(max_length=255, blank=True, null=True, default="Clan League")
    game_allocation_started = models.BooleanField(default=False, null=True, blank=True)
    start_day = models.IntegerField(default=0, null=True, blank=True)
    start_month = models.IntegerField(default=0, null=True, blank=True)
    start_year = models.IntegerField(default=0, null=True, blank=True)

    def fill_teams(self):
        pass

    def update_game_creation_allowed(self, allowed):
        self.game_creation_allowed = allowed

        tournaments = ClanLeagueTournament.objects.filter(parent_tournament=self)
        for tournament in tournaments:
            tournament.game_creation_allowed = allowed
            tournament.save()

        self.save()

    def start_template(self, templateid):
        try:
            template = ClanLeagueTemplate.objects.get(id=templateid)
            # now that we have the template, locate all tournaments using this template in this league and start them
            # accordingly
            print("Starting template: {}".format(template.name))

            tournaments = ClanLeagueTournament.objects.filter(clan_league_template=template)
            for tournament in tournaments:
                # start them all
                tournament.start()

        except ObjectDoesNotExist:
            raise Exception("The requested template was not found in this league.")

    def invite_player(self, request_data):
        # update the slot based on the request data
        if 'data_attrib[player]' in request_data:
            playerid = request_data['data_attrib[player]']

        # look up the associated clan/division/template/team and add this player to the team in the correct slot
        # if the playerid == 0 then this means it was an empty slot
        try:
            if 'data_attrib[swapid]' in request_data:
                # add the player to the team
                tplayer = TournamentPlayer.objects.get(id=int(playerid))
                templateid = tplayer.team.round_robin_tournament.template
                player = Player.objects.get(id=int(request_data['data_attrib[swapid]']))
                if is_player_allowed_join(player, templateid):
                    log_tournament("Swapped {} [{}] with {} [{}]".format(tplayer.player.name, tplayer.player.token, player.name, player.token), self)
                    tplayer.player = player
                    tplayer.save()
                else:
                    raise Exception("{} is not allowed to play this template.".format(player.name))

        except ObjectDoesNotExist:
            log_exception()

    def update_clans(self, request):
        if 'divisionid' in request.POST and 'clans' in request.POST:
            divisionid = request.POST['divisionid']
            clans = request.POST['clans']
            if len(clans) > 0:
                for clan in clans.split(','):
                    clan_obj = Clan.objects.filter(pk=int(clan))
                    if clan_obj:
                        clan_obj = clan_obj[0]
                        # are we removing or adding?
                        if 'optype' in request.POST:
                            division = ClanLeagueDivision.objects.filter(pk=int(divisionid))
                            if division:
                                division = division[0]
                                if request.POST['optype'] == "update":
                                    # adding
                                    div_clan = ClanLeagueDivisionClan(clan=clan_obj, division=division)
                                    div_clan.save()
                                elif request.POST['optype'] == "remove-clan":
                                    # removing
                                    clan_rem = ClanLeagueDivisionClan.objects.filter(clan=clan_obj, division=division)
                                    if clan_rem:
                                        clan_rem[0].delete()
                    else:
                        log_tournament("Clan {} was not found".format(clan), self)

        else:
            raise Exception("Division and Clans must be passed in")

    def get_divisions_data(self):
        return self.get_divisions_data_impl(False)

    def get_editable_divisions_data(self):
        return self.get_divisions_data_impl(True)

    @staticmethod
    def has_duplicate_clans_across_divisions(divisions):
        all_clans = set()
        for division in divisions:
            clans = ClanLeagueDivisionClan.objects.filter(division=division)
            clans_set = set()
            for clan in clans:
                clans_set.add(clan.clan.id)
            total_clans = len(all_clans) + len(clans_set)
            all_clans = all_clans.union(clans_set)
            if len(all_clans) < total_clans:
                return True
        return False

    def get_divisions_data_impl(self, editable):
        division_data = ""
        divisions = ClanLeagueDivision.objects.filter(league=self.id)
        # check if duplicate clans across division and return warning
        if editable and ClanLeague.has_duplicate_clans_across_divisions(divisions):
            division_data += '<div class="alert alert-warning">'
            division_data += '<span type="button" class="close" aria-label="Close" data-dismiss="alert"><span aria-hidden="true">&times;</span></span>'
            division_data += '<span>Warning: duplicate clans across divisions</span>'
            division_data += '</div>'
        for division in divisions:
            # use cards, and outline the divisions here
            division_data += division.get_division_card("add-clans", editable)
        return division_data

    def add_new_division(self, request):
        if 'division-name' in request.POST:
            division_name = request.POST['division-name']
            if len(division_name) > 3 and len(division_name) <= 100:
                division = ClanLeagueDivision(title=division_name, league=self)
                division.save()
                return division
        raise Exception("Division name must be between 3-100 characters.")

    def remove_division(self, request):
        if 'divisionid' in request.POST:
            divisionid = request.POST['divisionid']
            division = ClanLeagueDivision.objects.filter(league=self, pk=int(divisionid))
            division[0].delete()
        else:
            raise Exception("Division not found to remove!")

    def add_template(self, request):
        # check the parameters
        if 'templateid' in request.POST and 'templatesettings' in request.POST and 'players_per_team' in request.POST and 'templatename' in request.POST:
            templateid = request.POST['templateid']
            templatesettings = request.POST['templatesettings']
            players_per_team = int(request.POST['players_per_team'])
            templatename = request.POST['templatename']
            if players_per_team < 1 or players_per_team > 3:
                raise Exception("You many only have 1, 2, or 3 players per team for Clan Leagues")
            elif len(templateid) < 4:
                raise Exception("You must enter in a valid template id.")
            elif len(templatename) < 3 or len(templatename) > 250:
                raise Exception("Template name must be between 3-250 characters")
            # has this template been added before? that is not allowed
            template = ClanLeagueTemplate.objects.filter(templateid=int(templateid), league=self)
            if template:
                raise Exception("This template has already been added to your Clan League. Please add another template")
            else:
                template = ClanLeagueTemplate(templateid=int(templateid), template_settings=templatesettings, league=self, players_per_team=players_per_team, name=templatename)
                template.save()
        else:
            raise Exception("Invalid arguments provided!")

    def remove_template(self, request):
        print("Removing template from CL: {}".format(request.POST))
        if 'templateid' in request.POST:
            templateid = request.POST['templateid']
            template = ClanLeagueTemplate.objects.filter(templateid=int(templateid), league=self)
            if template:
                template[0].delete()
        else:
            raise Exception("A valid template id is required")

    def get_editable_template_data(self):
        return self.get_template_data_impl(True)

    def get_template_data(self):
        return self.get_template_data_impl(False)

    def get_template_data_impl(self, editable):
        print("GetTemplate Data Editable: {}".format(editable))
        data = ""
        templates = ClanLeagueTemplate.objects.filter(league=self)
        if templates.count() > 0:
            if editable:
                data += '<p class="text-danger" id="template_start_error"></p>'
            data += '<table class="table table-hover table-condensed clot_table compact stripe cell-border" id="template_table">'
            data += '<tr>'
            data += '<th>Template ID</th>'
            data += '<th>Template Name</th>'
            data += '<th>Template Link</th>'
            data += '<th>Players Per Team</th>'
            data += '<th>Next Game</th>'
            data += '</tr>'

            need_start_buttons = False
            for template in templates:
                game_allocation_date = "N/A"
                # do we need to show the editable controls?
                tournaments = ClanLeagueTournament.objects.filter(clan_league_template=template)
                for tourney in tournaments:
                    if not tourney.has_started and editable:
                        need_start_buttons = True
                        break
                    else:
                        game_allocation_date = tourney.get_next_game_interval()
                        if game_allocation_date == "":
                            game_allocation_date = "N/A"
                        break

                data += '<tr>'
                data += '<td>{}</td>'.format(template.templateid)
                if editable and need_start_buttons:
                    data += '<td>{} <a href="javascript:void(0);" class="badge badge-success" id="cl-template-start-{}" data-template="{}">Start Tournaments</a></td>'.format(template.name, template.id, template.id)
                else:
                    data += '<td>{}</td>'.format(template.name)
                data += '<td><a href="https://warzone.com/MultiPlayer?TemplateID={}" target="_blank" class="badge badge-primary">Template</a></td>'.format(template.templateid)
                data += '<td>{}</td>'.format(template.players_per_team)

                # compute the countdown until the next game date
                time_to_game = game_allocation_date
                if len(game_allocation_date.split('/')) == 3:
                    # we have month/day/year
                    game_allocation_datetime = datetime.datetime.strptime(game_allocation_date, "%m/%d/%Y")
                    if game_allocation_datetime.replace(tzinfo=None) >= datetime.datetime.now().replace(tzinfo=None):
                        time_to_game = game_allocation_datetime.strftime("%b %d, %Y %H:%M:%S %p")
                data += '<td class="time_to_game">{}</td>'.format(time_to_game)
                data += '</tr>'
            data += '</table>'
        return data

    @property
    def can_start_tourney(self):
        # we can only start if we have a single division with more than 1 team
        start = True
        divisions = ClanLeagueDivision.objects.filter(league=self)
        if divisions.count() < 1:
            start = False
        for div in divisions:
            clans_in_div = ClanLeagueDivisionClan.objects.filter(division=div)
            if clans_in_div.count() < 2:
                start = False

        templates = ClanLeagueTemplate.objects.all()
        if templates.count() == 0:
            start = False

        return start

    def get_start_locked_data(self):
        # returns the html for the tournament
        return "<p>Are you sure you want to start Clan League? Once you've started Clan League you can pause/resume it and alter players and lineups but you cannot alter divisions, clans, or templates. </p>"

    def get_pause_resume(self, player):
        # pause resume for leagues can be used any way possible, but really
        # for cl we're going to use it as a start button
        if player and player.id == self.created_by.id:
            if self.game_creation_allowed:
                pause_resume = '<button type="button" class="btn btn-danger" name="pause" id="pause"><i class="fa fa-pause"></i>&nbsp;Pause {}</button>'.format(self.type)
            else:
                # resume case
                pause_resume = '<button type="button" class="btn btn-success" name="resume" id="resume"><i class="fa fa-play"></i>&nbsp;Resume {}</button>'.format(self.type)
            return pause_resume
        return ""

    def start(self, tournament_data):
        # we don't really care about tournament data
        # create all the clan league tournaments based on the templates/divisions
        # so that the creator can place players into slots

        # loop through all divisions, and then for each division create a clan league tournament for every template
        divisions = ClanLeagueDivision.objects.filter(league=self)
        templates = ClanLeagueTemplate.objects.filter(league=self)
        for division in divisions:
            teams_in_division = ClanLeagueDivisionClan.objects.filter(division=division)
            for template in templates:
                # create a tournament here
                # how many clans/team in this division?
                division_count = divisions.count()
                tournament_name = "{} - {}".format(division.title, template.name)
                cl_tourney = ClanLeagueTournament(division=division, created_by=self.created_by, template=template.templateid, players_per_team=template.players_per_team, max_players=teams_in_division.count()*template.players_per_team, private=True, parent_tournament=self, name=tournament_name, teams_per_game=2, clan_league_template=template)
                cl_tourney.save()

                # each tournament should already have teams able to be set up here (for round robin)
                # create the empty teams in the the rr_tourney, size of teams in division as all teams will play the template
                for clan in teams_in_division:
                    team = TournamentTeam(clan_league_clan=clan, clan_league_division=division, players=cl_tourney.players_per_team, tournament=self, round_robin_tournament=cl_tourney, max_games_at_once=teams_in_division.count())
                    team.save()

                    for i in range(0, cl_tourney.players_per_team):
                        empty_slot = Player.objects.filter(token=1)
                        if not empty_slot:
                            empty_slot = Player(token=1, name="Empty Slot")
                            empty_slot.save()
                        else:
                            empty_slot = empty_slot[0]
                        player = TournamentPlayer(player=empty_slot, tournament=self, team=team)
                        player.save()

        players = TournamentPlayer.objects.filter(tournament=self)
        if players:
            self.numbers_players = players.count()
        # the creator will get to assign players to these team slots now
        # so we can go ahead and mark us as "ClanLeague.started=True" and let the site handle this properly.
        self.has_started = True
        self.game_creation_allowed = False
        self.save()

    def process_new_games(self):
        # we should process the results here
        divisions = ClanLeagueDivision.objects.filter(league=self)
        for division in divisions:
            dclans = ClanLeagueDivisionClan.objects.filter(division=division)
            for dclan in dclans:
                # for each clan in the division, calculate max possible and current point totals
                pass

    def get_players_select(self):
        data = '<select id="clanleague-add-playerlist">'

        players = Player.objects.all()
        for player in players:
            data += '<option value="{}">{}</option>'.format(player.id, player.name)

        data += '</select>'
        # this returns the form that lets the creator add any player to any

    def get_roster_data(self):
        return self.get_roster_data_impl(0, False)

    def get_roster_data_impl(self, id, editable):
        data = ""
        # loop through divisions loading the editable division card
        if id == 0:
            divisions = ClanLeagueDivision.objects.filter(league=self.id)
            for division in divisions:
                data += '<div class="editable-division" id="division-data-{}">'.format(division.id)
                data += division.get_division_card('add-players', editable)
                data += '</div>'
        else:
            division = ClanLeagueDivision.objects.filter(id=id)
            if division:
                data += division[0].get_division_card('add-players', editable)
        return data

    def get_editable_roster_data(self, id=0):
        return self.get_roster_data_impl(id, True)

    def get_division_tournament_data(self):
        # returns the divisions + tournaments for each of them with links to the tournament pages
        data = ""

        # we should do a card for the division, and inside the card a table for each tournament with each row being a team
        # there will be one box of players at the top where the creator can add any player to any division/team combination
        return data

    def get_bracket_game_data(self):
        return self.bracket_game_data

    def update_bracket_game_data(self):
        self.bracket_game_data = ""
        self.save()

    def update_game_log(self):
        if self.number_players == 0:
            players = TournamentPlayer.objects.filter(tournament=self)
            self.number_players = players.count()
            self.save()
        log('Updating game log for Clan League "{}" (id={})'.format(self.name, self.id), LogLevel.informational)
        game_log = '<table class="table table-bordered table-condensed clot_table compact stripe cell-border" id="game_log_data_table"><thead><tr><th>Tournament</th><th>Division</th><th>Match-Up</th><th>Game Link</th><th>State</th><th>Winning Team</th><th>Start Time</th><th>End Time</th></tr></thead>'
        game_log += '<tbody>'
        tournaments = ClanLeagueTournament.objects.filter(parent_tournament=self)
        
        for t in tournaments:
            games = TournamentGame.objects.filter(tournament=t)
            for game in games:
                game_log += '<tr>'
                game_log += '<td>{}</td>'.format(t.clan_league_template.name)
                game_log += '<td>{}</td>'.format(t.division.title)

                # create the match-up text for the game
                game_data = game.teams.split('.')
                team1 = game_data[0]
                team2 = game_data[1]
                team_1 = TournamentTeam.objects.filter(id=int(team1))
                if team_1:
                    team_2 = TournamentTeam.objects.filter(id=int(team2))
                    if team_2:
                        game_log += '<td data-search="{} {} {} {}">{}</td>'.format(team_1[0].clan_league_clan.clan.name, team_2[0].clan_league_clan.clan.name, get_team_data_no_clan(team_1[0]), get_team_data_no_clan(team_2[0]), get_matchup_data(team_1[0], team_2[0]))
                game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(game.game_link)

                if game.is_finished:
                    finished_text = '<span class="text-success"><b>Finished</b></span>'
                else:
                    finished_text = '<span class="text-info">{}</span>'.format(game.current_state)
                game_log += '<td>{}</td>'.format(finished_text)

                if game.is_finished:
                    winning_team = '{}'.format(get_team_data(game.winning_team))
                else:
                    winning_team = ''
                game_log += '<td>{}</td>'.format(winning_team)
                time_to_boot_calculate = 0
                
                start_time = game.game_start_time.strftime("%b %d, %Y %H:%M:%S %p")

                # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
                end_time = game.game_finished_time.strftime("%b %d, %Y %H:%M:%S %p") if game.is_finished and game.game_finished_time else 'N/A'

                game_log += '<td>{}</td>'.format(start_time)
                game_log += '<td>{}</td>'.format(end_time)
                game_log += '</tr>'

        game_log += '</tbody></table>'
        self.game_log = game_log
        self.save()

    def get_join_leave(self, allow_buttons, logged_in, request_player):
        return ""

    def get_invited_players_inverse_table(self, creator_token, request_data, viewer_token):
        # get all the players, and only add the players we care about (excluding invited players) to the html
        table = '<table class="table table-hover table-condensed compact stripe" id="invite-filter">'
        table += '<thead><tr><th>Player Name</th><th> </th></tr></thead><tbody id="invite-filter-table">'

        print("Request data to generate CL player list: {}".format(request_data))
        is_player_available = False
        players = Player.objects.all()
        # list of player names associated with the rows so that we can do easy filtering on the client
        # side
        for player in players:
            is_player_available = True
            # player wasn't invited to this tournament
            # check if it's us, if it is, skip
            clan_name = ""
            if player.clan:
                clan_name = '{}'.format(player.clan.name)
            table += '<tr><td data-search="{} {}">'.format(clan_name, player.name)
            if player.clan is not None:
                table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                    player.clan.icon_link, player.clan.image_path, player.clan.name)

            table += '<a href="/stats/{}" target="_blank"><span class="invite_name">{}</span></a>'.format(
                player.token, player.name)
            table += '</td>'
            table += '<td><button class="btn btn-info btn-sm" id="cl-update-player-{}" name="slot" data-swapid="{}" data-player="{}">Swap</button></td>'.format(
                player.id, player.id, request_data['data_attrib[player]'])
            table += '</tr>'

        if not is_player_available:
            table += 'There are no players to invite.'

        table += '</tbody></table>'

        return table

    def get_invited_players_table(self):
        return ""

def get_multi_day_ladder(ladderId):
    try:
        if settings.DEBUG:
            # just try to get the first one
            ladder = RealTimeLadder.objects.all()
            if ladder:
                return ladder[0]
            else:
                return None
        ladder = MultiDayLadder.objects.get(id=int(ladderId))
        return ladder
    except ObjectDoesNotExist:
        return None

def get_real_time_ladder(ladderId):
    try:
        if settings.DEBUG:
            # just try to get the first one
            ladder = RealTimeLadder.objects.all()
            if ladder:
                return ladder[0]
            else:
                return None
        else:
            ladder = RealTimeLadder.objects.get(id=int(ladderId))
            return ladder
    except ObjectDoesNotExist:
        return None

class RealTimeLadder(Tournament):
    direct_seconds_per_turn = models.IntegerField(default=180, blank=True, null=True)
    auto_boot_seconds = models.IntegerField(default=180, blank=True, null=True)
    seconds_banked = models.IntegerField(default=300, blank=True, null=True)
    type = models.CharField(max_length=255, default="Real-Time Ladder")
    max_vetoes = models.IntegerField(default=1)

    def get_active_team_count(self):
        num_teams = TournamentTeam.objects.filter(tournament=self, active=True).count()
        self.number_players = num_teams
        self.save()
        return num_teams

    def get_active_teams(self):
        return TournamentTeam.objects.filter(tournament=self, active=True)

    def should_process_in_engine(self):
        return False

    def player_data_in_name(self):
        return True

    def join_tournament(self, token, buttonid):
        player = Player.objects.filter(token=token)
        if player:
            return self.join_leave_player(player[0], True, False)

    def decline_tournament(self, token):
        player = Player.objects.filter(token=token)
        if player:
            return self.join_leave_player(player[0], False, False)

    def get_join_leave(self, allow_buttons, logged_in, request_player):
        # get's the join/leave buttons based on the player wanting to join
        join = ''
        if request_player:
            log_tournament("[get_join_leave]: allow_buttons: {}, logged_in: {}, player: {}".format(allow_buttons, logged_in, request_player.name), self)
        if logged_in:
            # is the player currently active in the tournament?
            tournament_player = TournamentPlayer.objects.filter(player=request_player, tournament=self)
            if tournament_player and not tournament_player[0].team.active and allow_buttons:
                join += '<button type="button" class="btn btn-info" name="slot" id="join">Join Ladder</button>&nbsp;<button type="button" class="btn btn-info" name="slot" id="decline" disabled="disabled">Leave Ladder</button>'
            elif tournament_player and tournament_player[0].team.active:
                join += '<button type="button" class="btn btn-info" name="slot" id="join" disabled="disabled">Join Ladder</button>&nbsp;<button type="button" class="btn btn-info" name="slot" id="decline">Leave Ladder</button>'
            elif not tournament_player and allow_buttons:
                join += '<button type="button" class="btn btn-info" name="slot" id="join">Join Ladder</button>&nbsp;<button type="button" class="btn btn-info" name="slot" id="decline" disabled="disabled">Leave Ladder</button>'
        return join

    def get_ranked_unranked_teams(self):
        ranked_teams = []
        unranked_teams = []
        tournamentteams = TournamentTeam.objects.filter(tournament=self.id).order_by('-rating')
        if tournamentteams:
            # calculate the ranked versus unranked teams and then combine them for the list view
            for t in tournamentteams:
                if get_games_finished_for_team_since(t.id, self, 5) > 0:
                    ranked_teams.append(t)
                    if not t.ranked:
                        t.ranked = True
                        t.save()
                else:
                    unranked_teams.append(t)
                    t.ranked = False
                    t.save()
        return ranked_teams, unranked_teams

    def get_team_table(self, allowed_join, logged_in, player):
        team_list = self.get_active_teams()
        table = ''
        if self.has_started:
            table += '<table class="table table-condensed">'
            table += '<tr><th>Team</th><th>Rating</th><th>Record</th></tr>'
            for team in team_list:
                table += '<tr>'
                total_players = 0
                team_players = TournamentPlayer.objects.filter(team=team)
                table += '<td>'
                if team_players and team_players.count() > 1:
                    for player in team_players:
                        table += '<table class="table table-borderless"><tr><td>'
                        if player.player.clan is not None:
                            table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                                player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

                        table += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                            player.player.token, player.player.name)

                        table += '</td>'
                        table += '</tr></table>'

                        total_players += 1
                elif team_players:
                    table += get_player_data(team_players[0].player)

                table += '</td>'
                table += '<td>{}</td>'.format(team.rating)
                table += '<td>{}-{}</td>'.format(team.wins, team.losses)
                table += '</tr>'
            table += "</table>"

        return table

    def get_bracket_game_data(self):
        return self.bracket_game_data

    def get_player_from_teamid(self, team):
        tplayer = TournamentPlayer.objects.filter(team=int(team))
        if tplayer:
            return tplayer[0].player

    def remove_template(self, templateid):
        if templateid.isnumeric():
            template = RealTimeLadderTemplate.objects.filter(template=int(templateid))
            if template:
                template[0].delete()
                return "Template removed."
            else:
                return "Template {} does not exist on this ladder.".format(templateid)
        else:
            return "The template you have entered in invalid."

    def add_template(self, templateid):
        if templateid.isnumeric():
            # lookup the template settings
            api = API()
            ret = api.api_create_fake_game_and_get_settings(templateid)
            # what is the template name?
            if 'success' in ret and ret['success'] == 'true':
                settings = ret['settings']
            if 'PersonalMessage' in settings:
                name = settings['PersonalMessage']
                template = RealTimeLadderTemplate(name=name, template=int(templateid), ladder=self)
                template.save()
            else:
                return "Template must have a personal message."
            return "Template added successfully."
        else:
            return "The template you have entered is invalid."


    @property
    def can_start_tourney(self):
        False

    def update_game_log(self):
        game_log = '<div class="row"><div class="container">'
        game_log += '<table class="table table-hover table_condensed clot_table compact stripe cell-border" id="game_log_data_table">'
        game_log += '<thead><tr>'
        game_log += '<th>Match-up</th><th>Link</th><th>State</th><th>Winner</th><th>End-Time</th>'
        game_log += '</tr></thead>'
        game_log += '<tbody>'

        games_output = []
        tournament_game_entries = TournamentGameEntry.objects.filter(tournament=self).order_by('-created_date')
        for entry in tournament_game_entries:
            if entry.game.id in games_output:
                continue

            game_log += '<tr>'

            # Match-Up
            game_log += '<td>{} vs. {}</td>'.format(get_team_data_sameline(entry.team), get_team_data_sameline(entry.team_opp))

            # link to the game
            game_log += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(entry.game.game_link)

            # Game State
            if entry.game.is_finished:
                finished_text = '<span class="text-success"><b>Finished</b></span>'
            else:
                finished_text = '<span class="text-info">{}</span>'.format(entry.game.current_state)
            game_log += '<td>{}</td>'.format(finished_text)

            # Winner
            winner = ""
            if entry.game.winning_team is not None:
                if entry.team.id == entry.game.winning_team.id:
                    winner = get_team_data(entry.team)
                else:
                    winner = get_team_data(entry.team_opp)
            game_log += '<td>{}</td>'.format(winner)

            # End-Time
            # game.game_finished_time check is redundant but is done for backwards compability with bad existing data
            end_time = entry.game.game_finished_time.strftime(
                "%b %d, %Y %H:%M:%S %p") if entry.game.is_finished and entry.game.game_finished_time else 'N/A'
            game_log += '<td>{}</td>'.format(end_time)

            game_log += '</tr>'

            games_output.append(entry.game.id)
        game_log += '</tbody></table></div></div>'
        self.game_log = game_log
        self.save()

    def update_bracket_game_data(self):
        ranked_unranked = self.get_ranked_unranked_teams()
        team_list = ranked_unranked[0] + ranked_unranked[1]
        table = ''
        if self.has_started:
            table += '<table class="table table-condensed">'
            table += '<tr><th>Rank</th><th>Team</th><th>Rating</th><th>Record</th></tr>'
            current_team = 1
            for team in team_list:
                table += '<tr>'
                if team.ranked:
                    table += '<td>{}</td>'.format(current_team)
                    current_team += 1
                else:
                    table += '<td>{}</td>'.format("Unranked")

                total_players = 0
                team_players = TournamentPlayer.objects.filter(team=team)
                table += '<td>'
                if team_players and team_players.count() > 1:
                    for player in team_players:
                        table += '<table class="table table-borderless"><tr><td>'
                        if player.player.clan is not None:
                            table += '<a href="https://warzone.com{}" target="_blank"><img src="{}" alt="{}" /></a>'.format(
                                player.player.clan.icon_link, player.player.clan.image_path, player.player.clan.name)

                        table += '<a href="/stats/{}" target="_blank">{}</a>&nbsp;'.format(
                            player.player.token, player.player.name)

                        table += '</td>'
                        table += '</tr></table>'

                        total_players += 1
                elif team_players:
                    table += get_player_data(team_players[0].player)

                table += '</td>'
                table += '<td>{}</td>'.format(team.rating)
                table += '<td>{}-{}</td>'.format(team.wins, team.losses)
                table += '</tr>'
            table += "</table>"

        self.bracket_game_data = table
        self.save()

    def pick_template_for_game(self, team1, team2, templates_list):
        # each team must get a different template than the last 2 games, and must be allowed to play it
        templates_list_copy = templates_list.copy()

        log_tournament("Template list before prune: {}".format(templates_list_copy), self)
        # remove the last 2 templates each team played from the list
        games1 = TournamentGameEntry.objects.filter(team=team1).order_by('-created_date')[:2]
        for entry in games1:
            if entry.game.templateid != 0 and entry.game.templateid in templates_list_copy:
                templates_list_copy.remove(entry.game.templateid)

        games2 = TournamentGameEntry.objects.filter(team=team2).order_by('-created_date')[:2]
        for entry in games2:
            if entry.game.templateid != 0 and entry.game.templateid in templates_list_copy:
                templates_list_copy.remove(entry.game.templateid)

        log_tournament("Template list after prune: {}".format(templates_list_copy), self)
        while True:
            shuffle(templates_list_copy)
            for tid in templates_list_copy:
                log_tournament("Picked new template out of the list: {}".format(tid), self)
                if self.is_template_allowed(tid, team1) and self.is_template_allowed(tid, team2):
                    log_tournament("Picked FINAL template for game: {}".format(tid), self)
                    return tid


    def process_new_games(self):
        # handles creating new ladder games between players
        templates_list = []
        templates = RealTimeLadderTemplate.objects.filter(ladder=self)
        for t in templates:
            templates_list.append(t.template)

        round = TournamentRound.objects.filter(tournament=self, round_number=1)
        if not round:
            round = TournamentRound(tournament=self, round_number=1)
            round.save()
        else:
            round = round[0]

        if len(templates_list) > 0:
            teams_find_games = []
            teams = TournamentTeam.objects.filter(tournament=self, active=True).order_by('joined_time')
            for team in teams:
                # if the team has been sitting around for more than 30 minutes with no game
                # remove them if they are the only player on the ladder
                time_spent = timezone.now() - team.joined_time
                if time_spent.total_seconds() > (60*30):  # 30 minutes
                    log_tournament("Removing {} from ladder due to being on it for more than 30 minutes without a game.".format(team.id), self)
                    team.active = False
                    team.save()
                    self.number_players -= 1
                    self.save()
                    continue
                if get_games_unfinished_for_team(team.id, self) == 0:
                    teams_find_games.append(team)

            teams_find_games_against = teams_find_games.copy()
            # loop through teams_find_games, trying to get a matchup of an opponent from
            # teams_find_games_against, popping off teams that are the same or teams
            # that get games until we have exhausted all possibilities
            class ContinueOnError(Exception):  # define an exception to kick us back to the top of trying to find games
                pass

            while len(teams_find_games) > 0:
                try:
                    for team1_idx in range(len(teams_find_games)):
                        for team2_idx in range(len(teams_find_games_against)):
                            team1 = teams_find_games[team1_idx]
                            team2 = teams_find_games_against[team2_idx]
                            if team1.id == team2.id:
                                teams_find_games.pop(team1_idx)
                                raise ContinueOnError
                            
                            log_tournament("# of teams joined but not in a game: {}".format(len(teams_find_games)), self)
                            tid = self.pick_template_for_game(team1, team2, templates_list)

                            game_data = "{}.{}".format(team1.id, team2.id)

                            if get_games_against_since_hours(team1, team2, self, 1) == 0:
                                extra_settings = self.get_game_extra_settings()
                                game = self.create_game_with_template_and_data(round, game_data, tid, extra_settings)
                                if game:
                                    # the two lists are being handled as we're iterating...
                                    # this means if team1 gets a game against team2 we need to remove
                                    # team1 and team2 from both lists
                                    # that's hard to do since the indexes could be different so
                                    # after we create a game we explicitly remove them from each
                                    # list
                                    teams_find_games.pop(team1_idx)
                                    teams_find_games_against.pop(team2_idx)

                                    log_tournament("Created game {} vs {}: {} leave_after_game:{}, {}.leave_after_game:{}".format(team1.id, team2.id, team1.id, team1.leave_after_game, team2.id, team2.leave_after_game), self)

                                    if team1.leave_after_game:
                                        team1.active = False
                                        self.number_players -= 1
                                    if team2.leave_after_game:
                                        team2.active = False
                                        self.number_players -= 1

                                    team1.joined_time = timezone.now()
                                    team2.joined_time = timezone.now()
                                    self.save()
                                    team1.leave_after_game = False
                                    team2.leave_after_game = False

                                    # need to rest join times
                                    team1.save()
                                    team2.save()

                                    for i in range(len(teams_find_games)):
                                        if teams_find_games[i].id == team2.id:
                                            teams_find_games.pop(i)
                                            break
                                    for i in range(len(teams_find_games_against)):
                                        if teams_find_games_against[i].id == team1.id:
                                            teams_find_games_against.pop(i)
                                            break

                                    # we must bail here so we can try again
                                    # this resets our indexes
                                    raise ContinueOnError
                            else:
                                print("Teams have had a game in 1 hour, continue looking")
                    # if we get here, we must pop the item from the list and keep going
                    teams_find_games.pop(team1_idx)
                    raise ContinueOnError
                except ContinueOnError:
                    pass

    def get_game_extra_settings(self):
        settings = {}
        settings['Pace'] = 'RealTime'
        settings['DirectBoot'] = str(int(self.direct_seconds_per_turn/60))
        settings['AutoBoot'] = str(int(self.auto_boot_seconds/60))

        settings['BankingBootTimes'] = {'BankAmount': 0, 'InitialBankInMinutes' : '{}'.format(int(self.seconds_banked/60))}

        settings['PracticeGame'] = False
        settings.update({'BootedPlayersTurnIntoAIs': False, 'SurrenderedPlayersTurnIntoAIs': False, 'TimesCanComeBackFromAI': 0})
        print("Extra game settings: {}".format(settings))
        return settings

    def handle_finish_game_with_info(self, game_info):
        # handle the game info here
        log_tournament("[RTL]: Finished game_info: {}".format(game_info), self)
        if 'players' in game_info:
            players_data = game_info['players']
            for data in players_data:
                if 'state' in data and (data['state'] == 'Invited' or data['state'] == 'Booted' or data['state'] == 'Declined'):
                    # force remove this player from the ladder
                    if 'id' in data:
                        token = data['id']
                        player = TournamentPlayer.objects.filter(player__token=token)
                        if player:
                            player[0].team.active = False
                            player[0].team.save()
                            self.number_players -= 1
                            self.save()
                            log_tournament("Removing player {} ({}) from ladder".format(player[0].player.name, player[0].player.token), self)

    def join_leave_player(self, player, join, leave_after_game):
        tplayer = TournamentPlayer.objects.filter(player=player, tournament=self)
        if tplayer:
            tplayer = tplayer[0]
            # TODO for team ladder all players will have to be active
            if tplayer.team.active and join:
                return "You're already on the ladder!"
            elif not tplayer.team.active and join:
                # TODO check template validity first....
                tplayer.team.active = True
                tplayer.team.joined_time = timezone.now()
                tplayer.team.leave_after_game = leave_after_game
                tplayer.team.save()
                self.number_players += 1
                self.save()
                log_tournament(
                    "Team {} joined the ladder, leave after game: {}".format(tplayer.team.id, leave_after_game), self)
                return "You've joined the ladder!"
            elif tplayer.team.active and not join:
                tplayer.team.active = False
                tplayer.team.leave_after_game = False
                tplayer.team.save()
                self.number_players -= 1
                if self.number_players < 0:
                    self.number_players = 0
                self.save()
                return "You've left the ladder. Come back again soon."
            elif not tplayer.team.active and not join:
                return "You're currently not on the ladder."
        else:
            team = TournamentTeam(tournament=self, players=self.players_per_team, active=True, max_games_at_once=1, joined_time=timezone.now(), leave_after_game=leave_after_game)
            team.save()
            tplayer = TournamentPlayer(player=player, tournament=self, team=team)
            tplayer.save()
            self.number_players += 1
            self.save()
            return "Looks like you're new to the **{}**. Welcome, and best of luck!".format(self.name)

    def join_leave_discord(self, discord_id, join, leave_after_game):
        try:
            player = Player.objects.get(discord_member__memberid=discord_id)
            return self.join_leave_player(player, join, leave_after_game)
        except ObjectDoesNotExist:
            return "Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions."

    def get_current_vetoes(self, discord_id):
        try:
            player = Player.objects.get(discord_member__memberid=discord_id)
        except ObjectDoesNotExist:
            return "Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions."
        try:
            tp = TournamentPlayer.objects.get(player=player, tournament=self)
            data = ""
            vetoes = RealTimeLadderVeto.objects.filter(ladder=self, team=tp.team)
            if vetoes:
                data += "{}, your vetoes are:\n".format(player.name)
                for veto in vetoes:
                    data += "{} | {}\n".format(veto.template.name, veto.template.template)
                return data
            else:
                return "You're a very diverse player, you have not vetoed any templates yet."
        except ObjectDoesNotExist:
            return "You haven't joined the ladder yet. You must join the ladder in order to veto a template."

    def is_player_allowed_join(self, player):
        # loop through all the templates and see if the player is allowed to join
        if player:
            templates = RealTimeLadderTemplate.objects.filter(ladder=self)
            for t in templates:
                allowed_join = is_player_allowed_join_by_token(player.token, t.template)
                # we only need a single template valid to be able to play...
                print("{} is {} allowed to play template {}".format(player.name.encode('utf-8'), allowed_join, t.template))
                if allowed_join:
                    return True
        return False

    def is_template_allowed(self, templateid, team):
        veto = RealTimeLadderVeto.objects.filter(team=team, ladder=self)
        if veto and veto[0].template.template == int(templateid):
            log_tournament("Found template veto {} for team {}".format(templateid, team.id), self)
            return False
        else:
            log_tournament("Template {} was not vetoed by team {}...checking requirements..".format(templateid, team.id), self)
            # check to see if the player can even play this template....
            tplayer = TournamentPlayer.objects.filter(team=team)
            if tplayer:
                tplayer = tplayer[0]
                return is_player_allowed_join_by_token(tplayer.player.token, templateid)
            return False

    def veto_template(self, discord_id, templateid, remove):
        # attempt to veto a template, and if they have already vetoed one tell them
        if templateid.isnumeric():
            template = RealTimeLadderTemplate.objects.filter(template=int(templateid))
            if template:
                template = template[0]
                try:
                    player = Player.objects.get(discord_member__memberid=discord_id)
                    tp = TournamentPlayer.objects.get(player=player, tournament=self)
                except ObjectDoesNotExist:
                    return "Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions."

                total_vetoes = RealTimeLadderVeto.objects.filter(ladder=self, team=tp.team)
                if total_vetoes.count() == self.max_vetoes and not remove:
                    return "You already have vetoed the max ({}) templates. Please use the **-vr templateid** command on the ladder to remove a veto.".format(self.max_vetoes)

                # are we adding or removing?
                if remove:
                    veto = RealTimeLadderVeto.objects.filter(template=template, ladder=self, team=tp.team)
                    if veto:
                        veto[0].delete()
                        return "You've removed your veto for {} | {}".format(template.name, templateid)
                    else:
                        return "You do not currently have a veto for {}".format(template.name)
                else:
                    veto = RealTimeLadderVeto.objects.filter(template=template, ladder=self, team=tp.team)
                    if veto:
                        return "You've already vetoed {}.".format(template.name)
                    veto = RealTimeLadderVeto(template=template, ladder=self, team=tp.team)
                    veto.save()
                    return "Vetoed {} successfully.".format(template.name)
            else:
                return "Please enter a valid template id."
        else:
            return "Please enter a valid template id."

    def join_ladder(self, discord_id, leave_after_game):
        return self.join_leave_discord(discord_id, True, leave_after_game)

    def leave_ladder(self, discord_id):
        return self.join_leave_discord(discord_id, False, False)

    def get_game_data(self, game_list):
        data = ""
        for game in game_list:
            teams = game.teams
            team1 = TournamentTeam.objects.filter(id=int(teams.split('.')[0]), tournament=self)
            team2 = TournamentTeam.objects.filter(id=int(teams.split('.')[1]), tournament=self)
            if team1 and team2:
                # lookup the players on the team
                data += "{} vs. {} | [Game Link]({})\n".format(get_team_data_no_clan(team1[0]),
                                                               get_team_data_no_clan(team2[0]), game.game_link)
        return data

    def get_current_games(self):
        # returns a list of all current games
        data = ""
        games = TournamentGame.objects.filter(tournament=self, is_finished=False)
        if games:
            data = self.get_game_data(games)
            data += "\n\n"
        # now grab the last 10 that finished
        finished_data = ""
        finished_games = TournamentGame.objects.filter(tournament=self, is_finished=True).order_by('-game_finished_time')[:10]
        if finished_games:
            finished_data = self.get_game_data(finished_games)

        if len(data) > 0 or len(finished_data) > 0:
            return (True, (data, finished_data))
        else:
            return (False, "There are no games in progress on the ladder.")

    def get_current_joined(self):
        data = "__**Players currently joined**__\n"
        teams = TournamentTeam.objects.filter(tournament=self, active=True).order_by('-rating')
        if teams:
            for team in teams:
                data += "{} | {} {}-{} \n".format(team.rating, get_team_data_no_clan(team), team.wins, team.losses)
        else:
            data += "There are no players currently on the ladder."
        return data

    def get_current_rankings(self, page):
        ranked_unranked = self.get_ranked_unranked_teams()
        teams = ranked_unranked[0] + ranked_unranked[1]

        # slice the list based on the page
        if page.isnumeric():
            page = int(page)
            # page == 1 is the first page, page == 2 is the second
            start = 10 * (page - 1)
            end = 10*page

            teams = teams[start:end]
            current_team = start + 1

            data = "__**Ladder Rankings**__ - Viewing Rankings {}-{}\n".format(current_team, end)
            if len(teams) > 0:
                for team in teams:
                    if team.ranked:
                        ranked_text = "{}".format(current_team)
                    else:
                        ranked_text = "Unranked"
                    data += "{} | {} | {}\n".format(ranked_text, team.rating, get_team_data_no_clan(team))
                    current_team += 1
                return data
            else:
                return data + "There are no players/rankings to view."
        else:
            return "The page to view must be numeric."

    def get_current_templates(self):
        data = ""
        templates = RealTimeLadderTemplate.objects.filter(ladder=self)
        if not templates or templates.count() == 0:
            data += "There are currently no templates added"
            return data

        for t in templates:
            data += "{} | {} | [Template Link](https://warzone.com/MultiPlayer?TemplateID={}){}".format(t.name, t.template, t.template, embed_list_special_delimiter())
        return data

    def get_player_data(self, discord_id):
        # get's the current player data
        data = ""
        try:
            player = Player.objects.get(discord_member__memberid=discord_id)
            tp = TournamentPlayer.objects.get(player=player, tournament=self)
        except ObjectDoesNotExist:
            return (False, "Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions. If you are linked to the CLOT you must join the ladder in order to use this command")

        if tp:
            data += "Player: {}\nRating: {}\nTotal W-L: {}-{}\n\n".format(get_team_data_no_clan(tp.team), tp.team.rating, tp.team.wins, tp.team.losses)
            return (True, data)
        else:
            return (False, "You haven't joined the ladder yet")

class RealTimeLadderTemplate(models.Model):
    template = models.IntegerField(default=0, blank=True, null=True, db_index=True)
    ladder = models.ForeignKey('RealTimeLadder', blank=True, null=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, default="My Template Name", blank=True, null=True)

    def __str__(self):
        return "{} | {}".format(self.template, self.name)


class RealTimeLadderVeto(models.Model):
    template = models.ForeignKey('RealTimeLadderTemplate', blank=True, null=True, on_delete=models.CASCADE)
    team = models.ForeignKey('TournamentTeam', blank=True, null=True, on_delete=models.CASCADE)
    ladder = models.ForeignKey('RealTimeLadder', blank=True, null=True, on_delete=models.CASCADE)

    def __str__(self):
        return "[{}]: {} vetoed by {}".format(self.ladder.name, self.template.name, self.team.id)

class MultiDayLadder(Tournament):
    type = "MDL"

    def update_game_log(self):
        try:
            mdl_url = "http://md-ladder.cloudapp.net/api/v1.0/players/"

            content = urllib.request.urlopen(mdl_url).read()

            data = json.loads(content)
            num_players = 0
            for index, player in enumerate(data['players']):
                # once we have the players, start printing out each of the top 10
                if 'rank' in player:
                    num_players += 1

            print("Found {} players on the MDL".format(num_players))
            self.number_players = num_players
            self.save()
        except HTTPError:
            pass
        except Exception as e:
            raise e

    def get_game_log(self):
        pass

    def update_bracket_game_data(self):
        pass

    def get_bracket_game_data(self):
        pass

    def process_new_games(self):
        pass

    def get_url(self):
        return "http://md-ladder.cloudapp.net/"


class DummyTournament(Tournament):
    def get_bracket_game_data(self):
        return self.bracket_game_data

    def update_bracket_game_data(self):
        self.bracket_game_data = ""

    def update_game_log(self):
        self.game_log = ""



class TestContent():

    template_data_12345 = {
    }

    def team_game(self, team1, team2):
        ret = {
            "termsOfUse": "Please use this data feed responsibly, as it can consume significant amounts of server resources if called repeatedly.  After getting the data for a game, please store the data locally so you don't need to retrieve it from the Warzone server again.  The format of this data feed may change in the future.  The feed requires that you be signed into your member Warzone account to use.  If you're trying to access it programmatically, you may POST your username and API Token to this page in the format Email=your@email.com&APIToken=token",
            "id": "17459334",
            "state": "Finished",
            "name": "Australia 5 vs. 5 - pure skill: First Round",
            "numberOfTurns": "6",
            "lastTurnTime": "1/9/2019 08:02:56",
        }

        # lookup the players from the teams we've passed in, and make sure we've added those ids
        # to the team
        tournament_team1 = TournamentTeam.objects.filter(pk=int(team1))
        tournament_team2 = TournamentTeam.objects.filter(pk=int(team2))

        ret['players'] = []
        if tournament_team1 and tournament_team2:
            # lookup the players
            tournament_players1 = TournamentPlayer.objects.filter(team=tournament_team1[0])
            tournament_players2 = TournamentPlayer.objects.filter(team=tournament_team2[0])
            if tournament_players1 and tournament_players2:
                for player1 in tournament_players1:
                    ret['players'].append({
                            "id": "{}".format(player1.player.token),
                            "name": "Symarion Muskoka",
                            "isAI": "False",
                            "humanTurnedIntoAI": "False",
                            "hasCommittedOrders": "True",
                            "color": "#0000ff",
                            "state": "Won",
                            "team": "{}".format(team1)
                        })

                for player2 in tournament_players2:
                    ret['players'].append({
                            "id": "{}".format(player2.player.token),
                            "name": "Totem",
                            "isAI": "False",
                            "humanTurnedIntoAI": "False",
                            "hasCommittedOrders": "True",
                            "color": "#00ff05",
                            "state": "SurrenderAccepted",
                            "team": "{}".format(team2)
                        })
        return ret