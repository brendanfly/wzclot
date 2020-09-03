# the main engine for the scheduler
import threading
import datetime
from wlct.logging import log, LogLevel, log_exception, Logger, TournamentLog, TournamentGameLog, TournamentGameStatusLog, ProcessGameLog, ProcessNewGamesLog, BotLog, LogManager
from bs4 import BeautifulSoup
from urllib.request import urlopen
from wlct.models import Clan, Engine, Player
from wlct.tournaments import ClanLeague, ClanLeagueTournament, find_tournament_by_id, Tournament, TournamentGame, TournamentPlayer, TournamentTeam, TournamentGameEntry, TournamentRound, get_multi_day_ladder
from django.conf import settings
import pytz
import threading
from apscheduler.schedulers.background import BlockingScheduler
from apscheduler.jobstores.base import ConflictingIdError
from django_apscheduler.jobstores import DjangoJobStore
from django.core.management.base import BaseCommand
import gc
from django.utils import timezone
import urllib.request
import sys, threading, json, time, traceback

def get_run_time():
    return 180


class Command(BaseCommand):
    help = "Runs the engine for cleaning up logs and creating new tournament games every 180 seconds"
    def handle(self, *args, **options):
        # set up git/restart handling
        self.last_known_commit = ""
        self.shutdown = False

        print("Creating communication thread...")
        self.comm_thread = threading.Thread(target=self.handle_git)
        self.comm_thread.start()

        self.flush_thread = threading.Thread(target=self.flush)
        self.flush_thread.start()

        self.schedule_jobs()
        self.scheduler = None

    def flush(self):
        while True and not self.shutdown:
            sys.stdout.flush()
            sys.stderr.flush()
            time.sleep(5)

    def handle_git(self):
        while not self.shutdown:
            try:
                # grab the latest commit the database knows about
                logger = Logger.objects.filter(level=LogLevel.webhook)[:1]  # only care about the last one
                if logger:
                    logger = logger[0]
                    if logger.msg is not None and len(logger.msg) > 0:
                        webhook_dict = json.loads('''{}'''.format(logger.msg))
                        if 'ref' in webhook_dict and 'before' in webhook_dict and 'after' in webhook_dict:
                            if webhook_dict['ref'] == 'refs/heads/master':
                                if webhook_dict['after'] != self.last_known_commit and self.last_known_commit is not "":
                                    print("Found commit to the master branch...processing")
                                    print("Commit is new, shutting down engine")
                                    self.shutdown = True
                                self.last_known_commit = webhook_dict['after']
                                print("Last known good commit: {}".format(self.last_known_commit))
            except:
                print(traceback.format_exc())
            finally:
                # sleep for 30 seconds before checking again
                print("Sleeping for 10 seconds. Last known commit: {}".format(self.last_known_commit))
                time.sleep(10)
                sys.stdout.flush()

            if self.shutdown is True:
                print('Waiting for all jobs to finish and shutting process down...')
                if self.scheduler is not None and self.scheduler.running:
                    print("Scheduler is running...shutting down")
                    print("Removing all jobs")
                    self.scheduler.remove_all_jobs()
                    print("Waiting for outstanding work to finish")
                    self.scheduler.shutdown(wait=True)
                    sys.exit(0)

    def schedule_jobs(self):
        # lookup the main scheduler, if it's not currently scheduled, add it every 3 min
        try:
            print("Scheduling jobs")
            scheduler = BlockingScheduler()
            # If you want all scheduled jobs to use this store by default,
            # use the name 'default' instead of 'djangojobstore'.
            scheduler.add_jobstore(DjangoJobStore(), 'default')
            if not scheduler.running:
                scheduler.add_job(tournament_engine, 'interval', seconds=get_run_time()*10, id='tournament_engine',
                                  max_instances=1, coalesce=True, replace_existing=True)
                scheduler.add_job(tournament_engine_real_time, 'interval', seconds=get_run_time()/3, id='tournament_engine_real_time',
                                  max_instances=1, coalesce=True, replace_existing=True)
                scheduler.add_job(tournament_caching, 'interval', seconds=(get_run_time()*12), id='tournament_caching',
                                  max_instances=1, coalesce=True, replace_existing=True)
                scheduler.add_job(tournament_caching_real_time, 'interval', seconds=get_run_time(), id='tournament_caching_real_time',
                                  max_instances=1, coalesce=True, replace_existing=True)
                scheduler.add_job(process_team_vacations, 'interval', seconds=(get_run_time()*20), id='process_team_vacations',
                                  max_instances=1, coalesce=True, replace_existing=True)
                scheduler.add_job(parse_and_update_clan_logo, 'interval', seconds=(get_run_time()*25), id='parse_and_update_clan_logo',
                                  max_instances=1, coalesce=True, replace_existing=True)
                scheduler.add_job(process_mdl_games, 'interval', seconds=(get_run_time()*20), id='process_mdl_games',
                                  max_instances=1, coalesce=True, replace_existing=True)
                self.scheduler = scheduler
                scheduler.start()
        except ConflictingIdError:
            pass

def process_mdl_games():

    log("Starting process MDL Games {}".format(datetime.datetime.utcnow()), LogLevel.engine)
    mdl_url = "http://md-ladder.cloudapp.net/api/v1.0/games?topk=10"

    try:
        content = urllib.request.urlopen(mdl_url).read()
    except Exception as e:
        return

    ladder = get_multi_day_ladder(168)
    round = TournamentRound.objects.filter(tournament=ladder, round_number=1)
    if not round:
        round = TournamentRound(tournament=ladder, round_number=1)
        round.save()
    else:
        round = round[0]

    data = json.loads(content)
    for index, game_data in enumerate(data['games']):
        gc.collect()
        # first check to see if the game has already been processed
        game = TournamentGame.objects.filter(tournament=ladder, gameid=game_data['game_id'])
        if not game:
            game_id = game_data['game_id']
            # need to find the two players here and create the corresponding game entry
            players = game_data['players']
            tplayers = []
            for player in players:
                # do we know about this player?
                token = player['player_id']
                name = player['player_name']

                player = Player.objects.filter(token=token)
                if not player:
                    clan = None
                    if 'clan' in player:
                        clan_name = player['clan']
                        # first, lookup the clan object
                        clan = Clan.objects.filter(name=clan_name)
                        if clan:
                            clan = clan[0]

                    player = Player(name=name, token=token, clan=clan)
                    player.save()
                else:
                    player = player[0]

                # we have the player, next check for the tournament player
                tplayer = TournamentPlayer.objects.filter(player=player, tournament=ladder)
                if tplayer:
                    tplayer = tplayer[0]
                    tplayers.append(tplayer)
                else:
                    # create the new team first
                    team = TournamentTeam(tournament=ladder)
                    team.save()
                    tplayer = TournamentPlayer(player=player, team=team, tournament=ladder)
                    tplayer.save()
                    tplayers.append(tplayer)

            if len(tplayers) == 2:
                # we have the tournament player objects which have the team objects and player objects
                # create both game entries + game objects so that the bot can log them
                teams = "{}.{}".format(tplayers[0].team.id, tplayers[1].team.id)
                finished = datetime.datetime.strptime(game_data['finish_date'], '%Y-%m-%d %H:%M:%S.%f').replace(
                    tzinfo=pytz.UTC)
                created = datetime.datetime.strptime(game_data['created_date'], '%Y-%m-%d %H:%M:%S.%f').replace(
                    tzinfo=pytz.UTC)
                game_link = 'https://www.warzone.com/MultiPlayer?GameID={}'.format(game_id)
                game = TournamentGame(game_link=game_link, gameid=game_id,
                                      players_per_team=1,
                                      team_game=False, tournament=ladder, is_finished=True,
                                      teams=teams, round=round, game_finished_time=finished, game_start_time=created)
                game.save()
                entry = TournamentGameEntry(team=tplayers[0].team, team_opp=tplayers[1].team, game=game,
                                            tournament=ladder)
                entry.save()
                entry = TournamentGameEntry(team=tplayers[1].team, team_opp=tplayers[0].team, game=game,
                                            tournament=ladder)
                entry.save()
                winning_token = game_data['winner_id']
                if str(winning_token) == str(tplayers[0].player.token):
                    game.winning_team = tplayers[0].team
                else:
                    game.winning_team = tplayers[1].team
                game.save()

def process_single_time_player_ratings():
    try:
        games = TournamentGame.objects.filter(is_finished=True).order_by('id')
        for g in games:
            g.handle_tournament_player_updates()
    except:
        log_exception()

def process_team_vacations():
    try:
        start_time = datetime.datetime.utcnow()
        log("Starting process team vacation: {}".format(start_time), LogLevel.engine)
        tournaments = Tournament.objects.filter(is_finished=False, has_started=True)
        for t in tournaments:
            gc.collect()
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
                if '/Clans' and '/Icon' in clan_href:
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
        if child_tournament:
            log("[CACHE]: Checking games for tournament: {}".format(tournament.name), LogLevel.engine)
            try:
                # we only need to cache if there are unfinished games
                games = TournamentGame.objects.filter(tournament=child_tournament, is_finished=False)
                child_tournament.cache_data()
                log("[CACHE]: Finished processing games for tournament {}".format(tournament.name), LogLevel.engine)
            except Exception as e:
                log_exception()
            finally:
                log("[CACHE]: Child tournament {} update done.".format(tournament.name), LogLevel.engine)
        gc.collect()

def check_games(**kwargs):
    log("Running check_games on thread {}".format(threading.get_ident()), LogLevel.engine)
    tournaments = Tournament.objects.filter(**kwargs)
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
    enddate = nowdate - datetime.timedelta(days=2)

    for log_type, value in vars(LogLevel).items():
        if not log_type.startswith('__'):
            if value == LogLevel.process_game or value == LogLevel.game or value == LogLevel.game_status:
                games = TournamentGame.objects.filter(is_finished=True)
                LogManager(value, game__is_finished=True).prune_keep_last(games, hours=1)
                LogManager(value, timestamp__lt=enddate, game__is_finished=False).prune()
            elif value == LogLevel.tournament or value == LogLevel.process_new_games:
                tournaments = Tournament.objects.filter(is_finished=True)
                LogManager(value, tournament__is_finished=True).prune_keep_last(tournaments, hours=1)
                LogManager(value, timestamp__lt=enddate, tournament__is_finished=False).prune()
            else:  # generic logging runtime cases
                LogManager(value, timestamp__lt=enddate, level=value).prune()
        gc.collect()

def tournament_caching_real_time():
    try:
        cache_games(has_started=True, multi_day=False)
    except:
        log_exception()

def tournament_caching():
    try:
        cleanup_logs()
        if settings.DEBUG:
            cache_games(has_started=True)
        else:
            cache_games(has_started=True, multi_day=True)
    except Exception as e:
        log_exception()

def tournament_engine_real_time():
    try:
        now_run_time = timezone.now()
        check_games(has_started=True, multi_day=False)
    except:
        log_exception()
    finally:
        finished_time = timezone.now()
        next_run = timezone.now() + datetime.timedelta(seconds=get_run_time()/3)
        total_run_time = (finished_time - now_run_time).total_seconds()
        log("RT Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time,
                                                                                              total_run_time, next_run),
            LogLevel.engine)
        print("RT Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time, total_run_time, next_run))

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
        check_games(has_started=True, multi_day=True)
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
