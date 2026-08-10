"""Trade-card rendering via de externe Node-renderer (render-signal.js).

Aanroep-contract (zoals live gebruikt):
    MEX_SIGNAL_OUT=/var/www/charts/signal-<ts>.png node render-signal.js
De event-payload gaat als JSON op stdin; het script schrijft de PNG naar
$MEX_SIGNAL_OUT. Pas RENDER_CMD/RENDER_DIR aan in .env als het contract afwijkt.
Faalt de render (exit!=0, timeout, geen bestand) -> None; de caller valt terug
op het originele tekst-embed zodat er nooit een bericht verloren gaat.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import time


async def render_card(payload: dict, *, render_cmd: str, render_dir: str,
                      timeout: float = 10.0) -> str | None:
    fname = f"signal-{int(time.time()*1000)}.png"
    out = os.path.join(render_dir, fname)
    env = {**os.environ, "MEX_SIGNAL_OUT": out}
    try:
        proc = await asyncio.create_subprocess_exec(
            *shlex.split(render_cmd),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env)
        await asyncio.wait_for(proc.communicate(json.dumps(payload).encode()), timeout=timeout)
    except Exception:
        return None
    return out if proc.returncode == 0 and os.path.exists(out) else None
