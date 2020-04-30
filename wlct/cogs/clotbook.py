import discord
from wlct.models import Clan, Player, DiscordUser, DiscordChannelTournamentLink
from wlct.tournaments import Tournament, TournamentTeam, TournamentPlayer, MonthlyTemplateRotation, get_games_finished_for_team_since, find_tournaments_by_division_id, find_tournament_by_id, get_team_data_no_clan, RealTimeLadder, get_real_time_ladder, get_team_data, ClanLeague, ClanLeagueTournament, ClanLeagueDivision, TournamentGame, TournamentGameEntry
from wlct.logging import ProcessGameLog, ProcessNewGamesLog, log_exception
from discord.ext import commands
from django.conf import settings
from wlct.cogs.common import has_admin_access, is_clotadmin
from wlct.clotbook import DiscordChannelCLOTBookLink, CLOTBook, Bet, BetOdds, get_clotbook
from channels.db import database_sync_to_async

class CLOTBook(commands.Cog, name="CLOTBook"):
    def __init__(self, bot):
        self.bot = bot
        self.bets = {}

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
                if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
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
                if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                    discord_channel_link = DiscordChannelCLOTBookLink.objects.filter(channelid=ctx.message.channel.id)
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
                cb = get_clotbook()
                user = self.bot.get_user(discord_user.memberid)
                emb = self.bot.get_embed()
                emb.title = "{}'s last 10 bets".format(user.name)
                bets = Bet.objects.filter(player=player)
                total_bets = bets.count()
                bets = bets[:10]
                for bet in bets:
                    if bet.placed:
                        bet_text = "[Game]({}) - Bet {} coins, and".format(bet.game.game_link)
                        if bet.winnings == 0:
                            bet_text += "and lost bet"
                        else:
                            bet_text += "and won {} coins".format(bet.winnings)
                    else:
                        bet_text = "Bet {} coins on [Game]({})".format(bet.wager, bet.game.game_link)

                if len(bet_text) > 0:
                    emb.add_field(name="Bets", value=bet_text)

                info_text = "Total Bets: {}\nBankroll: {} coins".format(total_bets, player.bankroll)
                emb.add_field(name="Info", value=info_text)
                await ctx.send(embed=emb)

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
                    odds = BetOdds.objects.filter(game=game)
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
                            bb!bet teamid 20 - places a bet of 20 Coins on teamid
                               - e.g. bb!bet 23456 20
                            bb!bet player_name 20 - places a bet of 20 Coins on AIs team in gameid
                               - e.g. bb!bet AI 20
                            bb!bet gameid - displays all current bets for this gameid
                            
                        ''')
    async def bet(self, ctx, gameid="", team="", wager=""):
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
            if gameid == "":
                await ctx.send("You must specify a gameid with the bet command.")
                return

            elif not gameid.isnumeric():
                await ctx.send("Game {} cannot be found on the CLOT. Please enter a valid gameid.".format(gameid))
                return

            gameid = int(gameid)
            game = TournamentGame.objects.filter(pk=gameid)
            if not game:
                await ctx.send("Game {} cannot be found on the CLOT. Please enter a valid gameid.")
            # try to look up the game first, then parse the rest of the arguments
            if not game.betting_open:
                await ctx.send("Betting is closed for game {}.".format(gameid))
                return

            if not team.isnumeric():
                await ctx.send("{} is not a valid team id. Please enter a valid teamid. Betting via typing in a player's name isn't supported yet.".format(team))
                return


            if not wager.isnumeric():
                await ctx.send("{} is not a valid wager. Please enter a valid wager amount.".format(wager))
                return

            # check to see if the player has enough coins to bet
            wager = int(wager)
            if player.bankroll < wager:
                await ctx.send("You only have {} coins to bet with. Please use a smaller wager.".format(player.bankroll))
                return

            team = int(team)
            tournament_team = (TournamentTeam.objects.filter(pk=team))
            if tournament_team:
                # we have the game, tournament team and player with the wager...
                # go ahead and create the bet
                initial_odds = BetOdds.objects.filter(game=game)
                if not initial_odds:
                    await ctx.send("This is an invalid bet. Please try to use a valid game and team combination.")
                    return
                cb = get_clotbook()
                bet = cb.create_new_bet(self, wager, player, game, team)
                await ctx.send("{}, bet placed on team {} in game {} for {} coins to win {} coins.".format(
                        ctx.message.author.name, team, gameid, bet.wager, bet.winnings))
        except:
            log_exception()

def setup(bot):
    bot.add_cog(CLOTBook(bot))
