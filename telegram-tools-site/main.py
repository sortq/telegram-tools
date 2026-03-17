from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import ADMIN_API_KEY, ADMIN_LOGIN, ADMIN_PASSWORD, ALLOWED_ORIGINS
from database import get_connection
from support_bot import send_request


BASE_DIR = Path(__file__).resolve().parent
VALID_STATUSES = {"new", "in_progress", "done"}
limiter = Limiter(key_func=get_remote_address)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class RequestPayload(BaseModel):
    username: Optional[str] = ""
    bot_name: str = ""
    comment: Optional[str] = ""


class RequestUpdatePayload(BaseModel):
    status: Optional[str] = None
    developer: Optional[str] = None


class AdminLoginPayload(BaseModel):
    login: str
    password: str


def verify_admin_key(api_key: str):
    if api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="forbidden")


@app.get("/")
def read_index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/index.html")
def read_index_html():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/admin")
def read_admin():
    return FileResponse(BASE_DIR / "admin.html")


@app.get("/login.html")
def read_login():
    return FileResponse(BASE_DIR / "login.html")


@app.get("/faq.html")
def read_faq():
    return FileResponse(BASE_DIR / "faq.html")


@app.get("/viral-tracker.html")
def read_viral_tracker():
    return FileResponse(BASE_DIR / "viral-tracker.html")


@app.get("/channel-analytics.html")
def read_channel_analytics():
    return FileResponse(BASE_DIR / "channel-analytics.html")


@app.get("/growth-monitor.html")
def read_growth_monitor():
    return FileResponse(BASE_DIR / "growth-monitor.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/send-request")
@limiter.limit("10/minute")
async def create_request(request: Request, payload: RequestPayload):
    username = (payload.username or "").strip() or "-"
    bot_name = payload.bot_name.strip()
    comment = (payload.comment or "").strip() or "-"

    if not bot_name:
        raise HTTPException(status_code=400, detail="bot_name is required")

    created_at = datetime.utcnow().isoformat(timespec="seconds")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(requests)")
        columns = {row[1] for row in cursor.fetchall()}

        payload_map = {
            "username": username,
            "bot": bot_name,
            "bot_name": bot_name,
            "comment": comment,
            "status": "new",
            "developer": "",
            "created_at": created_at,
            "updated_at": created_at,
        }

        insert_columns = [column for column in payload_map if column in columns]
        placeholders = ", ".join(["?"] * len(insert_columns))
        values = [payload_map[column] for column in insert_columns]

        cursor.execute(
            f"INSERT INTO requests ({', '.join(insert_columns)}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
        request_id = int(cursor.lastrowid)

    logger.info(f"New request #{request_id} | user={username} | bot={bot_name}")
    await send_request(request_id, username, bot_name, comment)
    return {"status": "saved", "id": request_id}


@app.post("/admin-login")
def admin_login(payload: AdminLoginPayload):
    if payload.login == ADMIN_LOGIN and payload.password == ADMIN_PASSWORD:
        return {"status": "ok", "api_key": ADMIN_API_KEY}
    raise HTTPException(status_code=401, detail="invalid credentials")


@app.get("/requests")
def get_requests(x_admin_key: str = Header(..., alias="X-ADMIN-KEY")):
    verify_admin_key(x_admin_key)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, username, bot, comment, status, developer, created_at
        FROM requests
        ORDER BY id DESC
        """)
        rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "username": r[1],
            "bot": r[2],
            "comment": r[3],
            "status": r[4],
            "developer": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


@app.post("/requests/{request_id}")
def update_request(
    request_id: int,
    payload: RequestUpdatePayload,
    x_admin_key: str = Header(..., alias="X-ADMIN-KEY"),
):
    verify_admin_key(x_admin_key)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM requests WHERE id = ?", (request_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="request not found")

        updates = []
        values = []

        if payload.status is not None:
            if payload.status not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail="invalid status")
            updates.append("status = ?")
            values.append(payload.status)

        if payload.developer is not None:
            updates.append("developer = ?")
            values.append(payload.developer.strip())

        if not updates:
            raise HTTPException(status_code=400, detail="nothing to update")

        values.append(request_id)
        cursor.execute(f"UPDATE requests SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()

        cursor.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
        return cursor.fetchone()
