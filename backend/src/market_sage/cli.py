"""MARKET SAGE command-line interface."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import date, datetime, time

from market_sage.core.timeutil import IST, utcnow


def _container():  # type: ignore[no-untyped-def]
    from market_sage.container import Container

    return Container.build()


def cmd_migrate(_: argparse.Namespace) -> None:
    from market_sage.db.engine import upgrade_to_head

    upgrade_to_head()
    print("database migrated to head")


def cmd_hash_password(_: argparse.Namespace) -> None:
    from market_sage.api.auth import hash_password

    pw = getpass.getpass("New password: ")
    if len(pw) < 12 or pw != getpass.getpass("Repeat: "):
        sys.exit("password must be at least 12 characters and match")
    print(hash_password(pw))


def cmd_totp_secret(_: argparse.Namespace) -> None:
    import pyotp

    secret = pyotp.random_base32()
    print("MARKET_SAGE_AUTH_TOTP_SECRET=" + secret)
    print("Provisioning URI:", pyotp.TOTP(secret).provisioning_uri("owner", issuer_name="MARKET SAGE"))


def cmd_vapid_keys(_: argparse.Namespace) -> None:
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    print("MARKET_SAGE_VAPID_PUBLIC_KEY=" + b64(pub))
    print("MARKET_SAGE_VAPID_PRIVATE_KEY=" + b64(priv))


def cmd_ingest_nse(a: argparse.Namespace) -> None:
    c = _container()
    rep = c.mds.ingest_nse_eod(date.fromisoformat(a.start), date.fromisoformat(a.end))
    print(json.dumps(rep.__dict__, default=str, indent=2))


def cmd_post_close(_: argparse.Namespace) -> None:
    from market_sage.workers.jobs import post_close_job

    print(json.dumps(post_close_job(_container()), default=str, indent=2))


def cmd_learn(_: argparse.Namespace) -> None:
    from market_sage.workers.jobs import learning_job

    print(json.dumps(learning_job(_container()), default=str, indent=2))


def cmd_verify_ledger(_: argparse.Namespace) -> None:
    c = _container()
    problems = c.ledger.verify()
    print(f"{c.ledger.count()} predictions; {len(problems)} integrity problems")
    for p in problems[:50]:
        print(" -", p)
    sys.exit(1 if problems else 0)


def cmd_worker(_: argparse.Namespace) -> None:
    from market_sage.workers.scheduler import run_worker

    run_worker()


def cmd_serve(a: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("market_sage.api.app:app", host=a.host, port=a.port)


def cmd_demo(a: argparse.Namespace) -> None:
    """Populate a SYNTHETIC demo: planted-signal fixture market, gated model, replayed decisions, paper trades.

    Every record is labelled synthetic; replayed ledger entries carry the real creation time and
    provenance mode SYNTHETIC_REPLAY. Nothing here is market data or evidence of real performance.
    """
    from market_sage.core.config import get_settings
    from market_sage.data.providers.fixture import SyntheticMarket
    from market_sage.learning.controlled import GateCriteria, run_learning_cycle
    from market_sage.workers.jobs import decision_job, paper_session_job

    st = get_settings()
    if st.data_mode != "fixture":
        sys.exit("refusing: set MARKET_SAGE_DATA_MODE=fixture for the synthetic demo (keeps real and synthetic apart)")
    c = _container()
    end = c.mds.calendar.latest_completed_session(utcnow())
    start = date(end.year - a.years, end.month, 1)
    market = SyntheticMarket(c.mds.calendar, start, end, n_stocks=a.stocks, seed=a.seed, planted_signal=a.signal)
    rep = c.mds.ingest_fixture(market)
    print(f"SYNTHETIC data ingested: {rep.instruments} instruments, {rep.rows} bars")
    sessions = c.mds.calendar.trading_days(start, end)
    replay = sessions[-a.replay:]
    learn_cut = sessions[-a.replay - 1]
    res = run_learning_cycle(c.store, c.registry, learn_cut, is_synthetic=True, n_folds=3,
                             criteria=GateCriteria(holdout_sessions=60))
    print(f"learning cycle at {learn_cut}: promoted={res.promoted} failed={res.gate_report['failed_checks']}")
    for d in replay:
        paper_session_job(c, d)
        out = decision_job(c, d, datetime.combine(d, time(18, 0), tzinfo=IST),
                           provenance_extra={"mode": "SYNTHETIC_REPLAY"})
        if out["buy"]:
            print(f"{d}: {out['buy']} BUY / {out['evaluated']} evaluated, {out['paper_intents']} paper intents")
    print("positions assessed:", len(c.monitor.assess_all(utcnow())))
    print("evaluations:", c.evaluator.evaluate_pending())
    print("alert outcomes:", c.performance.evaluate_alerts())
    print("ledger integrity problems:", len(c.ledger.verify()))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="market-sage", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("migrate", cmd_migrate), ("hash-password", cmd_hash_password), ("totp-secret", cmd_totp_secret),
                     ("vapid-keys", cmd_vapid_keys), ("post-close", cmd_post_close), ("learn", cmd_learn),
                     ("verify-ledger", cmd_verify_ledger), ("worker", cmd_worker)]:
        sub.add_parser(name).set_defaults(fn=fn)
    ing = sub.add_parser("ingest-nse", help="ingest NSE full bhavcopy (with delivery) for a date range")
    ing.add_argument("start")
    ing.add_argument("end")
    ing.set_defaults(fn=cmd_ingest_nse)
    srv = sub.add_parser("serve")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    srv.set_defaults(fn=cmd_serve)
    demo = sub.add_parser("demo", help="populate a clearly-labelled SYNTHETIC demo")
    demo.add_argument("--years", type=int, default=5)
    demo.add_argument("--stocks", type=int, default=24)
    demo.add_argument("--seed", type=int, default=5)
    demo.add_argument("--signal", type=float, default=3.0)
    demo.add_argument("--replay", type=int, default=40)
    demo.set_defaults(fn=cmd_demo)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
