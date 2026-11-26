"""Units en de rolgrens (D-17).

Web bouwde de code, Middleware App draait hem, want de trades en accounts leven
in `middleware/`. **Dit is sinds D-132 (08-10) de enige kopie** — de
handover-map `web/handover/mex_units/` is opgeruimd. Zie `README.md` hiernaast.

Bevat twee modules, allebei zonder datatoegang:

- `units` — rekent een bedrag op een markt om naar de eenheid (ticks/pips).
- `roles` — aggregeert trades tot een fleet-beeld en bouwt per rol een payload.

De `viewer`/`public` payloads bevatten geen bedragen — niet verborgen, afwezig.
`assert_no_currency()` is een tweede slot op de publicatiepoort.
"""
from . import roles, units  # noqa: F401
