from django.core.management.base import BaseCommand
from wlct.management.commands.engine import check_games

def get_run_time():
    return 180

class Command(BaseCommand):
    help = "Runs the engine for cleaning up logs and creating new tournament games every 180 seconds"
    def handle(self, *args, **options):
        check_games()
