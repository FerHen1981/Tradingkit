# D-02 — per-account day cap, daily loss limit and size

Concrete request for whoever builds the risk gate, once D-05 decides where it
lands (.NET `mex-receiver`, Pine inputs, or PMT per-account limits). Numbers and
derivation both, so the values can be recomputed instead of ageing in place.

**As of:** cockpit `/api/command?window=all`, `as_of 2026-08-19T11:16Z`,
`data_through 2026-08-18`, 594 trades, 19 accounts, 0 breached, **$0 withdrawable**.

⚠ **These values move daily.** They are derived from live buffers, so a builder
should implement the *rule* and recompute, not hardcode this table. It is a
snapshot for sanity-checking the implementation.

---

## The rule

Apex blocks a payout on three counts: ≥8 trading days, best day ≤30% of profit,
and balance above the safety net. The day cap exists for the middle one.

The non-obvious part: **your best day is fixed in the past.** You cannot lower it,
only out-grow it — and a new day that exceeds it drags the ceiling up with it, so
the ratio never improves. That gives two ways out, and the cheaper one wins:

**Route A — stay under the existing best day.** Cap at `0.9 × best_day`, so the
ceiling never moves. Days needed = `need / cap`. Best when the account already has
a large best day to hide under.

**Route B — let the best day rise, but spread over ≥4 days.** With *m* roughly
equal days the best day is `1/m` of the total, so **m ≥ 4 satisfies the 30% rule
on its own**. Cap = `need / m`, `m = max(4, days_to_go)`. Best when the best day is
small and the safety-net gap dominates.

`need` = whichever is larger: the profit still required for consistency
(`best_day / 0.30 − profit`), or the safety-net gap.

**Daily loss limit** = `min(20% of buffer, day cap)`. The second term matters: an
account must never be able to lose more in a day than it is allowed to win.

**Size** = `floor(DLL / (2 × stop_risk_per_contract))`, so two full stops fit
inside the day's loss limit. For MGC the observed stop is 10 points
(entry 4404 → SL 4394) at $10/point = **$100 risk per contract**.

---

## Per account

| Acct | Balance | Buffer | Days | Cons. | Best day | Need | **Cap** | **DLL** | **Qty** | ~Days | Route |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **018** | $54,033 | $3,933 | 7/8 | 62% | $2,488 | $4,262 | **$2,240** | **$790** | **3** | 2 | A |
| **013** | $55,303 | $5,203 | 8/8 | 44% | $2,323 | $2,439 | **$2,090** | **$1,040** | **5** | 2 | A |
| **016** | $50,851 | $751 | 7/8 | 88% | $745 | $1,749 | **$670** | **$150** | **1** | 3 | A |
| **015** | $51,181 | $1,283 | 7/8 | 67% | $795 | $1,468 | **$720** | **$260** | **1** | 3 | A |
| **017** | $50,401 | $1,848 | 6/8 | 37% | $150 | $2,199 | **$550** | **$370** | **1** | 4 | B |
| **021** | $50,053 | $2,113 | 3/8 | 60% | $32 | $2,547 | **$510** | **$420** | **2** | 5 | B |

Buffer = balance − trailing floor. 013, 018 and 016 sit on a locked floor of
$50,100; 015 ($49,898), 017 ($48,553) and 021 ($47,940) are still trailing.

**013 has met the 8-day requirement** and is now blocked by consistency alone —
$2,439 of spread profit, no day above $2,090. It is the closest payout in the fleet.

**017 is Route B on purpose.** Its consistency is nearly fine (37%, needs only ~$99),
but it is $2,199 below the safety net. Capping tightly there would take a month;
letting the best day rise to ~$550 over 4 days satisfies both.

---

## Three things the numbers say that the table does not

**1. Every account is now sized below the range the edge was validated at.**
MGC-funded was validated at q6–q10. Correct risk sizing today puts all six at
q1–q5. The buffers have shrunk to where safe size is below measured size — so the
$45/trade expectancy no longer applies at these sizes. This is a decision for
Ferry, not something to size around: either accept slower grinding, or stand
accounts down.

**2. 016 is effectively out of room.** A $751 buffer with a $100-per-contract stop
means one full stop is two-thirds of its daily limit. Running it at q1 is not
trading, it is waiting to breach. Recommend standing it down until it recovers.

**3. MGC deteriorated over the last four sessions.** Net $22,597.70 → $19,077.54
(−$3,520) and PF 2.52 → 1.92 between 14-08 and 18-08, on 55 more trades. The single
leg carrying the fleet is thinning. Not a reason to stop, but the day caps above
assume it still earns.

Also: **accounts 019 and 020 left the fleet** between 14-08 and 18-08 (21 → 19)
while `breached` stayed 0. Worth confirming what happened to them — closed, reset,
or dropped from the feed.

---

## What the gate must actually do

Per account, on realized day P&L:

- `>= cap` → halt the account for the session (no new entries; leave open positions
  to their own exits).
- `<= -DLL` → halt the account for the session.
- Reset at the CME session roll (18:00 ET).

Enforcement has to sit on the live path. `middleware/app/risk.py` already has
per-account per-day halt logic, but it hangs off `main.py`/`router.py`, which do
not run (D-02) — implementing there changes nothing about execution.
