"""One alert URL, two payload shapes.

TradingView posts every `alert()` a strategy fires to the SAME webhook, so `/webhook`
receives both the lean order Signal and the non-order f_sendDiscord bodies. These tests
pin which body takes which path — and that a broken order never quietly becomes a card.
"""
import json

import pytest

from app.notices import notice_from_payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIDDLEWARE_SECRET", "t")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("JOURNAL_DB", str(tmp_path / "j.db"))
    monkeypatch.setenv("ACCOUNTS_YAML", json.dumps({
        "notify": {"funded": "hook://funded", "eval": "hook://eval", "default": "hook://all"},
        "strategies": {"ES": {"accounts": ["f1", "e1"]}},
        "accounts": {"f1": {"broker": "pmt_tradovate", "kind": "funded"},
                     "e1": {"broker": "pmt_tradovate", "kind": "eval"}},
    }))
    import importlib
    from fastapi.testclient import TestClient
    from app import config, main, notify
    # Settings reads the environment in its dataclass defaults, so those are frozen at the
    # first import of app.config — reload it (and then main) to pick up this fixture's env.
    importlib.reload(config)
    importlib.reload(main)

    posted: list = []

    async def fake_post(webhook, text, embed=None, *, chat_id="", client=None):
        posted.append({"webhook": webhook, "text": text, "embed": embed})

    monkeypatch.setattr(notify, "_post", fake_post)
    c = TestClient(main.app)
    c.posted = posted
    return c


def pine(title, description):
    return {"username": "MΞX", "embeds": [
        {"title": title, "color": 3447003, "description": description, "footer": {"text": "ES1!"}}]}


ORDER = {"secret": "t", "strategy": "ES", "event": "ENTRY", "action": "buy", "symbol": "ES1!",
         "price": 5312.25, "order_type": "MKT", "dollar_sl": 400, "dollar_tp": 800, "qty": 2}


def test_an_order_body_still_fans_out(client):
    body = client.post("/webhook", json=ORDER).json()
    assert body["dispatched"] is True and body["dry_run"] is True
    assert len(body["results"]) == 2
    assert [p["webhook"] for p in client.posted] == ["hook://funded", "hook://eval"]


@pytest.mark.parametrize("title,desc,kind", [
    ("⏳ ES1! LIMIT EXPIRED", "Pending long cancelled @ 5312.25", "limit_expired"),
    ("🕔 ES1! AUTO FLAT", "Forced flat @ ~5312.25", "auto_flat"),
    ("⛔ ES1! SIGNAL BLOCKED", "Long setup ... blocked by: In position, VWAP veto", "signal_blocked"),
    ("⚙️ ES1! CONFIG", "ver=6.9.1;acct=Apex-1;phase=funded", "config"),
])
def test_pine_notice_on_the_same_webhook_renders_a_card(client, title, desc, kind):
    body = client.post("/webhook?secret=t", json=pine(title, desc)).json()
    assert body == {"accepted": True, "kind": kind, "strategy": "ES", "posted": 2}
    assert client.posted[0]["embed"]["title"].startswith(title[0])   # same emoji, new card
    assert [p["webhook"] for p in client.posted] == ["hook://funded", "hook://eval"]


def test_notice_on_the_webhook_needs_the_url_secret(client):
    assert client.post("/webhook", json=pine("🕔 ES1! AUTO FLAT", "x")).status_code == 401
    assert client.post("/webhook?secret=nope", json=pine("🕔 ES1! AUTO FLAT", "x")).status_code == 401
    assert client.posted == []


def test_a_broken_order_is_an_error_not_a_card(client):
    """A Signal missing a required field must still 422 — never get downgraded to a
    pretty notice, which would hide a dropped trade."""
    broken = {k: v for k, v in ORDER.items() if k != "action"}
    assert client.post("/webhook?secret=t", json=broken).status_code == 422
    assert client.posted == []


def test_unrecognisable_body_is_still_a_422(client):
    assert client.post("/webhook?secret=t", json={"foo": "bar"}).status_code == 422
    assert client.post("/webhook?secret=t", content=b"").status_code == 422


def test_plain_text_alert_line_renders_on_the_default_channel(client):
    """No title to classify on means no strategy to attribute it to, so it lands on the
    default channel rather than being fanned across the funded+eval streams."""
    body = client.post("/webhook?secret=t", content="MEX | ES1! | something happened".encode()).json()
    assert body["kind"] == "notice" and body["strategy"] == ""
    assert [p["webhook"] for p in client.posted] == ["hook://all"]


def test_suppressed_kind_is_accepted_but_not_posted(client):
    body = client.post("/webhook?secret=t", json=pine("📈 ES1! LONG LIMIT", "x")).json()
    assert body == {"accepted": True, "kind": "entry_intent", "posted": 0, "reason": "kind suppressed"}
    assert client.posted == []


def test_dedicated_notice_endpoint_takes_the_same_bodies(client):
    body = client.post("/notice?secret=t&strategy=ES",
                       json=pine("🕔 MES1! AUTO FLAT", "Forced flat @ ~5312.25")).json()
    assert body["kind"] == "auto_flat" and body["strategy"] == "ES"
    assert client.post("/notice?secret=t", json={"foo": "bar"}).status_code == 422


def test_notice_is_journalled_and_never_dispatches(client):
    client.post("/webhook?secret=t", json=pine("🔒 ES1! DAY HALT", "DLL hit | Today: $-1240.00"))
    events = client.get("/journal?secret=t&limit=10").json()["events"]
    kinds = [e["kind"] for e in events]
    assert "notice" in kinds and "dispatch" not in kinds
    assert notice_from_payload(pine("🔒 ES1! DAY HALT", "x")).kind == "day_halt"


def test_journal_filters_answer_did_it_arrive(client):
    client.post("/webhook?secret=t", json=pine("⛔ ES1! SIGNAL BLOCKED", "Long ... blocked by: DD guard"))
    client.post("/webhook", json=ORDER)
    client.post("/webhook?secret=t", json={"secret": "t", "strategy": "ES"})   # broken order -> error

    notices = client.get("/journal?secret=t&kind=notice").json()["events"]
    assert [e["detail"]["kind"] for e in notices] == ["signal_blocked"]
    assert notices[0]["detail"]["title"] == "⛔ ES1! SIGNAL BLOCKED"

    hits = client.get("/journal?secret=t&kind=notice,error&contains=BLOCKED").json()["events"]
    assert len(hits) == 1 and hits[0]["kind"] == "notice"

    assert [e["kind"] for e in client.get("/journal?secret=t&kind=error").json()["events"]] == ["error"]
    assert len(client.get("/journal?secret=t&strategy=ES").json()["events"]) >= 2


# ---------------------------------------------------------------- Pine v6.9.2 notices
# The literal bodies f_mwNotice builds — string-concatenated in Pine exactly like these.
def mw(kind, text, data="{}", secret="t", strategy="ES", symbol="ES1!"):
    return ('{"secret":"' + secret + '","strategy":' + json.dumps(strategy) +
            ',"kind":"' + kind + '","symbol":"' + symbol + '","text":"' + text +
            '","data":' + data + '}').encode()


def test_pine_signal_blocked_notice(client):
    reasons = "Day halt: Daily Loss, MAE guard (risk > cap)"
    body = mw("signal_blocked",
              "Long setup meets all strategy rules but was blocked by: " + reasons,
              '{"direction":"Long","reasons":"' + reasons + '"}')
    out = client.post("/webhook", content=body).json()
    assert out == {"accepted": True, "kind": "signal_blocked", "strategy": "ES", "posted": 2}
    f = {x["name"]: x["value"] for x in client.posted[0]["embed"]["fields"]}
    assert f["Direction"] == "Long"
    assert f["Blocked by (2)"] == "• Day halt: Daily Loss\n• MAE guard (risk > cap)"


def test_pine_auto_flat_notice(client):
    body = mw("auto_flat", "Forced flat @ ~5312.25", '{"price":"5312.25"}')
    out = client.post("/webhook", content=body).json()
    assert out["kind"] == "auto_flat"
    f = {x["name"]: x["value"] for x in client.posted[0]["embed"]["fields"]}
    assert f["Flat at"] == "~5312.25"


def test_pine_config_notice(client):
    cfg = "ver=6.9.2;acct=Apex-50k-1;qty=2;entry=limit50;stop=Swing;R=2.0;DLL=1000;phase=funded"
    out = client.post("/webhook", content=mw("config", cfg)).json()
    assert out["kind"] == "config"
    f = {x["name"]: x["value"] for x in client.posted[0]["embed"]["fields"]}
    assert f["Version"] == "6.9.2" and f["Phase"] == "funded" and f["Daily loss limit"] == "1000"


def test_structured_notice_authenticates_on_its_body_secret(client):
    """Pine puts the secret in the body, like an order — no ?secret= on the URL needed."""
    assert client.post("/webhook", content=mw("auto_flat", "x")).status_code == 200
    assert client.post("/webhook", content=mw("auto_flat", "x", secret="wrong")).status_code == 401
    assert len(client.posted) == 2   # only the authenticated one, on both channels


def test_a_broken_order_is_still_not_a_notice(client):
    """The kind-first check must not let a failed Signal through as a card."""
    assert client.post("/webhook?secret=t", json={"secret": "t", "strategy": "ES",
                                                  "action": "buy"}).status_code == 422
    assert client.posted == []
