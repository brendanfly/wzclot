import discord
from discord.ext import commands, tasks
from wlct.cogs.common import is_tournament_creator, embed_list_special_delimiter
from django.utils import timezone
from traceback import print_exc
from wlct.cogs.clotbridge import RealTimeLadderBridge



class Ladders(commands.Cog, name="ladders"):
    ''' Actually sends the help command '''

    def __init__(self, bot):
        self.bot = bot

    async def ladder_command(self, ctx, ladder, cmd, option):
        invalid_cmd_text = "You've entered an invalid command. bb!rtl no longer takes in a ladder id. Please see ``bb!help rtl`` for an updated list of commands."
        emb = discord.Embed(color=self.bot.embed_color)
        emb.set_author(icon_url=ctx.message.author.avatar_url, name=ctx.message.author)
        emb.set_footer(text="Bot created and maintained by -B#0292")
        do_embed = False
        discord_id = ctx.message.author.id

        ladder = RealTimeLadderBridge(ladder)  # use a ladder bridge for the db functions

        teams = ladder.get_active_team_count()
        await self.bot.bridge.log_bot_msg("Command: {}  Option: {} issued for ladder {}".format(cmd, option, ladder.id))
        if cmd == "-p":
            # display current players in the ladder
            retStr = ladder.get_current_joined()
        elif cmd == "-j":
            retStr = ladder.join_ladder(discord_id, False)
            current_joined = ladder.get_current_joined()
            retStr += "\n\n" + current_joined + "\n"
            await self.bot.bridge.log_bot_msg("[Ladder {}]: User {} has joined the RTL. New team count: {}".format(ladder.id, ctx.message.author.name, teams))
            if teams != ladder.get_active_team_count():
                await self.send_ladder_message(current_joined, ladder, False, ctx.message)
        elif cmd == "-jl":
            retStr = ladder.join_ladder(discord_id, True) + " (You will be removed once a game is created)"
            current_joined = ladder.get_current_joined()
            retStr += "\n\n" + current_joined + "\n"
            await self.bot.bridge.log_bot_msg("[Ladder {}]: User {} has joined the RTL for one game. New Team count: {}".format(ladder.id, ctx.message.author.name, teams))
            if teams != ladder.get_active_team_count():
                await self.send_ladder_message(current_joined, ladder, False, ctx.message)
        elif cmd == "-l":
            retStr = ladder.leave_ladder(discord_id)
            current_joined = ladder.get_current_joined()
            await self.bot.bridge.log_bot_msg("[Ladder {}]: User {} has left the RTL. New Team count: {}".format(ladder.id, ctx.message.author.name, teams))
            retStr += "\n\n" + current_joined + "\n"
            if not ladder.get_active_team_count():
                await self.send_ladder_message(current_joined, ladder, False, ctx.message)
        elif cmd == "-t":
            retStr = ladder.get_current_templates()
            do_embed = True
            emb.title = "Current Templates - Ladder {}".format(ladder.name)
            self.bot.embed_list(emb, "Templates", retStr.split(embed_list_special_delimiter()))
        elif cmd == "-r":
            if option == "invalid_option":
                option = "1"
            retStr = ladder.get_current_rankings(option)
        elif cmd == "-g":
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
        elif cmd == "-v":
            if option != "invalid_option":
                retStr = ladder.veto_template(discord_id, option, False)
                await self.bot.bridge.log_bot_msg("[Ladder {}]: User {} has vetoed template with id: {}".format(ladder.id, ctx.message.author.name, option))
            else:
                # display the users current veto
                retStr = ladder.get_current_vetoes(discord_id)
        elif cmd == "-vr":
            if option != "invalid_option":
                retStr = ladder.veto_template(discord_id, option, True)
                await self.bot.bridge.log_bot_msg("[Ladder {}]: User {} has vetoed template with id: {}".format(ladder.id, ctx.message.author.name, option))
            else:
                # display the users current veto
                retStr = ladder.get_current_vetoes(discord_id)
        elif cmd == "-ta":
            if option != "invalid_option":
                # check to make sure the author has access here
                if await is_tournament_creator(ctx.message.author.id, ladder):
                    await self.bot.bridge.log_bot_msg("[Ladder {}]: User {} has added template with id: {}".format(ladder.id, ctx.message.author.name, option))
                    retStr = ladder.add_template(option)
                else:
                    retStr = "Only the tournament creator can use this command."
            else:
                retStr = invalid_cmd_text
        elif cmd == "-tr":
            if option != "invalid_option":
                # check for access
                if await is_tournament_creator(discord_id, ladder):
                    retStr = ladder.remove_template(option)
                else:
                    retStr = "Only the tournament creator can use this command."
            else:
                retStr = invalid_cmd_text
        elif cmd == "-tv":
            if option != "invalid_option":
                if await is_tournament_creator(discord_id, ladder):
                    if option.isnumeric():
                        vetoes = int(option)
                        ladder.update_max_vetoes(vetoes)
                        retStr = "Updated {} # of vetoes to {} per team.".format(ladder.name, vetoes)
                    else:
                        retStr = "Please enter a valid # for updating veto count"
                else:
                    retStr = "Only the tournament creator can use this command."
            else:
                retStr = "Current total vetoes per team: {}.".format(ladder.max_vetoes)
        elif cmd == "-me":
            # me data returns a tuple of information
            # first is what rank/position you are
            # second is your last 10 games
            me_data = ladder.get_player_data(discord_id)
            if me_data[0]:  # success
                retStr = me_data[1]
                emb.title = "{} Ladder Stats".format(ladder.name)
                emb.add_field(name="Performance", value=retStr)
                do_embed = True
            else:
                # error
                retStr = me_data[1]
        else:
            retStr = invalid_cmd_text


        if do_embed:
             await ctx.send(embed=emb)
        else:
             await ctx.send(retStr)


    @commands.command(brief="Hosts a variety of commands for the 1v1 Real-Time Bot Ladder",
                   usage='''
                   -j : joins the 1v1 ladder
                   -l : leaves the 1v1 real-time ladder
                   -jl : joins the 1v1 real-time ladder for a single game
                   -t : displays all templates on the 1v1 real-time ladder
                   -p : displays all players currently on the 1v1 real-time ladder
                   -r : displays full ladder rankings
                   -g : displays all in progress games on the 1v1 real-time ladder
                   -v <templateid>: vetoes a template or displays the current one if no template id is passed
                   -me : displays information about yourself on the ladder
                   
                   Admin Commands - only creators of the ladder can add/remove templates
                   -ta <templateid>: adds a template to the ladder
                   -tr <templateid> : removes a template from the ladder
                   ''')
    async def rtl(self, ctx, cmd="invalid_cmd", option="invalid_option"):
        try:
            ladder = await self.bot.bridge.getRealTimeLadder(109)
            if ladder is not None:
                await self.ladder_command(ctx, ladder, cmd, option)
            else:
                await ctx.send("Real-time Ladder cannot be found. Please contact -B.")
        except:
            await self.bot.bridge.log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    @commands.command(brief="Hosts a variety of commands for the 1v1 Real-Time INSS Ladder",
                      usage='''
                     -j : joins the 1v1 Real-Time INSS ladder
                     -l : leaves the 1v1 Real-Time INSS ladder
                     -jl : joins the 1v1 Real-Time INSS ladder for a single game
                     -t : displays all templates on the 1v1 Real-Time INSS ladder
                     -p : displays all players currently on the 1v1 Real-Time INSS ladder
                     -r : displays full ladder rankings
                     -g : displays all in progress games on the 1v1 Real-Time INSS ladder
                     -v <templateid>: vetoes a template or displays the current one if no template id is passed
                     -me : displays information about yourself on the ladder
                     
                     Admin Commands - only creators of the ladder can add/remove templates
                     -ta <templateid>: adds a template to the ladder
                     -tr <templateid> : removes a template from the ladder
                     ''')
    async def rtl_inss(self, ctx, cmd="invalid_cmd", option="invalid_option"):
        try:
            ladder = await self.bot.bridge.get_real_time_ladder(167)
            if ladder is not None:
                await self.ladder_command(ctx, ladder, cmd, option)
            else:
                await ctx.send("Real-time Ladder cannot be found. Please contact -B.")
        except:
            await self.bot.bridge.log_exception()
            await ctx.send("An error has occurred and was unable to process the command.")

    '''
    Sends updates to guilds that are not guild_original_msg.
    This is mainly used to communicate people are doing things with the ladder across servers. 
    '''
    async def send_ladder_message(self, msg, ladder, is_embed, guild_original_msg):
        # loop through all rtl linked channels sending the appropriate message to all servers
        processed_channels = []
        channels = await self.bot.bridge.getChannelTournamentLinks(tournament=ladder)
        if channels and channels.count() > 0:
            await self.bot.bridge.log_bot_msg("Found {} channels to send RTL messages to.".format(channels.count()))
        for rtl_channel in channels:
            channel = self.bot.get_channel(rtl_channel.channelid)
            if rtl_channel.id in processed_channels:
                if guild_original_msg:
                    await self.bot.bridge.log_bot_msg(
                        "Found duplicate cached RTL guild with id {} for original msg id {}".format(guild_original_msg.guild.id, guild_original_msg.id))
                continue
            processed_channels.append(rtl_channel.id)
            if guild_original_msg:
                await self.bot.bridge.log_bot_msg("Server id to send RTL message to: {}, server original message with msg id {} came from: {}".format(channel.guild.id,  guild_original_msg.id, guild_original_msg.guild.id))
            if guild_original_msg and channel.guild.id == guild_original_msg.guild.id:
                # skip this one, it came from here
                continue
            try:
                if is_embed:
                    await channel.send(embed=msg)
                else:
                    await channel.send(msg)
            except:
                await self.bot.bridge.log_exception()
                await self.bot.bridge.log_bot_msg("Failed while sending msg to channel: {}".format(channel.name))

def setup(bot):
    bot.add_cog(Ladders(bot))