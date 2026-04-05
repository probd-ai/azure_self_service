import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from src.api.routes.chat import router as chat_router
from src.api.routes.download import router as download_router
from src.tools.index_builder import build_index

app = FastAPI(
    title="Azure Self-Service AI Agent",
    description="AI-driven self-service for Azure infrastructure deployment using company-approved Terraform templates.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """Build the template navigation index on startup."""
    result = build_index()
    if "error" in result:
        logger.error(f"Failed to build template index: {result['error']}")
    else:
        logger.info(f"Template index ready: {result['templates_indexed']} templates indexed")

app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(download_router, prefix="/api", tags=["Download"])

# Serve the full-page chat UI
_static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
_index_html  = os.path.join(_static_dir, "index.html")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse(_index_html)


@app.get("/health")
def health():
    return {"status": "ok"}
