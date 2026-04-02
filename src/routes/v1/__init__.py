"""API v1 router aggregation."""

from fastapi import APIRouter
from src.routes.v1.authors.router import router as authors_router
from src.routes.v1.books.router import router as books_router
from src.routes.v1.orders.router import router as orders_router
from src.routes.v1.users.router import router as users_router

router = APIRouter(prefix="/api/v1")

router.include_router(users_router)
router.include_router(authors_router)
router.include_router(books_router)
router.include_router(orders_router)
