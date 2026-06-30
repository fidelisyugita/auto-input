from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.runner import runner
from app.settings import (
    load_settings,
    nik_info,
    nik_path,
    progress_summary,
    save_settings,
    tail_log,
)

app = FastAPI(title="MAP Automation Control Panel")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("WEB_SECRET_KEY", "change-me-in-production"),
    session_cookie="map_session",
    max_age=86400 * 7,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def web_username() -> str:
    return os.getenv("WEB_USERNAME", "admin")


def web_password() -> str:
    return os.getenv("WEB_PASSWORD", "admin")


def logged_in_user(request: Request) -> str | None:
    return request.session.get("user")


def require_user(request: Request) -> RedirectResponse | str:
    user = logged_in_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return user


@app.get("/")
async def root():
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
async def health():
    return {"status": "ok", "runner": runner.status_dict()}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if logged_in_user(request):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == web_username() and password == web_password():
        request.session["user"] = username
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid username or password."},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "settings": load_settings(),
            "nik": nik_info(),
            "runner": runner.status_dict(),
            "progress": progress_summary(),
            "logs": tail_log(50),
            "message": request.query_params.get("message"),
            "error": request.query_params.get("error"),
        },
    )


def _normalize_quantity_pattern(raw: str) -> str:
    """Keep only positive integers, e.g. "1, 2 ,2" -> "1,2,2"."""
    values = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if chunk.isdigit() and int(chunk) >= 1:
            values.append(str(int(chunk)))
    return ",".join(values) or "1"


@app.post("/settings")
async def update_settings(
    request: Request,
    merchant_phone: str = Form(...),
    merchant_pin: str = Form(...),
    action_delay_ms: int = Form(500),
    quantity_pattern: str = Form("1,2,2"),
):
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    if runner.is_running():
        return RedirectResponse(
            "/dashboard?error=Stop+the+bot+before+changing+settings",
            status_code=303,
        )
    save_settings(
        {
            "merchant_phone": merchant_phone.strip(),
            "merchant_pin": merchant_pin.strip(),
            "action_delay_ms": action_delay_ms,
            "quantity_pattern": _normalize_quantity_pattern(quantity_pattern),
        }
    )
    return RedirectResponse("/dashboard?message=Settings+saved", status_code=303)


@app.post("/upload-nik")
async def upload_nik(
    request: Request,
    nik_file: UploadFile = File(...),
):
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    if runner.is_running():
        return RedirectResponse(
            "/dashboard?error=Stop+the+bot+before+uploading+NIK+file",
            status_code=303,
        )

    filename = nik_file.filename or "nik.json"
    if not filename.lower().endswith(".json"):
        return RedirectResponse(
            "/dashboard?error=Only+.json+NIK+files+are+supported",
            status_code=303,
        )

    raw = await nik_file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return RedirectResponse(
            "/dashboard?error=Invalid+JSON+file",
            status_code=303,
        )

    niks = data.get("niks", data if isinstance(data, list) else None)
    if not isinstance(niks, list) or not niks:
        return RedirectResponse(
            "/dashboard?error=JSON+must+contain+a+niks+array",
            status_code=303,
        )

    dest = nik_path()
    payload = {
        "description": data.get("description", "Uploaded NIK list"),
        "total": len(niks),
        "niks": [str(n).strip() for n in niks],
    }
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    save_settings({"nik_file": dest.name})
    return RedirectResponse(
        f"/dashboard?message=Uploaded+{len(niks)}+NIKs",
        status_code=303,
    )


@app.post("/start")
async def start_bot(request: Request):
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    settings = load_settings()
    if not settings.get("merchant_phone") or not settings.get("merchant_pin"):
        return RedirectResponse(
            "/dashboard?error=Set+merchant+phone+and+PIN+first",
            status_code=303,
        )
    if not nik_path().exists():
        return RedirectResponse(
            "/dashboard?error=Upload+a+NIK+JSON+file+first",
            status_code=303,
        )
    ok, msg = runner.start()
    param = "message" if ok else "error"
    return RedirectResponse(f"/dashboard?{param}={msg.replace(' ', '+')}", status_code=303)


@app.post("/stop")
async def stop_bot(request: Request):
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    ok, msg = runner.stop()
    param = "message" if ok else "error"
    return RedirectResponse(f"/dashboard?{param}={msg.replace(' ', '+')}", status_code=303)


@app.get("/api/status")
async def api_status(request: Request):
    user = require_user(request)
    if isinstance(user, RedirectResponse):
        return user

    return JSONResponse(
        {
            "runner": runner.status_dict(),
            "nik": nik_info(),
            "logs": tail_log(30),
        }
    )
