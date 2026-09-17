from .api import app
from .auth.mercadolivre_router import router as mercadolivre_router
from .shopee.router import router as shopee_router

app.include_router(shopee_router)
app.include_router(mercadolivre_router)

__all__ = ["app"]
