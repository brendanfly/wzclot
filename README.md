# Warzone Custom Tournament and Ladder
Warzone CLOT focused around custom leagues and tournaments, initially developed by -B and now publically available to contribute to.

# Setting up your test server
This web application is written in the Django framework and the server side pieces are entirely written in python. The database used is postgreSQL and connection pooling with max 20 active connections runs on the server.
To setup a local test site you will need to do the following. 

Install Python 3.7 - 
Install virtualenv - 
Install postgreSQL 11.6-3 - 



# Object Model
There are a handful of top level objects that are used on the CLOT



# Bot
The Warzone bot is able to run in any server and was created to integrate with the CLOT directly. There is a real-time ladder, clan-league updates, and general rankings and statistics from the CLOT and main Warzone sites as well. 

Please see bot.py

# Engine
Running in a separate process on the server, the engine runs every 180 seconds and processes ALL tournaments/leagues that are not finished

Please see engine.py
