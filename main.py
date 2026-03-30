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
from pydantic import BaseModel
import uvicorn

# Local Modules
from database import supabase
from bot import send_owner_notif
from ai_agent import get_ai_recommendation

# ==============================================================================
# 0. KONFIGURASI LOGGING & ENVIRONMENT
# ==============================================================================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("barangunik.engine")

ADMIN_USER = os.getenv("ADMIN_USER", "adminunik")
ADMIN_PASS = os.getenv("ADMIN_PASS", "UnikSultan2026!")
SECRET_TOKEN = os.getenv("SECRET_TOKEN", "rahasia-banget-bre-2026")
ADMIN_COOKIE = "unik_admin_session"
CUSTOMER_COOKIE = "unik_customer_session"

# ==============================================================================
# 1. INISIALISASI FASTAPI APP
# ==============================================================================
app = FastAPI(title="Barang Unik Enterprise Web Engine", version="3.0.0-SuperDewa")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

class RequestTimerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        if (time.time() - start_time) > 1.0:
            logger.warning(f"🐢 [PERFORMANCE] {request.method} {request.url.path} agak lelet nih.")
        return response

app.add_middleware(RequestTimerMiddleware)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ==============================================================================
# 2. DATA SCHEMAS (PYDANTIC)
# ==============================================================================
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
# 3. SECURITY ENGINE (ADMIN & CUSTOMER) 🔐
# ==============================================================================
def create_secure_cookie(data_str: str) -> str:
    signature = hashlib.sha256(f"{data_str}|{SECRET_TOKEN}".encode()).hexdigest()
    return base64.b64encode(f"{data_str}|{signature}".encode()).decode()

def verify_cookie(token: str, expected_parts: int):
    try:
        raw_decoded = base64.b64decode(token).decode()
        parts = raw_decoded.split("|")
        if len(parts) != expected_parts + 1: return None
        signature = parts[-1]
        data_str = "|".join(parts[:-1])
        if signature == hashlib.sha256(f"{data_str}|{SECRET_TOKEN}".encode()).hexdigest():
            return parts[:-1]
    except:
        pass
    return None

async def verify_admin(request: Request):
    token = request.cookies.get(ADMIN_COOKIE)
    if not token or not verify_cookie(token, 1):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return True

def get_current_customer(request: Request):
    token = request.cookies.get(CUSTOMER_COOKIE)
    if token:
        data = verify_cookie(token, 2)
        if data: return {"id": data[0], "email": data[1]}
    return None

def api_success(**payload): return {"status": "success", **payload}
def api_error(msg: str, code: int = 400): return JSONResponse(status_code=code, content={"status": "error", "message": msg})

# ==============================================================================
# 4. ROUTER: ZONA PUBLIK & PELANGGAN 🌐
# ==============================================================================
@app.get("/", response_class=HTMLResponse, tags=["Web Customer"])
async def read_root(request: Request, bg_tasks: BackgroundTasks):
    bg_tasks.add_task(send_owner_notif, "👀 <b>Radar Unik:</b> Seseorang mendarat di website lu bos!")
    produk_aktif = []
    if supabase:
        res = supabase.table("products").select("*").eq("is_active", True).order("id").execute()
        produk_aktif = res.data or []
    return templates.TemplateResponse(request=request, name="customer/index.html", context={"request": request, "produk": produk_aktif})

@app.get("/detail/{product_id}", response_class=HTMLResponse)
async def detail_product(request: Request, product_id: int):
    res = supabase.table("products").select("*").eq("id", product_id).single().execute()
    if not res.data: raise HTTPException(status_code=404, detail="Barang ga nemu bre")
    return templates.TemplateResponse(request=request, name="customer/detail.html", context={"request": request, "produk": res.data})

@app.get("/ai-assistant", response_class=HTMLResponse)
async def ai_assistant_page(request: Request):
    return templates.TemplateResponse(request=request, name="customer/cs_ai.html", context={"request": request})

# ==============================================================================
# 5. ROUTER: AUTHENTIKASI PELANGGAN 🔐
# ==============================================================================
@app.get("/auth", response_class=HTMLResponse)
async def customer_auth_page(request: Request):
    if get_current_customer(request):
        return RedirectResponse(url="/checkout", status_code=303)
    return templates.TemplateResponse(request=request, name="customer/auth.html", context={"request": request})

@app.post("/auth/register")
async def customer_register(full_name: str = Form(...), whatsapp: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if not supabase: raise HTTPException(status_code=503)
    try:
        # Hash password simpel (Buat prototype)
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        supabase.table("customers").insert({
            "full_name": full_name, "whatsapp_number": whatsapp, "email": email, "password_hash": pwd_hash, "shipping_address": "-"
        }).execute()
        return RedirectResponse(url="/auth", status_code=303) # Balik ke login
    except Exception as e:
        return HTMLResponse(f"Gagal daftar bre, email mungkin udah kepake: {e}")

@app.post("/auth/login")
async def customer_login(email: str = Form(...), password: str = Form(...)):
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    res = supabase.table("customers").select("id, email").eq("email", email).eq("password_hash", pwd_hash).execute()
    
    if res.data:
        cust = res.data[0]
        response = RedirectResponse(url="/checkout", status_code=303)
        cookie_val = create_secure_cookie(f"{cust['id']}|{cust['email']}")
        response.set_cookie(key=CUSTOMER_COOKIE, value=cookie_val, httponly=True, max_age=86400 * 30) # Tahan 30 hari
        return response
    return HTMLResponse("Email atau password salah bos!")

# ==============================================================================
# 6. ROUTER: CHECKOUT & API (WAJIB LOGIN) 🛒
# ==============================================================================
@app.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request):
    customer = get_current_customer(request)
    if not customer:
        return RedirectResponse(url="/auth", status_code=303) # Tendang ke halaman login kalo blm masuk
    return templates.TemplateResponse(request=request, name="customer/checkout.html", context={"request": request})

@app.post("/api/checkout")
async def api_process_checkout(request: Request, payload: CheckoutPayload, bg_tasks: BackgroundTasks):
    customer = get_current_customer(request)
    if not customer: return api_error("Wajib login dulu bre!", 401)
    if not supabase: return api_error("Database offline", 503)

    try:
        order_number = f"UNIK-{datetime.now().strftime('%y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
        cust_id = int(customer["id"])

        # Update alamat customer
        supabase.table("customers").update({"shipping_address": payload.customer.address}).eq("id", cust_id).execute()

        # Simpan Header Pesanan
        res_order = supabase.table("orders").insert({
            "order_number": order_number, "customer_id": cust_id, "total_amount": payload.total_amount,
            "payment_method": payload.customer.payment, "status": "Menunggu Pembayaran"
        }).execute()
        order_id = res_order.data[0]['id']

        # Proses Item & Potong Stok
        for item in payload.items:
            supabase.table("order_items").insert({
                "order_id": order_id, "product_id": item.id, "quantity": item.qty, "price_at_time": item.price
            }).execute()
            
            prod = supabase.table("products").select("stock_quantity").eq("id", item.id).single().execute()
            if prod.data:
                new_stock = max(0, int(prod.data.get("stock_quantity", 0)) - item.qty)
                supabase.table("products").update({"stock_quantity": new_stock}).eq("id", item.id).execute()

        # Notif Bos
        pesan_bos = (f"🚨 <b>ORDERAN MASUK DARI MEMBER!</b> 🚨\n\n👤 <b>Pembeli:</b> {payload.customer.name}\n"
                     f"💰 <b>Total:</b> Rp {payload.total_amount:,.0f}\n📦 <b>No. Order:</b> <code>{order_number}</code>")
        bg_tasks.add_task(send_owner_notif, pesan_bos)

        return api_success(order_number=order_number)
    except Exception as e:
        logger.error(f"❌ [CHECKOUT ERROR]: {e}")
        return api_error(str(e), 500)

@app.post("/api/chat")
async def api_chat_ai(payload: ChatPayload):
    if not payload.message.strip(): return api_error("Pesan kosong", 400)
    try:
        reply = await get_ai_recommendation(payload.message)
        return api_success(reply=reply)
    except: return api_error("Mimin pusing", 500)

# ==============================================================================
# 7. ROUTER: ZONA TERLARANG (ADMIN PANEL) 🔐
# ==============================================================================
@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if request.cookies.get(ADMIN_COOKIE): return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request=request, name="admin/login.html", context={"request": request})

@app.post("/admin/login")
async def do_admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(key=ADMIN_COOKIE, value=create_secure_cookie(username), httponly=True, max_age=43200)
        return response
    return templates.TemplateResponse(request=request, name="admin/login.html", context={"request": request, "error": "Salah bos!"})

@app.get("/admin/logout")
async def do_admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE)
    return response

@app.get("/admin", response_class=HTMLResponse, dependencies=[Depends(verify_admin)])
async def admin_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", context={"request": request})

@app.get("/admin/orders", response_class=HTMLResponse, dependencies=[Depends(verify_admin)])
async def admin_orders(request: Request):
    orders_data = []
    if supabase:
        res = supabase.table("orders").select("*, customers(full_name, whatsapp_number)").order("created_at", desc=True).execute()
        orders_data = res.data or []
    return templates.TemplateResponse(request=request, name="admin/orders.html", context={"request": request, "pesanan": orders_data})

@app.post("/admin/orders/update", dependencies=[Depends(verify_admin)])
async def update_order_status(order_id: int = Form(...), status_order: str = Form(...)):
    if not supabase: raise HTTPException(status_code=503)
    try:
        old_order = supabase.table("orders").select("status, total_amount, order_number").eq("id", order_id).single().execute()
        supabase.table("orders").update({"status": status_order}).eq("id", order_id).execute()
        
        if status_order.lower() == "selesai" and old_order.data.get("status").lower() != "selesai":
            supabase.table("finance_ledger").insert({
                "transaction_type": "IN", "amount": float(old_order.data.get("total_amount", 0)),
                "category": "Penjualan Barang Unik", "description": f"Pencairan order {old_order.data.get('order_number')}",
                "reference_order_id": order_id
            }).execute()
        return RedirectResponse(url="/admin/orders", status_code=303)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/inventory", response_class=HTMLResponse, dependencies=[Depends(verify_admin)])
async def admin_inventory(request: Request):
    produk_data = []
    if supabase:
        res = supabase.table("products").select("*").order("id").execute()
        produk_data = res.data or []
    return templates.TemplateResponse(request=request, name="admin/inventory.html", context={"request": request, "produk": produk_data})

@app.get("/admin/finance", response_class=HTMLResponse, dependencies=[Depends(verify_admin)])
async def admin_finance(request: Request):
    ledger_data = []
    if supabase:
        res = supabase.table("finance_ledger").select("*").order("created_at", desc=True).execute()
        ledger_data = res.data or []
    return templates.TemplateResponse(request=request, name="admin/finance.html", context={"request": request, "ledger": ledger_data})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
