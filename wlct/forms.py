from django.forms import ModelForm
from wlct.tournaments import SwissTournament, Tournament, TournamentTeam, SeededTournament, GroupStageTournament, GroupStageTournamentGroup, MonthlyTemplateRotation, PromotionalRelegationLeague, ClanLeague, RoundRobinTournament, RoundRobinRandomTeams
from wlct.form_message_handling import FormError
from wlct.validators import get_int, get_dropdown_to_boolean
import math
from django.conf import settings
import json
from wlct.logging import log_exception

def is_power2(num):
    return ((num & (num - 1)) == 0) and num != 0


class TournamentForm:

    def __init__(self, formdata, min_teams):
        self.name = formdata['name'].strip()
        self.template = formdata['templateid']
        self.description = formdata['description'].strip()
        self.type = formdata['type']
        self.is_started = False
        self.number_players = get_int(formdata['number_players'])
        self.number_teams = get_int(formdata['number_teams'])
        self.players_per_team = get_int(formdata['players_team'])
        self.private = get_dropdown_to_boolean('private', formdata)
        self.template_settings = formdata['templatesettings']
        self.number_rounds = formdata['rounds']
        self.errors = None
        self.multi_day = False
        self.start_when_full = get_dropdown_to_boolean('start_options_when_full', formdata)

        self.teams_per_game = 2
        self.max_players_per_team = 4
        self.min_players_per_team = 1
        self.max_teams = 256
        self.min_teams = min_teams

        self.max_players = self.max_teams * self.max_players_per_team
        self.min_players = self.min_teams * self.min_players_per_team

        self.max_name = 64
        self.min_name = 3
        self.max_description = 2000

        self.is_league = False

    def is_multiday(self):
        try:
            settings_dict = json.loads('''{}'''.format(self.template_settings))
            if 'Pace' in self.template_settings:
                return settings_dict['Pace'] == "MultiDay"
        except:
            log_exception()

    def validate_players_teams(self):
        # at this point the # of players has been validated
        if (self.number_teams < self.min_teams) or (self.number_teams > self.max_teams):
            self.errors = FormError({'error': "This tournament can only contain between {}-{} teams.".format(self.min_teams, self.max_teams)}).msgs
            return False
        elif not is_power2(self.number_teams):
            self.errors = FormError({'error': "You may only have # of teams = power of 2"}).msgs
            return False
        elif (self.number_players < self.min_players) or (self.number_players > self.max_players):
            self.errors = FormError({'error': "Seeded tournaments can only contain between {}-{} players.".format(self.min_players, self.max_players)}).msgs
            return False
        elif (self.players_per_team < self.min_players_per_team) or (self.players_per_team > self.max_players_per_team):
            self.errors = FormError({'error': "Players per team must be between {}-{}.".format(self.min_players_per_team, self.max_players_per_team)}).msgs
            return False
        elif (self.number_teams % 2) is not 0:
            self.errors = FormError({'error': "This tournament can only contain an even number of teams."}).msgs
            return False

        return True

    def is_valid(self):
        self.multi_day = self.is_multiday()
        if (len(self.name) > self.max_name) or (len(self.name) < self.min_name):
            self.errors = FormError({'error': "Tournament names can only be between 3-64 characters."}).msgs
            return False
        elif not self.template.isnumeric():
            self.errors = FormError({'error': "Template IDs must be entirely numeric."}).msgs
            return False
        elif self.template_settings == "":
            self.errors = FormError({'error': "The template is invalid, or we had trouble getting the settings."}).msgs
            return False
        elif len(self.description) > self.max_description:
            self.errors = FormError({'error': "Tournament description must be less than 2000 characters."}).msgs
            return False
        elif not self.validate_players_teams():
            return False

        return True

class GroupTournamentForm(TournamentForm):

    def __init__(self, formdata):
        self.tournament_type = "Group Stage"
        self.knockout_teams = get_int(formdata['knockout_teams'])
        self.knockout_rounds = math.ceil(math.log(self.knockout_teams, 2))

        super(GroupTournamentForm, self).__init__(formdata, 4)

    def create_and_save(self, player):
        tournament = GroupStageTournament(name=self.name, knockout_rounds=self.knockout_rounds, knockout_teams=self.knockout_teams, multi_day=self.multi_day, start_option_when_full=False,private=self.private, description=self.description, template=self.template, template_settings=self.template_settings, max_players=self.number_players, teams_per_game=self.teams_per_game,created_by=player,players_per_team=self.players_per_team,number_rounds=self.number_rounds,number_players=0,host_sets_tourney=True)
        tournament.save()

        # create all the objects associated with this tournament
        # including groups, teams, and
        for index in range(1, self.number_teams+1):
            tournament_team = TournamentTeam(tournament=tournament, players=tournament.players_per_team, team_index=index)
            tournament_team.save()

        return tournament.id

class SeededTournamentForm(TournamentForm):

    def __init__(self, formdata):
        self.tournament_type = "Seeded"

        super(SeededTournamentForm, self).__init__(formdata, 4)

    def create_and_save(self, player):
        tournament = SeededTournament(name=self.name,multi_day=self.multi_day,start_option_when_full=False,private=self.private,description=self.description,template=self.template,template_settings=self.template_settings,max_players=self.number_players,teams_per_game=self.teams_per_game,created_by=player,players_per_team=self.players_per_team,number_rounds=self.number_rounds,number_players=0,host_sets_tourney=True)
        tournament.save()

        # create all the team objects associated with this tournament
        # range goes up to number of team, and stops so we need to add 1 to both sides of range
        for index in range(1, self.number_teams+1):
            tournament_team = TournamentTeam(tournament=tournament, players=tournament.players_per_team, team_index=index)
            tournament_team.save()

        return tournament.id

# we could use django model forms, but it's much harder to customize those so we just basically implement the same
# is_valid, and cleaned_data (as a dict)
# as well as provide the specific errors as to why something failed
class SwissTournamentForm(TournamentForm):

    def __init__(self, formdata):
        self.tournament_type = "Swiss"

        super(SwissTournamentForm, self).__init__(formdata, SwissTournament.min_teams)

    def create_and_save(self, player):
        # django query sets and model writes will do the right thing with regards to
        # SQL Injection
        # determine multi-day or real-time
        tournament = SwissTournament(name=self.name,multi_day=self.multi_day,start_option_when_full=self.start_when_full,private=self.private,description=self.description,template=self.template,template_settings=self.template_settings,max_players=self.number_players,teams_per_game=self.teams_per_game,created_by=player,players_per_team=self.players_per_team,number_rounds=self.number_rounds, number_players=0)
        tournament.save()

        # create all the team objects associated with this tournament
        # range goes up to number of team, and stops so we need to add 1 to both sides of range
        for index in range(1, self.number_teams+1):
            tournament_team = TournamentTeam(tournament=tournament, players=tournament.players_per_team, team_index=index)
            tournament_team.save()
        return tournament.id


class RoundRobinRandomTeamsForm(TournamentForm):

    def __init__(self, formdata):
        self.tournament_type = "Round Robin Random Teams"

        super(RoundRobinRandomTeamsForm, self).__init__(formdata, RoundRobinRandomTeams.min_teams)

    def create_and_save(self, player):
        tournament = RoundRobinRandomTeams(name=self.name, multi_day = self.multi_day, start_option_when_full=False, private=self.private, description=self.description, template=self.template, template_settings=self.template_settings, max_players=self.number_players, teams_per_game=self.teams_per_game, created_by=player, players_per_team=self.players_per_team, number_rounds=self.number_rounds, number_players=0)
        tournament.save()

        for i in range(1, self.number_teams+1):
            tournament_team = TournamentTeam(tournament=tournament, players=tournament.players_per_team, team_index=i)
            tournament_team.save()
        return tournament.id

class LeagueForm:
    def __init__(self, formdata):
        self.name = formdata['name'].strip()
        self.description = formdata['description'].strip()
        self.type = formdata['type']
        self.is_started = False
        self.players_per_team = get_int(formdata['players_team'])
        self.private = get_dropdown_to_boolean('private', formdata)
        self.errors = None
        self.multi_day = False
        self.template = formdata['templateid']
        self.template_settings = formdata['templatesettings']

        self.teams_per_game = 2
        self.max_players_per_team = 4
        self.min_players_per_team = 1
        self.players_per_team = 1

        self.max_name = 64
        self.min_name = 3
        self.max_description = 2000

        self.is_league = True

    def is_multiday(self):
        try:
            settings_dict = json.loads('''{}'''.format(self.template_settings))
            if 'Pace' in self.template_settings:
                return settings_dict['Pace'] == "MultiDay"
        except:
            log_exception()

    def is_valid(self):
        if (len(self.name) > self.max_name) or (len(self.name) < self.min_name):
            self.errors = FormError({'error': "League names can only be between 3-64 characters."}).msgs
            return False
        elif len(self.description) > self.max_description:
            self.errors = FormError({'error': "League description must be less than 2000 characters."}).msgs
            return False

        return True

    def fill_league_with_teams(self, tournament):
        for index in range(1, self.number_teams+1):
            tournament_team = TournamentTeam(tournament=tournament, players=tournament.players_per_team, team_index=index)
            tournament_team.save()

class MonthlyTemplateCircuitForm(LeagueForm):
    def __init__(self, formdata):
        self.tournament_type = "Monthly Template Circuit"
        print("Creating Monthly Template Circuit: {}".format(formdata))
        super(MonthlyTemplateCircuitForm, self).__init__(formdata)

    def is_valid(self):
        self.multi_day = self.is_multiday()
        if super(MonthlyTemplateCircuitForm, self).is_valid():  # must come first, set's self.multiday
            if not self.multi_day and not settings.DEBUG:
                self.errors = FormError({'error': "Monthly Template Circuits only support MultiDay templates."}).msgs
                return False
            elif not self.template.isnumeric() or self.template == "" or len(self.template_settings) == 0 or self.template_settings == "":
                self.errors = FormError({'error': "Template must be provided for the initial month."}).msgs
                return False
            return True
        return False

    def create_and_save(self, player):
        self.multi_day = True
        league = MonthlyTemplateRotation(has_started=True, is_league=True, name=self.name, multi_day=self.multi_day, private=self.private, description=self.description, teams_per_game=self.teams_per_game, created_by=player, players_per_team=self.players_per_team, number_players=0, max_players=0, current_template=self.template, template=self.template, template_settings=self.template_settings)
        league.save()
        league.start()

        return league.id

class PromotionRelegationLeagueForm(LeagueForm):
    def __init__(self, formdata):
        self.tournament_type = "Promotion/Relegation League"
        formdata_copy = formdata.copy()
        print("Creating Promotional Relegation League: {}".format(formdata_copy))
        formdata_copy.update({'templateid': 0})  # fill this in as there is no template for P/R league until a season is created
        super(PromotionRelegationLeagueForm, self).__init__(formdata_copy)

    def is_valid(self):
        return super(PromotionRelegationLeagueForm, self).is_valid()

    def create_and_save(self, player):
        self.multi_day = True
        league = PromotionalRelegationLeague(has_started=False, is_league=True, name=self.name, multi_day=self.multi_day, private=self.private, description=self.description, teams_per_game=self.teams_per_game, created_by=player, players_per_team=self.players_per_team, number_players=0, max_players=0, template=self.template, template_settings=self.template_settings)
        league.save()
        return league.id

class ClanLeagueForm(LeagueForm):
    def __init__(self, formdata):
        self.tournament_type = "Clan League"
        print("Creating Clan League: {}".format(formdata))
        super(ClanLeagueForm, self).__init__(formdata)

    def is_valid(self):
        print("Checking validity...")
        return super(ClanLeagueForm, self).is_valid()

    def create_and_save(self, player):
        # real-time clan leagues are just not supported at this time
        self.multi_day = True
        league = ClanLeague(has_started=False, is_league=True, name=self.name, multi_day=self.multi_day, private=self.private, description=self.description, teams_per_game=self.teams_per_game, created_by=player, players_per_team=0, number_players=0, max_players=0, template=0, template_settings="")
        league.save()
        return league.id



