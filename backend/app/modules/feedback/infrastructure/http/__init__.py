from app.modules.feedback.infrastructure.http.admin_routes import router as admin_router
from app.modules.feedback.infrastructure.http.user_routes import router

__all__ = ["admin_router", "router"]
