"""Trade-card rendering via de externe Node-renderer (render-signal.js).

Aanroep-contract (gepind op render-signal.js):
    MEX_SIGNAL_JSON='<event-json>' MEX_SIGNAL_OUT=/var/www/charts/signal-<ts>.png \
        node render-signal.js
De payload gaat via de MEX_SIGNAL_JSON-omgevingsvariabele (het script leest GEEN
stdin); de PNG komt op $MEX_SIGNAL_OUT. RENDER_CMD/RENDER_DIR in .env.
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
                      timeout: float = 45.0) -> str | None:
    fname = f"signal-{int(time.time()*1000)}.png"
    out = os.path.join(render_dir, fname)
    env = {**os.environ, "MEX_SIGNAL_OUT": out,
           "MEX_SIGNAL_JSON": json.dumps(payload)}
    try:
        proc = await asyncio.create_subprocess_exec(
            *shlex.split(render_cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env)
        await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except Exception:
        return None
    return out if proc.returncode == 0 and os.path.exists(out) else None
