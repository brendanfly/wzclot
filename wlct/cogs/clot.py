import traceback

import discord
from discord.ext import commands
from wlct.api import API
from wlct.cogs.common import is_clotadmin, has_tournament_admin_access
from wlct.logging import ProcessGameLog, ProcessNewGamesLog
from channels.db import database_sync_to_async

class PlayerStats:
    def __init__(self, wins, losses, tournaments, games, win_pct, rating):
        self.wins = wins
        self.losses = losses
        self.tournaments = tournaments
        self.games = games
        self.win_pct = win_pct
        self.rating = rating

class Clot(commands.Cog, name="clot"):
    def __init__(self, bot):
        self.bot = bot

    async def get_player_stats(self, token):
        # return a tuple of all the player stats
        # this tuple will be (Success, Wins, Losses, Tournaments Played In, Games Played In, Win %)
        # first, grab the player
        if token == 0:
            return False, None
        player = await self.bot.bridge.getPlayers(token=token)
        if len(player):
            player = player[0]
            wins = player.wins
            losses = player.losses
            rating = player.rating
            tpi = 0
            gpi = 0
            tplayer = await self.bot.bridge.getTournamentPlayers(player=player)
            for p in tplayer:
                tpi += 1
                games = await self.bot.bridge.getTournamentGameEntries(team=p.team_id)
                gpi += len(games)
            win_pct = 0
            if wins + losses != 0:
                win_pct = (wins / (wins + losses)) * 100
                win_pct = round(win_pct, 2)
            return True, PlayerStats(wins, losses, tpi, gpi, win_pct, rating)
        else:
            return False, None

    @commands.command(brief="View CLOT statistics",
                      usage='''
                          bb!stats clot - shows overall CLOT stats
                          bb!stats me - shows your personal stats
                          bb!stats token - shows the users CLOT stats based on Warzone token
                          bb!stats discord_name - shows the CLOT stats for a player matching that discord name
                      ''')
    async def stats(self, ctx, option=""):
        try:
            if option == "clot":
                emb = self.bot.get_default_embed()
                # grab total tournaments + games + players
                p = await self.bot.bridge.getPlayersAll()
                emb.add_field(name="# of Players", value="{}".format(len(p)))
                t = await self.bot.bridge.getTournamentsAll()
                emb.add_field(name="# of Tournaments Created", value="{}".format(len(t)))
                g = await self.bot.bridge.getGamesAll()
                emb.add_field(name="# of Games Played", value="{}".format(len(g)))
                await ctx.send(embed=emb)
            elif option == "me" or option.isnumeric() or option != "":
                token = 0
                discord_user = None
                if option == "me":
                    discord_user = ctx.message.author
                    discord_user_id = discord_user.id
                    player = await self.bot.bridge.getPlayers(discord_member__memberid=discord_user_id)
                    if len(player):
                        token = player[0].token
                elif option.isnumeric():
                    # try to lookup the player by token
                    print("Option is numeric, using it as the token")
                    token = option
                else:
                    await ctx.send("bb!stats <player name> is currently under construction")
                    return
                    '''players = Player.objects.filter(name__istartswith=option)
                    message = await ctx.send("Searching all players I've seen for {}".format(option))
                    original_text = message.content
                    await self.bot.update_progress(message, original_text, 0.0)

                    users = self.bot.users
                    num_users = len(users)
                    step = 100.0 / num_users
                    current_step = step
                    for user in users:
                        user_name = user.name.lower()
                        if option in user_name:
                            discord_user = user
                            discord_user_id = discord_user.id
                            break
                        current_step += step
                        await self.bot.update_progress(message, original_text, round(current_step, 2))
                    await self.bot.update_progress(message, original_text, 100.0)'''

                stats = await self.get_player_stats(token)
                if stats[0]:
                    # success
                    pstats = stats[1]
                    if discord_user:
                        emb = self.bot.get_embed(discord_user)
                    else:
                        emb = self.bot.get_default_embed()
                    emb.add_field(name="CLOT Rating", value="{}".format(pstats.rating))
                    emb.add_field(name="Overall Record", value="{}-{}".format(pstats.wins, pstats.losses))
                    emb.add_field(name="Winning %", value="{}".format(pstats.win_pct))
                    emb.add_field(name="Tournaments Played In", value="{}".format(pstats.tournaments))
                    emb.add_field(name="Games Played In", value="{}".format(pstats.games))
                    await ctx.send(embed=emb)
                else:
                    await ctx.send(self.bot.discord_link_text_user)
            else:
                await ctx.send("You must enter a valid option to the command. Use ``bb!help stats`` to see options.")
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Admin commands to manage and debug CLOT",
                      usage='''
                          bb!admin logs -pg <gameid> - shows last 2 ProcessGame logs for game
                          bb!admin logs -png <tournamentid> - shows last 2 ProcessNewGame logs for tournament
                          bb!admin logs -tt <teamid> - list players a part of the tournament team
                          bb!admin logs -debug on - turns on debug 
                          bb!admin mtc -p - shows current players on the MTC
                          bb!admin mtc -r <player_token> - removes player from MTC using wz token
                          bb!admin rtl -p - shows current players on the RTL
                          bb!admin rtl -r <discord_id> - removes player from RTL using Discord ID
                          bb!admin cache <tournament_id> - forcibly runs the cache on a tournament
                          bb!admin update_clan <clan_id> - forcibly update player clans in specified clan
                          bb!admin add <player_token> <tournament_id> - adds this player as an admin for the tournament
                          bb!admin create_game <tournament_id> <round_number> <game_data> - creates a game with the game data in the specified round number
                          bb!admin delete_game <game_id> - deletes a game from the clot and warzone if possible
                          bb!admin sub <tournament_id> <new_player_id> <old_player_id> - subs the new player in place of the old player for specified tournament
                          bb!admin tournament_keys <tournament_id> - grabs tournament and team IDs for CL tournament
                          ''',
                      category="clot")
    async def admin(self, ctx, cmd="", option="", arg="", arg2=""):
        try:
            if cmd == "logs":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command.")
                    return
                if option == "-pg":
                    if arg:
                        game = await self.bot.bridge.getGames(gameid=arg)
                        if game:
                            game_logs = await self.bot.bridge.getProcessGameLogsLast2(game=game[0])
                            if game_logs:
                                await self.send_log_message(ctx, "process game", game_logs)
                            else:
                                await ctx.send("No process game logs were found with that game id")
                        else:
                            await ctx.send("Unable to find game with id: {}".format(arg))
                    else:
                        await ctx.send("Please enter a valid game id")
                elif option == "-png":
                    if arg and arg.isnumeric():
                        tournament = await self.bot.bridge.getTournaments(id=int(arg))
                        if len(tournament):
                            new_game_logs = await self.bot.brige.getProcessNewGameLogsLast2(tournament=tournament[0])
                            if len(new_game_logs):
                                await self.send_log_message(ctx, "process new game", new_game_logs)
                            else:
                                await ctx.send("No process new game logs were found with that tournament id")
                        else:
                            await ctx.send("Unable to find tournament with id: {}. Use ``bb!admin tournaments`` to see ids".format(arg))
                    else:
                        await ctx.send("Please enter a valid tournament id. Use the ``bb!tournaments`` command to see ids")
                elif option == "-tt":
                    if not is_clotadmin(ctx.message.author.id):
                        await ctx.send("Only CLOT admins can use this command.")
                        return
                    if arg and arg.isnumeric():
                        tt = await self.bot.bridge.getTournamentTeams(id=int(arg))
                        if len(tt):
                            tt = tt[0]
                            players = await self.bot.bridge.getTournamentPlayers(team=tt)
                            team_name_list = []
                            for player in players:
                                team_name_list.append(player.player.name)
                            team_str = ", ".join(team_name_list)
                            await ctx.send("Team {}\n{}\n{}".format(arg, team_str, tt.tournament.name))
                        else:
                            await ctx.send("Unable to find team with id: {}".format(arg))
                    else:
                        await ctx.send("Please enter a valid tournament team id")
                elif option == "-debug":
                    if not is_clotadmin(ctx.message.author.id):
                        await ctx.send("Only CLOT admins can use this command")
                        return
                    if arg == "on":
                        self.bot.enable_debug_print = True
                        await ctx.send("Debug print has been turned on")
                    elif arg == "off":
                        self.bot.enable_debug_print = False
                        await ctx.send("Debug print has been turned off")
                    else:
                        await ctx.send("Please enter a valid switch (on, off)")
                else:
                    await ctx.send("Please enter a valid option (-pg, )")
            elif cmd == "mtc":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only MTC admins can use this command.")
                    return
                mtc = await self.bot.bridge.getMonthlyTemplateRotations(id=22)
                if len(mtc):
                    mtc = mtc[0]
                    if option == "-p":
                        tplayers = await self.bot.bridge.getTournamentPlayers(tournament=mtc)
                        if len(tplayers):
                            player_data = "Current Players on the MTC:\n"
                            for tplayer in tplayers:
                                if tplayer.team.active:
                                    player_data += "{} | Id: {}\n".format(tplayer.player.name,
                                                                                  tplayer.player.token)
                            await ctx.send(player_data)
                        else:
                            await ctx.send("Currently there are no players on the MTC")
                    elif option == "-r":
                        if arg:
                            try:
                                mtc.decline_tournament(arg)
                                await ctx.send("Successfully removed player from MTC with id: {}".format(arg))
                            except:
                                await ctx.send("Unable to remove player from MTC with id: {}".format(arg))
                        else:
                            ctx.send("Please enter a valid token. Use ``bb!admin mtc -p`` to see current players.")
                    else:
                        await ctx.send("Please enter a valid option (-p or -r)")
                else:
                    await ctx.send("MTC with id {} is invalid. Please enter a valid MTC league id.".format(22))
            elif cmd == "rtl":
                rtl = await self.bot.bridge.getRealTimeLadders(id=109)[0]
                if not await has_tournament_admin_access(ctx.message.author.id, rtl):
                    await ctx.send("Only RTL admins can use this command.")
                    return
                if option == "-p":
                    tplayers = self.bot.bridge.getTournamentPlayers(tournament=rtl, team__active=True)
                    if len(tplayers):
                        player_data = "Current Players on the RTL:\n"
                        for tplayer in tplayers:
                            player_data += "{} | Discord Id: {}\n".format(tplayer.player.name, tplayer.player.discord_member.memberid)
                        await ctx.send(player_data)
                    else:
                        await ctx.send("Currently there are no players on the RTL")
                elif option == "-r":
                    if arg:
                        try:
                            await self.bot.bridge.removeRealTimeLadderPlayer(rtl, arg)
                            await ctx.send("Successfully removed player from RTL with id: {}".format(arg))
                        except:
                            await ctx.send("Unable to remove player from RTL with id: {}".format(arg))
                    else:
                        ctx.send("Please enter a valid id. Use ``bb!admin rtl -p`` to see current players.")
                else:
                    await ctx.send("Please enter a valid option (-p or -r)")
            elif cmd == "cache":
                # forcibly run the game caching
                if option.isnumeric():
                    # option is the tournament id to run caching on
                    tournament = await self.bot.bridge.findTournamentById(int(option), True)
                    if not await has_tournament_admin_access(ctx.message.author.id, tournament):
                        await ctx.send("Only tournament admins can use this command.")
                        return
                    if tournament:
                        self.bot.cache_queue.append(tournament.id)
                        await ctx.send("Successfully queued up {} to be re-cached".format(tournament.name))
                    else:
                        await ctx.send("Tournament {} does not exist.")
                else:
                    await ctx.send("Please enter a numeric id.")
            elif cmd == "update_clan":
                # set clan to queue for updating player clans
                if option.isnumeric():
                    # option is the clan id to run updating on
                    clan = await self.bot.bridge.getClans(id=int(option))
                    if clan:
                        self.bot.players_clan_queue.append(clan[0].id)
                        await ctx.send("Successfully queued up {} to have player clans updated".format(clan[0].name))
                    else:
                        await ctx.send("Clan {} does not exist.".format(option))
                else:
                    await ctx.send("Please enter a numeric id.")
            elif cmd == "process":
                if not option.isnumeric():
                    await ctx.send("Please enter a valid tournament id")
                    return
                tournament = await self.bot.bridge.findTournamentById(int(option), True)
                if not await has_tournament_admin_access(ctx.message.author.id, tournament):
                    await ctx.send("Only tournament admins can use this command.")
                    return
                if tournament:
                    self.bot.process_queue.append(tournament.id)
                    await ctx.send("Successfully queued up {} to be processed".format(tournament.name))
                    return
            elif cmd == "create_game":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command")
                    return
                await ctx.send("Validating data...")
                if not option.isnumeric():
                    await ctx.send("Please enter a valid tournament id")
                    return
                tournament = await self.bot.bridge.findTournamentById(int(option), True)
                if tournament is not None:
                    if not tournament.has_started:
                        await ctx.send("You cannot create a game in a tournament that hasn't started.")
                        return
                    if tournament.is_finished:
                        await ctx.send("You cannot create a game in a tournament that is finished.")
                        return
                    # check to make sure the round is valid
                    if not arg.isnumeric():
                        await ctx.send("Round number must be numeric")
                        return
                    round_number = int(arg)
                    tournament_round = await self.bot.bridge.getTournamentRounds(tournament=tournament.id, round_number=round_number)
                    if not len(tournament_round):
                        await ctx.send("Could not find round {} in Tournament: {} Id: {}".format(round_number, tournament.name, tournament.id))
                        return
                    tournament_round = tournament_round[0]
                    # check to make sure the game_data is valid for this tournament
                    if (len(arg2) == 0) or (len(arg2.split('.')) is not 2):
                        await ctx.send("You must specify game data in the format of Team1_Id.Team2_Id")
                        return
                    # validate the game data
                    game_data = arg2.split('.')
                    team1 = await self.bot.bridge.getTournamentTeams(tournament=tournament.id, pk=int(game_data[0]))
                    if not len(team1):
                        # try for the round_robin_tournament
                        team1 = await self.bot.bridge.getTournamentTeams(round_robin_tournament=tournament.id, pk=int(game_data[0]))
                        if not len(team1):
                            await ctx.send("Could not find team {} in tournament: {}, id: {}".format(game_data[0], tournament.name, tournament.id))
                            return
                    team2 = await self.bot.bridge.getTournamentTeams(tournament=tournament.id, pk=int(game_data[1]))
                    if not len(team2):
                        # try for the round_robin_tournament
                        team2 = await self.bot.bridge.getTournamentTeams(round_robin_tournament=tournament.id, pk=int(game_data[1]))
                        if not len(team2):
                            await ctx.send("Could not find team {} in tournament: {}, id: {}".format(game_data[1], tournament.name, tournament.id))
                            return
                    # at this point we've validated everything...go ahead and create the one-off game
                    tournament_game = await self.bot.bridge.createGame(tournament, tournament_round, arg2)
                    await ctx.send("Created game in {} between teams {} and {}. Game Link: {}".format(tournament.name, game_data[0], game_data[1], tournament_game.game_link))

                else:
                    await ctx.send("Tournament is not valid. Please enter a valid tournament #")
                    return

            elif cmd == "delete_game":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command")
                    return
                if not option.isnumeric():
                    await ctx.send("Please enter a valid tournament id")
                    return

                game = await self.bot.bridge.getGames(gameid=option)
                if not game:
                    await ctx.send("Unable to find a game with id {}".format(option))
                    return

                api = API()
                if game.current_state == "WaitingForPlayers":
                    api.api_delete_game(game.gameid)
                    await ctx.send("Deleted the game with ID {} on Warzone".format(option))
                game.delete()
                await ctx.send("Deleted the game with ID {} on the CLOT".format(option))
                return
            elif cmd == "sub":
                # option = tourney
                # arg = new sub player id
                # arg2 = old sub player id
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command")
                    return
                tournament = await self.bot.bridge.findTournamentById(int(option), True)
                new_player = await self.bot.bridge.getPlayers(token=arg)
                old_player = await self.bot.bridge.getPlayers(token=arg2)
                if not tournament:
                    await ctx.send("Unable to find tournament with id {}".format(option))
                    return
                if not new_player:
                    await ctx.send("Unable to find new player to sub in with id {}".format(arg))
                    return
                if not old_player:
                    await ctx.send("Unable to find old player to sub out with id {}".format(arg2))
                    return
                tplayer = await self.bot.bridge.getTournamentPlayers(team__round_robin_tournament=tournament, player__token=old_player[0].token)

                if not tplayer:
                    await ctx.send("Unable to find tournament player for tourney {} / player {}".format(option, arg2))
                    return
                tplayer[0].player = new_player[0]
                await self.bot.bridge.saveObject(tplayer[0])
                await ctx.send("Successfully subbed in {} ({}) for {} ({}) on {} ({})".format(new_player[0].name, new_player[0].token, old_player[0].name, old_player[0].token, tournament.name, tournament.id))
            elif cmd == "tournament_keys":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command")
                    return
                if not option.isnumeric():
                    await ctx.send("Please enter a valid tournament id")
                    return
                tournament = await self.bot.bridge.findTournamentById(int(option), True)
                if tournament is not None:
                    teams = await self.bot.bridge.getTournamentTeams(round_robin_tournament=tournament.id)
                    if not teams:
                        await ctx.send("Could not find teams in tournament: {}, id: {}".format(tournament.name, tournament.id))
                        return

                    # Print out tournament data
                    output_str = "{} (ID: {})".format(tournament.name, tournament.id)
                    for team in teams:
                        output_str += "\n{} (ID: {})".format(team.clan_league_clan.clan.name, team.id)

                    await ctx.send(output_str)
                    return
            elif cmd == "add":
                if not is_clotadmin(ctx.message.author.id):
                    await ctx.send("Only CLOT admins can use this command.")
                    return
                if option.isnumeric() and arg.isnumeric():
                    admin = await self.bot.bridge.getTournamentAdministrators(player__token=option, tournament__id=int(arg))
                    if admin:
                        await ctx.send("{} is already an administrator of tournament {}".format(option, arg))
                        return
                    else:
                        player = await self.bot.bridge.getPlayers(token=option)
                        if len(player):
                            tournament = await self.bot.bridge.findTournamentById(int(arg), True)
                            if tournament:
                                await self.bot.bridge.createTournamentAdministrator(player=player[0], tournament=tournament)
                                await ctx.send("Added {} as a {} admin successfully.".format(player[0].name, tournament.name))
                                return
                await ctx.send("Please enter a valid player token and tournament id.")
            else:
                await ctx.send("Please enter a valid command. Use ``bb!help admin`` to see commands.")

        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(
        brief="Creates filters for game logs to only show games fulfilling criteria.",
        usage='''
                Hint: Any parameter with [] is optional. Excluding [tournament_id]s will apply filter to all games
                bb!filter -a -c clan_id [tournament_id] - adds filters for the channel to show logs from a clan
                bb!filter -r -c clan_id [tournament_id] - removes clan filters from the channel
                bb!filter -a -p player_token [tournament_id] - adds filters for the channel to show logs from a player
                bb!filter -r -p player_token [tournament_id] - removes player filters from the channel           
                bb!filter -rall - removes all filters from the channel
                ''',
        category="clot")
    async def filter(self, ctx, arg="invalid_cmd", arg2="invalid_cmd", id="invalid_id", tournament_id=""):
        try:
            discord_user = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)

            # Ensure parameters follow syntax
            if arg == "invalid_cmd" or arg != "-a" and arg != "-r" and arg != "-rall":
                await ctx.send("Please enter a valid option (-a or -r or -rall). Use ``bb!help filter`` to see commands.")
                return

            if arg != "-rall" and (arg2 == "invalid_cmd" or arg2 != "-c" and arg2 != "-p"):
                await ctx.send("Please enter a valid option (-c or -p). Use ``bb!help filter`` to see commands.")
                return

            if arg != "-rall" and (id == "invalid_id" or not id.isnumeric()):
                await ctx.send("Please enter a valid id. Use ``bb!help filter`` to see commands.")
                return

            if arg != "-rall" and tournament_id and not tournament_id.isnumeric():
                await ctx.send("Please enter a valid tournament ID (or exclude to filter all applicable games). Use ``bb!help tournaments`` to see tournaments.")
                return

            # we must find the tournament id, and the player associated with the discord user must be the creator
            # validate that here
            if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                if tournament_id:
                    tournament = await self.bot.bridge.findTournamentById(int(tournament_id), True)
                    if not tournament:
                        await ctx.send("Unable to find tournament with id {}. Use ``bb!tournaments`` to see list of tournaments.".format(tournament_id))
                        return

                    discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(channelid=ctx.message.channel.id,
                                                                                       tournament=tournament)
                else:
                    discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(channelid=ctx.message.channel.id)

                if not len(discord_channel_link):
                    await ctx.send("There were no links found in this channel satisfying the command. Use ``bb!help linkt`` to see commands to link.")
                    return

                if arg2 == "-c":
                    clan = await self.bot.bridge.getClans(id=int(id))
                    if not len(clan):
                        await ctx.send("Unable to find clan with id {}. Use ``bb!clans`` to see list of clans.".format(id))
                        return
                    clan = clan[0]
                elif arg2 == "-p":
                    player = await self.bot.bridge.getPlayers(token=id)
                    if not len(player):
                        await ctx.send("Unable to find player with token {}.".format(id))
                        return
                    player = player[0]

                if arg == "-a":
                    total_filters_added = 0
                    for cl in discord_channel_link:
                        if arg2 == "-c":
                            # Adds clan filters to the channel
                            discord_channel_filter = await self.bot.bridge.getDiscordChannelClanFilters(link=cl, clan=clan)
                            if discord_channel_filter:
                                await ctx.send("Filter for {} and {} (id: {}) already exists. Use ``bb!links`` to see all links and filters.".format(clan.name, cl.tournament.name, cl.tournament.id))
                                continue
                            new_filter = await self.bot.bridge.createDiscordChannelClanFilter(link=cl, clan=clan)
                        elif arg2 == "-p":
                            # Adds player filters to the channel
                            discord_channel_filter = await self.bot.bridge.getDiscordChannelPlayerFilters(link=cl, player=player)
                            if discord_channel_filter:
                                await ctx.send("Filter for {} and {} (id: {}) already exists. Use ``bb!links`` to see all links and filters.".format(player.name, cl.tournament.name, cl.tournament.id))
                                continue
                            new_filter = await self.bot.bridge.createDiscordChannelPlayerFilter(link=cl, player=player)

                        await self.bot.bridge.saveObject(new_filter)
                        total_filters_added += 1

                    await ctx.send("Successfully added {} filters to this channel.".format(total_filters_added))
                else:
                    total_filters_removed = 0

                    if arg == "-rall":
                        # Remove all filters from the channel
                        clan_filters = await self.bot.bridge.getDiscordChannelClanFilters(link__channelid=ctx.message.channel.id)
                        player_filters = await self.bot.bridge.getDiscordChannelPlayerFilters(link__channelid=ctx.message.channel.id)
                        for cf in clan_filters:
                            await self.bot.bridge.deleteObject(cf)
                            total_filters_removed += 1
                        for pf in player_filters:
                            await self.bot.bridge.deleteObject(pf)
                            total_filters_removed += 1
                    else:
                        for cl in discord_channel_link:
                            if arg2 == "-c":
                                # Remove all filters applying to the channel, clan and (optionally) tournament
                                discord_channel_filter = await self.bot.bridge.getDiscordChannelClanFilters(link=cl, clan=clan)
                                if discord_channel_filter:
                                    await self.bot.bridge.deleteObject(discord_channel_filter[0])
                                    total_filters_removed += 1
                            elif arg2 == "-p":
                                # Remove all filters applying to the channel, player and (optionally) tournament
                                discord_channel_filter = await self.bot.bridge.getDiscordChannelPlayerFilters(link=cl, player=player)
                                if discord_channel_filter:
                                    await self.bot.bridge.deleteObject(discord_channel_filter[0])
                                    total_filters_removed += 1

                    if total_filters_removed:
                        await ctx.send("Successfully removed {} filters from the channel".format(total_filters_removed))
                    else:
                        await ctx.send("Unable to find any filters to remove. Use ``bb!links`` to see all links and filters.")
            else:
                await ctx.send("Sorry, you must be a server administrator to use this command.")
                return
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))


    '''
    Sends messages containing logs to the channel that the admin used to invoke the command.
    '''
    @staticmethod
    async def send_log_message(ctx, log_type, logs):
        if len(logs) == 1:
            ctx.send("One {} log found: [{} UTC]:\n{}".format(log_type, logs[0].timestamp, logs[0].msg[:1900]))
        else:
            await ctx.send("Last two {} logs: ".format(log_type))
            for log in logs:
                await ctx.send("[{} UTC]:\n{}".format(log.timestamp, log.msg[:1900]))

    @commands.command(
        brief="Links a channel on your server to CL division tournaments on the CLOT. You must be the tournament creator to succesfully link the tournament.",
        usage='''
            bb!linkd -a division_id - adds a link from this discord channel to stream game logs for tournaments from division_id
            bb!linkd -r division_id - removes an existing link from this discord channel for tournaments from division_id
            ''',
        category="clot")
    async def linkd(self, ctx, arg="invalid_cmd", arg2="invalid_id"):
        try:
            discord_user = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)
            if not len(discord_user):
                discord_user = await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)
            else:
                discord_user = discord_user[0]

            if arg == "invalid_cmd":
                # list the current links for this channel
                links = "__**Tournaments Linked to this Channel**__\n"
                discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(channelid=ctx.message.channel.id)
                if discord_channel_link.count() == 0:
                    links += "There are currently no links."
                else:
                    for link in discord_channel_link:
                        links += link.tournament.name + "\n"
                await ctx.send(links)
                return
            elif arg != "-a" and arg != "-r":
                await ctx.send("Please enter a valid option for the command (-a or -r).")
                return

            if arg2 == "invalid_id" or not arg2.isnumeric():
                await ctx.send("Please enter a valid division id to link to this channel.")
                return

            # we must find the tournament id, and the player associated with the discord user must be the creator
            # validate that here
            if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                tournaments = await self.bot.bridge.findTournamentByDivisionId(int(arg2))
                total_successfully_updated = 0
                total_filters_removed = 0
                if not len(tournaments):
                    await ctx.send(
                        "Please enter a valid division id to link to this channel. Use ``bb!divisions`` to see list of divisions.")
                    return
                for tournament in tournaments:
                    # if a private tournament, the person sending this command must be linked and be the creator
                    if tournament.private:
                        player = await self.bot.bridge.getPlayers(discord_member__memberid=ctx.message.author.id)
                        if len(player):
                            player = player[0]
                            if hasattr(tournament, 'parent_tournament'):
                                if tournament.parent_tournament:
                                    print("Tournament Parent ID {}".format(tournament.parent_tournament_id))
                                if player.id != tournament.created_by_id and (
                                        tournament.parent_tournament and tournament.parent_tournament_id != 369):  # hard code this for clan league
                                    await ctx.send(
                                        "The creator of the tournament is the only one who can link private tournaments: {}".format(
                                            tournament.name))
                                    continue
                            else:
                                # no parent tournament, must be creator
                                if player.id != tournament.created_by_id:
                                    await ctx.send(
                                        "The creator of the tournament is the only one who can link private tournaments: {}".format(
                                            tournament.name))
                                    continue
                        else:
                            await ctx.send(
                                "Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions.")
                            return
                    if arg == "-a":
                        # there can be a many:1 relationship from tournaments to channel, so it's completely ok if there's
                        # already a tournament hooked up to this channel. We don't even check, just add this tournament
                        # as a link to this channel
                        discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(tournament=tournament,
                                                                                           channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            await ctx.send("You've already linked this channel to tournament: {}".format(tournament.name))
                            continue
                        await self.bot.bridge.createChannelTournamentLink(tournament=tournament,
                                                                            discord_user=discord_user,
                                                                            channelid=ctx.message.channel.id,
                                                                            name="{}.{}".format(ctx.message.channel.guild.name, ctx.message.channel.name))
                        total_successfully_updated += 1
                    elif arg == "-r":
                        discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(tournament=tournament,
                                                                                           channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            discord_channel_link = discord_channel_link[0]

                            clan_filters = await self.bot.bridge.getDiscordChannelClanFilters(link=discord_channel_link)
                            for cf in clan_filters:
                                total_filters_removed += 1
                                await self.bot.bridge.deleteObject(cf)
                            player_filters = await self.bot.bridge.getDiscordChannelPlayerFilters(link=discord_channel_link)
                            for pf in player_filters:
                                total_filters_removed += 1
                                await self.bot.bridge.deleteObject(pf)

                            await self.bot.bridge.deleteObject(discord_channel_link)
                            total_successfully_updated += 1
                        else:
                            await ctx.send(
                                "There is no existing link for tournament {} and this channel.".format(tournament.name))
            else:
                await ctx.send("Sorry, you must be a server administrator to use this command.")
            if total_successfully_updated and arg == "-a":
                await ctx.send(
                    "You've linked this channel to {} out of {} tournaments. Game logs will now show-up here in real-time.".format(
                        total_successfully_updated, len(tournaments)))
            elif total_successfully_updated and arg == "-r":
                await ctx.send("You've removed the link to this channel for {} out of {} tournaments and {} filters.".format(
                    total_successfully_updated, len(tournaments), total_filters_removed))
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(
        brief="Links a channel on your server to a tournament on the CLOT. You must be the tournament creator to succesfully link the tournament.",
        usage='''
            Hint: you can link the RTL (id: 109) and the MTC (id: 22) game logs
            bb!linkt -a tournament_id - adds a link from this discord channel to stream game logs for tournament_id
            bb!linkt -r tournament_id - removes an existing link from this discord channel to tournament_id
            ''',
        category="clot")
    async def linkt(self, ctx, arg="invalid_cmd", arg2="invalid_id"):
        try:
            discord_user = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)
            if not discord_user:
                discord_user = await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)
            else:
                discord_user = discord_user[0]

            if arg == "invalid_cmd":
                # list the current links for this channel
                links = "__**Tournaments Linked to this Channel**__\n"
                discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(channelid=ctx.message.channel.id)
                if len(discord_channel_link) == 0:
                    links += "There are currently no links."
                else:
                    for link in discord_channel_link:
                        links += link.tournament.name + "\n"
                await ctx.send(links)
                return
            elif arg != "-a" and arg != "-r":
                await ctx.send("Please enter a valid option for the command (-a or -r).")
                return

            if arg2 == "invalid_id" or not arg2.isnumeric():
                await ctx.send("Please enter a valid tournament or league id to link to this channel.")
                return

            # we must find the tournament id, and the player associated with the discord user must be the creator
            # validate that here
            if ctx.message.author.guild_permissions.administrator or is_clotadmin(ctx.message.author.id):
                # user is a server admin, process to create the channel -> tournament link
                tournament = await self.bot.bridge.findTournamentById(int(arg2), True)
                if tournament:
                    # if a private tournament, the person sending this command must be linked and be the creator
                    if tournament.private:
                        player = await self.bot.bridge.getPlayers(discord_member__memberid=ctx.message.author.id)
                        if len(player):
                            player = player[0]
                            if hasattr(tournament, 'parent_tournament'):
                                if tournament.parent_tournament:
                                    print("Tournament Parent ID {}".format(tournament.parent_tournament_id))
                                if player.id != tournament.created_by_id and (tournament.id != 168) and (tournament.id != 109) and (tournament.id != 167) and (tournament.parent_tournament and tournament.parent_tournament_id != 369):  # hard code this for clan league
                                    await ctx.send("The creator of the tournament is the only one who can link private tournaments.")
                                    return
                            else:
                                # no parent tournament, must be creator
                                if player.id != tournament.created_by_id:
                                    await ctx.send(
                                        "The creator of the tournament is the only one who can link private tournaments.")
                                    return
                        else:
                            await ctx.send("Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions.")
                            return
                    if arg == "-a":
                        # there can be a many:1 relationship from tournaments to channel, so it's completely ok if there's
                        # already a tournament hooked up to this channel. We don't even check, just add this tournament
                        # as a link to this channel
                        discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(tournament=tournament, channelid=ctx.message.channel.id)
                        if len(discord_channel_link):
                            await ctx.send("You've already linked this channel to tournament: {}".format(tournament.name))
                            return
                        discord_channel_link = await self.bot.bridge.createChannelTournamentLink(tournament=tournament,
                                                                                                 discord_user=discord_user,
                                                                                                 channelid=ctx.message.channel.id,
                                                                                                 name="{}.{}".format(ctx.message.channel.guild.name, ctx.message.channel.name))
                        await ctx.send("You've linked this channel to tournament: {}. Game logs will now show-up here in real-time.".format(tournament.name))
                    elif arg == "-r":
                        total_filters_removed = 0
                        discord_channel_link = await self.bot.bridge.getChannelTournamentLinks(tournament=tournament, channelid=ctx.message.channel.id)
                        if discord_channel_link:
                            discord_channel_link = discord_channel_link[0]
                            clan_filters = await self.bot.bridge.getDiscordChannelClanFilters(link=discord_channel_link)
                            for cf in clan_filters:
                                total_filters_removed += 1
                                await self.bot.bridge.deleteObject(cf)
                            player_filters = await self.bot.bridge.getDiscordChannelPlayerFilters(link=discord_channel_link)
                            for pf in player_filters:
                                total_filters_removed += 1
                                await self.bot.bridge.deleteObject(pf)

                            await self.bot.bridge.deleteObject(discord_channel_link)
                            await ctx.send("You've removed the link from this channel and {} filters".format(total_filters_removed))
                        else:
                            await ctx.send("There is no existing link for tournament {} and this channel.".format(tournament.name))
                else:
                    await ctx.send("Please enter a valid tournament or league id to link to this channel.")
            else:
                await ctx.send("Sorry, you must be a server administrator to use this command.")
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(
        brief="Shows all links and filters for the channel.",
        usage='''
            bb!links - List the links and filters for the channel
            ''',
        category="clot")
    async def links(self, ctx):
        try:
            discord_user = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)
            if not discord_user:
                await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)

            # Get all of the channel links
            discord_channel_links = await self.bot.bridge.getChannelTournamentLinks(channelid=ctx.message.channel.id)
            if not len(discord_channel_links):
                await ctx.send("No links were found for this channel. Use ``bb!help linkt`` to see how to link.")
                return

            # List all channel links and create queryset of clan and player filters
            clan_filters = []
            player_filters = []
            message_data = "Tournament Links:\n"
            for cl in discord_channel_links:
                if len(message_data) > 1500:
                    await ctx.send(message_data)
                    message_data = ""

                message_data += "{} (ID: {})\n".format(cl.tournament.name, cl.tournament.id)

                clan_filters = clan_filters + await self.bot.bridge.getDiscordChannelClanFilters(link=cl)
                player_filters = player_filters + await self.bot.bridge.getDiscordChannelPlayerFilters(link=cl)

            # List all clan filters
            message_data += "\nClan Filters:\n"
            for cf in clan_filters:
                if len(message_data) > 1500:
                    await ctx.send(message_data)
                    message_data = ""

                message_data += "{} (ID: {}) | {} (ID: {})\n".format(cf.clan.name, cf.clan.id, cl.tournament.name, cl.tournament.id)

            # List all player filters
            message_data += "\nPlayer Filters:\n"
            for pf in player_filters:
                if len(message_data) > 1500:
                    await ctx.send(message_data)
                    message_data = ""

                message_data += "{} (Token: {}) | {} (ID: {})\n".format(pf.player.name, pf.player.token, cl.tournament.name, cl.tournament.id)

            if message_data:
                await ctx.send(message_data)

        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(
        brief="Links your discord account with your CLOT/Warzone account for use with creating games and bot ladders.",
        usage="bot_token_from_clot_site",
        category="clot")
    async def linkme(self, ctx, arg):
        try:
            if isinstance(ctx.message.channel, discord.DMChannel):
                print("Token for linking: {} for user: {}".format(arg, ctx.message.author.id))
                # check to see if this player is already linked
                player = await self.bot.bridge.getPlayers(bot_token=arg)
                if len(player):
                    player = player[0]
                    # make sure the discord id is not already here
                    discord_member = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)

                    if len(discord_member) and player.discord_member_id != discord_member[0].id:
                        cd_name = self.bot.get_user(ctx.message.author.id)
                        new_name = ctx.message.author.name

                        # do the unlinking
                        player.discord_member = None
                        await self.bot.bridge.saveObject(player)
                        await ctx.send("Your discord ID is already associated with another account, unlinking {} and linking {}.".format(cd_name, new_name))
                    elif len(discord_member):
                        await ctx.send("Your account is already linked to the CLOT")

                    if not player.discord_member_id:
                        print("Saving discord id: {} for user".format(ctx.message.author.id))
                        discord_obj = await self.bot.bridge.getDiscordUsers(memberid=ctx.message.author.id)
                        if not len(discord_obj):
                            discord_obj = await self.bot.bridge.createDiscordUser(memberid=ctx.message.author.id)
                        else:
                            discord_obj = discord_obj[0]
                        player.discord_member = discord_obj
                        await self.bot.bridge.saveObject(player)
                        await ctx.send("You've successfully linked your discord account to the CLOT.")
                else:
                    await ctx.send(
                        "Bot token is invalid. Please visit http://wzclot.eastus.cloudapp.azure.com/me to retrieve your token.")
            else:
                await ctx.send("You cannot use the !linkme command unless you are privately messaging the bot.")
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Displays division data from the CLOT",
                      usage='''
                          bb!divisions : Displays CL Divisions
                          ''',
                      category="clot")
    async def divisions(self, ctx):
        try:
            await ctx.send("Gathering tournament data....")
            division_data = "Clan League Divisions\n"

            cl = await self.bot.bridge.getClanLeagues(id=369)
            if len(cl):
                divisions = await self.bot.bridge.getClanLeagueDivisionsOrderByTitle(league=cl[0])

                for division in divisions:
                    if len(division_data) > 1500:
                        await ctx.send(division_data)
                        division_data = ""
                    division_data += "{} | Id: {}\n".format(division.title, division.id)

                await ctx.send(division_data)
            else:
                await ctx.send("There are no active CL divisions to link")
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Displays tournament data from the CLOT",
                      usage='''
                          bb!tournaments -f : Displays Finished Tournaments
                          bb!tournaments -o : Displays Open Tournaments
                          bb!tournaments -p : Displays Tournaments In Progress
                          bb!tournaments -cl : Displays Clan League Tournaments
                          bb!tournaments -s <search_text> : Searches for tournaments by their name
                          ''',
                          category="clot")
    async def tournaments(self, ctx, option="invalid", arg=""):
        try:
            tournament_data = ""
            tournaments = await self.bot.bridge.getTournamentsAll()
            if option == "-f":
                tournament_data += "Finished Tournaments\n"
            elif option == "-o":
                tournament_data += "Open Tournaments\n"
            elif option == "-p":
                tournament_data += "Tournaments In Progress\n"
            elif option == "-cl":
                tournament_data += "Clan League Tournaments\n"
            elif option == "-s":
                await ctx.send("Searching for Tournaments starting with {}...".format(arg))
                tournaments = (await self.bot.bridge.getTournaments(name__istartswith=arg.lower(), private=False))[:10]
                data = "Showing top 10 results\n"
                for t in tournaments:
                    data += "{} (Id: {}) | <{}>\n".format(t.name, t.id, t.get_full_public_link())
                if data != "" and len(data) > 0:
                    await ctx.send(data)
                else:
                    await ctx.send("No tournaments found that start with {}".format(arg))
                return
            else:
                await ctx.send("You must specify an option. Use ``bb!help tournaments`` to see commands.")
                return

            await ctx.send("Gathering tournament data....")
            for tournament in tournaments:
                child_tournament = await self.bot.bridge.findTournamentById(tournament.id, True)
                if child_tournament:
                    if len(tournament_data) > 1500:
                        await ctx.send(tournament_data)
                        tournament_data = ""

                    link_text = "http://wzclot.eastus.cloudapp.azure.com/"
                    if child_tournament.is_league:
                        link_text += "leagues/{}".format(child_tournament.id)
                    else:
                        link_text += "tournaments/{}".format(child_tournament.id)
                    if option == "-f":  # only finished tournaments
                        if child_tournament.is_finished:
                            winning_team = await self.bot.bridge.get_team_data(child_tournament.winning_team_id)
                            tournament_data += "{} (Id: {}) | <{}> | Winner: {}\n".format(child_tournament.name, child_tournament.id, link_text, winning_team)
                    elif option == "-o":  # only open tournaments
                        if not child_tournament.has_started and not child_tournament.private:
                            open_spots = await self.bot.bridge.get_tournament_open_seats(child_tournament)
                            tournament_data += "{} (Id: {}) | <{}> | {}\n".format(child_tournament.name, child_tournament.id, link_text, open_spots)
                    elif option == "-p":  # only in progress
                        if child_tournament.has_started and not child_tournament.private:
                            tournament_data += "{} (Id: {}) | <{}>\n".format(child_tournament.name, child_tournament.id, link_text)
                    elif option == "-cl":  # only in progress
                        if child_tournament.id == 369 and child_tournament.has_started:
                            cl_tourneys = await self.bot.bridge.getClanLeagueTournamentsOrderById(parent_tournament=child_tournament)
                            for cl_tourney in cl_tourneys:
                                tournament_data += "{} (Id: {})\n".format(cl_tourney.name, cl_tourney.id)
            if len(tournament_data) > 0:
                await ctx.send(tournament_data)
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Displays the MTC top ten on the CLOT. Optional arguments to show any MTC top 10.",
                      usage="""
                      Hint: official MTC will be selected if no id is included
                      bb!mtc <league_id>
                      """)
    async def mtc(self, ctx, mtc_id="0"):
        try:
            tournament_data = ""

            if mtc_id == "0":
                mtc_id = "22"

            if not mtc_id.isnumeric():
                await ctx.send("You've entered and invalid MTC league id.")
                return

            tournament = await self.bot.bridge.getMonthlyTemplateRotations(id=int(mtc_id))
            if len(tournament):
                await ctx.send("Gathering Monthly Template Rotation data....")
                tournament = tournament[0]
                tournamentteams = await self.bot.bridge.getTournamentTeamsOrderByRatingWins(tournament=tournament.id, active=True)
                tournament_data += "MTC Top 10\n"
                teams_found = 0
                for team in tournamentteams:
                    if teams_found < 10:
                        games_finished = await self.bot.bridge.get_games_finished_for_team_since(team.id, tournament, 90)
                        if games_finished >= 10:
                            tournament_data += "{}) {} - {}\n".format(teams_found + 1, await self.bot.bridge.get_team_data_no_clan(team), team.rating)
                            teams_found += 1
                print("MTC: {}\nLength: {}".format(tournament_data.encode('utf-8'), len(tournament_data)))
                await ctx.send(tournament_data)
            else:
                await ctx.send("You've entered an invalid MTC league id.")

        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Displays all registered clan members on the CLOT",
                      usage='''
                          Hint: to see a list of clan ids, use bb!clans
                          bb!clan clanid
                          bb!clan clanid -d - List of players in the clan who have linked their discord accounts
                          ''')
    async def clan(self, ctx, clanid="", discord_arg=""):
        try:
            if not clanid:
                await ctx.send("No clanid has been entered. Please use ``bb!clans`` to show clans.")
                return
            await ctx.send("Gathering player data for clan {}....".format(clanid))
            clan_obj = await self.bot.bridge.getClans(pk=int(clanid))
            emb = discord.Embed(color=self.bot.embed_color)
            if len(clan_obj):
                emb.title = "{}".format(clan_obj[0].name)
                emb.set_thumbnail(url=clan_obj[0].image_path)
                player_data = ""
                field_name = ""
                if discord_arg != "-d":
                    field_name = "Registered on CLOT"
                    players = await self.bot.bridge.getPlayersOrderByName(clan=clan_obj[0].id)
                else:
                    field_name = "Discord Linked on CLOT"
                    players = await self.bot.bridge.getPlayersOrderByName(clan=clan_obj[0].id, discord_member__isnull=False)
                current_player = 0
                if players:
                    for player in players:
                        current_player += 1
                        player_data += "{} [Profile](https://www.warzone.com/Profile?p={})\n".format(player.name, player.token)
                        if current_player % 10 == 0:
                            emb.add_field(name=field_name, value=player_data)
                            player_data = ""  # reset this for the next embed

                        if len(emb) > 5000:
                            await ctx.send(embed=emb)
                            emb = discord.Embed(color=self.bot.embed_color)
                            emb.title = "{}".format(clan_obj[0].name)
                            emb.set_thumbnail(url=clan_obj[0].image_path)

                    if len(player_data) > 0:
                        emb.add_field(name=field_name, value=player_data)
                    await ctx.send(embed=emb)
                else:
                    await ctx.send("No players are registered on the CLOT for {}".format(clan_obj[0].name))
            else:
                await ctx.send("Clan with id {} not found. Please use bb!clans to show valid clans.".format(clanid))
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Displays all clans on the CLOT")
    async def clans(self, ctx):
        try:
            clans = await self.bot.bridge.getClansDictOrderByIdWithPlayerCount()
            await ctx.send("Gathering clans data....")
            clans_data = "Clans on the CLOT\n\n"
            for clan in clans:
                if clan['clan'] is not None and clan['player_count']:
                    if len(clans_data) > 1500:
                        await ctx.send(clans_data)
                        clans_data = ""
                    clans_data += "{}: {}\n".format(clan['clan'], clan['clan__name'])
            await ctx.send(clans_data)
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))

    @commands.command(brief="Display your Warzone Profile Link and Searches for others",
                      usage='''
                          bb!profile - Displays your personal warzone profile
                          bb!profile master - Displays warzone profile for players starting with 'master' 
                      ''')
    async def profile(self, ctx, option=""):
        try:
            if option == "":
                discord_id = ctx.message.author.id
                player = await self.bot.bridge.getPlayers(discord_member__memberid=discord_id)
                if len(player):
                    player = player[0]
                    await ctx.send("{} | <http://wzclot.com/stats/{}> | <https://warzone.com/Profile?p={}>".format(player.name, player.token, player.token))
                else:
                    await ctx.send("Your discord account is not linked to the CLOT. Please see http://wzclot.eastus.cloudapp.azure.com/me/ for instructions.")
            else:
                await ctx.send("Searching the CLOT for players starting with {}...".format(option))
                players = await self.bot.bridge.getPlayers(name__istartswith=option)
                data = ""
                current_player = 0
                for player in players:
                    current_player += 1
                    data += "{} | {} | <http://wzclot.com/stats/{}> | <https://warzone.com/Profile?p={}>\n".format(player.name, player.token, player.token, player.token)
                    if current_player % 20 == 0:
                        if data != "" and len(data) > 0:
                            await ctx.send(data)
                            data = ""
                if data != "" and len(data) > 0:
                    await ctx.send(data)
        except Exception as e:
            await self.bot.handle_command_exception(ctx, str(e))


def setup(bot):
    bot.add_cog(Clot(bot))