from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os
import gspread
from google.oauth2 import service_account

app = Flask(__name__)

# ==========================================
# 🔹 ADMINS AUTORIZADOS
# ==========================================
ADMINS = [
    "+593991769796",
    "+593989921225",
    "+447594501771",
    "+593989777246",
    "+593990516017",   # Nuevo número agregado
]

# ==========================================
# 🔹 ID de la hoja
# ==========================================
ARCHIVO_GS_ID = "1v-CK37p7ngUVNk3iX6XiCM8EfwXMrXZJ_2RLHqt2n_A"

# ==========================================
# 🔹 Google Sheets
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

credentials = service_account.Credentials.from_service_account_info(
    credentials_dict, scopes=scope
)

client = gspread.authorize(credentials)
archivo = client.open_by_key(ARCHIVO_GS_ID)

hojas = {}
for ws in archivo.worksheets():
    hojas[ws.title] = ws


# ==========================================
# 🔹 FORMATOS
# ==========================================

FORMATO_V = (
    "CLIENTE:\n"
    "BANCO:\n"
    "NOMBRE:\n"
    "VALOR:\n"
    "USUARIO:\n"
    "ID:\n"
)

FORMATO_G = (
    "CATEGORIA:\n"
    "DESCRIPCION:\n"
    "VALOR:\n"
    "MONEDA:\n"
    "ID:\n"
)

FORMATO_C = (
    "CREDITOS:\n"
    "ID:\n"
)

FORMATO_BANCOS = {
    "PICHINCHA": (
        "BANCO: Pichincha\n"
        "TELEFONO:\n"
        "CODIGO:\n"
        "CEDULA:\n"
        "MONTO:\n"
        "USUARIO:\n"
        "RETIRAR HASTA:\n"
        "ID:\n"
    ),
    "GUAYAQUIL": (
        "BANCO: Guayaquil\n"
        "TELEFONO:\n"
        "CLAVE RETIRO:\n"
        "CLAVE ENVIO:\n"
        "MONTO:\n"
        "USUARIO:\n"
        "RETIRAR HASTA:\n"
        "ID:\n"
    ),
    "PACIFICO": (
        "BANCO: Pacifico\n"
        "TELEFONO:\n"
        "CODIGO:\n"
        "CEDULA:\n"
        "MONTO:\n"
        "USUARIO:\n"
        "RETIRAR HASTA:\n"
        "ID:\n"
    ),
    "PRODUBANCO": (
        "BANCO: Produbanco\n"
        "TELEFONO:\n"
        "CODIGO:\n"
        "CEDULA:\n"
        "MONTO:\n"
        "USUARIO:\n"
        "RETIRAR HASTA:\n"
        "ID:\n"
    ),
}

# ==========================================
# 🔹 CAMPOS OBLIGATORIOS
# ==========================================

OBLIGATORIOS = {
    "V": ["CLIENTE", "BANCO", "NOMBRE", "VALOR", "USUARIO", "ID"],
    "G": ["CATEGORIA", "DESCRIPCION", "VALOR", "MONEDA", "ID"],
    "C": ["CREDITOS", "ID"],
    "CO_PICHINCHA": ["TELEFONO", "CODIGO", "CEDULA", "MONTO", "USUARIO", "RETIRAR HASTA", "ID"],
    "CO_PRODUBANCO": ["TELEFONO", "CODIGO", "CEDULA", "MONTO", "USUARIO", "RETIRAR HASTA", "ID"],
    "CO_PACIFICO": ["TELEFONO", "CODIGO", "CEDULA", "MONTO", "USUARIO", "RETIRAR HASTA", "ID"],
    "CO_GUAYAQUIL": ["TELEFONO", "CLAVE RETIRO", "CLAVE ENVIO", "MONTO", "USUARIO", "RETIRAR HASTA", "ID"],
}

# Estados
ESTADO = {}
ESPERANDO_BANCO = {}


# ==========================================
# 🔹 PARSEADOR
# ==========================================
def parse_formato(texto):
    data = {}
    for linea in texto.split("\n"):
        if ":" in linea:
            campo, valor = linea.split(":", 1)
            data[campo.strip().upper()] = valor.strip()
    return data


# ==========================================
# 🔹 DETECTAR HOJA SEGÚN ID
# ==========================================
def obtener_hoja(tipo, id_letra):

    id_letra = id_letra.upper()

    MAP = {
        ("V", "F"): "INGRESOS_F",
        ("V", "D"): "INGRESOS_D",
        ("G", "F"): "GASTOS_F",
        ("G", "D"): "GASTOS_D",
        ("C", "F"): "CREDITOS_F",
        ("C", "D"): "CREDITOS_D",
        ("CO", "F"): "CODIGOS_F",
        ("CO", "D"): "CODIGOS_D",
    }

    return MAP.get((tipo, id_letra), None)


# ==========================================
# 🔹 WEBHOOK
# ==========================================
@app.route("/webhook", methods=["POST"])
def webhook():

    msg = request.form.get("Body", "").strip()
    sender = request.form.get("From", "").replace("whatsapp:", "")
    msg_upper = msg.upper()

    resp = MessagingResponse()
    r = resp.message()

    # Validación de admin
    if sender not in ADMINS:
        r.body("❌ No autorizado.")
        return str(resp)

    # ==========================================
    # 1️⃣ Solicitud de formato
    # ==========================================
    if msg_upper in ["V", "G", "C", "CO"]:
        ESTADO[sender] = msg_upper

        if msg_upper == "V":
            r.body(FORMATO_V)
        elif msg_upper == "G":
            r.body(FORMATO_G)
        elif msg_upper == "C":
            r.body(FORMATO_C)
        elif msg_upper == "CO":
            ESPERANDO_BANCO[sender] = True
            r.body("¿De qué banco necesitas el formato? (Pichincha / Guayaquil / Pacifico / Produbanco)")
        return str(resp)

    # ==========================================
    # 2️⃣ Usuario selecciona banco
    # ==========================================
    if sender in ESPERANDO_BANCO:
        banco = msg_upper
        if banco in FORMATO_BANCOS:
            ESTADO[sender] = "CO_" + banco    # ejemplo: CO_PICHINCHA
            ESPERANDO_BANCO.pop(sender)
            r.body(FORMATO_BANCOS[banco])
            return str(resp)
        else:
            r.body("❌ Banco no válido. Usa: Pichincha, Guayaquil, Pacifico, Produbanco.")
            return str(resp)

    # ==========================================
    # 3️⃣ Procesar formulario lleno
    # ==========================================
    if sender in ESTADO:
        tipo_formulario = ESTADO[sender]  # V / G / C / CO_PICHINCHA / ...
        data = parse_formato(msg)

        # Validar ID
        if "ID" not in data or data["ID"] == "":
            r.body("❌ Falta el campo obligatorio ID.")
            return str(resp)

        # Validar campos obligatorios
        obligatorios = OBLIGATORIOS.get(tipo_formulario, [])
        faltantes = [campo for campo in obligatorios if campo not in data or data[campo] == ""]

        if faltantes:
            lista = "\n".join(f"• {c}" for c in faltantes)
            r.body(f"❌ Faltan campos obligatorios:\n{lista}")
            return str(resp)

        # Determinar hoja
        tipo_base = tipo_formulario.split("_")[0]  # CO_PICHINCHA → CO
        hoja_nombre = obtener_hoja(tipo_base, data["ID"])

        if hoja_nombre not in hojas:
            r.body(f"❌ Hoja destino no encontrada: {hoja_nombre}")
            return str(resp)

        ws = hojas[hoja_nombre]

        # Registrar fila
        fila = [f"{k}: {v}" for k, v in data.items()]
        ws.append_row(fila)

        ESTADO.pop(sender, None)

        r.body(f"✅ Registro exitoso en *{hoja_nombre}*")
        return str(resp)

    # ==========================================
    # 4️⃣ No entendido
    # ==========================================
    r.body("❌ No entendí tu mensaje.\nEscribe: V, G, C o CO.")
    return str(resp)


# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
