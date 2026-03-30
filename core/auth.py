import os
import hashlib
import base64
import logging
from fastapi import Request, HTTPException, status
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("barangunik.auth")

SECRET_TOKEN = os.getenv("SECRET_TOKEN", "rahasia-banget-bre-2026")
COOKIE_NAME = "unik_admin_session"

def create_secure_cookie(username: str) -> str:
    """Bikin tiket cookie anti-maling menggunakan SHA-256"""
    raw_data = f"{username}|{SECRET_TOKEN}"
    signature = hashlib.sha256(raw_data.encode()).hexdigest()
    # Ubah ke Base64 biar aman disimpen di browser
    return base64.b64encode(f"{username}|{signature}".encode()).decode()

async def verify_admin(request: Request):
    """Fungsi penjaga pintu: Cek apakah yang akses beneran Admin"""
    token = request.cookies.get(COOKIE_NAME)
    
    if not token:
        # Kalau gak bawa tiket (cookie), lempar ke halaman login
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    
    try:
        # Bongkar tiketnya
        raw_decoded = base64.b64decode(token).decode()
        username, signature = raw_decoded.split("|")
        
        # Bikin signature pembanding untuk validasi
        expected_sig = hashlib.sha256(f"{username}|{SECRET_TOKEN}".encode()).hexdigest()
        
        if signature != expected_sig:
            raise ValueError("Waduh, Cookie dipalsukan!")
            
        # Kalau aman, simpan nama admin di state biar bisa dipanggil di HTML
        request.state.admin_user = username
        return True
        
    except Exception as e:
        logger.warning(f"🔒 [HACK ATTEMPT] Gagal masuk: {e}")
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
