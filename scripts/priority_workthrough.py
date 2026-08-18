"""Priority formula worked example — the live-wire vs pothole case from the problem statement."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.engines import priority

cases = [
    {"name": "pothole cluster (40 complaints, 6 days, near school)",
     "severity": 4, "affected": 40, "days": 6.0, "has_proximity": True, "urgent": False},
    {"name": "live wire (2 complaints, 0 days, no POI)",
     "severity": 5, "affected": 2, "days": 0.0, "has_proximity": False, "urgent": True},
    {"name": "garbage (5 complaints, 2 days)",
     "severity": 2, "affected": 5, "days": 2.0, "has_proximity": False, "urgent": False},
    {"name": "waterlogging (12 complaints, 1 day, near hospital)",
     "severity": 3, "affected": 12, "days": 1.0, "has_proximity": True, "urgent": False},
]

print("=" * 78)
print("NAGARAI PRIORITY FORMULA — WORKED EXAMPLES")
print("formula: score = band(S); within bands rank = P(affected) * T(days) * L(proximity)")
print("=" * 78)
for c in cases:
    r = priority.compute(c["severity"], c["affected"], c["days"], c["has_proximity"], c["urgent"])
    reason = r["reason"]
    print(f"\n▶ {c['name']}")
    print(f"  S={reason['S']}  P={reason['P']} (n={c['affected']}, log-dampened)  "
          f"T={reason['T']} (d={c['days']}d, saturating)  L={reason['L']}")
    print(f"  band={reason['band']}  →  priority = {r['score']}/100")
    if c["urgent"]:
        print("  ✓ severity band-1 gate: live hazard always ranks above volume complaints")
