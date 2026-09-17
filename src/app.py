from .api import app
from .shopee.router import router as shopee_router

app.include_router(shopee_router)

__all__ = ["app"]
