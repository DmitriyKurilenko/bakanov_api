from ninja import NinjaAPI

from apps.crm.api import router as crm_router
from apps.integrations.api import router as integrations_router

api = NinjaAPI(title="Bakanov API", version="0.1.0")
api.add_router("/crm/", crm_router)
api.add_router("/integrations/", integrations_router)


@api.get("/healthz")
def healthz(request):
    return {"status": "ok"}
