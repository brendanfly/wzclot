import discord
from wlct.models import Clan, Player, DiscordUser, DiscordChannelTournamentLink
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision, TournamentGame, TournamentGameEntry
from wlct.logging import ProcessGameLog, ProcessNewGamesLog, log_exception
from discord.ext import commands
from django.conf import settings
from wlct.cogs.common import has_admin_access, is_clotadmin
from wlct.clotbook import DiscordChannelCLOTBookLink, CLOTBook, Bet, BetGameOdds, get_clotbook
from channels.db import database_sync_to_async

class CLOTBook(commands.Cog, name="CLOTBook"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(brief="Turn on CLOTBook Updates for this channel",
                      usage='''
                          bb!cb on - turns ON CLOTBook updates (a lot of messages) for this channel
                          bb!cb off - turns OFF CLOTBook updates for this channel
                          bb!cb stats - displays stats for the CLOTBook
                          bb!cb me - displays CLOTBook information about you
                          bb!cb initial <game_id> - forces initial odds to be recalculated for a specific game
                      ''')
    async def cb(self, ctx, option="", arg=""):
        try:
            discord_user = await database_sync_to_async(DiscordUser.objects.filter(memberid=ctx.message.author.id))
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
                if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                    discord_channel_link = await database_sync_to_async(DiscordChannelCLOTBookLink.objects.filter(channelid=ctx.message.channel.id))
                    if discord_channel_link.count() == 0:
                        discord_channel_link = await database_sync_to_async(DiscordChannelCLOTBookLink(channelid=ctx.message.channel.id, discord_user=discord_user))
                        discord_channel_link.save()
                        await ctx.send("The CLOTBook will start using this channel to send live betting updates.")
                    else:
                        await ctx.send("This channel is already registered to receive CLOTBook Updates")
                else:
                    await ctx.send("You must be a server administrator to use this command.")
            elif option == "off":
                if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                    discord_channel_link = await database_sync_to_async(DiscordChannelCLOTBookLink.objects.filter(
                          channelid=ctx.message.channel.id))
                    if discord_channel_link:
                        discord_channel_link[0].delete()
                        await ctx.send("The CLOTBook will no longer use this channel for updates.")
                    else:
                        await ctx.send("This channel is not hooked up to receive CLOTBook updates.")
                else:
                    await ctx.send("You must be a server administrator to use this command.")
            elif option == "me":
                player = await database_sync_to_async(Player.objects.filter(discord_member=discord_user))
                if not player:
                    await ctx.send(self.bot.discord_link_text)
                    return
                player = player[0]
                cb = get_clotbook()
                await ctx.send("{}, you have {} {} left in your account.".format(player.name, player.bankroll, cb.currency_name))
            elif option == "initial":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command.")
                    return
                if arg.isnumeric():
                    game = TournamentGame.objects.filter(gameid=arg)
                    if not game:
                        game = TournamentGame.objects.filter(pk=int(arg))
                        if not game:
                            await ctx.send("You must specify a valid game id to use with this command.")
                            return
                    game = game[0]
                    odds = BetGameOdds.objects.filter(game=game)
                    for odd in odds:
                        odd.delete()
                    game.create_initial_lines()
                    await ctx.send("Updated initial lines for game {}".format(game.gameid))
                    return
            else:
                await ctx.send("You must specify an option with this command.")
        except:
            log_exception()

    @commands.command(brief="Place your wagers, and view existing bets on the CLOTBook",
                      usage='''
                            bb!bet gameid teamid 20 - places a bet of 20 Coins on teamid in gameid
                               - e.g. bb!bet 5346 23456 20
                            bb!bet 5346 player_name 20 - places a bet of 20 Coins on AIs team in gameid
                               - e.g. bb!bet 5346 AI 20
                            bb!bet gameid - displays all current bets for this gameid
                            
                        ''')
    async def bet(self, ctx, option="", option2="", option3=""):
        try:
            discord_user = DiscordUser.objects.filter(memberid=ctx.message.author.id)
            if not discord_user:
                print("No discord user present...creating one")
                discord_user = DiscordUser(memberid=ctx.message.author.id)
                discord_user.save()
            else:
                print("Found a discord user...using that")
                discord_user = discord_user[0]

            player = Player.objects.filter(discord_member=discord_user)
            if not player:
                print("Could not find player {} in the database with discord_user.id {}".format(ctx.message.author.name, ctx.message.author.id))
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
