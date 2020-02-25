import discord
from wlct.models import Clan, Player
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, TournamentGame
from discord.ext import commands, tasks
from wlct.cogs.common import is_admin
from django.utils import timezone
from traceback import print_exc

class Ladders(commands.Cog, name="ladders"):
    ''' Actually sends the help command '''

    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief="Lists all real-time ladders hosted by this bot and their IDs",
             usage='''
                   109 -j : joins ladder 109
                   109 -l : leaves ladder 109
                   109 -t : displays all templates on the ladder
                   109 -p : displays all players currently on the ladder
                   109 -r : displays full ladder rankings
                   109 -g : displays all in progress games
                   109 -v templateid: vetoes a template or displays the current one if no template id is passed
                   ''')
    async def rtl(self, ctx, arg_id="invalid_id", arg_cmd="invalid_cmd", arg_cmd2="invalid_cmd2"):
        print("Arguments for RTL id: {} command: {}".format(arg_id, arg_cmd))
        invalid_cmd_text = "You've entered an invalid command. Please correct it and try again."
        retStr = ""
        do_embed = False
        do_all_channels = False
        embed_name = ""
        if arg_id != "invalid_id":
            emb = discord.Embed(color=self.bot.embed_color)
            emb.set_author(icon_url=ctx.message.author.avatar_url, name=ctx.message.author)
            emb.set_footer(text="Bot created and maintained by -B#0292")
            if arg_id.isnumeric():
                ladder = get_real_time_ladder(int(arg_id))
                discord_id = ctx.message.author.id
                if ladder is not None:
                    if arg_cmd == "-p":
                        # display current players in the ladder
                        retStr = ladder.get_current_joined()
                    elif arg_cmd == "-j":
                        retStr = ladder.join_ladder(discord_id)
                        current_joined = ladder.get_current_joined()
                        retStr += "\n\n" + current_joined + "\n"
                        await self.send_ladder_message(current_joined, False, ctx.message)
                    elif arg_cmd == "-l":
                        retStr = ladder.leave_ladder(discord_id)
                        current_joined = ladder.get_current_joined()
                        retStr += "\n\n" + current_joined + "\n"
                        await self.send_ladder_message(current_joined, False, ctx.message)
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
                        emb.title = "Current Games - Ladder {}".format(ladder.name)
                        emb.add_field(name="In Progress", value=retStr)
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
                    else:
                        retStr = invalid_cmd_text
                else:
                    retStr = "You've entered an invalid ladder ID."
            else:
                retStr = "You've entered an invalid ladder ID."
        elif arg_id == "invalid_id":
            retStr += "__**Current Real-Time Ladders**__\n"
            ladders = RealTimeLadder.objects.all()
            if not ladders or ladders.count() == 0:
                retStr += "There are no real-time ladders created yet."
            else:
                for ladder in ladders:
                    retStr += "{} | Id: {}".format(ladder.name, ladder.id)
        else:
            retStr = "You have entered an invalid command. Please correct it and try again."

        if do_embed:
            await ctx.send(embed=emb)
        else:
            await ctx.send(retStr)

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
                msg = "**New Ladder Activity**\n\n" + msg
                await rtl_channel.send(msg)

def setup(bot):
    bot.add_cog(Ladders(bot))