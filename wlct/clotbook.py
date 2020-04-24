from django.db import models
from django.utils import timezone

# Models for the Off-site betting for the CLOT
def get_clotbook():
    cb = CLOTBook.objects.all()
    if cb.count() == 1:
        return cb[0]
    else:
        cb = CLOTBook()
        cb.save()
        return cb

class CLOTBook(models.Model):
    total_bets = models.BigIntegerField(default=0)
    in_progress_bets = models.BigIntegerField(default=0)

    currency_name = "Nohams"

    def create_new_bet(self, wager, player):
        pass

    '''
    Creates a new BetOdds object that serves as the initial line for the game
    '''
    def create_initial_odds_for_game(self, game, ratings1, ratings2):


class DiscordChannelCLOTBookLink(models.Model):
    channelid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    discord_user = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.CASCADE)

class Bet(models.Model):
    gameid = models.BigIntegerField(default=0)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)
    player = models.ForeignKey('Player', on_delete=models.CASCADE)
    bet_created = models.DateTimeField(timezone.now)

class BetOdds(models.Model):
    gameid = models.BigIntegerField(default=0)
    game = models.ForeignKey('TournamentGame', on_delete=models.CASCADE)
    players = models.CharField(max_length=255, default="")
    odds = models.IntegerField(default=0)
    bet = models.ForeignKey('Bet', on_delete=models.CASCADE)
    last_changed = models.DateTimeField(timezone.now)
    initial = models.BooleanField(default=False)
