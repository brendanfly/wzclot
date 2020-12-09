import discord
from discord.ext import commands, tasks
from django.utils import timezone
from traceback import print_exc
from wlct.logging import LogLevel
from wlct.api import API
import gc
import datetime
import pytz
import urllib.request
import json
import gc
import asyncio

class Tasks(commands.Cog, name="tasks"):
    def __init__(self, bot):
        self.bot = bot
        self.last_task_run = timezone.now()
        self.executions = 0
        self.bg_task.start()

    async def handle_rtl_tasks(self):
        ladders = await self.bot.bridge.getRealTimeLaddersAll()
        for ladder in ladders:
            games = await self.bot.bridge.getGames(tournament=ladder, is_finished=False, mentioned=False)
            # cache the game data + link for use with the embed
            emb = discord.Embed(color=self.bot.embed_color)
            emb.set_author(icon_url=self.bot.user.avatar_url, name="WarzoneBot")
            emb.title = "New Ladder Game Created"
            emb.set_footer(text="Bot created and maintained by -B#0292")
            for game in games:
                data = ""
                team1 = game.teams.split('.')[0]
                team2 = game.teams.split('.')[1]
                player1 = ladder.get_player_from_teamid(team1)
                player2 = ladder.get_player_from_teamid(team2)
                if player1.discord_member and player2.discord_member:
                    data += "<@{}> vs. <@{}> [Game Link]({})\n".format(player1.discord_member.memberid, player2.discord_member.memberid,
                                                                       game.game_link)
                elif player1.discord_member:
                    data += "<@{}> vs. <{}> [Game Link]({})\n".format(player1.discord_member.memberid, player2.name,
                                                                       game.game_link)
                elif player2.discord_member:
                    data += "<{}> vs. <@{}> [Game Link]({})\n".format(player1.name, player2.discord_member.memberid,
                                                                       game.game_link)
                else:
                    await self.bot.bridge.updateGameMentioned(game)
                    return
                emb.add_field(name="Game", value=data, inline=True)
                if player1 and player1.discord_member:
                    user = self.bot.get_user(player1.discord_member.memberid)
                    if user:
                        try:
                            await user.send(embed=emb)
                        except:
                            await self.bot.bridge.log_bot_msg("Could not send RTL game msg to {} ".format(player1.name))
                if player2 and player2.discord_member:
                    user = self.bot.get_user(player2.discord_member.memberid)
                    if user:
                        try:
                            await user.send(embed=emb)
                        except:
                            await self.bot.bridge.log_bot_msg("Could not send RTL game msg to {} ".format(player2.name))
                await self.bot.bridge.updateGameMentioned(game)

    async def handle_clan_league_next_game(self):
        clt = await self.bot.bridge.getClanLeagueTournaments(is_finished=False)
        for t in clt:
            # get the time until next game allocation
            start_times = t.games_start_times.split(';')

            # always take the next (first) one
            if len(start_times[0]) >= 8:  # every start time is a day/month/year, and we need at least 8 characters
                next_start = datetime.datetime.strptime(start_times[0], "%m.%d.%y")
                diff = datetime.datetime.utcnow() - next_start
                # diff is our delta, compute how many days, hours, minutes remaining

    async def handle_clotbook(self):
        channel_links = await self.bot.bridge.getChannelClotbookLinks(results_only=False)
        odds_created_sent = []
        odds_finished_sent = []
        cb = await self.bot.bridge.getCLOTBook()
        try:
            for cl in channel_links:
                channel = self.bot.get_channel(cl.channelid)
                if hasattr(self.bot, 'uptime') and channel:
                    bet_odds = await self.bot.bridge.getBetGameOddsOrderByCreatedTime(sent_created_notification=False, initial=True)
                    for bo in bet_odds:
                        if not cl.does_game_pass_filter(bo.game):
                            odds_created_sent.append(bo)
                            continue
                        emb = self.bot.get_default_embed()
                        emb = cb.get_initial_bet_card(bo, emb)
                        await channel.send(embed=emb)
                        odds_created_sent.append(bo)

            channel_links = await self.bot.bridge.getChannelClotbookLinks(results_only=True)
            for cl in channel_links:
                channel = self.bot.get_channel(cl.channelid)
                if hasattr(self.bot, 'uptime') and channel:
                    bet_odds = await self.bot.bridge.getBetGameOddsOrderByCreatedTime(sent_finished_notification=False, game__is_finished=True)
                    print("Found {} finished bet game odds".format(bet_odds.count()))
                    for bo in bet_odds:
                        if bo.game.winning_team:
                            if not cl.does_game_pass_filter(bo.game):
                                odds_finished_sent.append(bo)
                                continue
                            emb = self.bot.get_default_embed()
                            emb = cb.get_bet_results_card(bo, emb)
                            if emb:
                                await channel.send(embed=emb)
                            odds_finished_sent.append(bo)
                        else:
                            print("Game {} does not have a winning team, skipping".format(bo.game.gameid))
        except Exception:
            await self.bot.bridge.log_exception()
        finally:
            for odds in odds_created_sent:
                await self.bot.bridge.updateBetOddsSentCreated(odds)
            for odds in odds_finished_sent:
                await self.bot.bridge.updateBetOddsSentFinished(odds)

    async def handle_game_logs(self):
        channel_links = await self.bot.bridge.getChannelTournamentLinksAll()
        games_sent = []
        try:
            for cl in channel_links:
                channel = self.bot.get_channel(cl.channelid)
                # for each channel, see if there are any new games that have finished in the tournament that's linked
                # only look at games that have finished times greater than when the bot started
                game_log_text = ""
                if hasattr(self.bot, 'uptime') and channel:
                    time_since = self.bot.uptime-datetime.timedelta(days=3)
                    games = await self.bot.bridge.getGames(is_finished=True, tournament=cl.tournament, game_finished_time__gt=(time_since), game_log_sent=False)
                    if len(games) > 0:
                        await self.bot.bridge.log_bot_msg("Found {} games to log in channel {}".format(len(games), channel.name))
                    for game in games:
                        if game.game_finished_time is None and game.winning_team or not game.winning_team:
                            continue  # ignore games with no finished time (which might be 0 and returned in this query)
                        # we have the game, construct the log text and send it to the channel

                        # Check if game passes player/clan filter
                        if not cl.does_game_pass_filter(game):
                            games_sent.append(game)
                            continue

                        # bold the clans if any, and italicize
                        teams = game.teams.split('.')
                        team_list = []
                        team_list.append(game.winning_team.id)
                        for team in teams:
                            if int(team) not in team_list:
                                team_list.append(int(team))

                        player_team_id_list = None
                        if game.players:
                            player_team_id_list = game.players.split("-")

                        wrote_defeats = False
                        for team in team_list:
                            tt = await self.bot.bridge.getTournamentTeams(pk=team)
                            if len(tt):
                                tt = tt[0]
                                # look up the clan for this team, and bold/write the clan name in there.
                                if tt.clan_league_clan and tt.clan_league_clan.clan:
                                    game_log_text += "**{}** ".format(tt.clan_league_clan.clan.name)

                                # if game has 'players' value, use that otherwise get names from TournamentPlayer
                                if player_team_id_list:
                                    tplayers = player_team_id_list[teams.index(str(team))].split(".")
                                else:
                                    tplayers = await self.bot.bridge.getTournamentPlayers(team=tt)

                                for tplayer in tplayers:
                                    if player_team_id_list:
                                        player_name = await self.bot.bridge.getPlayers(token=tplayer)
                                        player_name = player_name[0].name
                                    else:
                                        player_name = tplayer.player.name
                                    game_log_text += "*{}*, ".format(player_name)

                                game_log_text = game_log_text[:-2]
                                if not wrote_defeats:
                                    game_log_text += " defeats "
                                    wrote_defeats = True

                        tournament = await self.bot.bridge.findTournamentById(game.tournament.id, True)
                        if tournament and hasattr(tournament, 'clan_league_template') and tournament.clan_league_template:
                            game_log_text += "\n{}".format(tournament.clan_league_template.name)

                        game_log_text += "\n<{}>".format(game.game_link)

                        await self.bot.bridge.log_bot_msg("Looping through channels to log: {}, length: {}".format(game_log_text, len(game_log_text)))
                        if channel and len(game_log_text) > 0:
                            await self.bot.bridge.log_bot_msg("Sending game_log to channel: {}".format(channel.name))
                            try:
                                await channel.send(game_log_text)
                                games_sent.append(game)
                                game_log_text = ""
                            except:
                                await self.bot.bridge.log_bot_msg("Exception: {} when sending message to server {}, channel {}".format(await self.bot.bridge.log_exception(), channel.guild.name, channel.name))

        except Exception:
            await self.bot.bridge.log_exception()
        finally:
            for g in games_sent:
                await self.bot.bridge.updateGameLogSent(g)

    async def handle_server_stats(self):
        pass

    async def handle_hours6_tasks(self):
        #await self.handle_clan_league_next_game()
        pass

    async def handle_hours4_tasks(self):
        # every 4 hours we currently only send clan league updates
        pass

    async def handle_hours_tasks(self):
        pass

    async def handle_day_tasks(self):
        await self.handle_server_stats()

    async def handle_no_winning_team_games(self):
        games = await self.bot.bridge.getGames(winning_team__isnull=True, is_finished=True, no_winning_team_log_sent=False)
        msg = ""
        if games:
            msg += "**Games finished with no winning team found**"
        for game in games:
            for cc in self.bot.critical_error_channels:
                msg += "\n{} | ID: {} \nLink: <{}> \nLogs: <http://wzclot.eastus.cloudapp.azure.com/admin/wlct/processgamelog/?q={}>".format(game.tournament.name, game.gameid, game.game_link, game.gameid)
                msg = msg[:1999]
                await cc.send(msg)
                await self.bot.bridge.updateGameNoWinningTeamSent(game)
                msg = ""

    async def handle_rt_ladder(self):
        tournaments = await self.bot.bridge.getTournaments(has_started=True, is_finished=False)
        for tournament in tournaments:
            child_tournament = await self.bot.bridge.findTournamentById(tournament.id, True)
            if child_tournament and not child_tournament.should_process_in_engine():
                try:
                    await self.bot.bridge.updateRealTimeLadderUpdateInProgress(child_tournament, True)
                    games = await self.bot.bridge.getGames(is_finished=False, tournament=tournament)
                    for game in games.iterator():
                        # process the game
                        # query the game status
                        child_tournament.process_game(game)
                    # in case tournaments get stalled for some reason
                    # for it to process new games based on current tournament data
                    child_tournament.process_new_games()
                    await self.handle_rtl_tasks()
                except Exception as e:
                    await self.bot.bridge.log_exception()
                finally:
                    await self.bot.bridge.updateRealTimeLadderUpdateInProgress(child_tournament, False)
            gc.collect()

    async def handle_process_queue(self):
        for i in range(0, len(self.bot.process_queue)):
            gc.collect()
            t = await self.bot.bridge.findTournamentById(self.bot.process_queue[i], True)
            if t:
                print("Processing data for {}".format(t.name))
                games = await self.bot.bridge.getGames(is_finished=False, tournament=t)
                for game in games:
                    # process the game
                    # query the game status
                    await self.bot.bridge.process_game(t, game)
                    gc.collect()
                await self.bot.bridge.process_new_games(t)
                self.bot.process_queue.pop(i)

    async def handle_cache_queue(self):
        for i in range(0, len(self.bot.cache_queue)):
            gc.collect()
            t = await self.bot.bridge.findTournamentById(self.bot.cache_queue[i], True)
            if t:
                print("Caching data for {}".format(t.name))
                await self.bot.bridge.cache_data(t)
                self.bot.cache_queue.pop(i)

    async def handle_critical_errors(self):
        logs = await self.bot.bridge.getLogs(level=LogLevel.critical, bot_seen=False)
        for log in logs:
            for cc in self.bot.critical_error_channels:
                msg = "**Critical Log Found**\n"
                msg += log.msg
                msg = msg[:1999]
                await cc.send(msg)
                await asyncio.sleep(1)

                # Update the log
                await self.bot.bridge.updateLogSeen(log)

    async def handle_discord_tournament_updates(self):
        try:
            updates = await self.bot.bridge.getTournamentUpdates(bot_send=False)
            for u in updates:
                # look up the tournament, and get all channel links for that tournament
                channel_links = await self.bot.bridge.getChannelTournamentLinks(tournament=u.tournament)
                for c in channel_links:
                    channel = self.bot.get_channel(c.channelid)
                    if channel:
                        await channel.send(u.update_text)
                await self.bot.bridge.updateTournamentUpdateSent(u)
        except:
            await self.bot.bridge.log_exception()

    async def handle_all_tasks(self):
        # calculate the time different here
        # determine if we need hours run or 4 hours run
        # for 1 hour, executions should be 360
        if self.bot.shutdown:
            await self.bot.logout()
            return
        start = datetime.datetime.utcnow()
        hours = (self.executions % 360 == 0)
        hours4 = (self.executions % (360*4) == 0)
        hours6 = (self.executions % (360*6) == 0)
        day = (self.executions % (360*24) == 0)
        two_minute = (self.executions % 12 == 0)

        try:
            if hours:
                await self.handle_hours_tasks()
            if hours4:
                await self.handle_hours4_tasks()
            if hours6:
                await self.handle_hours6_tasks()
            if day:
                await self.handle_day_tasks()
            if two_minute:
                start = datetime.datetime.utcnow()
                await self.handle_rt_ladder()
                end = datetime.datetime.utcnow()
                self.bot.perf_counter("RT Ladder Tasks took {} total seconds".format((end-start).total_seconds()))

            # always tasks
            start = datetime.datetime.utcnow()
            await self.handle_always_tasks()
            end = datetime.datetime.utcnow()
            self.bot.perf_counter("Always Tasks took {} total seconds".format((end-start).total_seconds()))
        except Exception:
            await self.bot.bridge.log_exception()
        finally:
            end = datetime.datetime.utcnow()
            self.bot.perf_counter("All Tasks took {} total seconds".format((end-start).total_seconds()))
            gc.collect()

    async def handle_always_tasks(self):
        start = datetime.datetime.utcnow()
        await self.handle_critical_errors()
        end = datetime.datetime.utcnow()
        self.bot.perf_counter("Critical Errors Tasks took {} total seconds".format((end-start).total_seconds()))
        start = datetime.datetime.utcnow()
        await self.handle_game_logs()
        end = datetime.datetime.utcnow()
        self.bot.perf_counter("Game Logs Tasks took {} total seconds".format((end-start).total_seconds()))
        start = datetime.datetime.utcnow()
        await self.handle_cache_queue()
        end = datetime.datetime.utcnow()
        self.bot.perf_counter("Cache queue took {} total seconds".format((end-start).total_seconds()))
        start = datetime.datetime.utcnow()
        await self.handle_process_queue()
        end = datetime.datetime.utcnow()
        self.bot.perf_counter("Process queue took {} total seconds".format((end-start).total_seconds()))
        start = datetime.datetime.utcnow()
        await self.handle_discord_tournament_updates()
        end = datetime.datetime.utcnow()
        self.bot.perf_counter("Tournament updates Tasks took {} total seconds".format((end-start).total_seconds()))
        start = datetime.datetime.utcnow()
        await self.handle_clotbook()
        end = datetime.datetime.utcnow()
        self.bot.perf_counter("CLOTBook Tasks took {} total seconds".format((end-start).total_seconds()))

    async def process_member_join(self, memid):
        member = self.bot.get_user(memid)
        if member:
            send_message = False
            discord_user = await self.bot.bridge.getDiscordUsers(memberid=memid)
            emb = discord.Embed(color=self.bot.embed_color)
            emb.set_author(icon_url=self.bot.user.avatar_url, name="WarzoneBot")
            emb.title = "It's nice to meet you!"
            emb.set_footer(text="Bot created and maintained by -B#0292")
            msg = "Hello {},\n\nI'm a homemade Warzone Discord Bot. \n\nI'm reaching out because your discord account".format(
                member.name)
            msg += " is not linked to the CLOT (custom ladder or tournament). Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions"
            msg += " on how to link the two accounts together.\n\nThis will allow you to participate in the bot's"
            msg += " new real-time-ladder, as well as help to become verified in the Warzone discord server."
            emb.add_field(name="Welcome", value=msg)

            if not discord_user:
                await self.bot.bridge.createDiscordUser(memberid=memid)
            else:
                discord_user = discord_user[0]

            if not discord_user.link_mention:
                print("Sending welcome message to {}".format(member.name.encode('utf-8')))
                await member.send(embed=emb)
                await self.bot.bridge.updateDiscordUserLinkMention(discord_user)

    @tasks.loop(seconds=30.0)
    async def bg_task(self):
        # runs every 10 seconds to check various things
        # are there any new games on the RTL that just got allocated?
        try:
            await self.bot.wait_until_ready()
            owner = self.bot.owner
            await self.handle_all_tasks()
            self.last_task_run = timezone.now()
            self.executions += 1
        except:
            print_exc()
            raise

def setup(bot):
    bot.add_cog(Tasks(bot))