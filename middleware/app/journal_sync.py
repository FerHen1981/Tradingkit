"""Runner: turn downloaded Tradovate Fills-CSVs into live Notion Trade Journal rows.

Loop (run on a systemd timer, every ~5-10 min on mex-mw-01):
  scan EXPORTS_DIR/*_Fills.csv
    -> parse + FIFO-pair fills into completed trades   (app.fills_pairing)
    -> join the originating signal from INTENT_DIR      (Signal Price -> slippage)
    -> derive Framework (the El___ script)              (product + account phase)
    -> upsert into the Notion Trade Journal             (app.notion_journal, key = Webhook ID)

Idempotent: the Notion upsert keys on `Webhook ID`, so re-running over the same CSVs never
duplicates. DRY when NOTION_TOKEN / NOTION_JOURNAL_DB are unset (logs what it would write).

Config via env:
  NOTION_TOKEN, NOTION_JOURNAL_DB   Notion integration token + Trade Journal database id
  EXPORTS_DIR   (default /root/exports)        where the Fills-CSVs land
  INTENT_DIR    (default /root/intent-store)   the intents_*.jsonl signal log
  INTENT_WINDOW_S (default 900)                max seconds a signal may precede its entry fill
"""
from __future__ import annotations

import asyncio
import datetime as dt
import glob
import json
import logging
import os

from .fills_pairing import parse_fills_csv, pair_fills, CompletedTrade
from .notion_journal import TradeRecord, NotionTradeJournal

log = logging.getLogger("mex.journal_sync")

# Product root -> asset class (gold vs es), then (asset, phase) -> the EXACT Framework
# relation title in Notion. Titles pulled live from the Framework DB (the 4 funded edges).
# Unknown assets (NQ/YM = eval-only variance) leave Framework empty rather than guess a title.
_ASSET = {"GC": "gold", "MGC": "gold", "ES": "es", "MES": "es"}
FRAMEWORK = {
    ("gold", "funded"): "💎 ΞL TΞSORO — MGC Funded",
    ("gold", "eval"):   "⛏️ ΞL MINΞRO — GC Eval",
    ("es", "funded"):   "👑 ΞL RΞY — MES Funded",
    ("es", "eval"):     "🦁 ΞL LΞON — ES",
}


def _phase(account: str) -> str:
    """PA/funded vs eval from the account name (PAAPEX… = funded PA; APEX… = eval)."""
    return "funded" if account.upper().startswith(("PA", "PAAPEX")) else "eval"


def _sym_root(symbol: str) -> str:
    """'MES1!' -> 'MES'; strips a trailing continuous-contract marker."""
    s = symbol.upper().split("!")[0]
    while s and s[-1].isdigit():
        s = s[:-1]
    return s


class IntentIndex:
    """Signals from intents_*.jsonl, indexed to answer: what signal preceded this entry fill?"""

    def __init__(self, intent_dir: str):
        self._by_key: dict[tuple[str, str, str], list[tuple[dt.datetime, float]]] = {}
        for path in sorted(glob.glob(os.path.join(intent_dir, "intents_*.jsonl"))):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        o = json.loads(line)
                        ts = dt.datetime.fromisoformat(o["ReceivedUtc"].replace("Z", "+00:00"))
                        key = (o["Account"].strip(), _sym_root(o["Symbol"]), o["Action"].upper())
                        self._by_key.setdefault(key, []).append((ts, float(o["Price"])))
            except Exception as exc:
                log.warning("intent parse failed for %s: %r", path, exc)
        for v in self._by_key.values():
            v.sort()

    def signal_price(self, account: str, product: str, entry_action: str,
                     entry_ts: dt.datetime, window_s: float) -> float | None:
        key = (account, _sym_root(product), entry_action.upper())
        best = None
        for ts, price in self._by_key.get(key, []):
            if ts <= entry_ts and (entry_ts - ts).total_seconds() <= window_s:
                best = price          # latest signal at/just before the fill
            elif ts > entry_ts:
                break
        return best


def to_record(t: CompletedTrade, intents: IntentIndex, window_s: float) -> TradeRecord:
    phase = _phase(t.account)
    framework = FRAMEWORK.get((_ASSET.get(t.product.upper(), ""), phase), "")
    entry_action = "BUY" if t.direction == "BUY" else "SELL"
    sig = intents.signal_price(t.account, t.product, entry_action, t.entry_ts, window_s)
    size = "50k"  # from account size if known; Account Types is derived below
    return TradeRecord(
        account_id=t.account, buy_fill_id=t.buy_fill_id, sell_fill_id=t.sell_fill_id,
        direction=t.direction, contract=t.contract, symbol=f"{t.product}1!",
        position_size=t.qty, entry_price=t.entry_price, exit_price=t.exit_price,
        gross_pnl=t.gross_pnl, commissions=t.commissions,
        open_dt=t.entry_ts, close_dt=t.exit_ts,
        framework=framework,
        account_types=f"Apex {size} {'PA' if phase == 'funded' else 'Eval'} (Intraday)",
        tick_size=t.tick_size or None,
        signal_price=sig,
    )


async def run_once() -> dict:
    exports = os.environ.get("EXPORTS_DIR", "/root/exports")
    intent_dir = os.environ.get("INTENT_DIR", "/root/intent-store")
    window_s = float(os.environ.get("INTENT_WINDOW_S", "900"))
    journal = NotionTradeJournal(os.environ.get("NOTION_TOKEN", ""),
                                 os.environ.get("NOTION_JOURNAL_DB", ""))
    if journal.enabled:
        try:
            import httpx  # noqa: F401  — needed for the real upsert path
        except ModuleNotFoundError:
            log.error("httpx not installed in THIS interpreter. Run via the venv: "
                      "`.venv/bin/pip install -r requirements.txt` then "
                      "`.venv/bin/python -m app.journal_sync`.")
            return {"error": "httpx missing (use the venv python)", "trades": 0, "upserted": 0}
    state_file = os.environ.get("STATE_FILE", "journal_sync_state.json")
    intents = IntentIndex(intent_dir)

    # incremental: skip trades already written in a previous run (steady-state stays light)
    done: set[str] = set()
    try:
        with open(state_file) as f:
            done = set(json.load(f))
    except (FileNotFoundError, ValueError):
        pass

    csvs = sorted(glob.glob(os.path.join(exports, "*_Fills.csv")))
    all_trades: list[CompletedTrade] = []
    for csv_path in csvs:
        try:
            all_trades.extend(pair_fills(parse_fills_csv(csv_path)))
        except Exception as exc:
            log.warning("failed to process %s: %r", csv_path, exc)

    ok = skipped = 0
    for t in all_trades:
        key = f"{t.account[-3:]}_{t.buy_fill_id}_{t.sell_fill_id}"
        if key in done:
            skipped += 1
            continue
        try:
            await journal.upsert(to_record(t, intents, window_s))
            ok += 1
            if journal.enabled:      # only remember what was really written
                done.add(key)
        except Exception as exc:
            log.warning("upsert failed for %s: %r", key, exc)

    if journal.enabled:
        try:
            with open(state_file, "w") as f:
                json.dump(sorted(done), f)
        except Exception as exc:
            log.warning("could not write state %s: %r", state_file, exc)

    summary = {"csv_files": len(csvs), "trades": len(all_trades),
               "new": ok, "skipped": skipped, "dry": not journal.enabled}
    log.info("journal_sync run: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(asyncio.run(run_once()))
