from __future__ import annotations

import html
import os
import time

import requests

from .models import Job, Verdict


class Telegram:
    """Sends HTML messages to one chat. Without credentials (or with dry_run) it prints.
    send() returns True on success so callers can keep unsent messages for the next run."""

    def __init__(self, dry_run: bool = False):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.dry = dry_run or not (self.token and self.chat)
        self.broken = ""   # set on a config error (bad chat id / token): stop trying this run

    def send(self, text: str) -> bool:
        text = text[:4000]
        if self.dry:
            print("---- telegram (dry) ----\n" + text)
            return True
        if self.broken:
            return False
        for _ in range(3):
            try:
                r = requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage", json={
                    "chat_id": self.chat, "text": text, "parse_mode": "HTML",
                    "disable_web_page_preview": True}, timeout=20)
            except requests.RequestException as e:   # network hiccup: retry
                print(f"telegram send failed: {e}")
                time.sleep(3)
                continue
            if r.ok:
                time.sleep(1.1)   # stay under Telegram's ~1 msg/sec per chat
                return True
            try:
                body = r.json()
            except ValueError:
                body = {}
            if r.status_code == 429:
                time.sleep(int(body.get("parameters", {}).get("retry_after", 5)))
                continue
            desc = body.get("description", r.text[:200])
            print(f"telegram send failed: {r.status_code} {desc}")
            if r.status_code < 500:   # 400/401/403 = configuration problem, retrying won't help
                self.broken = desc
                print("  -> check the TELEGRAM_CHAT_ID / TELEGRAM_BOT_TOKEN secrets, and that you "
                      "pressed Start in the bot. Unsent messages stay queued for the next run.")
                return False
            time.sleep(3)
        return False


def _e(s: str) -> str:
    return html.escape(s or "", quote=False)


def _years(v: Verdict) -> str:
    if not v.years:
        return "לא צוין"
    lo, hi = v.years
    return f"{lo}-{hi} שנים" if hi is not None else (f"{lo}+ שנים" if lo else "ללא ניסיון")


def job_message(job: Job, v: Verdict) -> str:
    head = "🟢 <b>משרה חדשה שמתאימה</b>" if v.status == "match" else \
           "🟡 <b>משרה חדשה – לבדיקה</b> (לא צוין ותק)"
    lines = [head, f"<b>{_e(job.company)}</b> — {_e(job.title)}"]
    meta = [f"📍 {_e(job.location)}" if job.location else "", f"⏳ ותק: {_years(v)}"]
    if v.grad_friendly:
        meta.append("🎓 מתאים לבוגרים")
    lines.append(" | ".join(m for m in meta if m))
    if v.requirements:
        lines.append("\n<b>דרישות עיקריות:</b>")
        lines += [f"• {_e(r)}" for r in v.requirements]
    lines.append(f"\n🔗 {_e(job.url)}")
    return "\n".join(lines)
