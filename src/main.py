import logging
from itertools import chain

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.routing import APIRoute, APIWebSocketRoute
from src.routes.health import router as health_router
from src.routes.v1 import router as v1_router
from src.settings import settings
from src.utils.app_lifespan import lifespan

# Configure logging
logging.basicConfig(
    level=settings.LOGGING_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def get_application() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Technical Test API",
        description="A FastAPI template with PostgreSQL and Redis",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT == "LOCAL" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "LOCAL" else None,
    )
    logger.info("FastAPI application initialising")

    # Add compression middleware to compress larger responses
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,  # Don't compress tiny responses
    )

    # Collect all routes from all routers
    routers = [health_router, v1_router]
    routes = list(chain.from_iterable(router.routes for router in routers))

    # Add routes to the app
    app.include_router(APIRouter(routes=routes))

    # Log the addition of each route
    for route in routes:
        if isinstance(route, APIRoute):
            logger.info(f"HTTP Route added: {route.path} - {route.methods}")
        elif isinstance(route, APIWebSocketRoute):
            logger.info(f"WebSocket Route added: {route.path}")

    logger.info(f"FastAPI application initialised with {len(routes)} routes")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    return app


app = get_application()
