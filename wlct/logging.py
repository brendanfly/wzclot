from django.db import models
from django.contrib import admin
import datetime
import traceback
from django.conf import settings

# list of levels
class LogLevel():
    informational = "Informational"
    critical = "Critical"
    error = "Error"
    warning = "Warning"
    tournament = "Tournament"
    game = "TournamentGame"
    game_status = "TournamentGameStatus"


def log_exception():
    log(traceback.format_exc(), LogLevel.critical)

def log(msg, level):
    logger = Logger(msg=msg, level=level)

    if settings.DEBUG:
        print("{} log level: {}".format(level, msg))

    logger.save()

def log_tournament(msg, tournament):
    logger = TournamentLog(tournament=tournament, msg=msg, level=LogLevel.tournament)

    if settings.DEBUG:
        print("{} log: {}".format(logger.level, msg))

    logger.save()

def log_game(msg, tournament, game):
    logger = TournamentGameLog(msg=msg, tournament=tournament, game=game, level=LogLevel.game)

    if settings.DEBUG:
        print("{} log: {}".format(logger.level, msg))

    logger.save()

def log_game_status(msg, tournament, game):
    logger = TournamentGameStatusLog(msg=msg, tournament=tournament, game=game, level=LogLevel.game_status)

    if settings.DEBUG:
        print("{} log: {}".format(logger.level, msg))

    logger.save()

class Logger(models.Model):

    msg = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    # free-form logging is the best kind, do not tie this to
    # another object so we can use any level we so choose
    level = models.CharField(max_length=20, null=True)

    def __str__(self):
        return "[Time: {} Level: {}]: {}".format(self.timestamp, self.level, self.msg)


class ProcessGameLog(Logger):
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)

    def __str__(self):
        return "[Time: {} Level: {}]: GameID: {}".format(self.timestamp, self.level, self.game.gameid)


class ProcessNewGamesLog(Logger):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)


class TournamentLog(Logger):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    
    def __str__(self):
        return "Tournament {}-{}".format(self.tournament.id, self.tournament.name)


class TournamentGameLog(Logger):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)


class TournamentGameStatusLog(Logger):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)