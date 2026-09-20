from .api import app
from .auth.mercadolivre_router import router as mercadolivre_oauth_router
from .mercadolivre.router import router as mercadolivre_api_router
from .shopee.router import router as shopee_router

app.include_router(shopee_router)
app.include_router(mercadolivre_oauth_router)
app.include_router(mercadolivre_api_router)

__all__ = ["app"]
