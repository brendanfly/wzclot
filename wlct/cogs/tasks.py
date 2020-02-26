import discord
from wlct.models import Clan, Player, DiscordUser
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, TournamentGame
from discord.ext import commands, tasks
from wlct.cogs.common import is_admin
from django.utils import timezone
from traceback import print_exc
from wlct.logging import log_exception, log, LogLevel
import gc

class Tasks(commands.Cog, name="tasks"):
    def __init__(self, bot):
        self.bot = bot
        self.last_task_run = timezone.now()
        self.executions = 0
        self.bg_task.start()

    async def handle_rtl_tasks(self):
        ladders = RealTimeLadder.objects.all()
        for ladder in ladders:
            print("Handling rtl tasks....")
            games = TournamentGame.objects.filter(tournament=ladder, is_finished=False, mentioned=False)
            print("Total game count: {}".format(games.count()))
            # cache the game data + link for use with the embed
            emb = discord.Embed(color=self.bot.embed_color)
            emb.set_author(icon_url=self.bot.user.avatar_url, name="WarzoneBot")
            emb.title = "New Ladder Game Created"
            emb.set_footer(text="Bot created and maintained by -B#0292")
            for game in games:
                print("RTL: Found game")
                data = ""
                team1 = game.teams.split('.')[0]
                team2 = game.teams.split('.')[1]
                player1 = ladder.get_player_from_teamid(team1)
                player2 = ladder.get_player_from_teamid(team2)
                data += "<@{}> vs. <@{}> [Game Link]({})\n".format(player1.discord_member.memberid, player2.discord_member.memberid,
                                                                   game.game_link)
                emb.add_field(name="Game", value=data, inline=True)
                if player1:
                    user = self.bot.get_user(player1.discord_member.memberid)
                    if user:
                        await user.send(embed=emb)
                if player2:
                    user = self.bot.get_user(player2.discord_member.memberid)
                    if user:
                        await user.send(embed=emb)
                        game.mentioned = True
                        game.save()

    async def handle_hours4_tasks(self):
        # every 4 hours if you haven't linked your WZ account to the CLOT, you should do so
        # get all the members in all servers
        print("Running 4 hours tasks")

    async def handle_hours_tasks(self):
        print("Running hourly task")
        pass

    async def handle_rtl_ladder(self):
        tournaments = Tournament.objects.filter(has_started=True, is_finished=False)
        for tournament in tournaments:
            child_tournament = find_tournament_by_id(tournament.id, True)
            if child_tournament and not child_tournament.should_process_in_engine():
                try:
                    if child_tournament.update_in_progress:
                        continue
                    elif not child_tournament.game_creation_allowed:
                        continue
                    child_tournament.update_in_progress = True
                    child_tournament.save()
                    games = TournamentGame.objects.filter(is_finished=False, tournament=tournament)
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

    async def handle_all_tasks(self):
        # calculate the time different here
        # determine if we need hours run or 4 hours run
        # for 1 hour, executions should be 360
        hours_executions = 360
        hours = (self.executions % 360 == 0)
        hours4 = (self.executions % (360*4) == 0)
        two_minute = (self.executions % 12 == 0)

        if hours:
            await self.handle_hours_tasks()
        if hours4:
            await self.handle_hours4_tasks()
        if two_minute:
            await self.handle_rtl_ladder()

        # always tasks
        await self.handle_always_tasks()

    async def handle_always_tasks(self):
        await self.handle_rtl_tasks()

    async def process_member_join(self, memid):
        member = self.bot.get_user(memid)
        if member:
            send_message = False
            discord_user = DiscordUser.objects.filter(memberid=memid)
            emb = discord.Embed(color=self.bot.embed_color)
            emb.set_author(icon_url=self.bot.user.avatar_url, name="WarzoneBot")
            emb.title = "It's nice to meet you!"
            emb.set_footer(text="Bot created and maintained by -B#0292")
            msg = "Hello {},\n\nI'm a homemade Warzone Discord Bot. \n\nI'm reaching out because your discord account".format(
                member.name)
            msg += " is not linked to the CLOT (custom ladder or tournament). Please see http://wztourney.herokuapp.com/me/ for instructions"
            msg += " on how to link the two accounts together.\n\nThis will allow you to participate in the bot's"
            msg += " new real-time-ladder, as well as help to become verified in the Warzone discord server."
            emb.add_field(name="Welcome", value=msg)

            if not discord_user:
                discord_user = DiscordUser(memberid=memid)
                discord_user.save()
            else:
                discord_user = discord_user[0]

            if not discord_user.link_mention:
                print("Sending welcome message to {}".format(member.name))
                await member.send(embed=emb)
                discord_user.link_mention = True
                discord_user.save()


    @tasks.loop(seconds=10.0)
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