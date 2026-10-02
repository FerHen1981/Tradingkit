"""End-to-end net income model for the 4 legacy accounts under the designed
inrichting: pass the eval on ES (El León), harvest funded on GC (El Tesoro).

Combines measured numbers from this project:
  * eval pass-rate  -> expected attempts (and cost) to (re)fund an account
  * funded flywheel -> banked $/yr and funded breaches/yr on GC

Every FUNDED breach kills the PA; to continue you must re-pass an eval and
re-activate. So:

  net/yr  =  banked/yr  -  breaches/yr * refund_cost  -  annual_fixed
  refund_cost = eval_attempts * eval_attempt_cost + pa_activation
  eval_attempts = 1 / eval_pass_rate

Costs are ASSUMPTIONS (Apex-legacy, promo-dependent) — override with your real
fee basis. Break-even refund cost = banked / breach (fee-assumption-free).
"""
from __future__ import annotations

# --- measured inputs (this project, 3y window) --------------------------------
# funded = GC (El Tesoro), capped/wait-for-cap model; per account size.
FUNDED = {   # size: (banked_3y, breaches_3y)  -- from tools/funded_flywheel_sim.py
    "250k": (25_500, 14),
    "300k": (59_000, 18),   # qty3, flywheel scaled
}
EVAL_PASS = {"250k": 0.18, "300k": 0.13}   # ES El León @2-3ct, from the funnel sweep
YEARS = 3.0

# --- cost scenarios (ASSUMPTIONS — replace with your fees) ---------------------
# eval_attempt_cost: $ per eval attempt (reset / month of sub); pa_activation:
# one-time per PA; annual_fixed: data/platform per account per year.
SCENARIOS = {
    "Low (promo/lifetime)":  dict(eval_attempt_cost=35,  pa_activation=130, annual_fixed=0),
    "Base":                  dict(eval_attempt_cost=80,  pa_activation=130, annual_fixed=200),
    "High (full price)":     dict(eval_attempt_cost=167, pa_activation=140, annual_fixed=1000),
}

# fleet: which account sizes you hold
FLEET = ["250k", "250k", "250k", "300k"]


def refund_cost(size, sc):
    attempts = 1.0 / EVAL_PASS[size]
    return attempts * sc["eval_attempt_cost"] + sc["pa_activation"]


def account_net(size, sc):
    banked_3y, breaches_3y = FUNDED[size]
    banked_yr = banked_3y / YEARS
    breaches_yr = breaches_3y / YEARS
    rc = refund_cost(size, sc)
    gross = banked_yr
    breach_cost = breaches_yr * rc
    net = gross - breach_cost - sc["annual_fixed"]
    return dict(banked_yr=banked_yr, breaches_yr=breaches_yr, refund=rc,
                breach_cost=breach_cost, net=net,
                breakeven_refund=banked_3y / breaches_3y)


def main():
    print("Design: eval on ES (El León), funded on GC (El Tesoro). Costs are ASSUMPTIONS.\n")
    for scname, sc in SCENARIOS.items():
        print(f"=== {scname} ===  (eval ${sc['eval_attempt_cost']}/attempt, "
              f"activation ${sc['pa_activation']}, fixed ${sc['annual_fixed']}/yr)")
        print(f"  {'size':>5} {'banked/yr':>10} {'breach/yr':>10} {'refund$':>9} "
              f"{'breachcost/yr':>13} {'NET/yr':>9}  break-even refund")
        fleet_net = 0.0
        per = {}
        for size in ("250k", "300k"):
            a = account_net(size, sc)
            per[size] = a
            print(f"  {size:>5} ${a['banked_yr']:>8,.0f} {a['breaches_yr']:>10.1f} "
                  f"${a['refund']:>7,.0f} ${a['breach_cost']:>11,.0f} ${a['net']:>7,.0f}"
                  f"   ${a['breakeven_refund']:,.0f} (fee-free)")
        fleet_net = sum(per[s]["net"] for s in FLEET)
        print(f"  FLEET (3x250k + 1x300k) NET/yr = ${fleet_net:,.0f}\n")

    print("Note: break-even refund is fee-assumption-free (= banked/breach). As long")
    print("as your all-in cost to re-fund a blown PA stays under it, the account is")
    print("net positive. The binding constraint is CHURN TIME, not $: at these breach")
    print("rates you re-pass ~1/pass_rate evals per blown PA — see caveats.")


if __name__ == "__main__":
    main()
