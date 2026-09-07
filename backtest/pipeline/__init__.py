"""The MEX research pipeline (v7) — twelve gated stages.

`stages` is the spine, `fleet` the released v1_0_0 engines that flow through it,
`state` the per-engine status, and `audit` / `parity` the first two stages.
"""
from .stages import STAGES, GROUND_RULES, BY_KEY, BY_N   # noqa: F401
