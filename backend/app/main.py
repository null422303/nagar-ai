import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.models.store import init_store

app = FastAPI(title="NagarAI", version="1.0.0")

# "We don't allow VPN" page — styled to match the Ward Control Room theme.
_VPN_BLOCK_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>404 · NAGAR AI — Not Allowed</title>
<style>
  :root{--ink:#12100c;--ink-deep:#0c0a07;--paper:#e7e1ce;--muted:#a89e83;
    --faint:#8a8167;--marigold:#e8a93a;--marigold-dk:#b9822a;--signal-red:#b23a2e;
    --route-green:#3f6b4a;--card-line:#d7d0b6;}
  *{box-sizing:border-box;}
  html,body{margin:0;min-height:100vh;}
  body{
    background:var(--ink);
    background-image:
      radial-gradient(1100px 640px at 50% -12%, rgba(232,169,58,.06), transparent 62%),
      repeating-linear-gradient(0deg, rgba(231,225,206,.022) 0 1px, transparent 1px 46px),
      repeating-linear-gradient(90deg, rgba(231,225,206,.022) 0 1px, transparent 1px 46px);
    color:var(--paper);
    font-family:'IBM Plex Sans',ui-sans-serif,system-ui,sans-serif;
    font-size:14px; line-height:1.5; display:flex; flex-direction:column;
    -webkit-font-smoothing:antialiased;
  }
  /* hazard strip like the app header */
  .hazard{height:6px; flex:0 0 6px;
    background:repeating-linear-gradient(135deg,var(--marigold) 0 14px, var(--ink) 14px 28px);}
  main{flex:1; display:flex; align-items:center; justify-content:center; padding:32px 20px;}
  .card{max-width:560px; width:100%; text-align:center; padding:40px 36px 46px;
    border:1px solid #2b2618; border-radius:6px;
    background:linear-gradient(180deg, rgba(255,255,255,.02), transparent 40%),
               rgba(18,16,12,.55);
    box-shadow:0 18px 60px rgba(0,0,0,.45);}
  .mark{width:56px; height:56px; margin:0 auto 18px; display:block; border-radius:8px;
    background:#0F141C; padding:6px;}
  .mark svg{width:100%; height:100%; display:block;}
  h1{font-family:Georgia,'Times New Roman',serif; font-size:88px; line-height:.95;
    margin:0; color:var(--signal-red); letter-spacing:.02em;}
  .tagline{font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace;
    font-size:.66rem; letter-spacing:.22em; text-transform:uppercase;
    color:var(--marigold); margin:14px 0 8px;}
  h2{font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace;
    font-size:.85rem; letter-spacing:.12em; text-transform:uppercase;
    color:var(--paper); margin:0 0 10px; font-weight:600;}
  p{color:var(--muted); font-size:14px; line-height:1.7; margin:0 auto; max-width:430px;}
  .note{margin-top:22px; padding-top:16px; border-top:1px dashed #3a3527;
    font-family:'IBM Plex Mono',ui-monospace,Menlo,monospace;
    font-size:.62rem; letter-spacing:.14em; text-transform:uppercase; color:var(--faint);}
  a{color:var(--marigold); text-decoration:none; border-bottom:1px solid transparent;}
  a:hover{border-bottom-color:var(--marigold);}
</style></head>
<body>
  <div class="hazard" aria-hidden="true"></div>
  <main>
    <div class="card">
      <span class="mark" aria-hidden="true">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
          <defs><linearGradient id="b-radar" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#2B7FF5"/><stop offset="1" stop-color="#2FA84F"/>
          </linearGradient></defs>
          <rect width="64" height="64" rx="10" fill="#0F141C"/>
          <circle cx="32" cy="32" r="26" fill="none" stroke="#3A3626" stroke-width="1.4"/>
          <circle cx="32" cy="32" r="17" fill="none" stroke="#3A3626" stroke-width="1"/>
          <circle cx="32" cy="32" r="9" fill="none" stroke="#3A3626" stroke-width="1"/>
          <path d="M32 32 L56 18 A32 32 0 0 0 50 6 Z" fill="url(#b-radar)" opacity=".85"/>
          <circle cx="44" cy="14" r="2.2" fill="#E8A93A"/>
          <circle cx="50" cy="26" r="1.6" fill="#E7E1CE"/>
          <circle cx="38" cy="8" r="1.2" fill="#E7E1CE"/>
          <circle cx="32" cy="32" r="2" fill="#E8A93A"/>
          <line x1="32" y1="32" x2="48" y2="20" stroke="#E8A93A" stroke-width="1.6"/>
        </svg>
      </span>
      <h1>404</h1>
      <div class="tagline">Access denied</div>
      <h2>We don't allow VPN connections</h2>
      <p>Your connection looks like it's coming through a VPN or proxy.
         For civic-verification reasons we block these, so your location is real
         and traceable when you report an issue in your ward.</p>
      <p style="margin-top:10px">Please turn off your VPN and reload this page.</p>
      <div class="note">NAGAR AI · Ward Control Room</div>
    </div>
  </main>
  <div class="hazard" aria-hidden="true"></div>
</body></html>
"""


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def vpn_guard(request: Request, call_next):
    """Block clients behind VPNs/proxies with a 'we don't allow VPN' 404 page.
    Uses a free lookup (ip-api.com) that is only queried for the first request
    from each IP (cached 10 min). API callers get a JSON 403; page visitors get
    the styled 404 page. Localhost and unknown IPs are always allowed through."""
    from app.services import vpn_detect

    check = await vpn_detect.check_client(request)
    if check and check.get("block"):
        accept = request.headers.get("accept", "")
        if "/json" in accept or request.url.path.startswith("/api/"):
            return JSONResponse(status_code=403, content={
                "detail": "We don't allow VPN connections. Please disable your VPN and retry.",
                "reason": check.get("reason"),
            })
        return HTMLResponse(content=_VPN_BLOCK_PAGE, status_code=404)
    return await call_next(request)

# The production website is the redesigned Ward Control Room site
# (frontend/site/ — self-hosted fonts/css/js, same-origin /api wiring).
_SITE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "site")

# API routes first so they win over the SPA catch-all
app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup():
    init_store()


# serve static assets (css/js/fonts)
if os.path.isdir(os.path.join(_SITE_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_SITE_DIR, "assets")), name="site-assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str):
    if full_path.startswith("api/"):
        return {"detail": "Not Found"}
    idx = os.path.join(_SITE_DIR, "index.html")
    if os.path.isfile(idx):
        from fastapi.responses import Response
        body = open(idx, "rb").read()
        return Response(
            content=body,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"detail": "frontend not built"}
