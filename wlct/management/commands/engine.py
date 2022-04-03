# the main engine for the scheduler
import threading
import datetime
from wlct.logging import log, LogLevel, log_exception, Logger, TournamentLog, TournamentGameLog, TournamentGameStatusLog, ProcessGameLog, ProcessNewGamesLog, BotLog, LogManager
from bs4 import BeautifulSoup
from urllib.request import urlopen
from wlct.models import Clan, Engine, Player, update_player_clans
from wlct.tournaments import ClanLeague, ClanLeagueTournament, find_tournament_by_id, Tournament, TournamentGame, TournamentPlayer, TournamentTeam, TournamentGameEntry, TournamentRound, get_multi_day_ladder
from django.conf import settings
import pytz
import threading
from apscheduler.schedulers.background import BlockingScheduler, BackgroundScheduler
from apscheduler.jobstores.base import ConflictingIdError
from django_apscheduler.jobstores import DjangoJobStore
from django.core.management.base import BaseCommand
import gc
from django.utils import timezone
import urllib.request
import os
import sys, threading, json, time, traceback

def get_run_time():
    return 180


class Command(BaseCommand):
    help = "Runs the engine for cleaning up logs and creating new tournament games every 180 seconds"
    def handle(self, *args, **options):
        # set up git/restart handling
        self.shutdown = False

        self.handle_shutdown_thread = threading.Thread(target=self.handle_shutdown)
        self.handle_shutdown_thread.start()

        self.shutdown_event = threading.Event()

        self.tournament_engine_thread = threading.Thread(target=self.tournament_engine)
        self.tournament_engine_thread.start()

        self.tournament_engine_real_time_thread = threading.Thread(target=self.tournament_engine_real_time)
        self.tournament_engine_real_time_thread.start()

        self.worker_thread = threading.Thread(target=self.worker_routine)
        self.worker_thread.start()

        self.update_player_thread = threading.Thread(target=self.update_player_profiles_routine)
        self.update_player_thread.start()

    def handle_shutdown(self):
        path = os.getcwd()
        path += "\\shutdown_file.txt"
        f = None
        print("Shutdown file location: {}".format(path))
        while not self.shutdown:
            # check for shutdown file to be written...
            try:
                f = open(path)
                print("Found shutdown file...")
                self.shutdown = True
                self.shutdown_event.set()
                break
            except IOError:
                pass
            finally:
                if f:
                    f.close()
                time.sleep(10)

        if self.shutdown is True:
            print('Waiting for all jobs to finish and shutting process down...')

            print("Shutdown Event: {}".format(self.shutdown_event.is_set()))
            # wait for all worker threads to complete

            self.update_player_thread.join()
            print("Player update thread completed")
            self.worker_thread.join()
            print("Worker thread completed")
            self.tournament_engine_real_time_thread.join()
            print("Tournament real time engine thread completed")
            self.tournament_engine_thread.join()
            print("Tournament engine thread completed")
            sys.exit(0)

    def update_player_profiles_routine(self):
        while not self.shutdown:
            try:
                # Updates every player's name and clan
                self.update_all_player_clans()
            except:
                log_exception()
            print("[WAIT - PLAYER PROFILE UPDATE]")
            # Run once a day
            self.shutdown_event.wait(timeout=get_run_time()*480)

    def worker_routine(self):
        while not self.shutdown:
            try:
                self.process_mdl_games()
                self.parse_and_update_clan_logo()
                #self.process_team_vacations() # for now do not process any team vacations...that takes too long
            except Exception:
                log_exception()

            print("[WAIT - WORKER]")
            self.shutdown_event.wait(timeout=get_run_time()*20)

    def process_mdl_games(self):
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
            print("Found {} MDL games to process".format(len(data['games'])))
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

    def process_team_vacations(self):
        try:
            start_time = datetime.datetime.utcnow()
            log("Starting process team vacation: {}".format(start_time), LogLevel.engine)
            tournaments = Tournament.objects.filter(is_finished=False, has_started=True)
            for t in tournaments:
                if self.shutdown:
                    return
                gc.collect()
                t = find_tournament_by_id(t.id, True)
                teams = TournamentTeam.objects.filter(tournament=t)
                for team in teams:
                    if self.shutdown:
                        return
                    team.on_vacation = t.is_team_on_vacation(team)
                    team.save()
            end_time = datetime.datetime.utcnow()
            log("End process team vacations. Total Time: {}".format((end_time-start_time).total_seconds()), LogLevel.engine)
        except Exception:
            log_exception()

    def parse_and_update_clan_logo(self):
        url = 'https://www.warzone.com/Clans/List'
        clan_page = urlopen(url)

        text_soup = BeautifulSoup(clan_page, features="html.parser")

        log("Refreshing clans", LogLevel.engine)
        links = text_soup.findAll("a")
        for link in links:
            if self.shutdown:
                return
            try:
                clan_href = link.attrs["href"]
                if '/Clans' in clan_href and link.contents[2].strip():
                    clan_name = link.contents[2].strip()

                    # Not all clans have an img
                    image = link.findAll("img")[0].attrs["src"] if len(link.findAll("img")) else ""
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

    def update_all_player_clans(self):
        if self.shutdown:
            return

        log("Updating player clans for all players", LogLevel.engine)
        players = Player.objects.all()
        update_player_clans(players, self)

    def is_correct_player(self, player_token, player_team):
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

    def cache_games(self, **kwargs):
        tournaments = Tournament.objects.filter(**kwargs)
        for tournament in tournaments:
            games_in_progress = 0
            if self.shutdown:
                return
            child_tournament = find_tournament_by_id(tournament.id, True)
            if child_tournament:
                log("[CACHE]: Checking games for tournament: {}, shutdown: {}".format(tournament.name, self.shutdown), LogLevel.engine)
                try:
                    # we only need to cache if there are unfinished games
                    games = TournamentGame.objects.filter(tournament=child_tournament, is_finished=False)
                    games_in_progress = games.count()
                    child_tournament.cache_data()
                except Exception as e:
                    log_exception()
                finally:
                    log("[CACHE]: Child tournament {} update done.".format(tournament.name), LogLevel.engine)

                # if the tournament is finished and there are no more outstanding games that are in progress
                # the cache is no longer dirty and we should stop looking at it
                log("[CACHE]: {} has {} games in progress, is_finished: {}".format(child_tournament.name, games_in_progress, child_tournament.is_finished), LogLevel.engine)
                if child_tournament.is_finished and games_in_progress == 0:
                    log("[CACHE]: Child tournament {} cache is no longer dirty.".format(tournament.name), LogLevel.engine)
                    child_tournament.is_cache_dirty = False
                    child_tournament.save()
                elif games_in_progress > 0:
                    child_tournament.is_cache_dirty = True
                    child_tournament.save()
                    # cache is not dirty...let's get this on the next time around


            gc.collect()

    def check_games(self, **kwargs):
        log("Running check_games on thread {}".format(threading.get_ident()), LogLevel.engine)
        tournaments = Tournament.objects.filter(**kwargs)
        for tournament in tournaments:
            games_in_progress = 0
            if self.shutdown:
                return

            # if we get this far, we actually need to check the tournament
            child_tournament = find_tournament_by_id(tournament.id, True)
            if child_tournament and child_tournament.should_process_in_engine():
                try:
                    games = TournamentGame.objects.filter(is_finished=False, tournament=tournament)
                    games_in_progress = games.count()
                    log("[PROCESS GAMES]: Processing {} games for tournament {}".format(games.count(), tournament.name), LogLevel.engine)
                    for game in games.iterator():
                        # process the game
                        # query the game status
                        child_tournament.process_game(game)
                    # in case tournaments get stalled for some reason
                    # for it to process new games based on current tournament data
                    child_tournament.process_new_games()

                    if hasattr(child_tournament, 'clan_league_template') and not child_tournament.multi_day:
                        child_tournament.multi_day = True
                        child_tournament.save()
                except Exception as e:
                    log_exception()
                finally:
                    child_tournament.update_in_progress = False
                    child_tournament.save()

                # if we are finished, and there are no outstanding games in progress...we are deemed "all_games_completed"
                if child_tournament.is_finished and games_in_progress == 0:
                    log("[PROCESS GAMES]: Child tournament {} has all games completed.".format(tournament.name), LogLevel.engine)
                    child_tournament.all_games_completed = True
                    child_tournament.save()

            gc.collect()

    def cleanup_logs(self):
        # get all the logs older than 2 days
        nowdate = datetime.datetime.utcnow()
        enddate = nowdate - datetime.timedelta(days=2)

        for log_type, value in vars(LogLevel).items():
            if self.shutdown:
                return
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

    def tournament_engine_real_time(self):
        while not self.shutdown:
            print("[WAIT - TOURNAMENT ENGINE REAL-TIME]")
            self.shutdown_event.wait(timeout=get_run_time()/3)
            try:
                now_run_time = timezone.now()
                self.check_games(has_started=True, multi_day=False, all_games_completed=False)
                self.cache_games(has_started=True, multi_day=False, is_cache_dirty=True)
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

    def tournament_engine(self):
        while not self.shutdown:
            print("[WAIT - TOURNAMENT ENGINE]")
            self.shutdown_event.wait(timeout=get_run_time()*10)
            try:
                engine = Engine.objects.all()
                if not engine or engine.count() == 0:
                    # create the engine object!
                    engine = Engine()
                    engine.save()
                else:
                    engine = engine[0]
                    engine.last_run_time = timezone.now()
                    engine.next_run_time = timezone.now() + datetime.timedelta(seconds=get_run_time()*10)
                    engine.save()

                print("Process Games Starting...")

                # bulk of the logic, we handle all types of tournaments separately here
                # there must be logic for each tournament type, as the child class contains
                # the logic
                self.check_games(has_started=True, multi_day=True, all_games_completed=False)
                self.cache_games(has_started=True, multi_day=True, is_cache_dirty=True)
                self.cleanup_logs()
            except Exception as e:
                log_exception()
            finally:
                finished_time = timezone.now()
                next_run = timezone.now() + datetime.timedelta(seconds=get_run_time()*10)
                total_run_time = (finished_time - engine.last_run_time).total_seconds()
                log("Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time, total_run_time, next_run),
                    LogLevel.engine)
                print("Engine done running at {}, ran for a total of {} seconds. Next run at {}".format(finished_time,
                                                                                                      total_run_time, next_run))
                engine.last_run_time = finished_time
                engine.next_run_time = next_run
                engine.save()

            # sleep for the next iteration