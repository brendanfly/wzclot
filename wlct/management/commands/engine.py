# the main engine for the scheduler
import threading
import datetime
from wlct.logging import log, LogLevel, log_exception, Logger, TournamentLog
from bs4 import BeautifulSoup
from urllib.request import urlopen
from wlct.models import Clan, Engine
from wlct.tournaments import TournamentGame, Tournament, TournamentRound, find_tournament_by_id, TournamentGameEntry, MonthlyTemplateRotation, MonthlyTemplateRotationMonth
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
                scheduler.start()
        except ConflictingIdError:
            pass

def parse_and_update_clan_logo():
    try:
        url = 'https://www.warzone.com/Clans/List'
        clan_page = urlopen(url)

        text_soup = BeautifulSoup(clan_page, features="html.parser")

        log("Refreshing clans", LogLevel.informational)
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
                        log("Added new clan: {}".format(clan_name), LogLevel.informational)
                    elif clan_exist and clan_exist[0].image_path != image:  # updated image code path
                        clan_exist[0].image_path = image
                        clan_exist[0].save()
            except:
                continue
    except Exception:
        log_exception()

def check_games():
        tournaments = Tournament.objects.filter(has_started=True, is_finished=False)
        for tournament in tournaments:
            child_tournament = find_tournament_by_id(tournament.id, True)
            if child_tournament:
                log("Checking games for tournament: {}".format(tournament.name), LogLevel.informational)
                try:
                    if child_tournament.update_in_progress:
                        continue
                    elif not child_tournament.game_creation_allowed:
                        continue
                    child_tournament.update_in_progress = True
                    child_tournament.save()
                    games = TournamentGame.objects.filter(is_finished=False, tournament=tournament)
                    log("Processing {} games for tournament {}".format(games.count(), tournament.name), LogLevel.informational)
                    for game in games.iterator():
                        # process the game
                        # query the game status
                        child_tournament.process_game(game)
                    # in case tournaments get stalled for some reason
                    # for it to process new games based on current tournament data
                    child_tournament.process_new_games()

                    # after we process games we always cache the latest data for quick reads
                    child_tournament.cache_data()
                except Exception as e:
                    log_exception()
                finally:
                    child_tournament.update_in_progress = False
                    child_tournament.save()
            gc.collect()

def cleanup_logs():
    # get all the logs older than 2 days
    print("Cleaning up logs, thread {}".format(threading.currentThread().ident))
    nowdate = datetime.datetime.now(tz=pytz.UTC)
    enddate = nowdate - datetime.timedelta(days=2)
    logs = Logger.objects.filter(timestamp__lt=enddate)
    for log in logs.iterator():
        log.delete()
        gc.collect()

        # only get 3 minutes to run, the engine must continue
        if (datetime.datetime.now(tz=pytz.UTC) - nowdate).total_seconds() >= get_run_time():
            return

    if logs:
        print("Cleaned up {} logs.".format(logs.count()))

    tournament_logs = TournamentLog.objects.filter(timestamp__lt=enddate)
    for tournament_log in tournament_logs.iterator():
        tournament_log.delete()
        gc.collect()

        # only get 3 minutes to run, the engine must continue
        if (datetime.datetime.now(tz=pytz.UTC) - nowdate).total_seconds() >= get_run_time():
            return

    if tournament_logs:
        print("Cleaned up {} tournament logs.".format(tournament_logs.count()))


def check_leagues():
    # placeholder to check league statuses
    pass

def check_bot_data():
    # placeholder to update the bot data cache
    pass

def validate_game_entries():
    # loop through all game entries not finished....query the games and see if they are...
    # these should have been finished in finish_game...but for some reason are not
    tournaments = MonthlyTemplateRotation.objects.all()
    for tournament in tournaments:
        print("Looking at MTC: {}".format(tournament.name))
        current_month = tournament.get_current_month()
        # grab all the games and game entries in that month
        games = TournamentGame.objects.filter(tournament=tournament)
        for game in games:
            print("Getting game entries for game {} between {}/{} which is finished: {}".format(game.id, game.teams.split('.')[0], game.teams.split('.')[1], game.is_finished))
            # get the game entries associated with this game
            entries = TournamentGameEntry.objects.filter(game=game, tournament=tournament)
            for entry in entries:
                print("Found Game Entry: Game: {}, Entry: {}".format(game, entry))
                if not entry.is_finished and game.is_finished:
                    print("Updating game entry")
                    entry.is_finished = True
                    entry.save()


# globals to get executed on every load of the web server
slow_update_threshold = 25
current_clan_update = 1

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
        if engine.count() == 0:
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
        #validate_game_entries()
        check_games()
        cleanup_logs()
        check_bot_data()
    except Exception as e:
        log_exception()
    finally:
        print("Engine done running....waiting until next run")
        engine.last_run_time = timezone.now()
        engine.next_run_time = timezone.now() + datetime.timedelta(seconds=get_run_time())
        engine.save()
        pass