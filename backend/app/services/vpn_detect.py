"""Free VPN/proxy detection.

Uses ip-api.com's free endpoint (no API key, ~45 req/min per IP) which returns
`proxy` and `hosting` flags. A small in-memory cache avoids hammering the free tier.

Policy (precision over recall — never block legit residential/cloud users):
  - `proxy: true`  -> ip-api's own proxy/VPN flag -> block
  - `hosting: true` AND the ASN is a *known consumer-VPN* ASN -> block
    (NOT generic clouds like Vultr/Google/Amazon — those host our own server
    and countless legit sites; their clients are real users, not VPN exits.)
"""
import time
from typing import Optional

import httpx

# Known consumer VPN / proxy ASNs (by AS number) — high precision, no false hits
# on ordinary datacenter/cloud providers.
_VPN_ASNS = {
    "AS212238",   # Datacamp (NordVPN, Surfshark etc.)
    "AS60068",    # Datacamp CDN
    "AS9009",     # M247 (ExpressVPN etc.)
    "AS47890",    # Next Layer (AzireVPN)
    "AS49505",    # Selectel VPN
    "AS30860",    # Voxility (proxy ranges)
    "AS212318",   # Datacamp/Leaseweb VPN ranges
    "AS11420",    # TorGuard / VPNArea
    "AS40873",    # VPNTRAFFIC / proxy
    "AS46475",    # Limestone Networks (proxy)
    "AS3214",     # xTom (VPN/proxy ranges)
    "AS212104",   # xTom
    "AS57463",    # NetIX (proxy)
    "AS26496",    # AS-26496 (hosting/proxy mixes)
}

_cache: dict = {}


async def check_ip(ip: str) -> Optional[dict]:
    """Return {'block': bool, 'reason': str} for a client IP. None = unknown."""
    if not ip or ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        return {"block": False, "reason": "localhost"}
    now = time.time()
    hit = _cache.get(ip)
    if hit and now - hit["ts"] < 600:
        return hit["result"]

    url = f"http://ip-api.com/json/{ip}"
    params = {"fields": "status,message,query,proxy,hosting,isp,org,as,country"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            data = r.json()
    except Exception:
        return None

    if data.get("status") != "success":
        return None

    proxy = bool(data.get("proxy"))
    hosting = bool(data.get("hosting"))
    asn = (data.get("as") or "").split(" ")[0]

    reason = ""
    block = False
    if proxy:
        block = True
        reason = "open proxy / VPN"
    elif hosting and asn in _VPN_ASNS:
        block = True
        reason = f"datacenter VPN exit ({asn})"

    result = {"block": block, "reason": reason}
    _cache[ip] = {"ts": now, "result": result}
    if len(_cache) > 5000:
        _cache.clear()
    return result


async def check_client(request) -> Optional[dict]:
    """Resolve the client IP (respecting proxies) and run detection."""
    ip = request.client.host if request.client else ""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return await check_ip(ip)
