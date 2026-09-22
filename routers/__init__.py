from routers.auth_router import router as auth_router
from routers.calendar_router import router as calendar_router
from routers.me_router import router as me_router
from routers.admin_router import router as admin_router

__all__ = ["auth_router", "calendar_router", "me_router", "admin_router"]
