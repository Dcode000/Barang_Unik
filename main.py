import os
import time
import uuid
import hashlib
import base64
import logging
import asyncio
from typing import List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv

# ==============================================================================
# FASTAPI & ENTERPRISE DEPENDENCIES
# ==============================================================================
from fastapi import FastAPI, Request, Form, HTTPException, status, Depends, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
import uvicorn

# ==============================================================================
# MODULE IMPORT (Database, AI, Bot)
# ==============================================================================
from database import supabase
from bot import send_owner_notif
from ai_agent import get_ai_recommendation

# ==============================================================================
# 0. KONFIGURASI LOGGING & ENVIRONMENT
# ==============================================================================
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("barangunik.engine")

ADMIN_USER = os.getenv("ADMIN_USER", "adminunik")
ADMIN_PASS = os.getenv("ADMIN_PASS", "UnikSultan2026!")
SECRET_TOKEN = os.getenv("SECRET_TOKEN", "rahasia-banget-bre-2026")
COOKIE_NAME = "unik_admin_session"

# ==============================================================================
# 1. INISIALISASI FASTAPI APP & MIDDLEWARE
# ==============================================================================
app = FastAPI(
    title="Barang Unik Enterprise Web Engine",
    description="Backend Monolith Terstruktur untuk E-Commerce Barang Unik",
    version="2.0.0-Dewa"
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware Performance Tracker
class RequestTimerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        if process_time > 1.0:
            logger.warning(f"🐢 [PERFORMANCE] {request.method} {request.url.path} butuh {process_time:.2f} detik")
        return response

app.add_middleware(RequestTimerMiddleware)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ==============================================================================
# 2. DATA VALIDATION SCHEMAS (PYDANTIC)
# ==============================================================================
# Schema untuk nangkep data JSON dari Frontend (checkout.html)
class CustomerData(BaseModel):
    name: str
    whatsapp: str
    address: str
    payment: str

class CartItem(BaseModel):
    id: int
    name: str
    price: float
    qty: int
    image: str

class CheckoutPayload(BaseModel):
    customer: CustomerData
    items: List[CartItem]
    total_amount: float

class ChatPayload(BaseModel):
    message: str

# ==============================================================================
# 3. SECURITY & AUTHENTICATION ENGINE 🔐
# ==============================================================================
def create_secure_cookie(username: str) -> str:
    raw_data = f"{username}|{SECRET_TOKEN}"
    signature = hashlib.sha256(raw_data.encode()).hexdigest()
    return base64.b64encode(f"{username}|{signature}".encode()).decode()

async def verify_admin(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    try:
        raw_decoded = base64.b64decode(token).decode()
        username, signature = raw_decoded.split("|")
        expected_sig = hashlib.sha256(f"{username}|{SECRET_TOKEN}".encode()).hexdigest()
        if signature != expected_sig:
            raise ValueError("Signature Cookie Dipalsukan!")
        request.state.admin_user = username
        return True
    except Exception as e:
        logger.warning(f"🔒 [AUTH HACK ATTEMPT]: {e}")
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})

# Helper function buat standar response API
def api_success(**payload):
    return {"status": "success", **payload}

def api_error(message: str, status_code: int = 400):
    return JSONResponse(status_code=status_code, content={"status": "error", "message": message})

# ==============================================================================
# 4. ROUTER: ZONA PUBLIK (CUSTOMER FRONTEND) 🌐
# ==============================================================================
@app.get("/", response_class=HTMLResponse, tags=["Web Customer"])
async def read_root(request: Request, bg_tasks: BackgroundTasks):
    """Halaman Katalog Utama"""
    bg_tasks.add_task(send_owner_notif, "👀 <b>Radar Unik:</b> Seseorang baru saja mendarat di website lu bos!")
    produk_aktif = []
    
    if supabase:
        try:
            res = supabase.table("products").select("*").eq("is_active", True).order("id").execute()
            produk_aktif = res.data or []
        except Exception as e:
            logger.error(f"❌ [DB ERROR] Gagal load produk: {e}")

    return templates.TemplateResponse(request=request, name="customer/detail.html", context={"request": request, "produk": res.data})

@app.get("/detail/{product_id}", response_class=HTMLResponse, tags=["Web Customer"])
async def detail_product(request: Request, product_id: int):
    """Halaman Detail Produk Spesifik"""
    if not supabase: raise HTTPException(status_code=503, detail="Database Offline")
    try:
        res = supabase.table("products").select("*").eq("id", product_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Barang tidak ditemukan")
        return templates.TemplateResponse("customer/detail.html", {"request": request, "produk": res.data})
    except Exception as e:
        logger.error(f"❌ [DB ERROR] Gagal load detail: {e}")
        raise HTTPException(status_code=404, detail="Barang tidak ditemukan")

@app.get("/checkout", response_class=HTMLResponse, tags=["Web Customer"])
async def checkout_page(request: Request):
    """Halaman Checkout"""
    return templates.TemplateResponse("customer/checkout.html", {"request": request})

@app.get("/ai-assistant", response_class=HTMLResponse, tags=["Web Customer"])
async def ai_assistant_page(request: Request):
    """Halaman Mimin AI"""
    return templates.TemplateResponse("customer/cs_ai.html", {"request": request})

# ==============================================================================
# 5. ROUTER: API ENDPOINT (LOGIC PROCESSING) ⚙️
# ==============================================================================
@app.post("/api/chat", tags=["API Customer"])
async def api_chat_ai(payload: ChatPayload):
    """Jembatan antara user dan Mimin Unik (Gemini)"""
    if not payload.message.strip():
        return api_error("Pesan kosong bre", 400)
    
    try:
        reply = await get_ai_recommendation(payload.message)
        return api_success(reply=reply)
    except Exception as e:
        logger.error(f"❌ [AI ERROR]: {e}")
        return api_error("Aduh, Mimin lagi pusing. Coba lagi bentar ya!", 500)

@app.post("/api/checkout", tags=["API Customer"])
async def api_process_checkout(payload: CheckoutPayload, bg_tasks: BackgroundTasks):
    """Mesin Pemroses Pesanan (Insert DB & Update Stok)"""
    if not supabase: return api_error("Database sedang offline", 503)

    try:
        # 1. Bikin Nomor Order Unik
        order_number = f"UNIK-{datetime.now().strftime('%y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
        
        # 2. Simpan Data Customer
        res_cust = supabase.table("customers").insert({
            "full_name": payload.customer.name,
            "whatsapp_number": payload.customer.whatsapp,
            "shipping_address": payload.customer.address
        }).execute()
        cust_id = res_cust.data[0]['id']

        # 3. Simpan Header Pesanan
        res_order = supabase.table("orders").insert({
            "order_number": order_number,
            "customer_id": cust_id,
            "total_amount": payload.total_amount,
            "payment_method": payload.customer.payment,
            "status": "Menunggu Pembayaran"
        }).execute()
        order_id = res_order.data[0]['id']

        # 4. Proses Item & Potong Stok Real-time
        for item in payload.items:
            # Simpan Item
            supabase.table("order_items").insert({
                "order_id": order_id,
                "product_id": item.id,
                "quantity": item.qty,
                "price_at_time": item.price
            }).execute()

            # Potong Stok
            prod_data = supabase.table("products").select("stock_quantity").eq("id", item.id).single().execute()
            if prod_data.data:
                old_stock = int(prod_data.data.get("stock_quantity", 0))
                new_stock = max(0, old_stock - item.qty)
                supabase.table("products").update({"stock_quantity": new_stock}).eq("id", item.id).execute()

        # 5. Notifikasi ke Telegram Owner (Background Task)
        pesan_bos = (
            f"🚨 <b>BOS, ADA ORDERAN MASUK!</b> 🚨\n\n"
            f"👤 <b>Pembeli:</b> {payload.customer.name}\n"
            f"📞 <b>WA:</b> {payload.customer.whatsapp}\n"
            f"💳 <b>Metode:</b> {payload.customer.payment}\n"
            f"💰 <b>Total:</b> Rp {payload.total_amount:,.0f}\n"
            f"📦 <b>No. Order:</b> <code>{order_number}</code>\n\n"
            f"Buka dashboard web sekarang buat proses resinya bre!"
        )
        bg_tasks.add_task(send_owner_notif, pesan_bos)

        logger.info(f"✅ [CHECKOUT] Order {order_number} sukses dibuat!")
        return api_success(order_number=order_number)

    except Exception as e:
        logger.error(f"❌ [CHECKOUT ERROR]: {e}")
        return api_error(str(e), 500)

# ==============================================================================
# 6. ROUTER: ZONA TERLARANG (ADMIN PANEL) 🔐
# ==============================================================================
@app.get("/admin/login", response_class=HTMLResponse, tags=["Admin Auth"])
async def login_page(request: Request):
    if request.cookies.get(COOKIE_NAME):
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("admin/login.html", {"request": request})

@app.post("/admin/login", response_class=HTMLResponse, tags=["Admin Auth"])
async def do_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        logger.info(f"🔓 Admin '{username}' berhasil login.")
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key=COOKIE_NAME, value=create_secure_cookie(username), httponly=True, max_age=43200)
        return response
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Username/Password salah!"})

@app.get("/admin/logout", tags=["Admin Auth"])
async def do_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response

# --- ADMIN DASHBOARD VIEWS ---
@app.get("/admin", response_class=HTMLResponse, tags=["Admin Core"], dependencies=[Depends(verify_admin)])
async def admin_dashboard(request: Request):
    """Pusat Komando: Analitik Ringkas"""
    # Dummy data buat preview, nanti bisa diganti query DB beneran
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})

@app.get("/admin/orders", response_class=HTMLResponse, tags=["Admin CRM"], dependencies=[Depends(verify_admin)])
async def admin_orders(request: Request):
    """Manajemen Pesanan"""
    orders_data = []
    if supabase:
        try:
            res = supabase.table("orders").select("*, customers(full_name, whatsapp_number)").order("created_at", desc=True).execute()
            orders_data = res.data or []
        except Exception as e:
            logger.error(f"Gagal load orders: {e}")
            
    return templates.TemplateResponse("admin/orders.html", {"request": request, "pesanan": orders_data})

@app.post("/admin/orders/update", tags=["Admin CRM"], dependencies=[Depends(verify_admin)])
async def update_order_status(order_id: int = Form(...), status_order: str = Form(...)):
    """Update Status & Otomatis Catat Keuangan kalau Selesai"""
    if not supabase: raise HTTPException(status_code=503)
    try:
        # Tarik data lama
        old_order = supabase.table("orders").select("status, total_amount, order_number").eq("id", order_id).single().execute()
        old_status = old_order.data.get("status")
        
        # Update status
        supabase.table("orders").update({"status": status_order}).eq("id", order_id).execute()
        
        # LOGIC DEWA: Kalau status jadi "Selesai", otomatis catat ke Buku Kas (Ledger)
        if status_order.lower() == "selesai" and old_status.lower() != "selesai":
            omset = float(old_order.data.get("total_amount", 0))
            no_order = old_order.data.get("order_number")
            
            supabase.table("finance_ledger").insert({
                "transaction_type": "IN",
                "amount": omset,
                "category": "Penjualan Barang Unik",
                "description": f"Pencairan dana otomatis dari order {no_order}",
                "reference_order_id": order_id
            }).execute()
            logger.info(f"💰 Omset Rp {omset} dari {no_order} masuk ke Ledger!")

        return RedirectResponse(url="/admin/orders", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Gagal update status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# RUNNER
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
