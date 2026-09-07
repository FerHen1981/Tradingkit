"""Repair-tool: alleen ONTERECHTE `GEWEIGERD 200 door doelserver`-labels omzetten.

De bug: `Rejected()` in de .NET-receiver matchte op de substring `"error"`, wat
óók een succesvol `"error":false`-antwoord opvangt. De gefixte code laat die
door; deze tool ruimt het spoor op dat de oude code al in de log heeft achtergelaten.

De tests gaan expliciet zowel over wat er *wel* moet gebeuren (succes-antwoorden
herstellen) als over wat er *nooit* mag gebeuren (echte weigeringen behouden,
niet-pmt-regels ongemoeid laten, sent-regels niet aanraken).
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.repair_routed_log import _is_false_weigering, repair_line, repair_file


# --- de kern: welke result is een valse GEWEIGERD? ---------------------------


def test_error_false_is_success():
    assert _is_false_weigering('GEWEIGERD 200 door doelserver: {"res":"Successfully send","error":false}')


def test_error_true_stays_a_real_weigering():
    assert not _is_false_weigering('GEWEIGERD 200 door doelserver: {"error":true,"reason":"no funds"}')


def test_success_false_is_a_real_weigering_even_if_error_false_present():
    # gek maar mogelijk: PMT stuurt success:false naast error:false — de kant
    # met de expliciete faal wint.
    assert not _is_false_weigering('GEWEIGERD 200 door doelserver: {"success":false,"error":false,"reason":"limit"}')


def test_textual_error_marker_wins_over_error_false():
    # Als de tekst zelf "not found in pool" bevat, is het een echte weigering,
    # zelfs als PMT tegelijk error:false meestuurt.
    assert not _is_false_weigering('GEWEIGERD 200 door doelserver: valid ip not found in pool; error:false')


def test_only_success_text_also_counts_as_false_weigering():
    # geen JSON-error-veld maar wel expliciete succes-tekst
    assert _is_false_weigering('GEWEIGERD 200 door doelserver: Successfully send order to broker')


def test_random_error_text_without_marker_stays_weigering():
    # Onherkenbaar → veiligheidsstand: laat staan.
    assert not _is_false_weigering('GEWEIGERD 200 door doelserver: something weird happened')


# --- de rewriter --------------------------------------------------------------


def _pmt(result: str, body: dict | None = None) -> str:
    body = body or {"symbol": "MYM1!", "data": "sell"}
    return json.dumps({
        "ts": "2026-08-25T10:45:07Z",
        "kind": "pmt",
        "account": "PAAPEX2700250000015",
        "result": result,
        "body": json.dumps(body),
    }) + "\n"


def test_false_weigering_is_rewritten_to_sent():
    line = _pmt('GEWEIGERD 200 door doelserver: {"res":"Successfully send","error":false}')
    new, decision = repair_line(line)
    assert decision == "rewritten"
    obj = json.loads(new)
    assert obj["result"].startswith("sent 200 (poging 1)"), obj["result"]
    # het spoor (het originele PMT-antwoord) blijft in de result staan
    assert "Successfully send" in obj["result"]


def test_real_weigering_is_left_alone():
    line = _pmt('GEWEIGERD 200 door doelserver: valid ip not found in pool')
    new, decision = repair_line(line)
    assert decision == "real_GEWEIGERD"
    assert new == line


def test_sent_line_is_not_touched():
    line = _pmt('sent 200 (poging 1) · {"res":"Successfully send","error":false}')
    new, decision = repair_line(line)
    assert decision in {"already_sent", "other"}
    assert new == line


def test_non_pmt_line_is_not_touched():
    line = json.dumps({"ts": "x", "kind": "discord", "body": "{}"}) + "\n"
    new, decision = repair_line(line)
    assert decision == "non_pmt"
    assert new == line


def test_unparseable_line_is_not_touched():
    line = "not json at all\n"
    new, decision = repair_line(line)
    assert decision == "unparseable"
    assert new == line


# --- file-level: dry-run vs apply --------------------------------------------


def _write(tmp: Path, name: str, lines: list[str]) -> Path:
    p = tmp / name
    p.write_text("".join(lines), encoding="utf-8")
    return p


def test_dry_run_reports_but_does_not_write(tmp_path):
    lines = [
        _pmt('GEWEIGERD 200 door doelserver: {"res":"Successfully send","error":false}'),
        _pmt('GEWEIGERD 200 door doelserver: valid ip not found in pool'),
        _pmt('sent 200 (poging 1) · ok'),
    ]
    p = _write(tmp_path, "routed_20260825.jsonl", lines)
    before = p.read_text()
    rep = repair_file(p, apply=False)
    assert rep.scanned == 3
    assert rep.rewritten == 1
    assert rep.real_geweigerd == 1
    assert rep.already_sent == 1
    # bestand blijft ongewijzigd
    assert p.read_text() == before
    # geen backup gemaakt
    assert not p.with_suffix(p.suffix + ".bak").exists()


def test_apply_rewrites_only_the_false_one_and_makes_a_backup(tmp_path):
    lines = [
        _pmt('GEWEIGERD 200 door doelserver: {"res":"Successfully send","error":false}'),
        _pmt('GEWEIGERD 200 door doelserver: valid ip not found in pool'),
        _pmt('sent 200 (poging 1) · ok'),
    ]
    p = _write(tmp_path, "routed_20260825.jsonl", lines)
    original = p.read_text()
    rep = repair_file(p, apply=True)
    assert rep.rewritten == 1
    # backup bevat het ORIGINEEL
    bak = p.with_suffix(p.suffix + ".bak")
    assert bak.exists()
    assert bak.read_text() == original
    # de nieuwe file bevat één sent-regel meer en een GEWEIGERD-regel behouden
    new = p.read_text()
    assert new.count('"result": "sent 200') + new.count('"result":"sent 200') == 2  # 1 hersteld + 1 origineel
    assert new.count('"result": "GEWEIGERD') + new.count('"result":"GEWEIGERD') == 1  # de echte blijft


def test_second_apply_is_a_noop(tmp_path):
    """Rerun mag niet schadelijk zijn — een idempotente tool is een veilige tool."""
    lines = [_pmt('GEWEIGERD 200 door doelserver: {"res":"Successfully send","error":false}')]
    p = _write(tmp_path, "routed_20260825.jsonl", lines)
    repair_file(p, apply=True)
    after_first = p.read_text()
    rep = repair_file(p, apply=True)
    assert rep.rewritten == 0
    assert p.read_text() == after_first
