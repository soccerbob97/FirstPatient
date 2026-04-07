"""FastAPI application entry point."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import recommendations, trials, investigators, chat
from api.schemas import HealthResponse

# Create FastAPI app
app = FastAPI(
    title="FirstPatient API",
    description="AI-powered PI + Site recommendation system for clinical trials",
    version="0.1.0",
)

# Configure CORS for frontend
# Allow production frontend URLs from environment variable
allowed_origins = [
    "http://localhost:5173",  # Vite dev server
    "http://localhost:5174",  # Vite dev server (alternate)
    "http://localhost:3000",  # Alternative dev port
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:3000",
]

# Add production frontend URL if set
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)
    # Also allow without trailing slash
    allowed_origins.append(frontend_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(recommendations.router, prefix="/api")
app.include_router(trials.router, prefix="/api")
app.include_router(investigators.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Cloud Run."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
    )


@app.get("/api/health", response_model=HealthResponse)
async def api_health_check():
    """API health check."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
    )
