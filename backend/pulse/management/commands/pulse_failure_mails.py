import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from pulse.failure_mail import run_hourly, run_once

logger = logging.getLogger("pulse.mail")


class Command(BaseCommand):
    help = ("Email new failed transactions to PULSE_FAILURE_EMAILS once a minute, and insufficient-funds failures "
            "once an hour as an Excel sheet.")

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="check one time and exit")
        parser.add_argument("--dry-run", action="store_true", help="print what would be sent, send nothing")
        parser.add_argument("--every", type=int, default=60, help="seconds between checks")

    def handle(self, *args, once=False, dry_run=False, every=60, **options):
        while True:
            try:
                run_once(dry_run=dry_run)
            except Exception:
                logger.exception("Failure mail check failed")
            try:
                run_hourly(dry_run=dry_run)
            except Exception:
                logger.exception("Hourly insufficient-funds mail failed")
            finally:
                close_old_connections()
            if once:
                return
            time.sleep(max(every, 15))
