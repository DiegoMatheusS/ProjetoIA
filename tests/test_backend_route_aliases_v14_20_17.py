from src.api import app


def _routes():
    return {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}


def test_backend_compatible_aliases_are_registered():
    routes = _routes()
    expected = {
        ("/api/admin/hardwares/descobrir/fontes", "GET"),
        ("/api/admin/hardwares/descobrir", "POST"),
        ("/api/admin/hardwares/descobrir/detalhar", "POST"),
        ("/api/admin/hardwares/descobrir/ia-tecnica/gerar-prompt", "POST"),
        ("/api/admin/hardwares/descobrir/ia-tecnica/enriquecer", "POST"),
        ("/api/admin/hardwares/descobrir/meta-ai-whatsapp/enriquecer", "POST"),
    }
    assert expected <= routes


def test_legacy_routes_remain_registered():
    routes = _routes()
    expected = {
        ("/descobrir-hardwares/fontes", "GET"),
        ("/descobrir-hardwares", "POST"),
        ("/descobrir-hardwares/detalhar", "POST"),
        ("/ia-tecnica/gerar-prompt", "POST"),
        ("/ia-tecnica/enriquecer", "POST"),
        ("/meta-ai-whatsapp/enriquecer", "POST"),
    }
    assert expected <= routes
