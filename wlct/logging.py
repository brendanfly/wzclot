from django.db import models
from django.contrib import admin
import datetime
import traceback
from django.conf import settings
from enum import Enum

# list of levels
class LogLevel:
    informational = "Informational"
    critical = "Critical"
    error = "Error"
    warning = "Warning"
    tournament = "Tournament"
    game = "TournamentGame"
    game_status = "TournamentGameStatus"
    engine = "Engine"
    bot = "Bot"
    clean_logs = "Log Cleanup"
    process_game = "Process Game"
    process_new_games = "Process New Games"

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

def log_bot_msg(msg):
    logger = BotLog(msg=msg, level=LogLevel.bot)
    if settings.DEBUG:
        print("{} log: {}".format(logger.level, msg))
    logger.save()

class Logger(models.Model):

    msg = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    bot_seen = models.BooleanField(default=False)

    # free-form logging is the best kind, do not tie this to
    # another object so we can use any level we so choose
    level = models.CharField(max_length=64, null=True)

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
        return "[{}] Tournament {}-{}: {}".format(self.timestamp, self.tournament.id, self.tournament.name, self.msg)


class TournamentGameLog(Logger):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)


class TournamentGameStatusLog(Logger):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)

class BotLog(Logger):
    pass


class LogManager():

    def __init__(self, type, **kwargs):
        # kwargs are used to load the query set
        # type is used to determine what type
        self.kwargs = kwargs
        self.type = type

    # prunes the logs but removes all logs prior to the delta passed in
    # Ex.
    # kwargs['hours'] = 12 (prune all logs before 12 hours prior to the last log)
    # kwargs['days'] = 1 (prune all logs before 1 day prior to the last log)
    def prune_keep_last(self, **kwargs):
        print("Removing logs from finished items")
        logs = None
        log_end = "No log end"
        start = datetime.datetime.utcnow()
        if self.type == LogLevel.tournament:
            logs = TournamentLog.objects.filter(**self.kwargs).order_by('-pk')
            if logs:
                log_end = logs[0].timestamp - datetime.timedelta(**kwargs)
        if self.type == LogLevel.game:
            logs = TournamentGameLog.objects.filter(**self.kwargs).order_by('-pk')
            if logs:
                log_end = logs[0].timestamp - datetime.timedelta(**kwargs)
        if self.type == LogLevel.game_status:
            logs = TournamentGameStatusLog.objects.filter(**self.kwargs).order_by('-pk')
            if logs:
                log_end = logs[0].timestamp - datetime.timedelta(**kwargs)
        if self.type == LogLevel.process_game:
            logs = ProcessGameLog.objects.filter(**self.kwargs).order_by('-pk')
            if logs:
                log_end = logs[0].timestamp - datetime.timedelta(**kwargs)
        if self.type == LogLevel.process_new_games:
            logs = ProcessNewGamesLog.objects.filter(**self.kwargs).order_by('-pk')
            if logs:
                log_end = logs[0].timestamp - datetime.timedelta(**kwargs)

        print("Log end time to delete prior: {}".format(log_end))
        current_log = 0
        if logs:
            for l in logs.iterator():
                if l.timestamp < log_end:
                    if current_log == 0:
                        print("Removing {} logs 'finished' {} logs older than: {}, first log was {}".format(logs.count(),
                                                                                                        self.type, log_end,
                                                                                                        l.timestamp))
                    current_log += 1
                    l.delete()
        time_spent = datetime.datetime.utcnow() - start
        log("Spent {} seconds prune_keep_last logs.".format(time_spent.total_seconds()), LogLevel.clean_logs)

    # straight prunes the logs based on the parameters passed in
    def prune(self):
        start = datetime.datetime.utcnow()
        logs = None
        if self.type == LogLevel.critical:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.informational:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.warning:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.error:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.bot:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.engine:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.clean_logs:
            logs = Logger.objects.filter(**self.kwargs)
        if self.type == LogLevel.tournament:
            logs = TournamentLog.objects.filter(**self.kwargs)
        if self.type == LogLevel.game:
            logs = TournamentGameLog.objects.filter(**self.kwargs)
        if self.type == LogLevel.game_status:
            logs = TournamentGameStatusLog.objects.filter(**self.kwargs)
        if self.type == LogLevel.process_game:
            logs = ProcessGameLog.objects.filter(**self.kwargs)
        if self.type == LogLevel.process_new_games:
            logs = ProcessNewGamesLog.objects.filter(**self.kwargs)

        if logs:
            for l in logs.iterator():
                l.delete()
        end = datetime.datetime.utcnow() - start
        log("Spent {} seconds pruning {} logs.".format(end.total_seconds(), self.type), LogLevel.clean_logs)
