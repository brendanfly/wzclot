from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib import admin
from django.utils import timezone

invalid_token_string = "invalid"
invalid_clan_string = "clan+#!invalid"
invalid_name_string = "missing no"

# Default User Model
# Custom user model using the default authentication implementation
class User(AbstractUser):
    pass

'''
Discord specific models. 
'''
class DiscordUser(models.Model):
    memberid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    link_mention = models.BooleanField(default=False, blank=True, null=True)

    def __str__(self):
        return "Member: {}, LinkMention: {}".format(self.memberid, self.link_mention)

class DiscordChannelTournamentLink(models.Model):
    tournament = models.ForeignKey('Tournament', on_delete=models.CASCADE, blank=True, null=True)
    channelid = models.BigIntegerField(default=0, blank=True, null=True, db_index=True)
    discord_user = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.CASCADE)

class Engine(models.Model):
    last_run_time = models.DateTimeField(default=timezone.now)
    next_run_time = models.DateTimeField(blank=True, null=True)


class Clan(models.Model):
    name = models.CharField(max_length=64, default=invalid_clan_string, db_index=True)
    icon_link = models.CharField(max_length=255, default=invalid_clan_string)
    image_path = models.CharField(max_length=255, default=invalid_clan_string)

    def __str__(self):
        return self.name

class ClanAdmin(admin.ModelAdmin):
    pass


admin.site.register(Clan, ClanAdmin)


class Player(models.Model):
    token = models.CharField(max_length=32, default=invalid_token_string, db_index=True)
    name = models.CharField(max_length=64, default=invalid_name_string, db_index=True)
    clan_text = models.CharField(max_length=64, default=invalid_clan_string)
    clan = models.ForeignKey('Clan', blank=True, null=True, on_delete=models.SET_NULL)
    is_on_vacation = models.BooleanField(default=False, blank=True, null=True)
    bot_token = models.CharField(max_length=34, default=invalid_token_string, db_index=True)
    discord_member = models.ForeignKey('DiscordUser', blank=True, null=True, on_delete=models.CASCADE, related_name='discord')

    def set_player_data(self, token, playerData):
        self.token = token
        self.clan_text = playerData['clan']
        self.name = playerData['name']


    def logout(self):
        self.token = None


    def __str__(self):
        if self.discord_member:
            return self.name + "({}), discord id: {}".format(self.token, self.discord_member.memberid)
        else:
            return self.name + "({})".format(self.token)

class PlayerAdmin(admin.ModelAdmin):
    search_fields = ['name', 'token', 'clan__name']

admin.site.register(Player, PlayerAdmin)

# Default User Admin
class UserAdmin(admin.ModelAdmin):
    pass

admin.site.register(User, UserAdmin)

class DiscordUserAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordUser, DiscordUserAdmin)

class DiscordChannelTournamentLinkAdmin(admin.ModelAdmin):
    pass

admin.site.register(DiscordChannelTournamentLink, DiscordChannelTournamentLinkAdmin)