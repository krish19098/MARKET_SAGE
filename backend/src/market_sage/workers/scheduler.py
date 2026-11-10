"""Worker entrypoint: APScheduler jobs in Asia/Kolkata time."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from market_sage.container import Container
from market_sage.core.timeutil import IST, utcnow
from market_sage.workers import jobs

log = logging.getLogger("market_sage.worker")


def run_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    c = Container.build()
    sched = BlockingScheduler(timezone="Asia/Kolkata")

    def live() -> None:
        if c.mds.calendar.session_state(utcnow()).trading_day:
            asyncio.run(jobs.live_session(c, jobs.market_close_today(utcnow())))

    def post_close() -> None:
        if c.mds.calendar.is_trading_day(utcnow().astimezone(IST).date()):
            log.info("post-close: %s", jobs.post_close_job(c))

    sched.add_job(live, "cron", day_of_week="mon-fri", hour=9, minute=10, id="live", max_instances=1)
    sched.add_job(post_close, "cron", day_of_week="mon-fri", hour=18, minute=30, id="post_close", max_instances=1)
    sched.add_job(lambda: log.info("learning: %s", jobs.learning_job(c)), "cron", day_of_week="sun", hour=10,
                  id="learning", max_instances=1)
    sched.add_job(lambda: jobs.heartbeat_job(c), "interval", minutes=5, id="heartbeat")
    log.info("MARKET SAGE worker started (execution mode: %s)", c.settings.execution_mode)
    sched.start()
