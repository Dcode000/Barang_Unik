import os
import time
import hashlib
import base64
import logging
import asyncio
from typing import Optional, List
from datetime import datetime
from dotenv import load_dotenv

# ==============================================================================
# FASTAPI & CORE DEPENDENCIES
# ==============================================================================
from fastapi import FastAPI, Request, Form, HTTPException, status, Depends, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
import uvicorn

# Local Modules (Pastikan file-file ini udah ada dan diisi)
from database import supabase
from bot import send_owner_notif
from ai_agent import get_ai_recommendation

# ==============================================================================
# 0. KONFIGURASI LINGKUNGAN & KEAMANAN
# ==============================================================================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("barangunik.core")

ADMIN_USER = os.getenv("ADMIN_USER", "adminunik")
ADMIN_PASS = os.getenv("ADMIN_PASS", "UnikSultan2026!")
SECRET_TOKEN = os.getenv("SECRET_TOKEN", "rahasia-banget-bre-2026")
COOKIE_NAME = "unik_admin_session"

# ==============================================================================
# 1. INISIALISASI FASTAPI APP
# ==============================================================================
app = FastAPI(
    title="Barang Unik Web Engine",
    description="Sistem e-commerce super cepat dengan integrasi AI dan Notifikasi Telegram",
    version="1.0.0"
)

# Middleware CORS (Biar aman kalau ada API eksternal)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware Timer (Buat ngecek seberapa cepet web lu dirender)
class RequestTimerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        if process_time > 1.0:
            logger.warning(f"🐢 {request.method} {request.url.path} agak lemot nih: {process_time:.2f}s")
        return response

app.add_middleware(RequestTimerMiddleware)

# Mount Folder Static & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ==============================================================================
# 2. SISTEM KEAMANAN (AUTH ENGINE) 🔐
# ==============================================================================
def create_secure_cookie(username: str) -> str:
    """Bikin tiket cookie anti-maling"""
    raw_data = f"{username}|{SECRET_TOKEN}"
    signature = hashlib.sha256(raw_data.encode()).hexdigest()
    return base64.b64encode(f"{username}|{signature}".encode()).decode()

def verify_admin(request: Request):
    """Fungsi penjaga pintu admin"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    try:
        raw_decoded = base64.b64decode(token).decode()
        username, signature = raw_decoded.split("|")
        expected_sig = hashlib.sha256(f"{username}|{SECRET_TOKEN}".encode()).hexdigest()
        if signature != expected_sig:
            raise ValueError("Waduh, Cookie dipalsukan!")
        request.state.admin_user = username
        return True
    except Exception as e:
        logger.warning(f"🔒 [HACK ATTEMPT] Gagal masuk: {e}")
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})

# ==============================================================================
# 3. ROUTER ZONA PUBLIK (CUSTOMER FRONTEND) 🌐
# ==============================================================================
@app.get("/", response_class=HTMLResponse, tags=["Web Customer"])
async def read_root(request: Request, bg_tasks: BackgroundTasks):
    """Halaman Utama: Katalog Barang Unik"""
    
    # Kirim notif ke telegram owner tanpa bikin web loading lama
    bg_tasks.add_task(send_owner_notif, "👀 <b>Ada Pengunjung Baru!</b>\nSeseorang sedang melihat-lihat katalog barangunik.com")
    
    produk_unik = []
    if supabase:
        try:
            res = supabase.table("products").select("*").eq("is_active", True).execute()
            produk_unik = res.data or []
        except Exception as e:
            logger.error(f"Gagal narik data produk: {e}")

    return templates.TemplateResponse("customer/index.html", {
        "request": request,
        "produk": produk_unik
    })

@app.get("/ai-assistant", response_class=HTMLResponse, tags=["Web Customer"])
async def ai_assistant_page(request: Request):
    """Halaman Chat AI Mimin Unik"""
    return templates.TemplateResponse("customer/cs_ai.html", {"request": request})

# ==============================================================================
# 4. ROUTER ZONA TERLARANG (ADMIN DASHBOARD) 🔐
# ==============================================================================
@app.get("/admin/login", response_class=HTMLResponse, tags=["Admin Auth"])
async def login_page(request: Request):
    if request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("admin/login.html", {"request": request})

@app.post("/admin/login", response_class=HTMLResponse, tags=["Admin Auth"])
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Validasi Login Admin"""
    if username == ADMIN_USER and password == ADMIN_PASS:
        logger.info(f"🔓 Admin '{username}' berhasil login.")
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        # Set cookie tahan 12 jam
        response.set_cookie(key=COOKIE_NAME, value=create_secure_cookie(username), httponly=True, max_age=43200)
        return response
    
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Username atau Password salah bre!"})

@app.get("/admin/logout", tags=["Admin Auth"])
async def do_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response

@app.get("/admin", response_class=HTMLResponse, tags=["Admin Core"], dependencies=[Depends(verify_admin)])
async def admin_dashboard(request: Request):
    """Dashboard Utama Admin"""
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "admin_name": getattr(request.state, "admin_user", "Bos")
    })

# ==============================================================================
# ENTRY POINT RUNNER
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Dijalankan dengan uvicorn (Bisa untuk lokal atau VPS production)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)