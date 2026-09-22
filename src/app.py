from .api import app
from .auth.mercadolivre_router import router as mercadolivre_oauth_router
from .mercadolivre.router import router as mercadolivre_api_router
from .shopee.router import router as shopee_router
from .offers.identical_product_router import router as identical_product_offers_router
from .extension.router import router as browser_extension_router

app.include_router(shopee_router)
app.include_router(mercadolivre_oauth_router)
app.include_router(mercadolivre_api_router)
app.include_router(identical_product_offers_router)
app.include_router(browser_extension_router)

__all__ = ["app"]
