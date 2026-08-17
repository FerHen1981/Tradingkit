"""Notice cards — the non-order strategy events (limit expired, auto flat, signal
blocked, config, ...).

The payloads below are the exact bodies `f_sendDiscord` builds in the Pine scripts, so
these tests fail the moment the parser drifts from what the strategies actually send.
"""
import pytest

from app.config import AccountMap
from app.notices import (KIND_CARDS, Notice, build_notice_embed, format_notice,
                         notice_from_payload, parse_config, parse_title, strategy_from_symbol)
from app.notify import COLOR_CRITICAL, COLOR_FLAT, COLOR_INFO, COLOR_WARNING


def pine(title: str, description: str) -> dict:
    """The literal body of f_sendDiscord(_title, _desc)."""
    return {"username": "MΞX ΞL RΞY", "embeds": [
        {"title": title, "color": 3447003, "description": description,
         "footer": {"text": "ES1!"}}]}


def fields(embed: dict) -> dict:
    return {f["name"]: f["value"] for f in embed["fields"]}


# ---------------------------------------------------------------- title parsing
@pytest.mark.parametrize("title,kind,symbol", [
    ("⏳ ES1! LIMIT EXPIRED", "limit_expired", "ES1!"),
    ("🕔 ES1! AUTO FLAT", "auto_flat", "ES1!"),
    ("⛔ ES1! SIGNAL BLOCKED", "signal_blocked", "ES1!"),
    ("⚙️ GC1! CONFIG", "config", "GC1!"),
    ("🔒 NQ1! DAY HALT", "day_halt", "NQ1!"),
    ("💰 ES1! PAYOUT 2 READY", "payout_ready", "ES1!"),
    ("🪜 ES1! PA DERISK", "derisk", "ES1!"),
    ("📥 ES1! FILL LONG", "fill", "ES1!"),
    ("📤 ES1! EXIT 🟢", "exit", "ES1!"),
    ("📈 ES1! LONG LIMIT", "entry_intent", "ES1!"),
])
def test_parse_title_maps_every_pine_event(title, kind, symbol):
    assert parse_title(title) == (kind, symbol)


def test_limit_expired_is_not_mistaken_for_an_entry_limit():
    assert parse_title("⏳ ES1! LIMIT EXPIRED")[0] == "limit_expired"
    assert parse_title("📈 ES1! LONG LIMIT")[0] == "entry_intent"


def test_unknown_title_falls_back_to_a_generic_notice():
    assert parse_title("🤷 something new")[0] == "notice"
    assert build_notice_embed(Notice(kind="notice", text="hi"))["color"] == COLOR_INFO


@pytest.mark.parametrize("symbol,strategy", [
    ("ES1!", "ES"), ("GC1!", "GC"), ("MNQ1!", "MNQ"), ("ESZ2025", "ES"), ("", "")])
def test_strategy_from_symbol(symbol, strategy):
    assert strategy_from_symbol(symbol) == strategy


# ---------------------------------------------------------------- the four cards
def test_limit_expired_card():
    note = notice_from_payload(pine("⏳ ES1! LIMIT EXPIRED", "Pending long cancelled @ 5312.25"))
    assert (note.kind, note.symbol, note.strategy) == ("limit_expired", "ES1!", "ES")
    embed = build_notice_embed(note)
    assert embed["title"] == "⏳ ES1! · Limit expired"
    assert embed["color"] == COLOR_FLAT
    assert fields(embed)["Direction"] == "Long"
    assert fields(embed)["Limit price"] == "5312.25"
    assert "never filled" in fields(embed)["Outcome"]


def test_auto_flat_card():
    note = notice_from_payload(pine("🕔 ES1! AUTO FLAT", "Forced flat @ ~5312.25"))
    embed = build_notice_embed(note)
    assert note.kind == "auto_flat"
    assert embed["title"] == "🕔 ES1! · Auto flat"
    assert fields(embed)["Flat at"] == "~5312.25"
    assert "Force-flat window" in fields(embed)["Reason"]


def test_signal_blocked_card_lists_every_reason():
    note = notice_from_payload(pine(
        "⛔ ES1! SIGNAL BLOCKED",
        "Long setup meets all strategy rules but was blocked by: In position, VWAP veto, CVD streak"))
    embed = build_notice_embed(note)
    assert note.kind == "signal_blocked"
    assert embed["color"] == COLOR_WARNING
    assert fields(embed)["Direction"] == "Long"
    blocked = fields(embed)["Blocked by (3)"]
    assert blocked == "• In position\n• VWAP veto\n• CVD streak"


def test_config_card_breaks_the_cfg_string_into_fields():
    cfg = ("ver=6.9.1;acct=Apex-50k-1;qty=2;entry=limit50;expiry=8;stop=Swing;tp=Fixed (units);"
           "R=2.0;guard=1;DLL=1200;phase=funded;tz=America/New_York;vwapVeto=1;cvd=0")
    note = notice_from_payload(pine("⚙️ ES1! CONFIG", cfg))
    embed = build_notice_embed(note)
    got = fields(embed)
    assert note.kind == "config"
    assert embed["title"] == "⚙️ ES1! · Config"
    assert got["Version"] == "6.9.1"
    assert got["Account"] == "Apex-50k-1"
    assert got["Phase"] == "funded"
    assert got["Daily loss limit"] == "1200"
    assert got["Timezone"] == "America/New_York"
    # everything not headlined still shows up, nothing is dropped
    rest = got["Other settings (3)"]
    assert "expiry=8" in rest and "vwapVeto=1" in rest and "cvd=0" in rest


def test_parse_config_ignores_junk_chunks():
    assert parse_config("a=1;;b=2;garbage;c=") == {"a": "1", "b": "2", "c": ""}


def test_config_card_survives_an_empty_config_string():
    embed = build_notice_embed(notice_from_payload(pine("⚙️ ES1! CONFIG", "")))
    assert embed["fields"] == []


# ---------------------------------------------------------------- other kinds
def test_day_halt_is_critical_and_keeps_its_detail():
    note = notice_from_payload(pine("🔒 ES1! DAY HALT", "DLL hit | Today: $-1240.00"))
    embed = build_notice_embed(note)
    assert embed["color"] == COLOR_CRITICAL
    assert fields(embed)["Detail"] == "DLL hit | Today: $-1240.00"


def test_every_declared_kind_renders():
    for kind in KIND_CARDS:
        embed = build_notice_embed(Notice(kind=kind, symbol="ES1!", strategy="ES", text="x"))
        assert embed["title"].endswith(KIND_CARDS[kind][1])
        assert isinstance(embed["color"], int)


# ---------------------------------------------------------------- input shapes
def test_structured_body_needs_no_text_parsing():
    note = notice_from_payload({"kind": "signal_blocked", "symbol": "GC1!", "strategy": "GC",
                                "data": {"direction": "Short", "reasons": ["MAE guard", "DD guard"]}})
    got = fields(build_notice_embed(note))
    assert got["Direction"] == "Short"
    assert got["Blocked by (2)"] == "• MAE guard\n• DD guard"


def test_structured_data_wins_over_the_parsed_text():
    note = notice_from_payload({"kind": "limit_expired", "symbol": "ES1!", "text": "Pending long cancelled @ 1",
                                "data": {"direction": "Short", "price": "5999.75"}})
    got = fields(build_notice_embed(note))
    assert got["Direction"] == "Short" and got["Limit price"] == "5999.75"


def test_plain_text_body_still_produces_a_card():
    note = notice_from_payload({"text": "⚙️ ES1! CONFIG ver=6.9.1;acct=x"})
    assert note.kind == "notice"          # no title to classify on
    assert build_notice_embed(note)["fields"][0]["value"].startswith("⚙️")


def test_query_strategy_overrides_the_symbol_guess():
    note = notice_from_payload(pine("🕔 MES1! AUTO FLAT", "Forced flat @ ~5312.25"), strategy="ES")
    assert note.strategy == "ES"          # micro contract, but it trades the ES strategy


def test_plain_text_fallback_line():
    note = notice_from_payload(pine("⛔ ES1! SIGNAL BLOCKED", "Long setup ... blocked by: In position"))
    assert format_notice(note) == "⛔ **ES1! SIGNAL BLOCKED** — Long setup ... blocked by: In position"


# ---------------------------------------------------------------- routing
def test_a_notice_goes_to_every_channel_the_strategy_touches():
    amap = AccountMap(
        strategies={"ES": {"accounts": ["f1", "e1", "f2"]}},
        accounts={"f1": {"kind": "funded"}, "e1": {"kind": "eval"}, "f2": {"kind": "funded"}},
        notify_channels={"funded": "hook://funded", "eval": "hook://eval", "default": "hook://all"})
    assert amap.notify_webhooks_for_strategy("ES", {}) == ["hook://funded", "hook://eval"]


def test_a_notice_for_a_strategy_without_accounts_uses_the_fallback():
    amap = AccountMap(strategies={"ES": {}}, notify_channels={"default": "hook://all"})
    assert amap.notify_webhooks_for_strategy("ES", {}) == ["hook://all"]
    assert amap.notify_webhooks_for_strategy("ES", {"default": "env://all"}) == ["hook://all"]
    assert AccountMap().notify_webhooks_for_strategy("ES", {}) == []
