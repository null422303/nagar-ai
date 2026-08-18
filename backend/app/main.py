import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings
from app.models.store import init_store

app = FastAPI(title="NagarAI", version="1.0.0")


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
