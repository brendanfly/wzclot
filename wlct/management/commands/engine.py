# the main engine for the scheduler
import threading
import datetime
from wlct.logging import log, LogLevel, log_exception, Logger, TournamentLog, TournamentGameLog, TournamentGameStatusLog, ProcessGameLog, ProcessNewGamesLog, BotLog
from bs4 import BeautifulSoup
from urllib.request import urlopen
from wlct.models import Clan, Engine, Player
from wlct.tournaments import ClanLeague, ClanLeagueTournament, find_tournament_by_id, Tournament, TournamentGame, TournamentPlayer, TournamentTeam, TournamentGameEntry, MonthlyTemplateRotation, MonthlyTemplateRotationMonth, TestContent
from django.conf import settings
from wlct.api import API
from django import db
import pytz
import threading
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.jobstores.base import ConflictingIdError
from django_apscheduler.jobstores import DjangoJobStore
from django.core.management.base import BaseCommand
import gc
from django.utils import timezone

def get_run_time():
    return 180

class Command(BaseCommand):
    help = "Runs the engine for cleaning up logs and creating new tournament games every 180 seconds"
    def handle(self, *args, **options):
        self.schedule_jobs()

    def schedule_jobs(self):
        # lookup the main scheduler, if it's not currently scheduled, add it every 3 min
        try:
            scheduler = BlockingScheduler()
            # If you want all scheduled jobs to use this store by default,
            # use the name 'default' instead of 'djangojobstore'.
            scheduler.add_jobstore(DjangoJobStore(), 'default')
            if not scheduler.running:
                scheduler.add_job(tournament_engine, 'interval', seconds=get_run_time(), id='tournament_engine',
                                  max_instances=1, coalesce=False)
                scheduler.add_job(tournament_caching, 'interval', seconds=(get_run_time()/2)*5, id='tournament_caching',
                                  max_instances=1, coalesce=False)
                scheduler.start()
        except ConflictingIdError:
            pass

def parse_and_update_clan_logo():
    try:
        url = 'https://www.warzone.com/Clans/List'
        clan_page = urlopen(url)

        text_soup = BeautifulSoup(clan_page, features="html.parser")

        log("Refreshing clans", LogLevel.engine)
        links = text_soup.findAll("a")
        for link in links:
            try:
                clan_id = link.attrs["href"].split('=')[1]
                clan_href = link.attrs["href"]
                if '/Clans' in clan_href:
                    clan_name = link.contents[2].strip()
                    image = link.findAll("img")[0].attrs["src"]
                    clan_exist = Clan.objects.filter(name=clan_name)
                    if not clan_exist:
                        clan = Clan(name=clan_name, icon_link=clan_href, image_path=image)
                        clan.save()
                        log("Added new clan: {}".format(clan_name), LogLevel.engine)
                    elif clan_exist and clan_exist[0].image_path != image:  # updated image code path
                        clan_exist[0].image_path = image
                        clan_exist[0].save()
            except:
                continue
    except Exception:
        log_exception()

def is_correct_player(player_token, player_team):
    try:
        player = Player.objects.filter(token=player_token)[0]
        tt = TournamentTeam.objects.filter(pk=player_team)[0]
        if player.clan and player.clan.name == tt.clan_league_clan.clan.name:
            return True

        tplayers = TournamentPlayer.objects.filter(team=tt)
        for tplayer in tplayers:
            if tplayer.player.token == player_token:
                return True
        return False
    except:
        log_exception()
        return False

def check_games(**kwargs):
    log("Running check_games, type={} on thread {}".format(kwargs['type'], threading.get_ident()), LogLevel.engine)
    caching = kwargs['type'] == 'cache'
    tournaments = Tournament.objects.filter(has_started=True, is_finished=False)
    for tournament in tournaments:
        child_tournament = find_tournament_by_id(tournament.id, True)
        if child_tournament and child_tournament.should_process_in_engine():
            log("Type[{}]: Checking games for tournament: {}".format(kwargs['type'], tournament.name), LogLevel.engine)
            try:
                if not child_tournament.game_creation_allowed and not caching:
                    continue
                games = TournamentGame.objects.filter(is_finished=False, tournament=tournament)
                log("Type[{}]: Processing {} games for tournament {}".format(kwargs['type'], games.count(), tournament.name), LogLevel.engine)
                for game in games.iterator():
                    # process the game
                    # query the game status
                    if not caching:
                        child_tournament.process_game(game)
                # in case tournaments get stalled for some reason
                # for it to process new games based on current tournament data
                if not caching:
                    log("Type[{}]: Processing new games for tournament {}".format(kwargs['type'], tournament.name), LogLevel.engine)
                    child_tournament.process_new_games()

                # after we process games we always cache the latest data for quick reads
                if caching:
                    log("Type[{}]: Caching data for {}".format(kwargs['type'], tournament.name), LogLevel.engine)
                    child_tournament.cache_data()
                log("Type[{}]: Finished processing games for tournament {}".format(kwargs['type'], tournament.name), LogLevel.engine)
            except Exception as e:
                log_exception()
            finally:
                child_tournament.update_in_progress = False
                child_tournament.save()
                log("Type[{}]: Child tournament {} update done.".format(kwargs['type'], tournament.name), LogLevel.engine)
        gc.collect()

def cleanup_logs():
    # get all the logs older than 2 days
    nowdate = datetime.datetime.utcnow()
    enddate = nowdate - datetime.timedelta(days=4)

    ''' TournamentLogs '''
    nowdate = datetime.datetime.utcnow()
    TournamentLog.objects.filter(timestamp__lt=enddate, is_finished=False).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning in progress TournamentLog.".format(time_spent.total_seconds()), LogLevel.clean_logs)

    nowdate = datetime.datetime.utcnow()
    tlogs = TournamentLog.objects.filter(is_finished=True).order_by('-pk')  # get the last logs first
    if tlogs:
        # grab the first one, then issue another query deleting everything older than 1 day before the first log
        log = tlogs[0]
        log_end = log.timestamp - datetime.timedelta(hours=12)
        TournamentLog.objects.filter(is_finished=True, timestamp__lt=log_end).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning finished TournamentLog".format(time_spent.total_seconds()), LogLevel.clean_logs)

    ''' TournamentGameLogs '''
    nowdate = datetime.datetime.utcnow()
    TournamentGameLog.objects.filter(timestamp__lt=enddate, is_finished=False).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning in progress TournamentGameLog".format(time_spent.total_seconds(), LogLevel.clean_logs))

    nowdate = datetime.datetime.utcnow()
    logs = TournamentGameLog.objects.filter(is_finished=True).order_by('-pk')  # get the last logs first
    if logs:
        # grab the first one, then issue another query deleting everything older than 1 day before the first log
        log = logs[0]
        log_end = log.timestamp - datetime.timedelta(hours=12)
        TournamentLog.objects.filter(is_finished=True, timestamp__lt=log_end).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning finished TournamentGameLog".format(time_spent.total_seconds()), LogLevel.clean_logs)

    ''' TournamentGameStatusLog '''
    nowdate = datetime.datetime.utcnow()
    TournamentGameStatusLog.objects.filter(timestamp__lt=enddate, is_finished=False).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning in progress TournamentGameLog".format(time_spent.total_seconds(), LogLevel.clean_logs))

    nowdate = datetime.datetime.utcnow()
    logs = TournamentGameStatusLog.objects.filter(is_finished=True).order_by('-pk')  # get the last logs first
    if logs:
        # grab the first one, then issue another query deleting everything older than 1 day before the first log
        log = logs[0]
        log_end = log.timestamp - datetime.timedelta(hours=12)
        TournamentGameStatusLog.objects.filter(is_finished=True, timestamp__lt=log_end).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning finished TournamentGameLog".format(time_spent.total_seconds()), LogLevel.clean_logs)

    ''' ProcessGame Logs '''
    nowdate = datetime.datetime.utcnow()
    ProcessGameLog.objects.filter(timestamp__lt=enddate, is_finished=False).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning in progress ProcessGameLog.".format(time_spent.total_seconds()), LogLevel.clean_logs)

    nowdate = datetime.datetime.utcnow()
    tlogs = ProcessGameLog.objects.filter(is_finished=True).order_by('-pk')  # get the last logs first
    if tlogs:
        # grab the first one, then issue another query deleting everything older than 1 day before the first log
        log = tlogs[0]
        log_end = log.timestamp - datetime.timedelta(hours=12)
        ProcessGameLog.objects.filter(is_finished=True, timestamp__lt=log_end).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning finished ProcessGameLog".format(time_spent.total_seconds()), LogLevel.clean_logs)

    ''' ProcessNewGame Logs '''
    nowdate = datetime.datetime.utcnow()
    ProcessNewGamesLog.objects.filter(timestamp__lt=enddate, is_finished=False).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning in progress ProcessGameLog.".format(time_spent.total_seconds()), LogLevel.clean_logs)

    nowdate = datetime.datetime.utcnow()
    tlogs = ProcessNewGamesLog.objects.filter(is_finished=True).order_by('-pk')  # get the last logs first
    if tlogs:
        # grab the first one, then issue another query deleting everything older than 1 day before the first log
        log = tlogs[0]
        log_end = log.timestamp - datetime.timedelta(hours=12)
        ProcessNewGamesLog.objects.filter(is_finished=True, timestamp__lt=log_end).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning finished ProcessGameLog".format(time_spent.total_seconds()), LogLevel.clean_logs)



    ''' Cleanup informational, critical, errors...etc... '''
    # for now delete all logs older than 4 days
    # eventually we will have separate logic for all logging types...as certain types of logs we want to keep around
    Logger.objects.filter(timestamp__lt=enddate).delete()
    time_spent = datetime.datetime.utcnow() - nowdate
    log("Spent {} seconds cleaning up all other logs.".format(time_spent.total_seconds()), LogLevel.clean_logs)


# globals to get executed on every load of the web server
slow_update_threshold = 25
current_clan_update = 1

def tournament_caching():
    cleanup_logs()
    check_games(type='cache')

def tournament_engine():
    try:
        global slow_update_threshold
        global current_clan_update

        if (current_clan_update % slow_update_threshold) == 0:
            parse_and_update_clan_logo()
            current_clan_update = 1
        else:
            current_clan_update += 1

        engine = Engine.objects.all()
        if engine and engine.count() == 0:
            # create the engine object!
            engine = Engine()
            engine.save()
        else:
            engine = engine[0]
            engine.last_run_time = timezone.now()
            engine.next_run_time = timezone.now() + datetime.timedelta(seconds=get_run_time())
            engine.save()

        # bulk of the logic, we handle all types of tournaments separately here
        # there must be logic for each tournament type, as the child class contains
        # the logic
        check_games(type='process')
    except Exception as e:
        log_exception()
    finally:
        finished_time = timezone.now()
        next_run = timezone.now() + datetime.timedelta(seconds=get_run_time())
        total_run_time = (finished_time - engine.last_run_time).total_seconds()
        log("Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time, total_run_time, next_run),
            LogLevel.engine)
        engine.last_run_time = finished_time
        engine.next_run_time = next_run
        engine.save()
