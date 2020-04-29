from django.db import models
from django.utils import timezone
from wlct.models import Player
from django.contrib import admin
from wlct.logging import log_cb_msg, log_exception

# Models for the Off-site betting for the CLOT
def get_clotbook():
    cb = CLOTBook.objects.all()
    if cb.count() == 1:
        return cb[0]
    else:
        cb = CLOTBook()
        cb.save()
        return cb


class DecimalOddsAdjustment:

    def __init_(self, odds_num, odds_value, adjustment_direction):
        self.odds_num = odds_num
        self.odds_value = odds_value
        self.adjustment_direction = adjustment_direction

    def adjust(self):
        self.odds_value += self.adjustment_direction
        return self.odds_value

class CLOTBook(models.Model):
    total_bets = models.BigIntegerField(default=0)
    in_progress_bets = models.BigIntegerField(default=0)

    currency_name = "Coins"

    # always gives the probability to win for ratings1 based on the opponents of ratings2
    def probability_to_win(self, ratings1, ratings2):
        prob_win = round((1 / (10**((-(ratings1-ratings2))/400) + 1)), 2)
        log_cb_msg("Probability: Favorite: {}/{}, Underdog {}/{}".format(ratings1, prob_win, ratings2, 1-prob_win))
        return (prob_win, 1-prob_win)

    def calculate_decimal_odds_winnings(self, odds, wager):
        # winnings are calculated based on the wager and the current odds
        # ex. odds of -105 means you'd have to bet 100 to win 105
        return (wager*odds)-wager

    def calculate_american_odds_winnings(self, odds, wager):
        odds = self.american_odds_to_decimal(odds)
        return self.calculate_decimal_odds_winnings(odds, wager)

    def decimal_odds_to_american(self, odds):
        if odds > 2.0:
            return int((odds-1)*100)
        else:
            return int(-100 // (odds-1))

    def american_odds_to_decimal(self, odds):
        if odds > 0:
            return round(odds / 100 + 1, 2)
        else:
            return round(100 / -(odds) + 1, 2)

    def prob_to_decimal_odds(self, prob):
        return round((1/prob), 2)

    def update_odds(self, bet_odds):
        pass

    def round_to_nearest_multiple(self, x, base=5):
        return base * round(x / base)

    def format_american(self, odds):
        if odds > 0:
            return "+{}".format(odds)
        return odds

    def adjust_line(self, game):
        # gather how much money on both sides would win
        # adjust the line to make sure we are slightly ahead on the other side
        winning1 = 0
        winning2 = 0
        wager1 = 0
        wager2 = 0

        bets = Bet.objects.filter(game=game)
        if bets.count() > 3:
            for bet in bets:
                odds1 = bet.odds.decimal_odds.split('!')[0]
                odds2 = bet.odds.decimal_odds.split('!')[1]
                if game.players.split('-')[0] == bet.players:
                    winning1 += self.calculate_decimal_odds_winnings(odds1, bet.wager)
                    wager1 += bet.wager
                else:
                    winning2 += self.calculate_decimal_odds_winnings(odds2, bet.wager)
                    wager2 += bet.wager

            print("Game {} winnings1 {} winnings2 {}".format(game.gameid, winning1, winning2))
            # we must have a default value even if no one bet on either team
            if winning1 == 0:
                wager1 = 5
            if winning2 == 0:
                wager2 = 5

            print("Before adjustment Game {} winnings1 {} winnings2 {} wager1 {} wager2 {}".format(game.gameid, winning1, winning2, wager1, wager2))
            if winning1 < winning2:
                # winning2 > winning1 means there is more money on the second line...


                odds_to_change = odds1
                bottom_line = odds1
                top_line = odds2
            else:
                odds_to_change = odds2
                bottom_line = odds2
                top_line = odds1

            print("Before adjustment Game {}, odds_to_change {} bottom_line {} top_line {}".format(game.gameid, odds_to_change, bottom_line, top_line))
            line_adjusted = False
            return

            new_odds1 = odds1
            new_odds2 = odds2
            new_odds = odds_to_change
            while not line_adjusted:
                if odds_to_change > 2:
                    # move the odds +
                    new_odds += 0.01
                else:
                    # move the odds -
                    new_odds -= 0.01

                new_winnings1 = self.calculate_decimal_odds_winnings(new_odds1, bet.wager)
                print("Adjusting line. New odds for odds_to_change {}, {} produces winning1 {} and winning2 {}".format(odds_to_change, new_odds))

    def create_new_bet(self, wager, player, game, team):
        # first we need to see which team the bet is on
        wager = int(wager)

        # players are the list of players the bet is on
        # the bet the player gets is based on the last odds we see
        odds = BetOdds.objects.filter(game=game).order_by('-created_time')[0]
        if odds:
            odds = odds[0]
            if str(team.id) == game.teams.split('.')[0]:
                players = game.players.split('-')[0]
                current_odds = odds.decimal_odds.split('!')[0]
            else:
                players = game.players.split('-')[1]
                current_odds = odds.decimal_odds.split('!')[1]

            winnings = self.calculate_decimal_odds_winnings(current_odds, wager)
            bet = Bet(players=players, gameid=game.gameid, game=game, odds=odds, player=player, wager=wager, winnings=winnings)
            bet.save()
            return bet

    '''
    Creates a new BetOdds object that serves as the initial line for the game
    '''
    def create_initial_odds_for_game(self, game, ratings1, ratings2):
        try:
            # get the ratings from the players in the game
            probs = self.probability_to_win(ratings1, ratings2)
            probs1 = probs[0]
            probs2 = probs[1]

            log_cb_msg("Initial probabilities for gameid {}: {}% to {}%".format(game.gameid, probs1, probs2))
            probability = "{}!{}".format(probs1, probs2)

            decimal1 = self.prob_to_decimal_odds(probs1)
            decimal2 = self.prob_to_decimal_odds(probs2)

            log_cb_msg("Decimal odds for gameid {}: {} {}".format(game.gameid, decimal1, decimal2))

            american1 = self.decimal_odds_to_american(decimal1)
            american2 = self.decimal_odds_to_american(decimal2)

            # round the american to the nearest 5 or 0, and change that back into decimal
            log_cb_msg("American odds for gameid {} before rounding: {} {}".format(game.gameid, american1, american2))
            american1 = self.round_to_nearest_multiple(american1)
            american2 = self.round_to_nearest_multiple(american2)
            american_odds = "{}!{}".format(american1, american2)

            log_cb_msg("American odds for gameid {}: {}".format(game.gameid, american_odds))

            decimal1 = self.american_odds_to_decimal(american1)
            decimal2 = self.american_odds_to_decimal(american2)
            decimal_odds = "{}!{}".format(decimal1, decimal2)
            log_cb_msg("Decimal odds for gameid {}: {}".format(game.gameid, decimal_odds))

            odds = BetOdds(gameid=game.id, game=game, players=game.players, initial=True, decimal_odds=decimal_odds, probability=probability, american_odds=american_odds)
            odds.save()

            log_cb_msg("Created initial odds for gameid {}".format(game.gameid))
        except:
            log_exception()

class CLOTBookAdmin(admin.ModelAdmin):
    pass

admin.site.register(CLOTBook, CLOTBookAdmin)

class DiscordChannelCLOTBookLink(models.Model):
    channelid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    discord_user = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.DO_NOTHING)


class DiscordChannelCLOTBookLinkAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordChannelCLOTBookLink, DiscordChannelCLOTBookLinkAdmin)


class Bet(models.Model):
    gameid = models.BigIntegerField(default=0, db_index=True)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, blank=True, null=True)
    players = models.CharField(max_length=255, default="")
    created_time = models.DateTimeField(default=timezone.now)
    odds = models.ForeignKey('BetOdds', on_delete=models.CASCADE, blank=True, null=True)
    wager = models.IntegerField(default=0)
    player = models.ForeignKey('Player', on_delete=models.CASCADE, blank=True, null=True)
    placed = models.BooleanField(default=False)
    winnings = models.IntegerField(default=0)

class BetAdmin(admin.ModelAdmin):
    raw_id_fields = ['game', 'odds']


admin.site.register(Bet, BetAdmin)

class BetOdds(models.Model):
    gameid = models.BigIntegerField(default=0, db_index=True)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE, blank=True, null=True)
    players = models.CharField(max_length=255, default="")
    decimal_odds = models.CharField(max_length=255, default="")
    american_odds = models.CharField(max_length=255, default="")
    created_time = models.DateTimeField(default=timezone.now)
    initial = models.BooleanField(default=False)
    probability = models.CharField(max_length=255, default="")
    sent_notification = models.BooleanField(default=False)


class BetOddsAdmin(admin.ModelAdmin):
    raw_id_fields = ['game']

admin.site.register(BetOdds, BetOddsAdmin)