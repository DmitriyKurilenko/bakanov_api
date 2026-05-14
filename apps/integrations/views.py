import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt

from apps.integrations.models import Bitrix24Portal
from apps.integrations.services.bitrix24_contract_service import Bitrix24ContractService
from apps.integrations.services.bitrix24_oauth import save_portal_from_request
from apps.integrations.services.email_service import send_contract_email

logger = logging.getLogger(__name__)


@csrf_exempt
@xframe_options_exempt
def bitrix24_install(request: HttpRequest) -> HttpResponse:
    """Handle Bitrix24 local-app install callback.

    Bitrix24 first makes a GET request to verify the URL is reachable,
    then POST with credentials inside the iframe.
    """
    if request.method == "GET":
        return render(request, "bitrix24/install_success.html")

    if request.method != "POST":
        return render(request, "bitrix24/error.html", {"message": "Method not allowed"}, status=405)

    data = request.POST.dict()
    member_id = data.get("member_id")
    if not member_id:
        logger.warning("Bitrix24 install: missing member_id")
        return render(request, "bitrix24/error.html", {"message": "Missing member_id"}, status=400)

    try:
        portal = save_portal_from_request(data)
    except Exception:
        logger.exception("Bitrix24 install failed for member_id=%s", member_id)
        return render(request, "bitrix24/error.html", {"message": "Install error"}, status=500)

    # Auto-register placement for contract form in deal detail tab
    if portal:
        try:
            from apps.integrations.services.bitrix24_service import Bitrix24Client
            client = Bitrix24Client.from_settings()
            client._call("placement.bind", {
                "PLACEMENT": "CRM_DEAL_DETAIL_TAB",
                "HANDLER": "https://kapitan.prvms.ru/bitrix24/contract/",
                "TITLE": "Договор",
            })
            logger.info("Placement CRM_DEAL_DETAIL_TAB registered for member_id=%s", member_id)
        except Exception:
            logger.warning("Failed to register placement for member_id=%s", member_id, exc_info=True)

    return render(request, "bitrix24/install_success.html")


@csrf_exempt
@xframe_options_exempt
def bitrix24_app(request: HttpRequest) -> HttpResponse:
    """Main app page rendered inside the Bitrix24 iframe.

    Bitrix24 may send GET (initial load) or POST (with auth tokens).
    """
    if request.method == "GET":
        # GET request — render without portal context (BX24 JS SDK handles auth)
        return render(request, "bitrix24/app.html", {
            "portal": None,
            "domain": "",
            "member_id": "",
        })

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


@csrf_exempt
@xframe_options_exempt
def bitrix24_contract_form(request: HttpRequest) -> HttpResponse:
    """Contract form rendered inside the Bitrix24 deal detail tab (placement).

    Bitrix24 sends POST with placement params:
    - PLACEMENT: e.g. "CRM_DEAL_DETAIL_TAB"
    - PLACEMENT_ID: deal ID
    - AUTH_ID, REFRESH_ID, etc.
    """
    data = request.POST.dict() if request.method == "POST" else request.GET.dict()
    member_id = data.get("member_id")
    placement = data.get("PLACEMENT", "")
    placement_id = data.get("PLACEMENT_ID", "")

    if not member_id:
        logger.warning("Bitrix24 contract form: missing member_id")
        return render(request, "bitrix24/error.html", {"message": "Missing member_id"}, status=400)

    try:
        portal = Bitrix24Portal.objects.get(member_id=member_id, is_active=True)
    except Bitrix24Portal.DoesNotExist:
        logger.warning("Bitrix24 contract form: unknown portal member_id=%s", member_id)
        return render(request, "bitrix24/error.html", {"message": "Портал не найден. Переустановите приложение."}, status=404)

    auth_id = data.get("AUTH_ID", "")
    if auth_id:
        save_portal_from_request(data)
        portal.refresh_from_db()

    return render(request, "bitrix24/contract_form.html", {
        "portal": portal,
        "domain": portal.domain,
        "member_id": portal.member_id,
        "placement": placement,
        "deal_id": placement_id,
    })


@csrf_exempt
@xframe_options_exempt
def bitrix24_contract_generate(request: HttpRequest) -> JsonResponse:
    """API endpoint: generate contract PDF from form data.

    Expects JSON body with:
        - member_id (str): portal identifier
        - deal_id (int): Bitrix24 deal ID
        - overrides (dict): user-edited fields from the form
        - email_to (str, optional): recipient email override
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "detail": "Method not allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return JsonResponse({"status": "error", "detail": f"Invalid JSON: {exc}"}, status=400)

    member_id = payload.get("member_id")
    deal_id = payload.get("deal_id")
    overrides = payload.get("overrides") or {}
    email_to = payload.get("email_to")

    if not member_id:
        return JsonResponse({"status": "error", "detail": "Missing member_id"}, status=400)
    if not deal_id:
        return JsonResponse({"status": "error", "detail": "Missing deal_id"}, status=400)

    try:
        from apps.integrations.services.bitrix24_service import Bitrix24Client
        client = Bitrix24Client.from_settings()
        service = Bitrix24ContractService(client)
        result = service.render_contract(int(deal_id), overrides=overrides)
    except Exception as exc:
        logger.exception("Contract generation failed for deal_id=%s", deal_id)
        return JsonResponse({"status": "error", "detail": str(exc)}, status=500)

    warnings: list[str] = []

    # Upload PDF to Bitrix24 deal file field
    file_field_id = getattr(settings, "BITRIX24_CONTRACT_FILE_FIELD_ID", "")
    if file_field_id:
        try:
            import base64
            file_content = result.file_path.read_bytes()
            file_name = result.file_path.name
            encoded = base64.b64encode(file_content).decode("utf-8")
            service.client._call("crm.deal.update", {
                "ID": int(deal_id),
                "fields": {
                    str(file_field_id): {"fileData": [file_name, encoded]},
                },
            })
        except Exception as exc:
            warning = f"Failed to upload PDF to deal field: {exc}"
            warnings.append(warning)
            logger.warning("PDF upload to deal failed for deal_id=%s: %s", deal_id, exc)

    # Send email
    if email_to:
        try:
            send_contract_email(
                {"name": overrides.get("client_fullname", "Клиент")},
                result.file_url,
                attachment_path=result.file_path,
            )
        except Exception as exc:
            warning = f"Failed to send email: {exc}"
            warnings.append(warning)
            logger.warning("Email send failed for deal_id=%s: %s", deal_id, exc)

    response_data = {
        "status": "ok" if not warnings else "warning",
        "file_url": result.file_url,
        "detail": "Contract generated successfully",
    }
    if warnings:
        response_data["warnings"] = warnings

    return JsonResponse(response_data)
