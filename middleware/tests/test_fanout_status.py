"""D-119 · Lees-API voor het fan-out-statusvenster. Classifier + aggregator +
runtime-snapshot-parser. Alleen leesgedrag — geen live-pad-mutaties."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import fanout_status as fs  # noqa: E402


def test_classify_covers_the_known_result_strings():
    assert fs.classify("sent 200 (poging 1) · {\"error\":false}") == "sent"
    assert fs.classify("card sent 200 (poging 1)") == "sent"
    assert fs.classify("card queued (tier B)") == "sent"
    assert fs.classify("dry_run -> https://api.pickmytrade.trade") == "sent"
    assert fs.classify("card rate-limited (tier B) (+17 gedempt)") == "suppressed"
    assert fs.classify("blocked-notice suppressed") == "suppressed"
    assert fs.classify("blocked: kill-switch") == "suppressed"
    assert fs.classify("GEWEIGERD 200 door doelserver: {}") == "failed"
    assert fs.classify("error 403 (4xx, niet opnieuw)") == "failed"
    assert fs.classify("card failed: timeout") == "failed"
    assert fs.classify("card exception: System.IO.IOException") == "suppressed"
    assert fs.classify("") == "other"
    # een onbekende vorm valt expliciet in "other" — niet stilzwijgend "sent"
    assert fs.classify("mystery message") == "other"


def test_classify_d116_text_fallback_counts_as_sent_not_suppressed():
    # D-116: na een gedempte of mislukte card valt de receiver door naar de
    # tekst-post. De audit-regel begint dan met "sent 200 …" maar bevat ook
    # "rate-limited" of "card exception" als context. Dat is géén demping: het
    # bericht is wél gestuurd. Prefix wint van substring.
    assert fs.classify(
        "sent 200 (poging 1) · {\"error\":false} · fallback via text (card rate-limited, +17 gedempt)"
    ) == "sent"
    assert fs.classify(
        "sent 200 (poging 1) · fallback via text (tier-C)"
    ) == "sent"
    assert fs.classify(
        "card sent 200 (poging 1) -> tekst-fallback: sent 200"
    ) == "sent"
    # Een pure "card rate-limited (tier B)" zonder sent-prefix blijft suppressed.
    assert fs.classify("card rate-limited (tier B)") == "suppressed"


def test_transport_prefers_explicit_field_then_falls_back_on_kind():
    assert fs.transport_of({"transport": "pmt_rithmic", "kind": "pmt"}) == "pmt_rithmic"
    assert fs.transport_of({"kind": "pmt"}) == "pmt_unknown"       # pre-D-106 PMT-rij
    assert fs.transport_of({"kind": "discord-card"}) == "discord-card"
    assert fs.transport_of({"kind": "journal"}) == "journal"
    assert fs.transport_of({}) == "unknown"


def test_aggregate_counts_per_bucket_and_remembers_last_error():
    now = dt.datetime(2026, 10, 6, 12, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    rows = [
        # binnen het laatste uur
        {"ts": "2026-10-06T11:30:00Z", "kind": "pmt", "account": "PA013",
         "transport": "pmt_tradovate", "result": "sent 200 (poging 1)"},
        {"ts": "2026-10-06T11:40:00Z", "kind": "pmt", "account": "PA018",
         "transport": "pmt_tradovate", "result": "GEWEIGERD 200 door doelserver: dag-cap"},
        {"ts": "2026-10-06T11:45:00Z", "kind": "pmt", "account": "PA022",
         "transport": "pmt_tradovate", "result": "error 403 (4xx, niet opnieuw)"},
        # buiten het laatste uur (meer dan 60 min geleden)
        {"ts": "2026-10-06T10:00:00Z", "kind": "pmt", "account": "PA999",
         "transport": "pmt_tradovate", "result": "sent 200 (poging 1)"},
    ]
    agg = fs.aggregate_window(rows, 3600, now)
    assert agg["totals"] == {"sent": 1, "suppressed": 0, "failed": 2, "other": 0}
    tr = agg["transports"]["pmt_tradovate"]
    assert tr["sent"] == 1 and tr["failed"] == 2
    # laatste foutstring = de meest recente failed in de iteratie-volgorde
    assert "4xx" in (tr["last_error"] or "")
    # accounts-lijst: PA999 valt buiten het venster
    accts = {r["account"] for r in agg["accounts"]}
    assert "PA999" not in accts
    assert accts == {"PA013", "PA018", "PA022"}


def test_aggregate_window_none_includes_everything():
    now = dt.datetime(2026, 10, 6, 12, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    rows = [
        {"ts": "2020-01-01T00:00:00Z", "kind": "pmt", "account": "OLD",
         "transport": "pmt_tradovate", "result": "sent 200"},
        {"ts": "2026-10-06T11:00:00Z", "kind": "pmt", "account": "NEW",
         "transport": "pmt_tradovate", "result": "sent 200"},
    ]
    agg = fs.aggregate_window(rows, None, now)
    assert agg["totals"]["sent"] == 2


def test_runtime_snapshot_parser_tolerates_missing_file():
    out = fs.read_runtime_snapshot("/no/such/path/runtime-snapshot.md")
    assert out["file_present"] is False
    assert out["src_lines"] is None
    assert out["binary_older_than_src"] is None


def test_runtime_snapshot_parser_reads_the_table_and_the_two_prose_fields():
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "snap.md")
        with open(p, "w") as f:
            f.write(
                "# Runtime-snapshot — mex-mw-01\n\n"
                "**Gemaakt:** 2026-10-06 11:00:00 UTC\n\n"
                "## mex-receiver\n\n"
                "| | |\n"
                "|---|---|\n"
                "| service        | active |\n"
                "| gestart        | 2026-10-06 06:14:00 UTC |\n"
                "| bron           | `/root/mex-middleware-b/src/Mex.Journal.Receiver/Program.cs` |\n"
                "| bron md5       | `5453ced73d60a92b288eaca4b3cdbb51` |\n"
                "| bron regels    | 1319 |\n"
                "\n**Binary ouder dan de bron?** nee\n"
            )
        out = fs.read_runtime_snapshot(p)
    assert out["file_present"] is True
    assert out["generated_at"] == "2026-10-06 11:00:00 UTC"
    assert out["service"] == "active"
    assert out["src_md5"] == "5453ced73d60a92b288eaca4b3cdbb51"
    assert out["src_lines"] == 1319
    assert out["binary_older_than_src"] is False


def test_aggregate_skips_rows_without_a_parseable_timestamp_when_window_set():
    now = dt.datetime(2026, 10, 6, 12, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    rows = [
        {"ts": "garbage", "kind": "pmt", "account": "PA013",
         "transport": "pmt_tradovate", "result": "sent 200"},
    ]
    agg = fs.aggregate_window(rows, 3600, now)
    # bericht met onparseerbare ts valt stil buiten elk tijdvenster — niet geteld
    assert agg["totals"]["sent"] == 0
