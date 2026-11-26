"""LIVE-tab: evals zijn geen winst (besluit Ferry 05-11-2026).

Alleen funded accounts tellen als geld; evaluaties komen apart; gearchiveerde accounts
komen niet in beeld; de fase komt uit de Accounts-DB en valt alleen gemarkeerd terug op
het naam-voorvoegsel."""
import json
import datetime as dt

import app.viewer as viewer
from app.viewer import classify_account, build_state


def _discord(ts, title, desc):
    body = json.dumps({"username": "MEX", "embeds": [{"title": title, "description": desc}]})
    return json.dumps({"ts": ts, "kind": "discord", "account": "", "result": "x", "body": body})


def _pmt(ts, account, symbol="MGC1!", action="buy", qty=1):
    body = json.dumps({"symbol": symbol, "data": action, "quantity": str(qty),
                       "multiple_accounts": [{"account_id": account, "quantity_multiplier": 1}]})
    return json.dumps({"ts": ts, "kind": "pmt", "account": account, "result": "sent 200 (poging 1)", "body": body})


def _trade(ts0, short, full, qty, pnl):
    """Eén volledige trade (order → fill → exit) op `ts0` (ISO, UTC)."""
    t0 = dt.datetime.fromisoformat(ts0.replace("Z", "+00:00"))
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    sign = "+" if pnl >= 0 else "-"
    return [
        _pmt(iso(t0), full, "MGC1!", "buy", qty),
        _discord(iso(t0 + dt.timedelta(seconds=1)), "📈 MGC1! LONG LIMIT",
                 "Entry 4000.0 | Stop 3990.0 | TP 4010.0 | Qty %d | Contraction" % qty),
        _discord(iso(t0 + dt.timedelta(seconds=5)), "📥 MGC1! FILL LONG",
                 "%s-0k-261105 | %dct @ 4000.0 | SL 3990.0 | TP 4010.0" % (short, qty)),
        _discord(iso(t0 + dt.timedelta(minutes=10)), "📤 MGC1! EXIT 🟢",
                 "%s-0k-261105 | long closed @ 4008.5 | TP | PnL %s$%.1f | MFE 80t · MAE 5t" % (short, sign, abs(pnl))),
    ]


ROSTER = {
    "PAAPEX2700250000040": {"status": "Funded Account", "archived": False},
    "PAAPEX2700250000013": {"status": "Funded Account", "archived": False},
    "APEX27002500000299": {"status": "Active Eval", "archived": False},
    "APEX27002500000243": {"status": "Breached", "archived": True},
    "PAAPEX2700250000016": {"status": "Breached", "archived": True},
}


def test_classify_from_accounts_db_not_prefix():
    assert classify_account("PAAPEX2700250000040", ROSTER) == ("funded", "accounts-db", False)
    assert classify_account("APEX27002500000299", ROSTER) == ("eval", "accounts-db", False)
    # gearchiveerd → hidden, ook al is het een PA-naam
    assert classify_account("PAAPEX2700250000016", ROSTER)[2] is True
    # niet in de roster → voorvoegsel, en dat staat erbij
    assert classify_account("PAAPEX2700250000099", ROSTER) == ("funded", "prefix", False)
    assert classify_account("APEX27002500000301", {}) == ("eval", "prefix", False)


def test_live_totals_count_only_funded(monkeypatch, tmp_path):
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    lines += _trade(ts, "PA040", "PAAPEX2700250000040", 2, 167.9)      # funded, geld
    lines += _trade(ts, "PA013", "PAAPEX2700250000013", 2, -84.1)      # funded, geld
    lines += _trade(ts, "AP299", "APEX27002500000299", 15, 9103.5)     # eval, GEEN geld
    lines += _trade(ts, "PA016", "PAAPEX2700250000016", 1, 500.0)      # gearchiveerd: onzichtbaar
    f = tmp_path / "routed_test.jsonl"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(viewer, "_recent_files", lambda: [str(f)])
    monkeypatch.setattr(viewer, "account_roster", lambda: ROSTER)

    s = build_state()
    fleet, evals = s["fleet"], s["evals"]
    assert fleet["money_scope"] == "funded"
    assert fleet["accounts"] == 2
    assert fleet["realized_today"] == round(167.9 - 84.1, 2)      # de eval-winst zit er NIET in
    assert fleet["trades_today"] == 2
    assert evals["accounts"] == 1 and evals["realized_today"] == 9103.5
    assert evals["note"].startswith("evaluaties")
    assert fleet["hidden_archived"] == 1
    assert fleet["prefix_fallback"] == 0
    shown = {r["account"]: r for r in s["accounts"]}
    assert "PAAPEX2700250000016" not in shown
    assert shown["APEX27002500000299"]["phase"] == "eval"
    assert [r["phase"] for r in s["accounts"]][:2] == ["funded", "funded"]   # funded bovenaan


def test_live_falls_back_to_prefix_when_roster_empty(monkeypatch, tmp_path):
    now = dt.datetime.now(dt.timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    f = tmp_path / "routed_test.jsonl"
    f.write_text("\n".join(_trade(ts, "PA040", "PAAPEX2700250000040", 2, 100.0)) + "\n", encoding="utf-8")
    monkeypatch.setattr(viewer, "_recent_files", lambda: [str(f)])
    monkeypatch.setattr(viewer, "account_roster", lambda: {})
    s = build_state()
    assert s["fleet"]["realized_today"] == 100.0
    assert s["fleet"]["prefix_fallback"] == 1
    assert s["accounts"][0]["phase_source"] == "prefix"
