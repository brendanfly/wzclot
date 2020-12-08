from wlct.models import Clan, Player, DiscordUser, DiscordChannelClanFilter, DiscordChannelPlayerFilter, DiscordChannelTournamentLink, TournamentAdministrator, DiscordTournamentUpdate
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision, TournamentGame, TournamentGameEntry, TournamentRound
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
    def getRealTimeLaddersAll(self):
        return list(RealTimeLadder.objects.all())

    @database_sync_to_async
    def getTournaments(self, **kwargs):
        return list(Tournament.objects.filter(**kwargs))

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
    def getLogs(self, **kwargs):
        return list(Logger.objects.filter(**kwargs))

    @database_sync_to_async
    def getTournamentUpdates(self, **kwargs):
        return list(DiscordTournamentUpdate.objects.filter(**kwargs))

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
    def getDiscordUsers(self, **kwargs):
        return list(DiscordUser.object.filter(**kwargs))

    @database_sync_to_async
    def getClanLeagueTournaments(self, **kwargs):
        return list(ClanLeagueTournament.objects.filter(**kwargs))

    @database_sync_to_async
    def findTournamentById(self, id, search_all):
        return find_tournament_by_id(id, search_all)

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

    @database_sync_to_async
    def updateBetOddsSentFinished(self, odds):
        odds.sent_finished_notification = True
        odds.save()

    @database_sync_to_async
    def createChannelClotbookLink(self, **kwargs):
        link = DiscordChannelCLOTBookLink(**kwargs)
        link.save()

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

    '''
    Methods used to create new objects, mainly discord user* objects
    '''
    @database_sync_to_async
    def createDiscordUser(self, **kwargs):
        discord_user = DiscordUser(*kwargs)
        discord_user.save()

    '''
    Exception handling which also needs to be async
    '''
    @database_sync_to_async
    def log_exception(self):
        log(traceback.format_exc(), LogLevel.critical)

    '''
    General Delete method
    '''
    @database_sync_to_async
    def deleteObject(self, obj):
        obj.delete()
