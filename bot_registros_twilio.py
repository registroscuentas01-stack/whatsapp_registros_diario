from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import re
from datetime import datetime
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import requests

app = Flask(__name__)

# ==========================================
# ⚙️ CONFIGURACIÓN DE USUARIOS Y PESTAÑAS
# ==========================================

USUARIOS = {
    "+593991769796": ["INGRESOS_F", "GASTOS_F", "CREDITOS_F"],
    "+593989921225": ["INGRESOS_F", "CREDITOS_F", "INGRESOS_D", "CREDITOS_D"],
    "+447594501771": ["CODIGOS_RETIRO", "INGRESOS_D", "GASTOS_D", "CREDITOS_D"],
    "+593989777246": ["INGRESOS_F", "GASTOS_F", "CREDITOS_F"],
}

ARCHIVO_GS = "REGISTROS_DIARIOS"

# ==========================================
# 🔹 GOOGLE SHEETS
# ==========================================

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials_dict = {
    "type": os.getenv("GOOGLE_TYPE"),
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
}

credentials = service_account.Credentials.from_service_account_info(credentials_dict, scopes=scope)

client = gspread.authorize(credentials)
drive_service = build('drive', 'v3', credentials=credentials)

archivo = client.open(ARCHIVO_GS)

# Pre-cargar todas las pestañas
hojas = {}
for ws in archivo.worksheets():
    hojas[ws.title] = ws

# ==========================================
# 🔹 CATEGORIZACIÓN
# ==========================================

def extraer_monto_y_moneda(texto):
    t = texto.lower()
    patrones = [
        (re.compile(r'(?:€)\s*([0-9]+(?:[.,][0-9]{1,2})?)'), "€"),
        (re.compile(r'(?:\$)\s*([0-9]+(?:[.,][0-9]{1,2})?)'), "$"),
        (re.compile(r'([0-9]+(?:[.,][0-9]{1,2})?)\s*€'), "€"),
        (re.compile(r'([0-9]+(?:[.,][0-9]{1,2})?)\s*\$'), "$"),
    ]

    for rex, moneda in patrones:
        m = rex.search(t)
        if m:
            return m.group(1).replace(",", "."), moneda

    m = re.search(r'\b([0-9]+(?:[.,][0-9]{1,2})?)\b', t)
    if m:
        return m.group(1).replace(",", "."), "€"

    return None, None


def clasificar_categoria(texto):
    texto = texto.lower()
    if "super" in texto: return "Supermercado"
    if "gasolina" in texto or "combustible" in texto: return "Combustible"
    if "rest" in texto or "comida" in texto or "almuerzo" in texto: return "Alimentación"
    return "Gastos varios"

def limpiar_descripcion(texto):
    return texto.strip().capitalize()

# ==========================================
# 🔹 SUBIR FOTO A DRIVE (OPCIONAL)
# ==========================================

def subir_foto_drive(url):
    try:
        r = requests.get(url)
        if r.status_code != 200:
            return None

        os.makedirs("temp", exist_ok=True)
        fname = f"temp/{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        with open(fname, "wb") as f:
            f.write(r.content)

        meta = {"name": os.path.basename(fname)}
        media = MediaFileUpload(fname, mimetype="image/jpeg")
        file = drive_service.files().create(body=meta, media_body=media, fields="id").execute()

        drive_service.permissions().create(
            fileId=file["id"],
            body={"role": "reader", "type": "anyone"}
        ).execute()

        link = f"https://drive.google.com/file/d/{file['id']}/view?usp=sharing"
        os.remove(fname)
        return link
    except:
        return None

# ==========================================
# 🔹 WEBHOOK PRINCIPAL
# ==========================================

@app.route("/webhook", methods=["POST"])
def webhook():
    msg = request.form.get("Body", "").strip()
    sender = request.form.get("From", "").replace("whatsapp:", "")
    num_media = int(request.form.get("NumMedia", 0))

    resp = MessagingResponse()
    r = resp.message()

    # ------------------------------------------
    # Validar usuario
    # ------------------------------------------
    if sender not in USUARIOS:
        r.body("❌ Usuario no autorizado.")
        return str(resp)

    # Extraer datos
    monto, moneda = extraer_monto_y_moneda(msg)
    categoria = clasificar_categoria(msg)
    descripcion = limpiar_descripcion(msg)
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    link = ""
    if num_media > 0:
        link = subir_foto_drive(request.form.get("MediaUrl0"))

    # Registrar en TODAS las pestañas asignadas a ese número
    for tab in USUARIOS[sender]:
        if tab in hojas:
            hojas[tab].append_row([fecha, sender, categoria, descripcion, monto, moneda, link])

    r.body(f"✅ Registrado en pestañas: {', '.join(USUARIOS[sender])}\n💰 {monto}{moneda}\n🏷️ {categoria}\n💬 {descripcion}")
    return str(resp)

# ==========================================
# 🔹 INICIO
# ==========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
