from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.http import FileResponse, HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from api_service import (
    DB_PATH,
    ServiceValidationError,
    ensure_storage,
    generate_trip_from_payload,
    plan_trip_from_payload,
    resolve_template_path,
    serialize_driver_profile,
    serialize_user,
)
from driver_log_renderer import list_dynamic_fields
from persistence import (
    create_session,
    create_user_with_organization,
    delete_session,
    get_daily_log,
    get_driver_profile,
    get_user_by_email,
    get_user_by_session_token,
    hash_password,
    init_db,
    upsert_driver_profile,
    verify_password,
)
from trip_planner import TripPlannerError


SESSION_COOKIE_NAME = "driver_session"

init_db(DB_PATH)
ensure_storage()


def json_error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"detail": message}, status=status)


def parse_json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceValidationError("Request body must be valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ServiceValidationError("Request body must be a JSON object.")
    return payload


def get_session_token(request: HttpRequest) -> str | None:
    cookie_token = request.COOKIES.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def get_current_user(request: HttpRequest):
    token = get_session_token(request)
    if not token:
        return None
    return get_user_by_session_token(DB_PATH, token)


def require_authenticated_user(request: HttpRequest):
    user = get_current_user(request)
    if user is None:
        raise PermissionError("Authentication required.")
    if user.role != "driver":
        raise PermissionError("Only driver accounts are supported in this assessment flow.")
    return user


def build_auth_response(user, *, status: int = 200) -> JsonResponse:
    session = create_session(DB_PATH, user.id)
    profile = get_driver_profile(DB_PATH, user.id)
    response = JsonResponse(
        {
            "user": serialize_user(user),
            "profile": serialize_driver_profile(profile),
            "onboarding_required": not bool(profile and profile.is_onboarding_complete),
        },
        status=status,
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session.token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=24 * 60 * 60,
    )
    return response


def health(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse({"status": "ok", "framework": "django"})


@csrf_exempt
def auth_signup(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        payload = parse_json_body(request)
        full_name = str(payload.get("full_name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))

        if len(full_name) < 2:
            raise ServiceValidationError("Full name is required.")
        if "@" not in email or "." not in email:
            raise ServiceValidationError("A valid email is required.")
        if len(password) < 8:
            raise ServiceValidationError("Password must be at least 8 characters.")

        workspace_name = f"{full_name.split()[0]}'s Driver Workspace"
        user = create_user_with_organization(
            db_path=DB_PATH,
            organization_name=workspace_name,
            full_name=full_name,
            email=email,
            role="driver",
            password_hash_value=hash_password(password),
        )
        upsert_driver_profile(
            db_path=DB_PATH,
            organization_id=user.organization_id,
            user_id=user.id,
            carrier_name="",
            main_office_address="",
            home_terminal_address="",
            truck_trailer_numbers="",
            cycle_rule="70",
            is_onboarding_complete=False,
        )
        return build_auth_response(user, status=201)
    except ServiceValidationError as exc:
        return json_error(str(exc), 422)
    except Exception as exc:
        message = str(exc)
        if "UNIQUE constraint failed: users.email" in message:
            return json_error("Email already exists.", 409)
        return json_error(message or "Unable to create account.", 400)


@csrf_exempt
def auth_login(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        payload = parse_json_body(request)
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        if not email or not password:
            raise ServiceValidationError("Email and password are required.")

        user, password_hash_value = get_user_by_email(DB_PATH, email)
        if user is None or not password_hash_value or not verify_password(password, password_hash_value):
            return json_error("Invalid email or password.", 401)

        return build_auth_response(user)
    except ServiceValidationError as exc:
        return json_error(str(exc), 422)


@csrf_exempt
def auth_logout(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    token = get_session_token(request)
    if token:
        delete_session(DB_PATH, token)

    response = JsonResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME, samesite="none", secure=True)
    return response


def auth_me(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    try:
        user = require_authenticated_user(request)
        profile = get_driver_profile(DB_PATH, user.id)
        return JsonResponse(
            {
                "user": serialize_user(user),
                "profile": serialize_driver_profile(profile),
                "onboarding_required": not bool(profile and profile.is_onboarding_complete),
            }
        )
    except PermissionError as exc:
        return json_error(str(exc), 401)


@csrf_exempt
def profile_detail(request: HttpRequest) -> JsonResponse:
    try:
        user = require_authenticated_user(request)
    except PermissionError as exc:
        return json_error(str(exc), 401)

    if request.method == "GET":
        return JsonResponse({"profile": serialize_driver_profile(get_driver_profile(DB_PATH, user.id))})

    if request.method != "PUT":
        return HttpResponseNotAllowed(["GET", "PUT"])

    try:
        current_profile = get_driver_profile(DB_PATH, user.id)
        if current_profile is not None and current_profile.is_onboarding_complete:
            return json_error(
                "Onboarding is locked once submitted for this assessment flow.",
                409,
            )

        payload = parse_json_body(request)
        carrier_name = str(payload.get("carrier_name", "")).strip()
        main_office_address = str(payload.get("main_office_address", "")).strip()
        home_terminal_address = str(payload.get("home_terminal_address", "")).strip()
        truck_trailer_numbers = str(payload.get("truck_trailer_numbers", "")).strip()

        if len(carrier_name) < 2:
            raise ServiceValidationError("Carrier name is required.")
        if len(main_office_address) < 5:
            raise ServiceValidationError("Main office address is required.")
        if len(home_terminal_address) < 5:
            raise ServiceValidationError("Home terminal address is required.")
        if len(truck_trailer_numbers) < 2:
            raise ServiceValidationError("Truck / trailer numbers are required.")

        profile = upsert_driver_profile(
            db_path=DB_PATH,
            organization_id=user.organization_id,
            user_id=user.id,
            carrier_name=carrier_name,
            main_office_address=main_office_address,
            home_terminal_address=home_terminal_address,
            truck_trailer_numbers=truck_trailer_numbers,
            cycle_rule="70",
            is_onboarding_complete=True,
        )
        return JsonResponse({"profile": serialize_driver_profile(profile)})
    except ServiceValidationError as exc:
        return json_error(str(exc), 422)


def fields(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    try:
        user = require_authenticated_user(request)
        del user
        template_path = resolve_template_path()
        return JsonResponse(
            {
                "template": template_path.name,
                "fields": list_dynamic_fields(template_path),
                "locked_profile_field_ids": [
                    "name-of-carrier",
                    "main-office-address",
                    "home-terminal-address",
                    "truck-trailer-numbers",
                ],
            }
        )
    except PermissionError as exc:
        return json_error(str(exc), 401)


@csrf_exempt
def trips_plan(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        user = require_authenticated_user(request)
        profile = get_driver_profile(DB_PATH, user.id)
        if profile is None or not profile.is_onboarding_complete:
            return json_error("Complete onboarding before planning a trip.", 409)

        payload = parse_json_body(request)
        plan = plan_trip_from_payload(payload, cycle_rule=profile.cycle_rule)
        return JsonResponse(plan)
    except PermissionError as exc:
        return json_error(str(exc), 401)
    except (ServiceValidationError, TripPlannerError) as exc:
        return json_error(str(exc), 422)


@csrf_exempt
def trips_generate(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        user = require_authenticated_user(request)
        profile = get_driver_profile(DB_PATH, user.id)
        if profile is None:
            return json_error("Driver profile not found.", 404)

        payload = parse_json_body(request)
        result = generate_trip_from_payload(
            payload,
            current_user=user,
            profile=profile,
            save_record=True,
        )
        return JsonResponse(result)
    except PermissionError as exc:
        return json_error(str(exc), 401)
    except (ServiceValidationError, TripPlannerError) as exc:
        return json_error(str(exc), 422)
    except Exception as exc:
        return json_error(str(exc) or "Trip generation failed.", 500)


def _log_file_response(request: HttpRequest, record_id: str, suffix: str, content_type: str):
    try:
        user = require_authenticated_user(request)
    except PermissionError as exc:
        return json_error(str(exc), 401)

    record = get_daily_log(DB_PATH, record_id)
    if record is None:
        return json_error("Log record not found.", 404)
    if record["organization_id"] != user.organization_id or record["driver_user_id"] != user.id:
        return json_error("You can only access your own logs.", 403)

    file_path = Path(str(record[f"{suffix}_path"]))
    if not file_path.exists():
        return json_error("Generated file is missing.", 404)

    response = FileResponse(file_path.open("rb"), content_type=content_type)
    response["Content-Length"] = str(file_path.stat().st_size)
    response["Content-Disposition"] = f'inline; filename="{file_path.name}"'
    return response


def log_svg(request: HttpRequest, record_id: str, filename: str | None = None):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _log_file_response(request, record_id, "svg", "image/svg+xml")


def log_pdf(request: HttpRequest, record_id: str, filename: str | None = None):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _log_file_response(request, record_id, "pdf", "application/pdf")
