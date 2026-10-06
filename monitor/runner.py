"""One monitoring pass. Meant to run every ~30 minutes (GitHub Actions cron).

  python -m monitor                 # normal run (Telegram if env vars are set)
  python -m monitor --dry-run       # print messages instead of sending
  python -m monitor --only valens   # just companies whose name contains "valens"
"""
from __future__ import annotations

import argparse
import html
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import yaml

from . import detect as detector
from .adapters import ADAPTERS, source_key
from .filters import Filters
from .http import Http
from .models import Job
from .notify import Telegram, job_message
from .store import DETECTION_VERSION, Store

REDETECT_AFTER = 24 * 3600   # retry failed detections once a day


@dataclass
class Feed:
    ats: str
    board: str
    company: str
    key: str


@dataclass
class Result:
    feed: Feed
    jobs: list[Job] = field(default_factory=list)       # every new job (not seen before)
    candidates: set[str] = field(default_factory=set)   # keys of new jobs worth classifying
    error: str = ""
    seconds: float = 0.0
    fetched: int = 0
    detail_errors: list[str] = field(default_factory=list)


def plan(c: dict, store: Store) -> tuple[str, tuple[str, str] | None]:
    """Decide how to get a company's feed: ("ready", (ats, board)) | ("detect", None) | ("skip", None)."""
    ats, board, status = c.get("ats"), c.get("board"), c.get("status")
    needs_lookup = status == "detect" or (ats == "comeet" and board and "|" not in board)
    if ats and board and not needs_lookup:
        return "ready", (ats, board)
    if not needs_lookup:
        return "skip", None          # "boards" / "custom": phase 2
    target = board if ats == "comeet" else (c.get("careers") or c.get("domain"))
    if not target or target == "TBD":
        return "skip", None
    cached = store.detection(c["name"])
    ttl = 7 * REDETECT_AFTER if cached and cached[2] else REDETECT_AFTER
    if cached and cached[4] == DETECTION_VERSION and time.time() - cached[3] < ttl:
        return ("ready", (cached[0], cached[1])) if cached[2] else ("skip", None)
    return "detect", None


def run_detection(c: dict, http: Http) -> tuple[tuple[str, str] | None, str]:
    """Network part of detection (thread-safe; no DB access)."""
    ats, board = c.get("ats"), c.get("board")
    target = board if ats == "comeet" else (c.get("careers") or c.get("domain"))
    trace: list[str] = []
    try:
        found = detector.detect(http, target, trace=trace)
        return found, "" if found else "; ".join(trace)[:400]
    except Exception as e:
        return None, (f"{type(e).__name__}: {e}; " + "; ".join(trace))[:400]


def process(feed: Feed, http: Http, flt: Filters, known: set[str]) -> Result:
    t0, res = time.time(), Result(feed)
    fetch, details = ADAPTERS[feed.ats]
    try:
        jobs = fetch(http, feed.board, feed.company)
        res.fetched = len(jobs)
        for job in jobs:
            if job.job_id in known:
                continue
            if flt.is_candidate(job):
                if job.description is None and details:
                    try:
                        details(http, feed.board, job)
                    except Exception as e:
                        # Leave this ID unseen: retry the description next run, before classifying.
                        res.detail_errors.append(f"{job.title[:70]}: {type(e).__name__}: {e}"[:200])
                        continue
                res.candidates.add(job.key)
            res.jobs.append(job)
    except Exception as e:
        res.error = f"{type(e).__name__}: {e}"[:400]
        traceback.print_exc()
    res.seconds = time.time() - t0
    return res


def run(args) -> int:
    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    companies = yaml.safe_load(open(args.companies, encoding="utf-8"))["companies"]
    store, tg = Store(args.db, snapshot=args.dry_run), Telegram(dry_run=args.dry_run)
    flt = Filters(cfg.get("filters", {}))
    rcfg = cfg.get("run", {})

    # 1) Which feeds to poll this run (detecting unknown ATSs in parallel, cached in the DB).
    feeds: dict[str, Feed] = {}
    detect_report: list[str] = []
    skipped: list[str] = []
    chosen = [c for c in companies if not args.only or args.only.lower() in c["name"].lower()]
    plans = {c["name"]: plan(c, store) for c in chosen}
    pending = [c for c in chosen if plans[c["name"]][0] == "detect"]
    if pending:
        with ThreadPoolExecutor(max_workers=int(rcfg.get("workers", 8))) as ex:   # one session per thread
            found_all = list(ex.map(lambda c: run_detection(c, Http(timeout=15, retries=2)), pending))
        for c, (found, note) in zip(pending, found_all):
            store.save_detection(c["name"], *(found or (None, None)), note=note)
            plans[c["name"]] = ("ready", found) if found else ("skip", None)
            if found:
                ok = "✅" if found[0] in ADAPTERS else "🕓 (adapter בשלב 2)"
                detect_report.append(f"• {c['name']} → {found[0]} {ok}")
            else:
                detect_report.append(f"• {c['name']} → ❌ לא זוהה  [{note}]")
    for c in chosen:
        state, found = plans[c["name"]]
        if state != "ready" or not found:
            skipped.append(c["name"])
            continue
        ats, board = found
        if ats not in ADAPTERS:
            skipped.append(f"{c['name']} ({ats})")
            continue
        key = source_key(ats, board)
        feeds.setdefault(key, Feed(ats, board, c["name"], key))
    store.commit()
    if detect_report:
        print("ATS detection:\n" + "\n".join(detect_report))
        tg.send("🔎 <b>זיהוי מערכות גיוס</b>\n" + "\n".join(r.split("  [")[0] for r in detect_report))

    # 2) Poll all feeds in parallel (network-bound).
    known = {k: store.known_ids(k) for k in feeds}
    baseline = {k: not store.source_seen(k) for k in feeds}
    results: list[Result] = []
    with ThreadPoolExecutor(max_workers=int(rcfg.get("workers", 8))) as ex:
        futs = [ex.submit(process, f, Http(), flt, known[k]) for k, f in feeds.items()]
        for fut in as_completed(futs):
            results.append(fut.result())

    # 3) Classify and store. Messages are queued in the DB, then sent in step 4.
    baseline_hits, baseline_total, baseline_done = 0, 0, 0
    baseline_reviews = 0
    baseline_max = int(rcfg.get("baseline_max", 10))
    baseline_review_max = int(rcfg.get("baseline_review_max", 5))
    alert_after = int(rcfg.get("failure_alert_after", 6))
    send_review = bool(cfg.get("notify", {}).get("send_review", True))
    for r in sorted(results, key=lambda r: r.feed.company):
        k = r.feed.key
        if r.error:
            n = store.mark_failure(k, r.error)
            print(f"{r.feed.company:28} {r.feed.ats:15} ERROR (x{n}) {r.error[:150]}")
            if n >= alert_after and store.should_alert(k):
                if tg.send(f"⚠️ המקור <b>{html.escape(r.feed.company)}</b> ({r.feed.ats}) "
                           f"נכשל {n} פעמים ברצף:\n<code>{html.escape(r.error[:300])}</code>"):
                    store.mark_alerted(k)
            store.commit()
            continue
        for job in r.jobs:
            if job.key not in r.candidates:
                store.add_job(job, "skip")
                continue
            v = flt.classify(job)
            msg = None
            if baseline[k]:
                if v.status == "match":
                    baseline_hits += 1
                    if baseline_hits <= baseline_max:
                        msg = job_message(job, v)
                elif v.status == "review" and send_review:
                    baseline_reviews += 1
                    if baseline_reviews <= baseline_review_max:
                        msg = job_message(job, v)
            elif v.status == "match" or (v.status == "review" and send_review):
                msg = job_message(job, v)
            store.add_job(job, v.status, v.reason, msg)
            if v.status != "reject":
                print(f"    {v.status:6} {job.title[:70]}  ({v.reason})")
        if baseline[k]:
            baseline_total += r.fetched
            baseline_done += 1
        previous_count, _ = store.source_counts(k)
        store.mark_ok(k, r.fetched)
        _, empty_runs = store.source_counts(k)
        store.commit()
        print(f"{r.feed.company:28} {r.feed.ats:15} fetched={r.fetched:4} new={len(r.jobs):4} "
              f"cand={len(r.candidates):3} {r.seconds:5.1f}s{' [baseline]' if baseline[k] else ''}")
        if not r.fetched and (baseline[k] or previous_count or empty_runs == 3):
            print(f"    WARNING empty feed (x{empty_runs}): verify board/endpoint; "
                  "an HTTP success does not establish that no jobs are open")
        for error in r.detail_errors:
            print(f"    RETRY details next run: {error}")

    # 4) Send: baseline summary, then queued job messages (incl. ones a failed run left behind).
    if baseline_done:
        tg.send(f"✅ <b>קו בסיס נשמר</b>: {baseline_total} משרות מ-{baseline_done} מקורות.\n"
                f"מעכשיו תקבל רק משרות שנפתחות מכאן והלאה."
                + f"\n\nמתוכן {baseline_hits} סומנו כמתאימות ו-{baseline_reviews} לבדיקה. "
                f"נשלחות עד {baseline_max} מתאימות ועד {baseline_review_max} לבדיקה.")
    queue = store.pending()
    sent = 0
    for key, msg in queue[: int(rcfg.get("max_messages", 20))]:
        if not tg.send(msg):
            break
        store.mark_notified(key)
        store.commit()  # checkpoint each confirmed delivery
        sent += 1
    store.commit()
    if queue:
        mode = "previewed" if args.dry_run else "sent"
        print(f"telegram: {mode} {sent}/{len(queue)} queued messages")
    polled_entries = sum(state == "ready" and bool(found) and found[0] in ADAPTERS
                         for state, found in plans.values())
    print(f"coverage: configured={len(chosen)} polled_entries={polled_entries} "
          f"feeds={len(feeds)} skipped={len(skipped)}")
    if args.dry_run:
        print("dry-run: preview only; persistent state and delivery flags are unchanged")
    if skipped and args.verbose:
        print("not polled (phase 2 / undetected):", ", ".join(skipped))
    store.close()
    return 1 if tg.failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="monitor")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--companies", default="companies.yaml")
    ap.add_argument("--db", default="state/jobs.db")
    ap.add_argument("--only", help="poll only companies whose name contains this text")
    ap.add_argument("--dry-run", action="store_true", help="print messages instead of sending")
    ap.add_argument("-v", "--verbose", action="store_true")
    raise SystemExit(run(ap.parse_args()))
