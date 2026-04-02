import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from src.api.routes.chat import router as chat_router

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

app.include_router(chat_router, prefix="/api", tags=["Chat"])

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
