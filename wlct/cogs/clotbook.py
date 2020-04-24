import discord
from wlct.models import Clan, Player, DiscordUser, DiscordChannelTournamentLink
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision, TournamentGame, TournamentGameEntry
from wlct.logging import ProcessGameLog, ProcessNewGamesLog, log_exception
from discord.ext import commands
from django.conf import settings
from wlct.cogs.common import has_admin_access, is_admin
from wlct.clotbook import DiscordChannelCLOTBookLink, CLOTBook, Bet, BetOdds

class CLOTBook(commands.Cog, name="CLOTBook"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief="Turn on CLOTBook Updates for this channel",
                      usage='''
                          bb!cb on - turns ON CLOTBook updates (a lot of messages) for this channel
                          bb!cb off - turns OFF CLOTBook updates for this channel
                          bb!cb stats - displays stats for the CLOTBook
                          bb!cb me - displays CLOTBook information about you
                      ''')
    async def cb(self, ctx, option=""):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()
            else:
                discord_user = discord_user[0]

            if option == "":
                await ctx.send("You must specify an option with this command.")
                return

            if option == "stats":
                await ctx.send("This command is currently under construction.")
            elif option == "on":
                if ctx.message.author.guild_permissions.administrator or is_admin(ctx.message.author.id):
                    discord_channel_link = DiscordChannelCLOTBookLink.objects.filter(channelid=ctx.message.channel.id)
                    if discord_channel_link.count() == 0:
                        discord_channel_link = DiscordChannelCLOTBookLink(channelid=ctx.message.channel.id, discord_user=discord_user)
                        discord_channel_link.save()
                        await ctx.send("The CLOTBook will start using this channel to send live betting updates.")
                    else:
                        await ctx.send("This channel is already registered to receive CLOTBook Updates")
                else:
                    await ctx.send("You must be a server administrator to use this command.")
            elif option == "off":
                if ctx.message.author.guild_permissions.administrator or is_admin(ctx.message.author.id):
                    discord_channel_link = DiscordChannelCLOTBookLink.objects.filter(
                          channelid=ctx.message.channel.id)
                    if discord_channel_link:
                        discord_channel_link[0].delete()
                        await ctx.send("The CLOTBook will no longer use this channel for updates.")
                    else:
                        await ctx.send("This channel is not hooked up to receive CLOTBook updates.")
                else:
                    await ctx.send("You must be a server administrator to use this command.")
            elif option == "me":
                player = Player.objects.filter(discord_member=discord_user)
                if not player:
                    await ctx.send(self.bot.discord_link_text)
                    return
                player = player[0]
                await ctx.send("{}, you have {} Nohams lef in your account.".format(player.name, player.bankroll))
            else:
                await ctx.send("You must specify an option with this command.")
        except:
            log_exception()

    @commands.command(brief="Place your wagers, and view existing bets on the CLOTBook",
                      usage='''
                            bb!bet gameid teamid 20 - places a bet of 20 Nohams on teamid in gameid
                               - e.g. bb!bet 256783 5346 20  
                            bb!bet gameid - displays all current bets for this gameid
                        ''')
    async def bet(self, ctx, option="", option2="", option3=""):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()
            else:
                discord_user = discord_user[0]

            player = Player.objects.filter(discord_member=discord_user)
            if not player:
                await ctx.send(self.bot.discord_link_text)
                return

            player = player[0]
            if option == "":
                await ctx.send("You must specify an option with the bet command.")
                return
            elif option.isnumeric():
                # try to look up the game first, then parse the rest of the arguments
                gameid = int(option)
                game = TournamentGame.objects.filter(gameid=gameid)
                if not game:
                    await ctx.send("That game cannot be found on the CLOT. Please enter a valid gameid.")
                    return



        except:
            log_exception()



def setup(bot):
    bot.add_cog(CLOTBook(bot))
