from app.modules.company_knowledge.infrastructure.http.public_routes import (
    router as public_router,
)
from app.modules.company_knowledge.infrastructure.http.routes import router
from app.modules.company_knowledge.infrastructure.http.web_routes import (
    router as web_router,
)

__all__ = ["public_router", "router", "web_router"]
