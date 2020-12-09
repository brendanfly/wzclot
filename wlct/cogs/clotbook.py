import discord
from wlct.logging import ProcessGameLog, ProcessNewGamesLog, log_exception
from discord.ext import commands
from django.conf import settings
from wlct.cogs.common import has_admin_access, is_clotadmin
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
                          bb!cb <game_id> - displays all bets for game_id
                      ''')
    async def cb(self, ctx, option="", arg="", coins=""):
        try:
            discord_user = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)
            if not discord_user:
                await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)
            else:
                discord_user = discord_user[0]

            if option == "":
                await ctx.send("You must specify an option with this command.")
                return

            if option == "stats":
                await ctx.send("This command is currently under construction.")
            elif option == "on":
                if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                    if arg == "results":
                        # create a link for results only
                        discord_channel_link = await self.bot.bridge.getDiscordChannelClotBookLinks(
                            channelid=ctx.message.channel.id, results_only=True)
                        if len(discord_channel_link.count) > 0:
                            await ctx.send("There is already a CLOTBook results link to this channel.")
                            return
                        await self.bot.bridge.createChannelClotbookLink(channelid=ctx.message.channel.id,
                                                                          discord_user=discord_user,
                                                                          results_only=True)
                        await ctx.send("The CLOTBook will start using this channel to send live betting results.")
                    else:
                        discord_channel_link = await self.bot.bridge.getDiscordChannelClotBookLinks(channelid=ctx.message.channel.id, results_only=True)
                        if len(discord_channel_link.count) == 0:
                            await self.bot.bridge.createChannelClotbookLink(channelid=ctx.message.channel.id, discord_user=discord_user)
                            await ctx.send("The CLOTBook will start using this channel to send live betting updates.")
                        else:
                            await ctx.send("This channel is already registered to receive CLOTBook Updates")
                else:
                    await ctx.send("You must be a server administrator to use this command.")
            elif option == "off":
                if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                    if arg == "results":
                        discord_channel_link = await self.bot.bridge.getDiscordChannelClotBookLinks(channelid=ctx.message.channel.id, results_only=True)
                        if discord_channel_link:
                            await self.bot.bridge.deleteObject(discord_channel_link[0])
                            await ctx.send("The CLOTBook will no longer use this channel for sending results.")
                        else:
                            await ctx.send("This channel is not hooked up to receive CLOTBook updates.")
                    else:
                        discord_channel_link = await self.bot.bridge.getDiscordChannelClotBookLinks(channelid=ctx.message.channel.id, results_only=False)
                        if discord_channel_link:
                            await self.bot.bridge.deleteObject(discord_channel_link[0])
                            await ctx.send("The CLOTBook will no longer use this channel for updates.")
                        else:
                            await ctx.send("This channel is not hooked up to receive CLOTBook updates.")
                else:
                    await ctx.send("You must be a server administrator to use this command.")
            elif option == "me":
                player = await self.bot.bridge.getPlayers(discord_member=discord_user)
                if not player:
                    await ctx.send(self.bot.discord_link_text)
                    return
                player = player[0]
                user = self.bot.get_user(discord_user.memberid)
                emb = self.bot.get_embed(user)
                emb.title = "{}'s last 10 bets".format(user.name)
                bets = await self.bot.bridge.getBetsOrderByCreatedTime(player=player)
                total_bets = len(bets)
                bets = bets[:10]
                bet_text = ""
                for bet in bets:
                    if bet.game.is_finished:
                        bet_text += "[Game Link]({}) - Bet {} coins, ".format(bet.game.game_link, bet.wager)
                        if bet.winnings == 0:
                            bet_text += "and lost bet\n"
                        else:
                            bet_text += "and won {} coins\n".format(bet.winnings)
                    else:
                        bet_text += "Bet {} coins on [Game]({}) to win {}\n".format(bet.wager, bet.game.game_link, bet.winnings)

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
                    game = await self.bot.bridge.getGames(gameid=arg)
                    if not len(game):
                        game = await self.bot.bridge.getGames(pk=int(arg))
                        if not len(game):
                            await ctx.send("You must specify a valid game id to use with this command.")
                            return
                    game = game[0]

                    odds = await self.bot.bridge.getBetGameOdds(game=game)
                    for odd in odds:
                        odd.delete()
                    game.create_initial_lines()
                    await ctx.send("Updated initial lines for game {}".format(game.gameid))
                    return
            elif option == "br":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command.")
                    return
                player = await self.bot.bridge.getPlayers(token=arg)
                if not len(player):
                    await ctx.send("Player with token {} cannot be found in the CLOT database.")
                    return
                if coins.isnumeric():
                    player[0].bankroll += float(coins)
                    player[0].save()

            elif option.isnumeric():
                # try to look up the game id
                game = int(option)
            else:
                await ctx.send("You must specify an option with this command.")
        except:
            log_exception()

    @commands.command(brief="Place your wagers, and view existing bets on the CLOTBook",
                      usage='''
                            bb!bet betid 20 - places a bet of 20 Coins on teamid
                               - e.g. bb!bet 23456 20
                            bb!bet player_name 20 - places a bet of 20 Coins on AIs team in betid
                               - e.g. bb!bet AI 20
                        ''')
    async def bet(self, ctx, team="", wager=""):
        try:
            discord_user = await self.bot.bridge.getdiscordUsers(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)
            else:
                discord_user = discord_user[0]

            player = await self.bot.bridge.getPlayers(discord_member=discord_user)
            if not len(player):
                await ctx.send(self.bot.discord_link_text)
                return

            player = player[0]
            if not team.isnumeric():
                await ctx.send("{} is not a valid team id. Please enter a valid teamid. Betting via typing in a player's name isn't supported yet.".format(team))
                return

            team = int(team)
            team_odds = await self.bot.bridge.getBetTeamOdds(pk=team)
            if not len(team_odds):
                await ctx.send("{} is not a valid bet id.".format(team))
                return

            team_odds = team_odds[0]
            if not wager.isnumeric() or int(wager) < 1:
                await ctx.send("{} is not a valid wager. Please enter a valid wager amount.".format(wager))
                return

            # check to see if the player has enough coins to bet
            wager = int(wager)
            if player.bankroll < wager:
                await ctx.send("You only have {} coins to bet with. Please use a smaller wager.".format(player.bankroll))
                return

            if not team_odds.bet_game.game.betting_open:
                await ctx.send("Betting is no longer open for game {}.".format(team_odds.bet_game.gameid))
                return

            for players_team in team_odds.bet_game.players.split('-'):
                for token in players_team.split('.'):
                    if player.token == token:
                        await ctx.send("You cannot bet on a game you are playing in. Please choose a different bet.")
                        return

            # we have the game, tournament team and player with the wager...
            # go ahead and create the bet
            cb = await self.bot.bridge.getCLOTBook()
            if cb.calculate_decimal_odds_winnings(team_odds.decimal_odds, wager) < 1:
                await ctx.send("You must bet enough to win at least 1 coin. Please enter a different wager amount.")
                return

            bet = cb.create_new_bet(wager, player, team_odds)
            team_players = await self.bot.bridge.get_team_data_no_clan_player_list(team_odds.players.split('.'))
            await ctx.send("{} placed a bet on {} in game {} for {} coins to win {} coins.".format(
                    ctx.message.author.name, team_players, team_odds.bet_game.game.id, bet.wager, bet.winnings))
        except:
            log_exception()

def setup(bot):
    bot.add_cog(CLOTBook(bot))
