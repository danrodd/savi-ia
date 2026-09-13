from app.modules.erp_databases.infrastructure.http.public_routes import (
    router as public_router,
)
from app.modules.erp_databases.infrastructure.http.routes import router

__all__ = ["public_router", "router"]
