import discord
from wlct.models import Clan, Player
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, TournamentGame
from wlct.logging import log_exception
from discord.ext import commands, tasks
from wlct.cogs.common import is_admin
from django.utils import timezone
from traceback import print_exc

class Ladders(commands.Cog, name="ladders"):
    ''' Actually sends the help command '''

    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief="Hosts a variety of commands for the 1v1 Real-Time Bot Ladder",
             usage='''
                   -j : joins the 1v1 ladder
                   -l : leaves the 1v1 real-time ladder
                   -jl : joins the 1v1 real-time ladder for single game
                   -t : displays all templates on the 1v1 real-time ladder
                   -p : displays all players currently on the 1v1 real-time ladder
                   -r : displays full ladder rankings
                   -g : displays all in progress games on the 1v1 real-time ladder
                   -v <templateid>: vetoes a template or displays the current one if no template id is passed
                   -me : displays information about yourself on the ladder
                   ''')

    async def rtl(self, ctx, arg_cmd="invalid_cmd", arg_cmd2="invalid_cmd2"):
        try:
            invalid_cmd_text = "You've entered an invalid command. bb!rtl no longer takes in a ladder id. Please see ``bb!help rtl`` for an updated list of commands."
            retStr = ""
            do_embed = False
            do_all_channels = False
            embed_name = ""
            emb = discord.Embed(color=self.bot.embed_color)
            emb.set_author(icon_url=ctx.message.author.avatar_url, name=ctx.message.author)
            emb.set_footer(text="Bot created and maintained by -B#0292")
            ladder = get_real_time_ladder(109)
            discord_id = ctx.message.author.id
            if ladder is not None:
                teams = ladder.get_active_team_count()
                if arg_cmd == "-p":
                    # display current players in the ladder
                    retStr = ladder.get_current_joined()
                elif arg_cmd == "-j":
                    retStr = ladder.join_ladder(discord_id, False)
                    current_joined = ladder.get_current_joined()
                    retStr += "\n\n" + current_joined + "\n"
                    if teams != ladder.get_active_team_count():
                        await self.send_ladder_message(current_joined, False, ctx.message)
                elif arg_cmd == "-jl":
                    retStr = ladder.join_ladder(discord_id, True) + " (You will be removed once a game is created)"
                    current_joined = ladder.get_current_joined()
                    retStr += "\n\n" + current_joined + "\n"
                    if teams != ladder.get_active_team_count():
                        await self.send_ladder_message(current_joined, False, ctx.message)
                elif arg_cmd == "-l":
                    retStr = ladder.leave_ladder(discord_id)
                    current_joined = ladder.get_current_joined()
                    retStr += "\n\n" + current_joined + "\n"
                elif arg_cmd == "-t":
                    retStr = ladder.get_current_templates()
                    do_embed = True
                    emb.title = "Current Templates - Ladder {}".format(ladder.name)
                    emb.add_field(name="Templates", value=retStr)
                elif arg_cmd == "-r":
                    retStr = ladder.get_current_rankings()
                elif arg_cmd == "-g":
                    do_embed = True
                    retStr = ladder.get_current_games()
                    if not retStr[0]:
                        do_embed = False
                        retStr = retStr[1]
                    else:
                        game_data = retStr[1][0]
                        finished_game_data = retStr[1][1]
                        emb.title = "Games - Ladder {}".format(ladder.name)
                        if len(game_data) > 0:
                            emb.add_field(name="In Progress", value=game_data)
                        if len(finished_game_data) > 0:
                            emb.add_field(name="Last 10 games", value=finished_game_data)
                elif arg_cmd == "-v":
                    if arg_cmd2 != "invalid_cmd2":
                        retStr = ladder.veto_template(discord_id, arg_cmd2)
                    else:
                        # display the users current veto
                        retStr = ladder.get_current_vetoes(discord_id)
                elif arg_cmd == "-ta":
                    if arg_cmd2 != "invalid_cmd2":
                        # check to make sure the author has access here
                        if is_admin(ctx.message.author.id):
                            retStr = ladder.add_template(arg_cmd2)
                    else:
                        retStr = invalid_cmd_text
                elif arg_cmd == "-tr":
                    if arg_cmd2 != "invalid_cmd2":
                        # check for access
                        if is_admin(ctx.message.author.id):
                            retStr = ladder.remove_template(arg_cmd2)
                    else:
                        retStr = invalid_cmd_text
                elif arg_cmd == "-me":
                    # me data returns a tuple of information
                    # first is what rank/position you are
                    # second is your last 10 games
                    me_data =  ladder.get_player_data(discord_id)
                    if me_data[0]: # success
                        retStr = me_data[1]
                        print("Me Data".format(retStr))
                        emb.title = "Ladder Stats".format(ladder.name)
                        emb.add_field(name="Performance", value=retStr)
                        do_embed = True
                    else:
                        # error
                        retStr = me_data[1]
                else:
                    retStr = invalid_cmd_text
            else:
                retStr = "Real-time Ladder cannot be found. Please contact -B."

            if do_embed:
                 await ctx.send(embed=emb)
            else:
                 await ctx.send(retStr)
        except:
            log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    '''
    Sends updates to guilds that are not guild_original_msg.
    This is mainly used to communicate people are doing things with the ladder across servers. 
    '''
    async def send_ladder_message(self, msg, is_embed, guild_original_msg):
        # loop through all rtl channels sending the appropriate message
        for rtl_channel in self.bot.rtl_channels:
            print("Server id to send message to: {}, server original message came from: {}".format(rtl_channel.guild.id, guild_original_msg.guild.id))
            if rtl_channel.guild.id == guild_original_msg.guild.id:
                # skip this one, it came from here
                continue
            if is_embed:
                await rtl_channel.send(embed=msg)
            else:
                await rtl_channel.send(msg)

def setup(bot):
    bot.add_cog(Ladders(bot))