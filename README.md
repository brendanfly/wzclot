# Warzone Custom Tournament and Ladder
Warzone CLOT focused around custom leagues and tournaments, initially developed by -B and now publically available to contribute to.

# Setting up your test server
Fork the repo to a local directory. 

This web application is written in the Django framework and the server side pieces are entirely written in python. The database used is postgreSQL and connection pooling with max 20 active connections runs on the server.
To setup a local test site you will need to do the following. 

Install Python 3.7 - https://www.python.org/downloads/windows/  
Install virtualenv - `pip install virtualenv` (you might need to open a new command windows after installing python, windows only)  
Install postgreSQL 11.6-3 - https://www.enterprisedb.com/downloads/postgres-postgresql-downloads  

In the project folder run:  
pip install -r requirements.txt  

Create `settings_local.py` in the `wltourney/` folder with the following:  

```
DEBUG=True  
TEMPLATE_DEBUG=True
DEBUG_ISSUES=False

ALLOWED_HOSTS=['*'] # any url django will serve  

DATABASES = {  
    'default': {  
        'ENGINE': 'django_postgrespool',  
        'NAME': 'your_database_name',  
        'USER': 'database_username',  
        'PASSWORD': 'database_password',
        'HOST': 'localhost',  
        'PORT': '5432',  
    }  
}  
```

You must create `.env` file in the project root...and set the following variables  

```
WZ_ENDPOINT=http://127.0.0.1:8000  
WZ_ACCOUNT_EMAIL=WZEmailAddress  
WZ_API_TOKEN=WZAPIToken - can be retrieved from https://www.warzone.com/wiki/Get_API_Token_API  
WZ_ACCOUNT_TOKEN=AccountToken - visit public profile e.g. https://www.warzone.com/Profile?p=2719017226 and use the p value 2719017226  
WZ_TEST_BOT_TOKEN=<discord-bot-token>
SECRET_KEY='<anything>'
```

Migrate database to the latest schema  
`python manage.py migrate`

Create a super user account for your local django database to be able to view the admin site (127.0.0.1:8000/admin)
`python manage.py createsuperuser`

Run the testserver locally  
`python manage.py runserver --noreload`

# Logging into the Local CLOT Server
The local server you're running will actually hit the warzone endpoint to log you in, however you need to set up the login redirect
since you'll be using your own credentials for use with the Warzone API. 

Visit  https://www.warzone.com/CLOT/Config and setup your redirect URL, which should always be http://127.0.0.1:8000/login

# Object Model  
There are a handful of top level objects that are used on the CLOT  

The framework being used is Django. Please read-up and use this documentation for reference. https://www.djangoproject.com/  

# Bot  
The Warzone bot is able to run in any server and was created to integrate with the CLOT directly. There is a real-time ladder, clan-league updates, and general rankings and statistics from the CLOT and main Warzone sites as well. 

Please see `bot.py`  

# Engine  
Running in a separate process on the server, the engine runs every 180 seconds and processes ALL tournaments/leagues that are not finished  

Please see `engine.py` 


# Want the Discord Bot in your Server? 
If you want the discord bot in your server please contact -B#0292. If the bot is already in your server you can create special channels that the bot will use to communicate updates to accordingly.  

Create a channel named any of the following:
real-time-ladder  
real_time_ladder  
monthly-template-circuit  
monthly_template_circuit  
clan-league-bot-chat  
clan_league_bot_chat  
