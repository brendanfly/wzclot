import discord
from discord.ext import commands
import urllib.request
import requests
import json
from bs4 import BeautifulSoup
from wlct.models import Engine
from wlct.logging import TournamentGameLog, ProcessGameLog, log_exception
from wlct.models import Player
from wlct.cogs.help import get_help_embed
from django.utils import timezone
import datetime
from django.core.paginator import Paginator


def embed_list_special_delimiter():
    return "$%"

def is_tournament_creator(discord_id, tournament):
    if is_admin(discord_id):
        return True

    player = Player.objects.filter(discord_member__memberid=discord_id)
    if player:
        return player[0].id == tournament.created_by.id
    else:
        return False

def has_admin_access(discord_id):
    # B/Cowboy/Justin's ID
    admins = ["288807658264330242", "199018621098262528", "162968893177069568"]
    if str(discord_id) in admins:
        return True
    return False

def is_admin(discord_id):
    if str(discord_id) == "288807658264330242":
        return True
    return False

class Common(commands.Cog, name="general"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief="Check the status of the CLOT or Warzone Server",
                      usage='''
                      status clot
                      status wz
                      ''')
    async def status(self, ctx, server):
        try:
            url = ""
            if server == "clot" or server == "CLOT":
                url = 'http://wztourney.herokuapp.com'
                r = requests.get(url)
            elif server == "wz" or server == "WZ":
                url = 'https://www.warzone.com/MultiPlayer/'
                r = requests.get(url)
            r.status_code
            if str(r.status_code) == "200":
                status = "{} - ONLINE".format(url)
            else:
                status = "{} - OFFLINE".format(url)

            await ctx.send("Server Status: {}".format(status))
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")


    def get_minutes_seconds(self, timedelta):
        minutes = int(timedelta.total_seconds() / 60)
        seconds = int(timedelta.total_seconds() % 60)

        return (minutes, seconds)


    @commands.command(brief="Displays data about the engine")
    async def engine(self, ctx):
        try:
            engine = Engine.objects.all()
            if engine:
                engine = engine[0]
                time_since_run = timezone.now() - engine.last_run_time
                if engine.next_run_time:
                    time_to_run = engine.next_run_time - timezone.now()

                text = "Last run {} minutes and {} seconds ago\n".format(self.get_minutes_seconds(time_since_run)[0], self.get_minutes_seconds(time_since_run)[1])
                if engine.next_run_time:
                    text += "Next run in {} minutes, {} seconds".format(self.get_minutes_seconds(time_to_run)[0], self.get_minutes_seconds(time_to_run)[1])
                await ctx.send(text)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")


    @commands.command(brief="[admin] Displays game logs for a tournament",
                      usage="bb!game_logs <gameid> <num_logs> <pages>")
    async def game_logs(self, ctx, game_id=0, num_logs=-1, page=-1):
        try:
            if is_admin(ctx.message.author.id):
                if game_id != 0 and num_logs != -1 and page != -1:
                    # good
                    print("Game Id: {}, num_logs per page: {}, page: {}".format(game_id, num_logs, page))
                    game_logs = ProcessGameLog.objects.filter(game__gameid=int(game_id)).order_by('id')
                    print("Number game logs: {}".format(game_logs.count()))
                    paginator = Paginator(game_logs, num_logs)
                    page = paginator.get_page(page)
                    for log in page:
                        await ctx.message.author.send(log.msg[0:1900])
                        if len(log.msg) > 1900:
                            await ctx.message.author.send(log.msg[1900:])
                else:
                    await ctx.send("You must pass in all parameters to the command.")
            else:
                await ctx.send("You must be an admin to use this command")
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.Cog.listener()
    async def on_member_joined(self, ctx, member: discord.Member):
        """Says when a member joined."""
        await ctx.send('Welcome, {0.name}! Please check out my commands below.'.format(member))
        emb = get_help_embed(self)
        await ctx.send(embed=emb)

    @commands.command(brief="Displays Deadman's Multi-Day Ladder Top 10")
    async def mdl(self, ctx):
        try:
            await ctx.send("Gathering MDL rankings data....")
            """displays the top 10 on Deadman's MDL"""
            mdl_url = "http://md-ladder.cloudapp.net/api/v1.0/players/?topk=10"

            content = urllib.request.urlopen(mdl_url).read()

            data = json.loads(content)
            mdl_data = "Deadman's Multi-Day Ladder Top 10"
            mdl_data += "================================="
            current_player = 1
            for index, player in enumerate(data['players']):
                # once we have the players, start printing out each of the top 10
                mdl_data += (str(current_player) + ") " + player['player_name'] + " Rating:" + str(
                    player['displayed_rating']) + "\n")
                current_player += 1

            await ctx.send(mdl_data)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Displays all Warzone ladder rankings")
    async def ladders(self, ctx):
        try:
            await ctx.send("Gathering ladder rankings data....")
            """displays the top 10 on all WL ladders"""
            ladder_pageurls = ['https://www.warzone.com/LadderSeason?ID=0', 'http://www.warzone.com/LadderSeason?ID=1',
                               'https://www.warzone.com/LadderSeason?ID=4']
            for ladder_pageurl in ladder_pageurls:
                ladder_page = urllib.request.urlopen(ladder_pageurl)
                soup = BeautifulSoup(ladder_page, 'html.parser')
                tables = soup.find_all('table')

                header_str = soup.title.string.split("-")
                for table in tables:
                    data = "__" + header_str[0].strip() + "__"
                    rows = table.find_all('tr')
                    for row in rows:
                        columns = row.find_all('td')
                        for column in columns:
                            if column.contents[0].strip() and "Rank" in column.contents[0].strip():
                                found_table = True
                                break
                            elif len(columns) == 3:
                                rating_column = columns[2]
                                team_column = columns[1]
                                data = columns[0].contents[0].strip()
                                data += ") "
                                current_link = 0
                                for link in team_column.find_all('a'):
                                    if "LadderTeam" in link.get('href'):
                                        if (link.contents[0].strip()) != "":
                                            data += link.contents[0].strip() + " "
                                        current_link += 1
                                        if (current_link > 1) and (current_link < len(columns)):
                                            data += "/ "

                                data += " Rating: " + rating_column.contents[0]
                        await ctx.send(data)
                    if found_table:
                        found_table = False
                        await ctx.send("====================================================")
                        break
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")


def setup(bot):
    bot.add_cog(Common(bot))
