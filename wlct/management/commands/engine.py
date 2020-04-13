# the main engine for the scheduler
import threading
import datetime
from wlct.logging import log, LogLevel, log_exception, Logger, TournamentLog, TournamentGameLog, TournamentGameStatusLog, ProcessGameLog, ProcessNewGamesLog, BotLog, LogManager
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
                scheduler.add_job(process_team_vacations, 'interval', seconds=(get_run_time()*20), id='process_team_vacations',
                                  max_instances=1, coalesce=False)
                scheduler.add_job(parse_and_update_clan_logo, 'interval', seconds=(get_run_time()*25), id='parse_and_update_clan_logo',
                                  max_instances=1, coalesce=False)
                scheduler.start()
        except ConflictingIdError:
            pass
        

def process_team_vacations():
    try:
        start_time = datetime.datetime.utcnow()
        log("Starting process team vacation: {}".format(start_time), LogLevel.engine)
        tournaments = Tournament.objects.filter(is_finished=False, has_started=True)
        for t in tournaments:
            t = find_tournament_by_id(t.id, True)
            teams = TournamentTeam.objects.filter(tournament=t)
            for team in teams:
                team.on_vacation = t.is_team_on_vacation(team)
                team.save()
        end_time = datetime.datetime.utcnow()
        log("End process team vacations. Total Time: {}".format((end_time-start_time).total_seconds()), LogLevel.engine)
    except Exception:
        log_exception()


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


def cache_games(**kwargs):
    tournaments = Tournament.objects.filter(**kwargs)
    for tournament in tournaments:
        child_tournament = find_tournament_by_id(tournament.id, True)
        if child_tournament and child_tournament.should_process_in_engine():
            log("[CACHE]: Checking games for tournament: {}".format(tournament.name), LogLevel.engine)
            try:
                child_tournament.cache_data()
                log("[CACHE]: Finished processing games for tournament {}".format(tournament.name), LogLevel.engine)
            except Exception as e:
                log_exception()
            finally:
                log("[CACHE]: Child tournament {} update done.".format(tournament.name), LogLevel.engine)
        gc.collect()

def check_games(**kwargs):
    log("Running check_games on thread {}".format(threading.get_ident()), LogLevel.engine)
    tournaments = Tournament.objects.filter(has_started=True, is_finished=False)
    for tournament in tournaments:
        child_tournament = find_tournament_by_id(tournament.id, True)
        if child_tournament and child_tournament.should_process_in_engine():
            log("[PROCESS GAMES]: Checking games for tournament: {}".format(tournament.name), LogLevel.engine)
            try:
                games = TournamentGame.objects.filter(is_finished=False, tournament=tournament)
                log("[PROCESS GAMES]: Processing {} games for tournament {}".format(games.count(), tournament.name), LogLevel.engine)
                for game in games.iterator():
                    # process the game
                    # query the game status
                    child_tournament.process_game(game)
                # in case tournaments get stalled for some reason
                # for it to process new games based on current tournament data
                log("[PROCESS GAMES]: Processing new games for tournament {}".format(tournament.name), LogLevel.engine)
                child_tournament.process_new_games()

                # after we process games we always cache the latest data for quick reads
                log("[PROCESS GAMES]: Finished processing games for tournament {}".format(tournament.name), LogLevel.engine)
            except Exception as e:
                log_exception()
            finally:
                child_tournament.update_in_progress = False
                child_tournament.save()
                log("[PROCESS GAMES]: Child tournament {} update done.".format(tournament.name), LogLevel.engine)
        gc.collect()

def cleanup_logs():
    # get all the logs older than 2 days
    nowdate = datetime.datetime.utcnow()
    enddate = nowdate - datetime.timedelta(days=3)

    for log_type, value in vars(LogLevel).items():
        if not log_type.startswith('__'):
            if value == LogLevel.process_game or value == LogLevel.game or value == LogLevel.game_status:
                games = TournamentGame.objects.filter(is_finished=True)
                LogManager(value, game__is_finished=True).prune_keep_last(games, hours=12)
                LogManager(value, timestamp__lt=enddate, game__is_finished=False).prune()
            elif value == LogLevel.tournament or value == LogLevel.process_new_games:
                tournaments = Tournament.objects.filter(is_finished=True)
                LogManager(value, tournament__is_finished=True).prune_keep_last(tournaments, hours=12)
                LogManager(value, timestamp__lt=enddate, tournament__is_finished=False).prune()
            else:  # generic logging runtime cases
                LogManager(value, timestamp__lt=enddate, level=value).prune()
        gc.collect()

def tournament_caching():
    try:
        cleanup_logs()
        if settings.DEBUG:
            cache_games(has_started=True)
        else:
            cache_games(has_started=True, is_finished=False)
    except Exception as e:
        log_exception()

def tournament_engine():
    try:
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

        print("Process Games Starting...")
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
        print("Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time,
                                                                                              total_run_time, next_run))
        engine.last_run_time = finished_time
        engine.next_run_time = next_run
        engine.save()
