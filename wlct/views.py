from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from wlct.form_message_handling import FormError
from wlct.api import API, get_account_token
from wlct.models import Player, Clan
from wlct.tournaments import SwissTournament, GroupStageTournament, SeededTournament, TournamentInvite, TournamentPlayer, find_tournament_by_id, Tournament, find_league_by_id, is_player_allowed_join, TournamentGameEntry, get_matchup_data
from wlct.forms import SwissTournamentForm, SeededTournamentForm, GroupTournamentForm, MonthlyTemplateCircuitForm, PromotionRelegationLeagueForm, ClanLeagueForm
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.exceptions import ObjectDoesNotExist
from wlct.logging import log, LogLevel, log_exception
import traceback
from django.conf import settings
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import ConflictingIdError
from django_apscheduler.jobstores import DjangoJobStore
from wlct.management.commands.engine import tournament_engine, tournament_caching
import string
import random

def schedule_jobs():
    # lookup the main scheduler, if it's not currently scheduled, add it every 5 min
    if settings.DEBUG:
        try:
            scheduler = BackgroundScheduler()
            # If you want all scheduled jobs to use this store by default,
            # use the name 'default' instead of 'djangojobstore'.
            scheduler.add_jobstore(DjangoJobStore(), 'default')
            if not scheduler.running:
                scheduler.add_job(tournament_caching, 'interval', seconds=10, id='tournament_engine',
                                  max_instances=1, coalesce=False)
                scheduler.start()
        except ConflictingIdError:
            pass

schedule_jobs()

# ajax post method that issues a start request to display host configurable data
def tournament_start_request(request):
    context = {'success': 'false'}
    if request.method == "POST" and is_player_token_valid(request):
        try:
            player = Player.objects.get(token=request.session['token'])

            tournamentid = request.POST['tournamentid']
            tournament = find_tournament_by_id(tournamentid, True)
            if tournament and (tournament.created_by.token == player.token):
                if settings.DEBUG:
                    tournament.fill_teams()

                if tournament.can_start_tourney:
                    if not tournament.start_locked:
                        print("Start locking tournament {} ".format(tournament.id))
                        tournament.start_locked = True
                        tournament.save()

                    tournament_start_data = tournament.get_start_locked_data()
                    context.update({'tournament_start_data': tournament_start_data})
                    context.update({'success': 'true'})
                else:
                    context.update({'error': 'You need the minimum number of teams ({}) in order to start the tournament, with 0 partially filled teams.'.format(tournament.min_teams)})
            else:
                return HttpResponseRedirect('/index/')

        except ObjectDoesNotExist:
            return HttpResponseRedirect('/index/')
        except Exception as e:
            log_exception()
            context.update({"error": str(e)})

        return JsonResponse(context)

    return HttpResponseRedirect('/index/')


# ajax post method that cancels the current start request
def tournament_cancel_request(request):
    context = {"success": "false"}
    if request.method == "POST" and is_player_token_valid(request):
        try:
            player = Player.objects.get(token=request.session['token'])

            tournamentid = request.POST['tournamentid']
            tournament = find_tournament_by_id(tournamentid, True)
            if tournament and (tournament.created_by.token == player.token):
                if tournament.start_locked:
                    # cancel the request
                    tournament.start_locked = False
                    print("Canceled tournament {}".format(tournament.id))
                    tournament.save()

                context.update({'success': 'true'})
            else:
                return HttpResponseRedirect('/index/')

        except ObjectDoesNotExist:
            return HttpResponseRedirect('/index/')
        except Exception as e:
            log_exception()
            context.update({"error": str(e)})

        return JsonResponse(context)

    return HttpResponseRedirect('/index/')


# ajax post method that starts the tournament
def tournament_start(request):
    # start the tournament by creating all the necessary rounds
    context = {"success" : "false"}
    if request.method == "POST" and is_player_token_valid(request):
        tournamentid = request.POST['tournamentid']

             # tournament data is unique based on the type of tournament
            # the tournament itself knows how to process the data
            # the data will be the entire html inside the modal when the host starts
            # the tournament, so each tournament will need to parse this data accordingly
        tournament_data = request.POST['tournament_data']

        try:
            player = Player.objects.get(token=request.session['token'])

            tournament = find_tournament_by_id(tournamentid, True)
            if tournament is not None and request.session['token'] == tournament.created_by.token:
                tournament.start(tournament_data)
                context.update({"success": "true"})
                if tournament.is_league:
                    context.update({'redirect_url': '/leagues/{}/'.format(tournamentid)})
                elif hasattr(tournament, 'pr_tournament'):
                    context.update({'redirect_url': '/pr/season/{}/'.format(tournamentid)})
                else:
                    context.update({'redirect_url': '/tournaments/{}/'.format(tournamentid)})

                return JsonResponse(context)
            else:
                log("Player {} is trying to start tournament {} but they didn't create it!".format(player.token,
                                                                                                   tournamentid),
                    LogLevel.warning)
                context.update({"error": "You cannot start a tournament you didn't create!"})
                return HttpResponseRedirect('/index/')
        except ObjectDoesNotExist:
            return HttpResponseRedirect('/index/')
        except Exception as e:
            log_exception()
            return HttpResponseRedirect('/index/')

    return HttpResponseRedirect('/index/')

# ajax post method that deletes the tournament
def tournament_delete(request):
    # must validate that we're the owner of the tournament
    # then simply look-up and delete
    context = {"success": "false"}
    if request.method == 'POST' and is_player_token_valid(request):
        tournamentid = request.POST['tournamentid']

        try:
            player = Player.objects.get(token=request.session['token'])

            tournament = find_tournament_by_id(tournamentid, True)
            if tournament is not None and request.session['token'] == tournament.created_by.token:
                tournament.delete()
                context.update({"success": "true"})
            else:
                log("Player {} is trying to delete tournament {} but they didn't create it!".format(player.token, tournamentid), LogLevel.warning)
                context.update({"error": "You cannot delete a tournament you didn't create!"})

        except ObjectDoesNotExist:
            # not found, go to homepage
            log("refresh_tournament: cannot find player based on token {}".format(
                request.session['token']), LogLevel.warning)
            return HttpResponseRedirect('/index/')

    return JsonResponse(context)

# method that returns the json for the refresh tournament
def refresh_tournament(request):
    context = {}
    if request.method == 'POST':
        tournamentid = request.POST['tournamentid']

        tournament = find_tournament_by_id(tournamentid, True)
        if tournament is not None:
            player = None
            if is_player_token_valid(request):
                try:
                    player = Player.objects.get(token=request.session['token'])

                    player_tourney = TournamentPlayer.objects.filter(player=player, tournament=tournament)
                    if player_tourney:
                        context.update({'player_in_tourney': True})

                except ObjectDoesNotExist:
                    # not found, go to homepage
                    log("refresh_tournament: cannot find player based on token {}".format(
                        request.session['token']), LogLevel.warning)
                    return HttpResponseRedirect('/index/')

            allowed_join = is_player_allowed_join(player, tournament.template)
            context.update({'team_table': tournament.get_team_table(allowed_join, is_player_token_valid(request), player)})
            context.update({'can_start_tourney': tournament.can_start_tourney})
            context.update({'bracket_game_data': tournament.get_bracket_game_data()})
            context.update({'game_log': tournament.get_game_log()})
            # now grab the entire tournament log and invited players list and send that back over as well
            # this should already be properly formatted html, so just pass the strings back
            context.update({'success': 'true'})
            ret = JsonResponse(context)
            return ret

def is_player_token_valid(request):
    # we kind of hack this here to make sure our single job is running to schedule games
    # since all views call this we will have at least one job running on our app
    request.session['account_token'] = get_account_token()  # always set the account token
    if "token" not in request.session:
        return False
    elif not request.session["token"].isnumeric():
        return False
    else:
        return True

def league_update_status(request):
    try:
        context = {}
        context.update({'success': 'false'})
        if request.method == 'POST' and is_player_token_valid(request):
            leagueid = request.POST['leagueid']
            league = find_league_by_id(leagueid)
            if league is not None:
                if 'pause' in request.POST:
                    league.update_game_creation_allowed(False)
                    print("Games cannot be created")
                elif 'resume' in request.POST:
                    league.update_game_creation_allowed(True)
                    print("Games can be created")

                player = Player.objects.get(token=request.session['token'])
                context.update({'success': 'true'})
                context.update({'pause_resume_buttons': league.get_pause_resume(player)})

                return JsonResponse(context)
    except:
        log_exception()

def league_submit_editing_window(request):
    try:
        context = {}
        context.update({"success": "false"})
        if request.method == 'POST' and is_player_token_valid(request):
            leagueid = request.POST['leagueid']
            league = find_league_by_id(leagueid)
            if league is not None:
                if 'league_editing_data' in request.POST:
                    update_ret = league.update_league_editing(request.POST['league_editing_data'])
                    if 'editing_window_status_text' in update_ret:
                        editing_window_status_text = update_ret['editing_window_status_text']

                    print("Submit window with ret: {}".format(update_ret))
                    context.update({'success': "true"})
                    context.update({'editing_window_status_text': editing_window_status_text})
                    context.update({'league_editor': league.get_league_editor()})
                else:
                    context.update({'editing_window_status_text': 'There was no data sent to the server!'})
            else:
                context.update({'editing_window_status_text': 'Unable to find the league!'})
        ret = JsonResponse(context)
        return ret
    except:
        log_exception()

def league_editor_view(request):
    try:
        context = {}
        context.update({"success": "false"})
        if request.method == 'POST' and is_player_token_valid(request):
            leagueid = request.POST['leagueid']
            league = find_league_by_id(leagueid)
            if league is not None:
                # get the editing content
                context.update({'league_editor': league.get_league_editor()})
                context.update({'success': 'true'})
                ret = JsonResponse(context)
                return ret
    except:
        log_exception()

@ensure_csrf_cookie
def league_display_view(request, id):
    try:
        league = find_league_by_id(id)
        context = {}
        player = None
        allowed_join = False
        if league is not None:
            # look-up if the current player is in the tournament
            context.update({'player_in_tourney': False})
            if is_player_token_valid(request):
                try:
                    player = Player.objects.get(token=request.session['token'])
                    player_tourney = TournamentPlayer.objects.filter(player=player, tournament=league)
                    if player_tourney:
                        context.update({'player_in_tourney': True})
                        context.update({'tourney_player': player_tourney[0]})
                except ObjectDoesNotExist:
                    # not found, go to homepage
                    log("tournament_display_view: cannot find player based on token {}".format(
                        request.session['token']), LogLevel.warning)
                    return HttpResponseRedirect('/index/')

                # get the api to check to see if we can display join buttons
                apirequestJson = {}
                if hasattr(league, 'current_template'):
                    allowed_join = is_player_allowed_join(player, league.current_template)
                else:
                    allowed_join = is_player_allowed_join(player, league.template)

            # clan-league is a special case, as it contains many sub-leagues underneath it
            # with the right requirements...if the league type is of clan league
            # we want to display this separately on a different page.
            if league.type == "Clan League":
                context.update({'pause_resume_buttons': league.get_pause_resume(player)})
                context.update({'tournament': league})
                return render(request, 'clan_league.html', context)
            elif league.type == "Promotion/Relegation League":
                context.update({'pause_resume_buttons' : league.get_pause_resume(player)})
                context.update({'tournament': league})
                return render(request, 'pr.html', context)
            if allowed_join and league.private:
                # if the template works and this tournament is private we are only
                # allowed to join if we've been invited by the host
                invites = TournamentInvite.objects.filter(tournament=league, player=player, joined=False)
                if not invites and player.id != league.created_by.id:
                    print("Player {} is not allowed to join.".format(player.name))
                    allowed_join = False

            context.update(
                {'team_table': league.get_team_table(allowed_join, is_player_token_valid(request), player)})
            context.update({'tournament': league})
            context.update({'pause_resume_buttons': league.get_pause_resume(player)})
            context.update({'join_leave_buttons': league.get_join_leave(allowed_join, is_player_token_valid(request), player)})
            context.update({'invited_players': league.get_invited_players_table()})
            context.update({'bracket_game_data': league.get_bracket_game_data()})
            context.update({'template_settings': league.get_template_settings_table()})
            context.update({'game_log': league.get_game_log()})
            return render(request, 'league.html', context)
        else:
            return HttpResponseRedirect('/index/')
    except Exception:
        log_exception()
        # return the default tournament page regardless
        return HttpResponseRedirect('/index/')


@ensure_csrf_cookie
def update_max_games_at_once(request):
    try:
        context = {'success': 'false'}
        print("Updating max games: {}".format(request.POST))
        if request.method == "POST" and 'leagueid' in request.POST and is_player_token_valid(request):
            player = Player.objects.filter(token=request.session['token'])
            player = player[0]
            tournament = find_tournament_by_id(request.POST['leagueid'], True)
            if tournament and 'team_id' in request.POST:
                tplayer = TournamentPlayer.objects.filter(tournament=tournament, player=player, team=int(request.POST['team_id']))
                if tplayer:
                    tplayer = tplayer[0]
                    if 'max_games' in request.POST:
                        tplayer.team.update_max_games_at_once(request.POST['max_games'])
                context.update({'success': "true"})
            else:
                context.update({'error': "You are not authorized to modify this league."})
            return JsonResponse(context)
        context.update({'error': 'Invalid Request'})
        return JsonResponse(context)
    except ObjectDoesNotExist:
        return HttpResponseRedirect('/index/')
    except Exception as e:
        log_exception()
        context.update({'error': str(e)})
        return JsonResponse(context)

@ensure_csrf_cookie
def cl_update_templates(request):
    try:
        context = {'success': 'false'}
        print("Request Parameters: {}".format(request.POST))
        if request.method == "POST" and 'tournamentid' in request.POST and is_player_token_valid(request):
            player = Player.objects.filter(token=request.session['token'])
            player = player[0]
            tournament = find_tournament_by_id(request.POST['tournamentid'], True)
            if tournament and tournament.created_by.id == player.id:
                optype = request.POST['optype']
                # what kind of operations are we performing?
                if optype == "add":
                    tournament.add_template(request)
                elif optype == "remove":
                    tournament.remove_template(request)

                templates = tournament.get_editable_template_data()
                context.update({'success': "true"})
                context.update({'templates': templates})
            else:
                context.update({'error': "You are not authorized to modify this league."})
            return JsonResponse(context)
    except ObjectDoesNotExist:
        return HttpResponseRedirect('/index/')
    except Exception as e:
        log_exception()
        context.update({'error': str(e)})
        return JsonResponse(context)

@ensure_csrf_cookie
def cl_start_template(request):
    try:
        context = {'success': 'false'}
        print("Request params: {}".format(request.POST))
        if request.method == "POST" and 'tournamentid' in request.POST and 'templateid' in request.POST and is_player_token_valid(request):
            player = Player.objects.get(token=request.session['token'])
            tournament = find_tournament_by_id(request.POST['tournamentid'], True)
            if tournament and tournament.created_by.id == player.id:
                tournament.start_template(request.POST['templateid'])
                context.update({'template_data': tournament.get_editable_template_data()})
                context.update({'success': 'true'})
            else:
                context.update({'error': "Your are not authorized to start this template tournament."})
        else:
            context.update({'error': "Invalid Request"})
        return JsonResponse(context)

    except Exception as e:
        log_exception()
        context.update({'error': str(e)})
        return JsonResponse(context)

@ensure_csrf_cookie
def cl_update_divisions(request):
    try:
        context = {'success': 'false'}
        # print("Request Parameters: {}".format(request.POST))
        if request.method == "POST" and 'tournamentid' in request.POST and is_player_token_valid(request):
            player = Player.objects.filter(token=request.session['token'])
            player = player[0]
            tournament = find_tournament_by_id(request.POST['tournamentid'], True)
            if tournament and tournament.created_by.id == player.id:
                optype = request.POST['optype']
                # what kind of operations are we performing?
                if optype == "add":  # adding a new division
                    # parse the division title
                    division = tournament.add_new_division(request)
                elif optype == "remove":  # removing a division
                    tournament.remove_division(request)
                elif optype == "update":  # updating a division with clans
                    # parse the division, and update the tournament
                    tournament.update_clans(request)
                elif optype == "remove-clan":
                    tournament.update_clans(request)
                #  PR LEAGUE ONLY FOR NOW
                elif optype == "add-team":
                    tournament.add_team_to_division(request)
                elif optype == "remove-team":
                    tournament.remove_team_from_division(request)

                divisions = tournament.get_editable_divisions_data()
                context.update({'success': "true"})
                context.update({'divisions': divisions})
            else:
                context.update({'error': "You are not authorized to modify this league."})
            return JsonResponse(context)
    except ObjectDoesNotExist:
        return HttpResponseRedirect('/index/')
    except Exception as e:
        log_exception()
        context.update({'error': str(e)})
        return JsonResponse(context)


@ensure_csrf_cookie
def pr_view_season(request, id):
    try:
        tournament = find_tournament_by_id(id, True)
        if tournament:
            print("Found p/r league season {}".format(id))
            context = {'tournament': tournament}
            return render(request, "pr_season.html", context)
        else:
            return HttpResponseRedirect('/index/')
    except Exception:
        log_exception()
        return HttpResponseRedirect('/index/')

@ensure_csrf_cookie
def pr_update_season(request):
    try:
        context = {'success': 'false'}
        player = None
        if request.method == "POST" and 'tournamentid' in request.POST and is_player_token_valid(request):
            tournament = find_tournament_by_id(request.POST['tournamentid'], True)
            if tournament:
                player = Player.objects.filter(token=request.session['token'])
                player = player[0]
                if player and player.id == tournament.created_by.id:
                    # create the season
                    try:
                        if request.POST['type'] == "add":
                            tournament.create_season(request.POST['season-name'])
                        elif request.POST['type'] == "remove":
                            tournament.remove_season(request.POST['season_id'])

                        context.update({'success': 'true'})
                        context.update({'season_data': tournament.get_seasons_editable()})
                    except ValueError as e:
                        context.update({'error': str(e)})
                else:
                    context.update({'error': "Only creators can create seasons."})
        return JsonResponse(context)

    except Exception as outer_e:
        log_exception()
        # return the default tournament page regardless
        context.update({'error': str(outer_e)})
        return JsonResponse(context)

@ensure_csrf_cookie
def tournament_display_view(request, id):
    try:
        tournament = find_tournament_by_id(id)
        context = {}
        player = None
        if tournament is not None:
            # look-up if the current player is in the tournament
            context.update({'player_in_tourney': False})
            allowed_join = False
            if is_player_token_valid(request):
                try:
                    player = Player.objects.get(token=request.session['token'])

                    player_tourney = TournamentPlayer.objects.filter(player=player, tournament=tournament)
                    if player_tourney:
                        context.update({'player_in_tourney': True})
                except ObjectDoesNotExist:
                    # not found, go to homepage
                    log("tournament_display_view: cannot find player based on token {}".format(request.session['token']), LogLevel.warning)
                    return HttpResponseRedirect('/index/')

                # get the api to check to see if we can display join buttons
                apirequestJson = {}
                allowed_join = is_player_allowed_join(player, tournament.template)
                if allowed_join and tournament.private:
                    # if the template works and this tournament is private we are only
                    # allowed to join if we've been invited by the host
                    invites = TournamentInvite.objects.filter(player=request.session['token'], joined=False)
                    if not invites:
                        allowed_join = False

            context.update({'team_table': tournament.get_team_table(allowed_join, is_player_token_valid(request), player)})
            context.update({'tournament': tournament})
            context.update({'invited_players': tournament.get_invited_players_table()})
            context.update({'bracket_game_data': tournament.get_bracket_game_data()})
            context.update({'template_settings': tournament.get_template_settings_table()})
            context.update({'game_log' : tournament.get_game_log()})
            return render(request, 'tournament.html', context)
        else:
            log("Tournament could not be found!", LogLevel.informational)
            return HttpResponseRedirect('/index/')
    except Exception:
        log_exception()
        # return the default tournament page regardless
        return HttpResponseRedirect('/index/')


def tournament_invite_players(request):
    context = {'success': 'false'}
    print("Invite Request: {}".format(request))
    if request.method == 'POST' and is_player_token_valid(request):
        print("Valid POST method and token")
        try:
            tournament = find_tournament_by_id(request.POST['tournamentid'], True)
            if tournament:
                # get the list of uninvited players (inverse list)
                print("Getting list of invited players")
                tournament.invite_player(request.POST)
                invited_players_inverse = tournament.get_invited_players_inverse_table(tournament.created_by.token, request.POST, request.session['token'])
                invited_players = tournament.get_invited_players_table()

                context.update({"invited_players_inverse": invited_players_inverse})
                context.update({"invited_players": invited_players})

                if 'cl-update-player' in request.POST:
                    tournament_player = TournamentPlayer.objects.filter(id=request.POST['data_attrib[player]'])
                    if tournament_player:
                        tournament_player = tournament_player[0]
                        divisionid = tournament_player.team.clan_league_division.id
                        context.update({"division_div": "division-data-{}".format(divisionid)})
                        division_card = tournament.get_editable_roster_data(divisionid)
                        context.update({"division_card": division_card})
                context.update({"success": "true"})
                print("Success returning back")
                return JsonResponse(context)
        except ObjectDoesNotExist:
            log("Player {} does not exist!", LogLevel.critical)
        except Exception as e:
            log_exception()
            context.update({"error": str(e)})
            return JsonResponse(context)

    return HttpResponseRedirect('/index/')


def tournament_player_status_change(request):

    context = {}
    if is_player_token_valid(request):
        if request.method == 'POST':
            print(request.POST)
            templateid = request.POST['templateid']
            tournamentid = request.POST['tournamentid']
            buttonid = request.POST['buttonid']

            if templateid.isnumeric() and tournamentid.isnumeric():
                # validate them
                tournament = find_tournament_by_id(tournamentid, True)
                if tournament is not None:
                    # valid tournament, process the join/decline here
                    try:
                        player = Player.objects.filter(token=request.session['token'])
                        if player:
                            if "join" in buttonid:
                                tournament.join_tournament(request.session['token'], buttonid)
                            elif "decline" in buttonid:
                                if "team" in request.POST:
                                    print("Host forcibly removing a player from MTC")
                                    teamid = request.POST['team']
                                    if teamid.isnumeric():
                                        tplayer = TournamentPlayer.objects.filter(team=int(teamid))
                                        if tplayer:
                                            tplayer = tplayer[0]
                                            tournament.decline_tournament(tplayer.player.token)
                                else:
                                    tournament.decline_tournament(request.session['token'])

                            # now refresh the list of players
                            allowed_join = is_player_allowed_join(player[0], tournament.template)
                            context.update({'team_table': tournament.get_team_table(allowed_join,
                                                                                       is_player_token_valid(
                                                                                           request), player[0])})
                            # we should always get this far
                            context.update({'is_league': tournament.is_league})
                            if tournament.is_league:
                                context.update({'join_leave_buttons': tournament.get_join_leave(allowed_join, is_player_token_valid(request), player[0])})
                            context.update({'can_start_tourney': tournament.can_start_tourney})
                            context.update({'success': 'true'})
                        else:
                            log("Player not found for token {} ".format(request.session['token']), LogLevel.critical)
                            context.update({'error': 'Player not found for token.'})

                    except Exception as e:
                        log_exception()
                        context.update({'error': str(e)})

                    ret = JsonResponse(context)

                    return ret

    return HttpResponseRedirect('/index/')


def template_check_view(request):
    if is_player_token_valid(request):
        if request.method == 'POST':
            templateid = request.POST['templateid']
            if templateid.isnumeric():
                # make the call
                api = API()
                ret = api.api_create_fake_game_and_get_settings(templateid)

                # pass back the json
                return JsonResponse(ret)
    else:
        return index(request)


@ensure_csrf_cookie
def mytourneys_view(request):
    context = {}
    if is_player_token_valid(request):
        try:
            player = Player.objects.get(token=request.session['token'])
            result_list = []
            tournaments_found = []  # holds the list of tournaments we've added, so we can add in order and keep duplicates out

            league_list = []
            leagues_found = []
            # try to get all the tournaments that the player has been invited to
            invites = TournamentInvite.objects.filter(player=player).select_related('tournament')
            if invites:
                for tourney in invites:
                    if tourney.tournament.id not in tournaments_found and not tourney.tournament.is_league:
                        child_tourney = find_tournament_by_id(tourney.tournament.id)
                        if child_tourney:
                            result_list.append(child_tourney)
                            tournaments_found.append(tourney.tournament.id)
                            tourney.tournament.setPlayerInvited(True)
                    elif tourney.tournament.id not in leagues_found and tourney.tournament.is_league:
                        child_league = find_league_by_id(tourney.tournament.id)
                        if child_league:
                            league_list.append(child_league)
                            leagues_found.append(child_league.id)

            # now grab all tournament the player is actually in
            joined = TournamentPlayer.objects.filter(player=player).select_related('tournament')
            if joined:
                for tourney in joined:
                    if tourney.tournament.id not in tournaments_found and not tourney.tournament.is_league:
                        child_tourney = find_tournament_by_id(tourney.tournament.id)
                        if child_tourney:
                            result_list.append(child_tourney)
                            tournaments_found.append(tourney.tournament.id)
                        elif tourney.tournament.id not in leagues_found and hasattr(tourney.tournament, 'pr_parent_tournament'):
                            child_league = find_league_by_id(tourney.tournament.id)
                            if child_league:
                                league_list.append(child_league.pr_tournament)
                                leagues_found.append(child_league.pr_tournament.id)
                    elif tourney.tournament.id not in leagues_found and tourney.tournament.is_league:
                        child_league = find_league_by_id(tourney.tournament.id)
                        if child_league:
                            league_list.append(child_league)
                            leagues_found.append(child_league.id)

            swiss_tournaments = SwissTournament.objects.filter(created_by=player).select_related('tournament_ptr').order_by('-created_date')
            if swiss_tournaments:
                for tourney in swiss_tournaments:
                    if tourney.id not in tournaments_found:
                        result_list.append(tourney)
                        tournaments_found.append(tourney.id)

            seeded_tournaments = SeededTournament.objects.filter(created_by=player).select_related('tournament_ptr').order_by('-created_date')
            if seeded_tournaments:
                for tourney in seeded_tournaments:
                    if tourney.id not in tournaments_found:
                        result_list.append(tourney)
                        tournaments_found.append(tourney.id)

            group_stage_tournaments = GroupStageTournament.objects.filter(created_by=player).select_related('tournament_ptr').order_by('-created_date')
            if group_stage_tournaments:
                for tourney in group_stage_tournaments:
                    if tourney.id not in tournaments_found:
                        result_list.append(tourney)
                        print("Tournament: {}".format(tourney))
                        tournaments_found.append(tourney.id)


            leagues = Tournament.objects.filter(created_by=player, is_league=True).order_by(
                "-created_date")
            for league in leagues:
                child_league = find_league_by_id(league.id)
                if child_league and league.id not in leagues_found:
                    league_list.append(child_league)
                    leagues_found.append(child_league.id)

            context.update({'leagues': league_list})
            context.update({'tournaments': result_list})

            return render(request, 'mytourneys.html', context)
        except ObjectDoesNotExist:
            #have a token and no player
            log("Found a token with no matching player: {} ".format(request.session['token']), LogLevel.critical)

    return index(request)


@ensure_csrf_cookie
def settings_view(request):
    context = {}
    if is_player_token_valid(request):
        try:
            player = Player.objects.get(token=request.session['token'])

            # we have the player, load some settings so that they can be displayed on the page
            if player.bot_token == "invalid":
                # generate one
                randomSource = string.ascii_letters + string.digits
                player.bot_token = ''.join(random.choice(randomSource) for i in range(32))
                player.save()

            print("Player Bot Token: {}".format(player.bot_token))
            context.update({'player': player})
            return render(request, "settings.html", context)
        except ObjectDoesNotExist:
            return index(request)
    else:
        return index(request)

@ensure_csrf_cookie
def mygames_view(request):
    context = {}
    # data table for all the games I am in

    game_data_table = '<div class="row"><div class="container"><table class="table table-bordered table-condensed clot_table" id="game_log_data_table">'
    game_data_table += '<thead><tr><th>Tournament</th><th>Game</th><th>Game Link</th><th>Outcome</th></tr></thead><tbody>'
    if is_player_token_valid(request):
        # valid token, get all the players games
        try:
            player = Player.objects.get(token=request.session['token'])

            tournament_players = TournamentPlayer.objects.filter(player=player)
            for tournament_player in tournament_players:
                game_entries = TournamentGameEntry.objects.filter(team=tournament_player.team)
                for game_entry in game_entries:
                    if game_entry.game.is_finished and game_entry.game.winning_team == tournament_player.team:
                        outcome = '<span class="label label-success">You Won</span>'
                    elif game_entry.game.is_finished:
                        outcome = '<span class="label label-danger">You Lost. Get Better.</span>'
                    else:
                        outcome = '<span class="label label-primary">In Progress</span>'
                    game_data_table += '<tr>'
                    game_data_table += '<td>{}</td>'.format(game_entry.tournament.name)
                    game_data_table += '<td>{}</td>'.format(get_matchup_data(game_entry.team, game_entry.team_opp))
                    game_data_table += '<td><a href="{}" target="_blank">Game Link</a></td>'.format(game_entry.game.game_link)
                    game_data_table += '<td>{}</td>'.format(outcome)

            game_data_table += '</tbody></table></div></div>'
            context.update({'my_games': game_data_table})
            return render(request, 'games.html', context)
        except ObjectDoesNotExist:
            # not found, go to homepage
            log("refresh_tournament: cannot find player based on token {}".format(
                request.session['token']), LogLevel.warning)
            return HttpResponseRedirect('/index/')

    return index(request)


# Create your views here.
@ensure_csrf_cookie
def index(request):
    context = {}
    try:
        request.session.set_expiry(0)
        request.session['account_token'] = get_account_token()

        result_list = []
        tournaments = Tournament.objects.filter(private=False, is_finished=False, has_started=False).order_by("-created_date")
        for tournament in tournaments:
            child_tournament = find_tournament_by_id(tournament.id)
            if child_tournament:
                result_list.append(child_tournament)

        league_list = []
        leagues = Tournament.objects.filter(private=False, is_finished=False, is_league=True).order_by("-is_official", "-created_date")
        for league in leagues:
            child_league = find_league_by_id(league.id)
            if child_league:
                league_list.append(child_league)

        context.update({'leagues': league_list})
        context.update({'tournaments': result_list})

        return render(request, 'mytourneys.html', context)
    except ObjectDoesNotExist:
        log("No open tournaments", LogLevel.informational)

        return render(request, 'mytourneys.html', context)


# The main Login View of the site
def login_view(request):
    try:
        # regardless, terminate the session when the browser is closed
        request.session.set_expiry(0)
        if not is_player_token_valid(request):
            if request.method == 'GET':
                # Cast token to long to ensure the only contain numerical digits (this is easy in python since longs can go to any size.
                # In other languages we might have to do more work here to avoid overflows since tokens can exceed 2^32)
                if 'token' in request.GET:
                    token = str(int(request.GET['token']))
                    clotpass = request.GET['clotpass']

                    if not token.isnumeric():
                        errors = FormError({'error': "There's an invalid login request being made. We're looking into it. "})
                        return render(request, 'error.html', {'errors': errors})

                    # get the api
                    api = API()
                    apirequest = api.api_validate_invite_token(token)
                    apirequestJson = apirequest.json()
                    log("Validate token info: {}".format(apirequestJson), LogLevel.informational)

                    if clotpass != apirequestJson['clotpass']:
                        errors = FormError({'error': "There's a problem with logging in. We're working on it."})
                        print("Clot pass error")
                        return render(request, 'error.html', {'errors': errors})

                    if "tokenIsValid" not in apirequestJson:
                        errors = FormError({'error': "There's a problem with logging in. We're working on it."})
                        return render(request, 'error.html', {'errors': errors})

                    request.session['token'] = token

                    # lookup the user in the DB
                    # if there is no user, create one and pass the user along
                    player = None
                    try:
                        player = Player.objects.get(token=token)

                        if 'clan' in apirequestJson:
                            # lookup the clan
                            clan = Clan.objects.filter(name=apirequestJson['clan'])
                            if clan:
                                player.clan = clan[0]
                        else:
                            # no clan in the player token data, so remove it for them
                            player.clan = None

                        # always update the name
                        player.name = apirequestJson['name']
                    except ObjectDoesNotExist:
                        if 'clan' in apirequestJson:
                            player = Player(token=token,clan_text=apirequestJson['clan'],name=apirequestJson['name'])

                            # lookup the clan
                            clan = Clan.objects.filter(name=apirequestJson['clan'])
                            if clan:
                                player.clan = clan[0]
                        else:
                            player = Player(token=token, name=apirequestJson['name'])

                    # save the player
                    player.save()

                    if player.clan is not None:
                        request.session['clan_icon_link'] = player.clan.icon_link
                        request.session['clan_image_path'] = player.clan.image_path

                    request.session['player_name'] = player.name

                return redirect('mytourneys_view')
        else:
            # found the token, lookup the player
            try:
                player = Player.objects.get(token=request.session['token'])
                request.session['player_name'] = player.name

                if player.clan is not None:
                    request.session['clan_icon_link'] = player.clan.icon_link
                    request.session['clan_image_path'] = player.clan.image_path
            except ObjectDoesNotExist:
                # TODO, really bad we should log
                log("Found token {} but no corresponding player".format(request.session['token']), LogLevel.critical)
                pass

            return HttpResponseRedirect('/index/')
    except KeyError:
        log(traceback.format_exc(), LogLevel.critical)
        return HttpResponseRedirect('/index/')


# The main logout view
def logout_view(request):
    # destroy the session
    return HttpResponseRedirect("/index")


def about_view(request):
    return render(request, 'about.html')


@ensure_csrf_cookie
def create_new_league_specific_view(request, encoded_url=None):
    if not is_player_token_valid(request):
        return HttpResponseRedirect('/index/')
    if encoded_url is not None:
        context = {}
        if encoded_url == "mtc":
            # pass the context
            return render(request, 'create_new_league.html', {'type': 'mtc', 'league_type': 'Monthly Template Circuit'})
        elif encoded_url == "pr":
            # pass the context
            return render(request, 'create_new_league.html', {'type': 'pr', 'league_type': 'Promotion/Relegation League'})
        elif encoded_url == "cl":
            # pass the context
            return render(request, 'create_new_league.html', {'type': 'cl', 'league_type': 'Clan League'})
    else:
        return render(request, 'create_new_league.html')


def create_new_league_view(request):
    return render(request, 'create_new_league.html')

@ensure_csrf_cookie
def create_new_view(request, type=None):

    if not is_player_token_valid(request):
        return HttpResponseRedirect('/index/')

    if type is not None:
        type = int(type)
    log("Creating tourney type: {}".format(type), LogLevel.informational)
    if type == 1:
        # creating a group stage tourney
        return render(request, 'create_new.html', {'type': '1', 'tournament_type': "Group Stage"})
    elif type == 2:
        return render(request, 'create_new.html', {'type': '2', 'tournament_type': "Swiss"})
    elif type == 3:
        # creating a seeded tournament
        return render(request, 'create_new.html', {'type': '3', 'tournament_type': "Seeded"})
    else:
        return render(request, 'create_new.html')


@ensure_csrf_cookie
def create_new_form_submit_view(request):
    try:
        if is_player_token_valid(request):
            form = None
            if request.method == "POST":
                # process the form

                try:
                    type = request.POST['type']
                    print(request.POST)
                    if type == "1":
                        form = GroupTournamentForm(request.POST)
                    elif type == "2":
                        form = SwissTournamentForm(request.POST)
                    elif type == "3":
                        form = SeededTournamentForm(request.POST)
                    elif type == "mtc":
                        form = MonthlyTemplateCircuitForm(request.POST)
                    elif type == "pr":
                        form = PromotionRelegationLeagueForm(request.POST)
                    elif type == "cl":
                        form = ClanLeagueForm(request.POST)
                except KeyError:
                    # redirect to the homepage, invalid request
                    log_exception()
                    return render(request, 'mytourneys.html')

                ret = vars(form)
                ret['errors'] = ''
                ret.update({'success': 'false'})
                if form.is_valid():
                    # create the tournament and redirect to the dashboard
                    print("Valid form...")
                    try:
                        token = request.session['token']
                        player = Player.objects.get(token=token)
                        ret['tourneyid'] = form.create_and_save(player)
                        ret['success'] = "true"
                        ret['errors'] = ''
                        print("Form to calculate return URL: {}".format(form))
                        if form.is_league:
                            ret['redirect_url'] = '/leagues/{}/'.format(ret['tourneyid'])
                        else:
                            ret['redirect_url'] = '/tournaments/{}/'.format(ret['tourneyid'])
                    except ObjectDoesNotExist:
                        log("Trying to create a tournament, but the player does not exist for token {}".format(request.session['token']), LogLevel.critical)
                    except:
                        errors = {'error': "There was a problem creating the tournament. We're looking into it."}
                        log_exception()
                        ret.update({'errors': errors})
                else:
                    if form.errors:
                        print("Form errors: {}".format(form.errors))
                        ret['errors'] = form.errors
                    else:
                        ret['errors'] = "There was an error when processing the form. We're looking into it."
                    ret['success'] = "false"

                print(ret)
                # we need to return json, send the response back
                return JsonResponse(ret)

    except:
        log(traceback.format_exc(), LogLevel.critical)
        return render(request, 'mytourneys.html')
