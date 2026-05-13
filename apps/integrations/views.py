import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt

from apps.integrations.models import Bitrix24Portal
from apps.integrations.services.bitrix24_oauth import save_portal_from_request

logger = logging.getLogger(__name__)


@csrf_exempt
@xframe_options_exempt
def bitrix24_install(request: HttpRequest) -> HttpResponse:
    """Handle Bitrix24 local-app install callback (POST inside iframe)."""
    if request.method != "POST":
        return render(request, "bitrix24/error.html", {"message": "Method not allowed"}, status=405)

    data = request.POST.dict()
    member_id = data.get("member_id")
    if not member_id:
        logger.warning("Bitrix24 install: missing member_id")
        return render(request, "bitrix24/error.html", {"message": "Missing member_id"}, status=400)

    try:
        save_portal_from_request(data)
    except Exception:
        logger.exception("Bitrix24 install failed for member_id=%s", member_id)
        return render(request, "bitrix24/error.html", {"message": "Install error"}, status=500)

    return render(request, "bitrix24/install_success.html")


@csrf_exempt
@xframe_options_exempt
def bitrix24_app(request: HttpRequest) -> HttpResponse:
    """Main app page rendered inside the Bitrix24 iframe."""
    if request.method != "POST":
        return render(request, "bitrix24/error.html", {"message": "Method not allowed"}, status=405)

    data = request.POST.dict()
    member_id = data.get("member_id")
    if not member_id:
        return render(request, "bitrix24/error.html", {"message": "Missing member_id"}, status=400)

    try:
        portal = Bitrix24Portal.objects.get(member_id=member_id, is_active=True)
    except Bitrix24Portal.DoesNotExist:
        logger.warning("Bitrix24 app: unknown portal member_id=%s", member_id)
        return render(request, "bitrix24/error.html", {"message": "Портал не найден. Переустановите приложение."}, status=404)

    # Update tokens from the fresh POST payload.
    auth_id = data.get("AUTH_ID", "")
    if auth_id:
        save_portal_from_request(data)
        portal.refresh_from_db()

    return render(request, "bitrix24/app.html", {
        "portal": portal,
        "domain": portal.domain,
        "member_id": portal.member_id,
    })
