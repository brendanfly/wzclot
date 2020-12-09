from wlct.models import Clan, Player, DiscordUser, DiscordChannelClanFilter, DiscordChannelPlayerFilter, DiscordChannelTournamentLink, TournamentAdministrator, DiscordTournamentUpdate
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision, TournamentGame, TournamentGameEntry, TournamentRound, get_team_data_no_clan_player_list
from wlct.logging import ProcessGameLog, ProcessNewGamesLog, log_command_exception
from wlct.clotbook import DiscordChannelCLOTBookLink, get_clotbook, BetGameOdds, BetTeamOdds, Bet
from wlct.logging import log_exception, log, LogLevel, Logger, log_bot_msg, log_cb_msg
import traceback
from django.conf import settings
from channels.db import database_sync_to_async

'''
Helper class that does the async interactions with the django application
'''
class CLOTBridge:

    def __init__(self):
        pass  # do nothing for now...maybe eventually we will cache stuff?

    '''
    Methods used to read querysets in the bot
    '''
    @database_sync_to_async
    def getPlayers(self, **kwargs):
        return list(Player.objects.filter(**kwargs))

    @database_sync_to_async
    def getPlayersOrderByName(self, **kwargs):
        return list(Player.objects.filter(**kwargs).order_by('name'))

    @database_sync_to_async
    def getPlayersAll(self):
        return list(Player.objects.all())

    @database_sync_to_async
    def getRealTimeLadders(self, **kwargs):
        return list(RealTimeLadder.objects.filter(**kwargs))

    @database_sync_to_async
    def getRealTimeLaddersAll(self):
        return list(RealTimeLadder.objects.all())

    @database_sync_to_async
    def getTournaments(self, **kwargs):
        return list(Tournament.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentsAll(self):
        return list(Tournament.objects.all())

    @database_sync_to_async
    def getTournamentPlayers(self, **kwargs):
        return list(TournamentPlayer.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentGameEntries(self, **kwargs):
        return list(TournamentGameEntry.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentTeams(self, **kwargs):
        return list(TournamentTeam.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentTeamsOrderByRatingWins(self, **kwargs):
        return list(TournamentTeam.objects.filter(**kwargs).order_by('-rating', '-wins'))

    @database_sync_to_async
    def getLogs(self, **kwargs):
        return list(Logger.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentUpdates(self, **kwargs):
        return list(DiscordTournamentUpdate.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentRounds(self, **kwargs):
        return list(TournamentRound.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentAdministrators(self, **kwargs):
        return list(TournamentAdministrator.objects.filter(**kwargs))

    @database_sync_to_async
    def getChannelTournamentLinks(self, **kwargs):
        return list(DiscordChannelTournamentLink.objects.filter(**kwargs))

    @database_sync_to_async
    def getChannelTournamentLinksAll(self):
        return list(DiscordChannelTournamentLink.objects.all())

    @database_sync_to_async
    def getGames(self, **kwargs):
        return list(TournamentGame.objects.filter(**kwargs))

    @database_sync_to_async
    def getGamesAll(self):
        return list(TournamentGame.objects.all())

    @database_sync_to_async
    def getDiscordUsers(self, **kwargs):
        return list(DiscordUser.object.filter(**kwargs))

    @database_sync_to_async
    def getDiscordChannelClanFilters(self, **kwargs):
        return list(DiscordChannelClanFilter.objects.filter(**kwargs))

    @database_sync_to_async
    def getDiscordChannelPlayerFilters(self, **kwargs):
        return list(DiscordChannelPlayerFilter.objects.filter(**kwargs))

    @database_sync_to_async
    def getClanLeagueTournaments(self, **kwargs):
        return list(ClanLeagueTournament.objects.filter(**kwargs))

    @database_sync_to_async
    def getMonthyTemplateRotations(self, **kwargs):
        return list(MonthlyTemplateRotation.objects.filter(**kwargs))

    @database_sync_to_async
    def getClans(self, **kwargs):
        return list(Clan.objects.filter(**kwargs))

    @database_sync_to_async
    def getClansAllOrderById(self, **kwargs):
        return list(Clan.objects.filter(**kwargs).order_by('id'))

    @database_sync_to_async
    def getClansAll(self, **kwargs):
        return list(Clan.objects.all())

    @database_sync_to_async
    def getClanLeagues(self, **kwargs):
        return list(ClanLeague.objects.filter(**kwargs))

    @database_sync_to_async
    def getClanLeagueDivisions(self, **kwargs):
        return list(ClanLeagueDivision.objects.filter(**kwargs))

    @database_sync_to_async
    def getClanLeagueDivisionsOrderByTitle(self, **kwargs):
        return list(ClanLeagueDivision.objects.filter(**kwargs).order_by('title'))

    @database_sync_to_async
    def getClanLeagueTournaments(self, **kwargs):
        return list(ClanLeagueTournament.objects.filter(**kwargs))

    @database_sync_to_async
    def getClanLeagueTournamentsOrderById(self, **kwargs):
        return list(ClanLeagueTournament.objects.filter(**kwargs).order_by('id'))

    @database_sync_to_async
    def findTournamentById(self, id, search_all):
        return find_tournament_by_id(id, search_all)

    @database_sync_to_async
    def findTournamentByDivisionId(self, id):
        return list(find_tournaments_by_division_id(id))

    @database_sync_to_async
    def getRealTimeLadder(self, id):
        return get_real_time_ladder(id)

    '''
    CLOTBook Methods
    '''
    @database_sync_to_async
    def getChannelClotbookLinks(self, **kwargs):
        return list(DiscordChannelCLOTBookLink.objects.filter(**kwargs))

    @database_sync_to_async
    def getBetGameOdds(self, **kwargs):
        return list(BetGameOdds.objects.filter(**kwargs))

    @database_sync_to_async
    def getBetTeamOdds(self, **kwargs):
        return list(BetTeamOdds.objects.filter(**kwargs))

    @database_sync_to_async
    def getBets(self, **kwargs):
        return list(Bet.objects.filter(**kwargs))

    @database_sync_to_async
    def getBetsOrderByCreatedTime(self, **kwargs):
        return list(Bet.objects.filter(**kwargs).order_by('-created_time'))

    @database_sync_to_async
    def getCLOTBook(self):
        return get_clotbook()

    @database_sync_to_async
    def updateBetOddsSentCreated(self, odds):
        odds.sent_created_notification = True
        odds.save()
        return odds

    @database_sync_to_async
    def updateBetOddsSentFinished(self, odds):
        odds.sent_finished_notification = True
        odds.save()
        return odds

    @database_sync_to_async
    def createChannelClotbookLink(self, **kwargs):
        link = DiscordChannelCLOTBookLink(**kwargs)
        link.save()
        return link

    @database_sync_to_async
    def createChannelTournamentLink(self, **kwargs):
        link = DiscordChannelTournamentLink(**kwargs)
        link.save()
        return link

    @database_sync_to_async
    def createDiscordChannelClanFilter(self, **kwargs):
        filter = DiscordChannelClanFilter(**kwargs)
        filter.save()
        return filter

    @database_sync_to_async
    def createDiscordChannelPlayerFilter(self, **kwargs):
        filter = DiscordChannelPlayerFilter(**kwargs)
        filter.save()
        return filter

    @database_sync_to_async
    def createGame(self, tournament, tournament_round, game_data):
        return tournament.create_game(tournament_round, game_data)

    @database_sync_to_async
    def createTournamentAdministrator(self, **kwargs):
        admin = TournamentAdministrator(**kwargs)
        admin.save()
        return admin

    '''
    Methods used to update the database as the bot performs work
    '''
    @database_sync_to_async
    def updateGameSeen(self, game):
        game.seen = True
        game.save()

    @database_sync_to_async
    def updateGameMentioned(self, game):
        game.mentioned = True
        game.save()

    @database_sync_to_async
    def updateDiscordUserLinkMention(self, discord_user):
        discord_user.link_mention = True
        discord_user.save()

    @database_sync_to_async
    def updateLogSeen(self, log):
        log.bot_seen = True
        log.save()

    @database_sync_to_async
    def updateTournamentUpdateSent(self, update):
        update.bot_send = True
        update.save()

    @database_sync_to_async
    def removeRealTimeLadderPlayer(self, rtl, player):
        rtl.leave_ladder(player)

    '''
    Methods used to create new objects, mainly discord user* objects
    '''
    @database_sync_to_async
    def createDiscordUser(self, **kwargs):
        discord_user = DiscordUser(*kwargs)
        discord_user.save()
        return discord_user

    '''
    Exception handling which also needs to be async
    '''
    @database_sync_to_async
    def log_exception(self):
        log(traceback.format_exc(), LogLevel.critical)

    @database_sync_to_async
    def log_command_exception(self, msg_info):
        log_command_exception(msg_info)

    @database_sync_to_async
    def log_bot_msg(self, msg):
        log_bot_msg(msg)

    @database_sync_to_async
    def getProcessGameLogs(self, **kwargs):
        return list(ProcessGameLog.objects.filter(**kwargs))

    @database_sync_to_async
    def getProcessNewGameLogs(self, **kwargs):
        return list(ProcessNewGamesLog.objects.filter(**kwargs))

    @database_sync_to_async
    def getProcessNewGameLogsLast2(self, **kwargs):
        return list(ProcessNewGamesLog.objects.filter(**kwargs).order_by('-timestamp')[:2])

    '''
    General methods
    '''
    @database_sync_to_async
    def deleteObject(self, obj):
        obj.delete()

    @database_sync_to_async
    def process_game(self, tournament, game):
        tournament.process_game(game)

    @database_sync_to_async
    def process_new_games(self, tournament):
        tournament.process_new_games()

    @database_sync_to_async
    def cache_data(self, tournament):
        tournament.cache_data()

    @database_sync_to_async
    def get_team_data(self, team):
        return get_team_data(team)

    @database_sync_to_async
    def get_team_data_no_clan(self, team):
        return get_team_data_no_clan(team)

    @database_sync_to_async
    def get_games_finished_for_teams_since(self, team, tournament, days):
        return get_games_finished_for_team_since(team, tournament, days)

    @database_sync_to_async
    def get_team_data_no_clan_player_list(self, data):
        return get_team_data_no_clan_player_list(data)

'''
Helper class to act as the ladder with a reference to the real ladder in order to make the DB operations async
'''
class RealTimeLadderBridge:

    def __init__(self, ladder):
        self.ladder = ladder

    @database_sync_to_async
    def get_active_team_count(self):
        return self.ladder.get_active_team_count()

    @database_sync_to_async
    def get_current_joined(self):
        return self.ladder.get_current_joined()

    @database_sync_to_async
    def join_ladder(self, discord_id, join):
        return self.ladder.join_ladder(discord_id, join)

    @database_sync_to_async
    def leave_ladder(self, discord_id):
        return self.ladder.leave_ladder(discord_id)

    @database_sync_to_async
    def get_current_games(self):
        return self.ladder.get_current_games()

    @database_sync_to_async
    def get_current_templates(self):
        return self.ladder.get_current_templates()

    @database_sync_to_async
    def get_current_rankings(self, option):
        return self.ladder.get_current_rankings(option)

    @database_sync_to_async
    def get_current_vetoes(self, discord_id):
        return self.ladder.get_current_vetoes(discord_id)

    @database_sync_to_async
    def veto_template(self, discord_id, option, veto):
        return self.ladder.veto_template(discord_id, option, veto)

    @database_sync_to_async
    def remove_template(self, option):
        return self.ladder.remove_template(option)

    @database_sync_to_async
    def add_template(self, option):
        return self.ladder.add_template(option)

    @database_sync_to_async
    def update_max_vetoes(self, vetoes):
        self.ladder.max_vetoes = vetoes
        self.ladder.save()

    @database_sync_to_async
    def get_player_data(self, discord_id):
        return self.ladder.get_player_data(discord_id)


