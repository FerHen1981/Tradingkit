"""Notify channel: message building, severity, rate-limiting, transport and routing.

Nothing here touches the network — `_post` is exercised through a fake httpx client so
we assert on the exact JSON body Discord/Telegram would receive.
"""
import asyncio

import pytest

from app.config import AccountMap
from app.models import Signal
from app.notify import (COLOR_CRITICAL, COLOR_LONG, COLOR_LOSS, COLOR_SHORT, COLOR_WIN,
                        AlertLimiter, _post, _telegram_request, alert_failures, build_embed,
                        build_failure, classify_failure, format_trade, notify_trade,
                        notify_trade_routes, severity_of)

DISCORD = "https://discord.com/api/webhooks/1/abc"
TELEGRAM = "https://api.telegram.org/bot123:XYZ/sendMessage"


def sig(**kw) -> Signal:
    base = dict(secret="s", strategy="ES", event="ENTRY", action="buy", symbol="ES1!",
                price=5312.25, dollar_sl=400, dollar_tp=800, qty=2)
    return Signal(**{**base, **kw})


def res(account, status="sent", **kw) -> dict:
    return {"account": account, "status": status, **kw}


class FakeClient:
    """Stands in for httpx.AsyncClient; records what would have been POSTed."""

    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, **kw):
        self.calls.append((url, json))
        return None


def run(coro):
    """Drive one coroutine to completion (no pytest-asyncio dependency)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------- plain one-liner
def test_format_trade_keeps_the_one_liner_shape():
    text = format_trade(sig(), [res("a1"), res("a2", "blocked", reason="cap"), res("a3", "error")])
    assert text.startswith("🟢 **ES BUY** ES1! @ 5312.25 · 2ct · SL 400.0/TP 800.0")
    assert "→ 1 account(s), 1 blocked, ⚠️ 1 failed" in text


def test_sell_and_close_get_their_own_marker():
    assert format_trade(sig(action="sell"), [res("a1")]).startswith("🔴")
    assert format_trade(sig(action="close", event="EXIT"), [res("a1")]).startswith("⚪")


# ---------------------------------------------------------------- embeds
def test_embed_colour_follows_direction_then_pnl():
    assert build_embed(sig(), [res("a1")])["color"] == COLOR_LONG
    assert build_embed(sig(action="sell"), [res("a1")])["color"] == COLOR_SHORT
    exit_sig = sig(action="close", event="EXIT")
    assert build_embed(exit_sig, [res("a1")], pnl={"realized": 412.0})["color"] == COLOR_WIN
    assert build_embed(exit_sig, [res("a1")], pnl={"realized": -95.5})["color"] == COLOR_LOSS


def test_embed_goes_critical_when_nothing_got_through():
    embed = build_embed(sig(), [res("a1", "error", http_status=401)])
    assert embed["color"] == COLOR_CRITICAL


def test_embed_lists_accounts_with_reasons_and_flags_dry_run():
    embed = build_embed(sig(), [res("a1", "dry_run"),
                                res("a2", "blocked", reason="daily entry cap 4 reached"),
                                res("a3", "error", http_status=502)], channel="funded")
    names = {f["name"]: f["value"] for f in embed["fields"]}
    assert names["Routed (1)"] == "`a1`"
    assert "daily entry cap 4 reached" in names["⛔ Blocked (1)"]
    assert "HTTP 502" in names["⚠️ Failed (1)"]
    assert embed["footer"]["text"] == "MEX middleware · funded · DRY RUN (no live orders)"


def test_embed_truncates_long_account_lists():
    embed = build_embed(sig(), [res(f"a{i}") for i in range(14)])
    routed = next(f["value"] for f in embed["fields"] if f["name"].startswith("Routed"))
    assert "+4 more" in routed


def test_embed_pnl_field_and_chart_image():
    embed = build_embed(sig(action="close", event="EXIT", chart_url="https://img/x.png"),
                        [res("a1")], pnl={"realized": 412.0, "open_pnl": -20.0, "accounts": 7})
    day = next(f["value"] for f in embed["fields"] if f["name"] == "Day P&L (fleet)")
    assert day == "+$412.00 realized · −$20.00 open · 7 acct(s)"
    assert embed["image"] == {"url": "https://img/x.png"}


def test_embed_omits_pnl_when_the_poller_has_no_data():
    embed = build_embed(sig(action="close", event="EXIT"), [res("a1")], pnl={"realized": None})
    assert not [f for f in embed["fields"] if f["name"] == "Day P&L (fleet)"]


# ---------------------------------------------------------------- severity
@pytest.mark.parametrize("result,expected", [
    ({"status": "error", "http_status": 401}, "critical"),
    ({"status": "error", "http_status": 503}, "warning"),
    ({"status": "error", "reason": "PMT_URL not configured"}, "critical"),
    ({"status": "error", "reason": "unknown broker 'foo'"}, "critical"),
    ({"status": "error", "reason": "ConnectTimeout()"}, "warning"),
])
def test_classify_failure(result, expected):
    assert classify_failure(result) == expected


def test_severity_escalates_when_the_whole_fan_out_failed():
    partial = [res("a1"), res("a2", "error", http_status=503)]
    assert severity_of(sig(), partial) == "warning"
    total = [res("a1", "error", http_status=503), res("a2", "error", http_status=503)]
    assert severity_of(sig(), total) == "critical"   # a missed trade, not a degraded one
    assert severity_of(sig(), [res("a1")]) == "info"


def test_build_failure_text_and_embed():
    sev, text, embed = build_failure(sig(), [res("a1"), res("a2", "error", reason="boom")])
    assert sev == "warning"
    assert "**WARNING**" in text and "a2: boom" in text
    assert embed["color"] and "Still routed (1)" in {f["name"] for f in embed["fields"]}


# ---------------------------------------------------------------- rate limiting
def test_limiter_admits_then_collapses_and_reports_the_suppressed_count():
    lim = AlertLimiter(max_per_window=2, window_s=60)
    assert lim.admit("ES:warning", now=0) == (True, 0)
    assert lim.admit("ES:warning", now=1) == (True, 0)
    assert lim.admit("ES:warning", now=2) == (False, 0)
    assert lim.admit("ES:warning", now=3) == (False, 0)
    # window has rolled: the next one goes out and carries the suppressed tally
    assert lim.admit("ES:warning", now=61) == (True, 2)
    assert lim.admit("ES:warning", now=62) == (True, 0)


def test_limiter_keys_are_independent():
    lim = AlertLimiter(max_per_window=1, window_s=60)
    assert lim.admit("ES:warning", now=0)[0] is True
    assert lim.admit("ES:warning", now=1)[0] is False
    assert lim.admit("GC:critical", now=1)[0] is True


def test_alert_failures_rate_limits_and_reports_what_it_did():
    lim = AlertLimiter(max_per_window=1, window_s=60)
    client = FakeClient()
    failed = [res("a1", "error", http_status=401)]
    first = run(alert_failures(DISCORD, sig(), failed, limiter=lim, client=client))
    second = run(alert_failures(DISCORD, sig(), failed, limiter=lim, client=client))
    assert first == {"sent": True, "severity": "critical", "failures": 1, "suppressed": 0}
    assert second["rate_limited"] is True and second["sent"] is False
    assert len(client.calls) == 1


def test_alert_failures_is_a_noop_without_failures_or_webhook():
    client = FakeClient()
    assert run(alert_failures(DISCORD, sig(), [res("a1")], client=client))["sent"] is False
    assert run(alert_failures("", sig(), [res("a1", "error")], client=client))["sent"] is False
    assert client.calls == []


# ---------------------------------------------------------------- transport
def test_discord_payload_carries_content_and_embed():
    client = FakeClient()
    run(notify_trade(DISCORD, sig(), [res("a1")], channel="funded", client=client))
    url, body = client.calls[0]
    assert url == DISCORD
    assert body["content"].startswith("🟢 **ES BUY**")
    assert body["embeds"][0]["title"] == "🟢 ES BUY · ES1!"


def test_telegram_payload_uses_text_chat_id_and_single_star_bold():
    client = FakeClient()
    run(notify_trade(TELEGRAM, sig(), [res("a1")], chat_id="4242", client=client))
    url, body = client.calls[0]
    assert url == TELEGRAM and "embeds" not in body
    assert body["chat_id"] == "4242" and body["parse_mode"] == "Markdown"
    assert "*ES BUY*" in body["text"] and "**" not in body["text"]


def test_telegram_chat_id_in_the_url_wins_and_is_moved_into_the_body():
    url, body = _telegram_request(TELEGRAM + "?chat_id=999", "hi", chat_id="4242")
    assert url == TELEGRAM and body["chat_id"] == "999"


def test_post_never_raises_when_the_sink_is_down():
    class Boom(FakeClient):
        async def post(self, *a, **kw):
            raise RuntimeError("discord down")

    run(_post(DISCORD, "hello", client=Boom()))          # must not raise
    run(notify_trade(DISCORD, sig(), [res("a1")], client=Boom()))


def test_routes_post_one_message_per_channel_over_one_client():
    client = FakeClient()
    routes = [("hook://funded", "funded", [res("apex_f5")]),
              ("hook://eval", "eval", [res("apex_e1")])]
    run(notify_trade_routes(routes, sig(), client=client))
    assert [url for url, _b in client.calls] == ["hook://funded", "hook://eval"]
    footers = [b["embeds"][0]["footer"]["text"] for _u, b in client.calls]
    assert footers == ["MEX middleware · funded", "MEX middleware · eval"]


def test_no_webhook_and_no_results_send_nothing():
    client = FakeClient()
    run(notify_trade("", sig(), [res("a1")], client=client))
    run(notify_trade(DISCORD, sig(), [], client=client))
    assert client.calls == []


# ---------------------------------------------------------------- routing
def _map() -> AccountMap:
    return AccountMap(
        strategies={"ES": {"accounts": ["apex_f5", "apex_e1", "ftmo_1"]}},
        accounts={"apex_f5": {"kind": "funded", "firm": "apex"},
                  "apex_e1": {"kind": "eval", "firm": "apex"},
                  "ftmo_1": {"kind": "funded", "firm": "ftmo"}},
        notify_channels={"funded": "hook://funded", "eval": "hook://eval", "default": "hook://all"},
    )


def test_routes_split_funded_and_eval_into_separate_streams():
    routes = _map().notify_routes("ES", [res("apex_f5"), res("apex_e1"), res("ftmo_1")], {})
    by_hook = {hook: (label, [r["account"] for r in subset]) for hook, label, subset in routes}
    assert by_hook["hook://funded"] == ("funded", ["apex_f5", "ftmo_1"])
    assert by_hook["hook://eval"] == ("eval", ["apex_e1"])


def test_firm_channel_is_used_when_no_kind_channel_matches():
    amap = _map()
    amap.notify_channels = {"ftmo": "hook://ftmo", "default": "hook://all"}
    routes = dict((hook, [r["account"] for r in sub]) for hook, _lbl, sub in
                  amap.notify_routes("ES", [res("apex_f5"), res("ftmo_1")], {}))
    assert routes == {"hook://all": ["apex_f5"], "hook://ftmo": ["ftmo_1"]}


def test_per_strategy_override_still_wins_over_group_channels():
    amap = _map()
    amap.strategies["ES"]["notify"] = "hook://es-only"
    routes = amap.notify_routes("ES", [res("apex_f5"), res("apex_e1")], {})
    assert len(routes) == 1 and routes[0][0] == "hook://es-only"


def test_account_override_beats_everything():
    amap = _map()
    amap.strategies["ES"]["notify"] = "hook://es-only"
    amap.accounts["apex_e1"]["notify"] = "hook://just-this-one"
    hooks = {hook for hook, _lbl, _sub in amap.notify_routes("ES", [res("apex_f5"), res("apex_e1")], {})}
    assert hooks == {"hook://es-only", "hook://just-this-one"}


def test_env_defaults_fill_in_when_yaml_has_no_notify_block():
    amap = AccountMap(strategies={"ES": {}}, accounts={"a1": {"kind": "eval"}, "a2": {}})
    routes = dict((hook, [r["account"] for r in sub]) for hook, _lbl, sub in
                  amap.notify_routes("ES", [res("a1"), res("a2")],
                                     {"default": "env://all", "eval": "env://eval"}))
    assert routes == {"env://eval": ["a1"], "env://all": ["a2"]}


def test_unconfigured_channel_drops_the_leg_instead_of_posting_nowhere():
    amap = AccountMap(strategies={"ES": {}}, accounts={"a1": {}})
    assert amap.notify_routes("ES", [res("a1")], {}) == []


def test_results_without_an_account_land_on_the_default_channel():
    amap = AccountMap(strategies={"ES": {}}, accounts={}, notify_channels={"default": "hook://all"})
    routes = amap.notify_routes("ES", [{"status": "no_accounts", "strategy": "ES"}], {})
    assert routes[0][0] == "hook://all" and routes[0][1] == "default"
