"""Priority engine — deterministic, formula-based, severity-band master gate.

priority = band(S)  and within bands 2-3, rank = P * T * L
  S severity 1-5
  P affected, log-dampened:  min(1, 0.4 + 0.6*log10(1+n)/log10(1+50))
  T days pending, saturating: 1 + 0.25*min(1,d/3) + 0.5*min(1,max(0,d-3)/7)
  L proximity: x1.5 within 100m of school/hospital, else x1.0

Bands:
  band 1 (S>=5 or urgent_hint): 90-99  — live hazards always on top
  band 2 (S==4): 70-89
  band 3 (S<=3): ranked by P*T*L within band

All terms are logged so the dashboard can render the exact arithmetic.
"""
import json
import math

PROXIMITY_RADIUS_M = 100.0
PROXIMITY_BONUS = 1.5


def _p(affected: int) -> float:
    if affected <= 0:
        return 0.0
    return min(1.0, 0.4 + 0.6 * math.log10(1 + affected) / math.log10(51))


def _t(days: float) -> float:
    d = max(0.0, days)
    return 1.0 + 0.25 * min(1.0, d / 3.0) + 0.5 * min(1.0, max(0.0, d - 3.0) / 7.0)


def _l(has_proximity: bool) -> float:
    return PROXIMITY_BONUS if has_proximity else 1.0


def compute(severity: int, affected: int, days_pending: float,
            has_proximity: bool = False, urgent_hint: bool = False) -> dict:
    """Returns {score, band, reason_json}."""
    s = max(1, min(5, severity))
    p, t, l = _p(affected), _t(days_pending), _l(has_proximity)
    rank = p * t * l

    if s >= 5 or urgent_hint:
        band, score = 1, round(min(99.0, 90.0 + 2.0 * min(1.0, rank / 3.0)), 1)
    elif s == 4:
        band, score = 2, round(70.0 + 15.0 * min(1.0, rank / 3.0), 1)
    else:
        band, score = 3, round(40.0 + 25.0 * min(1.0, rank / 3.0), 1)

    reason = {
        "band": band,
        "S": s,
        "P": round(p, 3),
        "T": round(t, 3),
        "L": round(l, 3),
        "rank": round(rank, 3),
        "formula": "score = band(S); rank = P*T*L",
        "explain": {
            "P": f"log-dampened affected count n={affected}",
            "T": f"days pending {round(days_pending,1)} (saturating)",
            "L": "x1.5 school/hospital within 100m" if has_proximity else "no proximity bonus",
        },
    }
    return {"score": score, "band": band, "reason": reason}


def score_to_json(reason: dict) -> str:
    return json.dumps(reason, ensure_ascii=False)
