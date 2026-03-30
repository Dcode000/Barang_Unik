import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
Kamu adalah Mimin Unik, asisten cerdas dari barangunik.com.
Tugasmu adalah merekomendasikan barang-barang unik, aneh, tapi berguna kepada pelanggan.
Gaya bicaramu asik, santai, dan persuasif (pake bahasa gaul dikit kayak 'bre', 'parah sih', 'wajib punya').
Jika ditanya produk, hubungkan dengan database stok yang ada.
"""

async def get_ai_recommendation(user_input: str):
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            config={"system_instruction": SYSTEM_PROMPT},
            contents=[user_input]
        )
        return response.text
    except Exception as e:
        return f"Waduh bre, otak gua lagi ngebul: {str(e)}"