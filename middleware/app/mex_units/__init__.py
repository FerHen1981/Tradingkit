"""Units en de rolgrens (D-17).

Overgenomen uit `web/handover/mex_units/` — Web bouwde de code, Middleware App
draait hem, want de trades en accounts leven in `middleware/`. De originele
handover-map blijft staan als bron; Web ruimt die zelf op.

Bevat twee modules, allebei zonder datatoegang:

- `units` — rekent een bedrag op een markt om naar de eenheid (ticks/pips).
- `roles` — aggregeert trades tot een fleet-beeld en bouwt per rol een payload.

De `viewer`/`public` payloads bevatten geen bedragen — niet verborgen, afwezig.
`assert_no_currency()` is een tweede slot op de publicatiepoort.
"""
from . import roles, units  # noqa: F401
