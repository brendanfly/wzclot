# main file for the apis to hit the wz endpoint
# most of these just take in the request or a user object
# and do the right thing

import requests
import json
from dateutil.relativedelta import relativedelta as rd
from django.conf import settings
from wlct.logging import log_exception, log, LogLevel
import os

LIVE_ENDPOINT = os.environ['WZ_ENDPOINT']
LIVE_ACCOUNT = os.environ['WZ_ACCOUNT_EMAIL']
LIVE_API_TOKEN = os.environ['WZ_API_TOKEN']
LIVE_ACCOUNT_TOKEN = os.environ['WZ_ACCOUNT_TOKEN']
LIVE_WARZONE_ENDPOINT = os.environ['WZ_LIVE_ENDPOINT']

# load local settings if there are any
# you must have a settings_local.py file next to settings.py for this to not pass on ImportError
try:
    from wltourney.settings_local import *
except ImportError:
    pass

def get_account_token():
    if settings.DEBUG and not settings.DEBUG_ISSUES:
        return LIVE_ACCOUNT_TOKEN
    else:
        return LIVE_ACCOUNT_TOKEN


def API():
    if settings.DEBUG and not settings.DEBUG_ISSUES:
        return API_TEST(LIVE_ENDPOINT, LIVE_ACCOUNT, LIVE_API_TOKEN)
    else:
        return API2(LIVE_ENDPOINT, LIVE_ACCOUNT, LIVE_API_TOKEN)


class API2:

    def __init__(self, endpoint, account, token):
        self.site_endpoint = endpoint
        self.client_email = account
        self.client_token = token

        # Define all our endpoints
        self.validate_invite_token_url = "/API/ValidateInviteToken"
        self.query_game_url = "/API/GameFeed"
        self.create_game_url = "/API/CreateGame"
        self.delete_game_url = "/API/DeleteLobbyGame"

    def api_create_fake_game_and_get_settings(self, templateid):
        # first, create the game
        ret = {}
        data = {}
        data['hostEmail'] = self.client_email
        data['hostAPIToken'] = self.client_token
        data['templateID'] = templateid
        data['gameName'] = "get template settings"
        data['players'] = [
            {"token": "OpenSeat", "team": "None"},
            {"token": "OpenSeat", "team": "None"}
        ]

        gameID = 0
        try:
            gameInfo = self.api_create_game(data)
            gameInfo = gameInfo.json()

            # the game has been posted, make sure we have a game id and then query the settings
            if 'gameID' in gameInfo:
                # great, query the settings
                gameID = gameInfo['gameID']
                data = {}
                data['gameID'] = gameID
                data['GetSettings'] = 'true'
                gameSettings = self.api_query_game_settings(gameID)

                # if 'error' in gameSettings.json():
                # return an error, and just delete the game
                # got the settings, now send this back as we want to display in the form
                # for the creator
                # delete the game first
                deleteGame = self.api_delete_game(int(gameID))
                deleteGame = deleteGame.json()

                if 'success' in deleteGame:
                    # game deleted successfully
                    ret['success'] = 'true'

                    # convert the gameSettings we need from here into readable text so that the client doesn't have to do
                    # any conversion
                    gameSettings = gameSettings.json()
                    log("Getting settings for template: {}".format(gameSettings), LogLevel.informational)
                    if 'settings' in gameSettings:
                        settings = gameSettings['settings']
                        # this is so we can cache the entire template settings if the tournament actually gets created
                        ret['settings'] = settings
                        if 'Pace' in settings:
                            # convert into days
                            directbootTimeMinutes = gameSettings['settings']['DirectBoot']
                            autobootTimeMinutes = gameSettings['settings']['AutoBoot']
                            ret['Pace'] = gameSettings['settings']['Pace']

                            fmt = ""
                            if ret['Pace'] == 'RealTime':
                                fmt = '{0.minutes} minutes {0.seconds} seconds'
                            else:
                                fmt = '{0.days} days {0.hours} hours'

                            if directbootTimeMinutes != 'none':
                                ret['directBoot'] = fmt.format(rd(minutes=directbootTimeMinutes))
                            if autobootTimeMinutes != 'none':
                                ret['autoBoot'] = fmt.format(rd(minutes=autobootTimeMinutes))
            else:
                # not good, error, TODO: Log???
                if 'error' in gameInfo:
                    ret['error'] = gameInfo['error']
        except:
            # catch the error, if we have created the game delete it here
            log_exception()
            if gameID != 0 and 'success' not in ret:
                data = {}
                data['gameID'] = gameID
                deleteGame = self.api_delete_game(int(gameID))

        if 'error' in gameInfo and gameInfo['error'] == 'GameTemplateKeyNotFound':
            ret['error'] = "The template id is invalid. Please enter a valid template id!"
        elif 'success' not in ret:
            ret['error'] = "There was a problem with getting the template settings. Please try again later."

        return ret


    def api_validate_invite_token(self, token):
        params = {"Email": self.client_email, "APIToken": self.client_token, "Token": token}

        endpoint = LIVE_WARZONE_ENDPOINT + self.validate_invite_token_url
        request = requests.post(endpoint, params=params)
        return request


    def api_validate_token_for_template(self, token, templateid):
        return self.api_post_request_params(self.validate_invite_token_url, {"Token": token, "TemplateIDs": templateid})


    def api_query_game_feed(self, gameid, game_info):
        return self.api_post_request_params(self.query_game_url, {"GameID": gameid, "GetSettings": "true"})


    def api_query_game_settings(self, gameid):
        return self.api_post_request_params(self.query_game_url, {"GameID": gameid, "GetSettings": "true"})


    def api_create_tournament_game(self, game_data):
        game_data['hostEmail'] = self.client_email
        game_data['hostAPIToken'] = self.client_token
        game_data.update(game_data)

        return self.api_create_game(game_data)

    def api_delete_game(self, gameID):
        data = {}
        data['gameID'] = int(gameID)
        data['Email'] = self.client_email
        data['APIToken'] = self.client_token

        return self.api_post_request_json(self.delete_game_url, data)

    def api_create_game(self, data):

        data['Email'] = self.client_email
        data['APIToken'] = self.client_token

        return self.api_post_request_json(self.create_game_url, data)

    def api_post_request_json(self, endpoint, json_data):
        endpoint = self.site_endpoint + endpoint

        json_data = json.dumps(json_data)
        request = requests.post(endpoint, data=json_data)

        return request

    def api_post_request_params(self, endpoint, payload):

        params = {"Email": self.client_email, "APIToken": self.client_token}
        params.update(payload)

        endpoint = self.site_endpoint + endpoint
        request = requests.post(endpoint, params=params)

        return request


class TestResponse():

    def __init__(self):
        self.response_dict = {}

    def json(self):
        return self.response_dict

    def text(self):
        return self.response_dict

    def status_code(self):
        return "200"


class API_TEST(API2):

    def __init__(self, endpoint, account, token):
        super(API_TEST, self).__init__(endpoint, account, token)

    def api_query_game_feed(self, gameid, game_info):
        response = TestResponse()
        response.response_dict = game_info
        response.response_dict['settings'] = json.loads('''{"PersonalMessage":"","Pace":"MultiDay","VoteToBoot":"none","DirectBoot":3,"AutoBoot":3,"BankingBootTimes":"null","PrivateMessaging":true,"PracticeGame":false,"Fog":"Foggy","MultiAttack":false,"AllowPercentageAttacks":true,"AllowTransferOnly":true,"AllowAttackOnly":true,"MoveOrder":"Random","InstantSurrender":"Instant","BootedPlayersTurnIntoAIs":false,"SurrenderedPlayersTurnIntoAIs":false,"TimesCanComeBackFromAI":2,"AIsSurrenderWhenOneHumanRemains":false,"AllowVacations":false,"AutoStartGame":true,"Map":72163,"AutomaticTerritoryDistribution":"Manual","CustomScenario":"null","DistributionMode":-1,"TerritoryLimit":4,"InitialPlayerArmiesPerTerritory":5,"InitialNonDistributionArmies":2,"InitialNeutralsInDistribution":4,"Wastelands":{"NumberOfWastelands":15,"WastelandSize":3},"Commerce":{},"Commanders":false,"OneArmyStandsGuard":true,"MinimumArmyBonus":5,"LuckModifier":0.16,"RoundingMode":"StraightRound","BonusArmyPer":0,"ArmyCap":"null","OffensiveKillRate":60,"DefensiveKillRate":70,"LocalDeployments":false,"NoSplit":false,"OverriddenBonuses":[{"bonusID":1,"value":0},{"bonusID":17,"value":0},{"bonusID":10,"value":0},{"bonusID":27,"value":0},{"bonusID":30,"value":0}],"ReinforcementCard":"none","SpyCard":"none","AbandonCard":"none","OrderPriorityCard":"none","OrderDelayCard":"none","AirliftCard":"none","GiftCard":"none","DiplomacyCard":"none","SanctionsCard":"none","ReconnaissanceCard":"none","SurveillanceCard":"none","BlockadeCard":{"NumPieces":1,"InitialPieces":1,"MinimumPiecesPerTurn":0,"Weight":0,"MultiplyAmount":3.141592},"BombCard":"none","MaxCardsHold":3,"NumberOfCardsToReceiveEachTurn":0,"CardPlayingsFogged":true,"CardsHoldingAndReceivingFogged":true,"Mods":[]}''')
        return response

    def api_create_game(self, data):
        response = TestResponse()
        response.response_dict['gameID'] = '12345'
        return response

    def api_delete_game(self, gameid):
        response = TestResponse()
        response.response_dict['success'] = 'true'
        return response

    def api_query_game_settings(self, id):
        response = TestResponse()
        response.response_dict['settings'] = json.loads('''{"PersonalMessage":"","Pace":"MultiDay","VoteToBoot":"none","DirectBoot":3,"AutoBoot":3,"BankingBootTimes":"null","PrivateMessaging":true,"PracticeGame":false,"Fog":"Foggy","MultiAttack":false,"AllowPercentageAttacks":true,"AllowTransferOnly":true,"AllowAttackOnly":true,"MoveOrder":"Random","InstantSurrender":"Instant","BootedPlayersTurnIntoAIs":false,"SurrenderedPlayersTurnIntoAIs":false,"TimesCanComeBackFromAI":2,"AIsSurrenderWhenOneHumanRemains":false,"AllowVacations":false,"AutoStartGame":true,"Map":72163,"AutomaticTerritoryDistribution":"Manual","CustomScenario":"null","DistributionMode":-1,"TerritoryLimit":4,"InitialPlayerArmiesPerTerritory":5,"InitialNonDistributionArmies":2,"InitialNeutralsInDistribution":4,"Wastelands":{"NumberOfWastelands":15,"WastelandSize":3},"Commerce":{},"Commanders":false,"OneArmyStandsGuard":true,"MinimumArmyBonus":5,"LuckModifier":0.16,"RoundingMode":"StraightRound","BonusArmyPer":0,"ArmyCap":"null","OffensiveKillRate":60,"DefensiveKillRate":70,"LocalDeployments":false,"NoSplit":false,"OverriddenBonuses":[{"bonusID":1,"value":0},{"bonusID":17,"value":0},{"bonusID":10,"value":0},{"bonusID":27,"value":0},{"bonusID":30,"value":0}],"ReinforcementCard":"none","SpyCard":"none","AbandonCard":"none","OrderPriorityCard":"none","OrderDelayCard":"none","AirliftCard":"none","GiftCard":"none","DiplomacyCard":"none","SanctionsCard":"none","ReconnaissanceCard":"none","SurveillanceCard":"none","BlockadeCard":{"NumPieces":1,"InitialPieces":1,"MinimumPiecesPerTurn":0,"Weight":0,"MultiplyAmount":3.141592},"BombCard":"none","MaxCardsHold":3,"NumberOfCardsToReceiveEachTurn":0,"CardPlayingsFogged":true,"CardsHoldingAndReceivingFogged":true,"Mods":[]}''')
        return response

    def api_create_tournament_game(self, game_data):
        response = TestResponse()
        response.response_dict['gameID'] = '12345'
        return response


    def api_validate_token_for_template(self, token, templateid):
        response = TestResponse()
        response.response_dict['tokenIsValid'] = 'true'
        template_key = "template{}".format(templateid)
        response.response_dict[template_key] = {'result': 'CanUseTemplate'}
        return response