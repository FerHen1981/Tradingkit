"""Rule-based Journey insight tests (stdlib)."""
from backtest.lab.insights import build_journey, classic_insights, eval_insights


def _run(tf, lens="classic", **kpis):
    return {"asset": "NQ", "strategy": "El_Toro", "timeframe": tf, "lens": lens, "kpis": kpis}


# the real El Toro classic results from the VPS run
CLASSIC = [
    _run("5m", trades=404, win_rate_pct=71.0, profit_factor=1.22, expectancy=28.31,
         net_profit=11437.7, max_drawdown=5383.0, avg_win=223.53, avg_loss=-450.56),
    _run("15m", trades=78, win_rate_pct=64.1, profit_factor=0.9, expectancy=-17.48,
         net_profit=-1363.6, max_drawdown=5176.2),
    _run("1h", trades=1, win_rate_pct=0.0, profit_factor=0.0, net_profit=-656.2),
]


def _texts(insights):
    return " ".join(i["text"] for i in insights)


def test_classic_picks_best_timeframe():
    ins = classic_insights(CLASSIC)
    assert "5m" in ins[0]["text"] and "1.22" in ins[0]["text"]
    assert ins[0]["tone"] == "good"


def test_classic_flags_thin_and_no_edge():
    t = _texts(classic_insights(CLASSIC))
    assert "15m" in t and ("thin sample" in t or "no edge" in t or "loses money" in t)
    assert "1h" in t   # 1-trade tf mentioned (thin)


def test_classic_return_over_drawdown():
    t = _texts(classic_insights(CLASSIC))
    assert "drawdown" in t.lower()


def test_all_thin_warns_not_decision_grade():
    thin = [_run("5m", trades=30, profit_factor=1.5, expectancy=10)]
    ins = classic_insights(thin)
    assert any("decision-grade" in i["text"] for i in ins)


def test_eval_pass_rate_tone():
    good = eval_insights([_run("5m", "eval", starts=200, pass_rate_pct=45, breach=50, timeout=60,
                               median_trades_to_resolve=12)])
    assert good[0]["tone"] == "good" and "45%" in good[0]["text"]
    bad = eval_insights([_run("5m", "eval", starts=200, pass_rate_pct=10, breach=150, timeout=30)])
    assert bad[0]["tone"] == "bad"


def test_build_journey_three_lenses_ordered():
    j = build_journey(CLASSIC)
    assert [l["lens"] for l in j["lenses"]] == ["classic", "eval", "funded"]
    assert j["strategy"] == "El_Toro" and j["assets"] == ["NQ"]
    # funded has no runs -> placeholder insight, not a crash
    funded = [l for l in j["lenses"] if l["lens"] == "funded"][0]
    assert funded["insights"] and "overlay" in funded["insights"][0]["text"]


def test_verdict_reflects_edge_then_eval():
    j = build_journey(CLASSIC)
    # edge exists on 5m but no eval runs -> verdict nudges to run eval
    assert j["verdict"]["tone"] in ("warn", "good")
    assert "eval" in j["verdict"]["text"].lower()


def test_verdict_no_edge():
    weak = [_run("5m", trades=300, profit_factor=0.8, net_profit=-500, max_drawdown=2000)]
    j = build_journey(weak)
    assert j["verdict"]["tone"] == "bad"
