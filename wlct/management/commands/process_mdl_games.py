from django.core.management.base import BaseCommand
from wlct.management.commands.engine import process_mdl_games

class Command(BaseCommand):
    help = "Runs the engine for cleaning up logs and creating new tournament games every 180 seconds"
    def handle(self, *args, **options):
        process_mdl_games()
