"""
Agente de Viagens Pessoal — Rodrigo Arruy
Telegram Bot + Claude API + Ferramentas de busca
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import httpx
import anthropic
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONFIGURAÇÃO (preencha com seus dados)
# ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "SUA_CHAVE_AQUI")
AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "")
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# IDs do Telegram autorizados (só você e quem quiser autorizar)
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "0").split(",")]

PROFILE_PATH = "data/profile.json"
HISTORY_PATH = "data/history.json"

# ─────────────────────────────────────────────
# PERFIL DO VIAJANTE
# ─────────────────────────────────────────────
DEFAULT_PROFILE = {
    "nome": "Rodrigo",
    "cidade_base": "São Paulo (GRU/CGH)",
    "passaporte": {
        "numero": "",
        "validade": "2028-01-01",
        "nacionalidade": "Brasileira"
    },
    "preferencias": {
        "assento": "janela",
        "companhias_preferidas": ["LATAM", "Azul", "GOL"],
        "classe_padrao": "economica",
        "classe_milhas": "executiva",
        "refeicao": "padrao",
        "bagagem": True
    },
    "fidelidades": {
        "smiles": {
            "numero": "",
            "categoria": "Ouro",
            "saldo_estimado": 0,
            "vencimento_proximo": None
        },
        "latam_pass": {
            "numero": "",
            "categoria": "Black",
            "saldo_estimado": 0,
            "vencimento_proximo": None
        },
        "livelo": {
            "numero": "",
            "saldo_estimado": 0,
            "vencimento_proximo": None
        },
        "tudoazul": {
            "numero": "",
            "categoria": "Topázio",
            "saldo_estimado": 0,
            "vencimento_proximo": None
        }
    },
    "cartoes": [
        {"nome": "Itaú Personnalité", "bandeira": "Visa Infinite", "programa": "Livelo", "pontos_por_real": 2.5},
        {"nome": "C6 Carbon", "bandeira": "Mastercard Black", "programa": "Livelo", "pontos_por_real": 2.5}
    ],
    "destinos_frequentes": ["Rio de Janeiro", "Brasília", "Miami", "Lisboa"],
    "notas": "Viaja a trabalho mensalmente para Rio e Brasília. Prefere voos diretos quando possível."
}


def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH) as f:
            return json.load(f)
    save_profile(DEFAULT_PROFILE)
    return DEFAULT_PROFILE


def save_profile(profile: dict):
    os.makedirs("data", exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def load_history() -> list:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH) as f:
            data = json.load(f)
            # mantém só as últimas 20 mensagens por sessão
            return data[-20:] if len(data) > 20 else data
    return []


def save_history(history: list):
    os.makedirs("data", exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history[-50:], f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# FERRAMENTAS DO AGENTE
# ─────────────────────────────────────────────
# ── WALLET ─────────────────────────────────────────────────────
WALLET_PATH = "data/wallet.json"

def load_wallet():
    if os.path.exists(WALLET_PATH):
        with open(WALLET_PATH) as f:
            return json.load(f)
    return {"voos": [], "hoteis": [], "alertas_gmail": []}

def save_wallet(wallet):
    os.makedirs("data", exist_ok=True)
    with open(WALLET_PATH, "w") as f:
        json.dump(wallet, f, ensure_ascii=False, indent=2)

def wallet_add_voo(dados):
    wallet = load_wallet()
    voo_id = f"VOO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    dados["id"] = voo_id
    dados["criado_em"] = datetime.now().isoformat()
    dados["checkin_feito"] = False
    wallet["voos"].append(dados)
    save_wallet(wallet)
    return voo_id

def wallet_add_hotel(dados):
    wallet = load_wallet()
    hotel_id = f"HTL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    dados["id"] = hotel_id
    dados["criado_em"] = datetime.now().isoformat()
    wallet["hoteis"].append(dados)
    save_wallet(wallet)
    return hotel_id

def wallet_get_proximos(dias=90):
    wallet = load_wallet()
    hoje = datetime.now().date()
    limite = hoje + timedelta(days=dias)
    voos = []
    for v in wallet["voos"]:
        try:
            d = datetime.strptime(v.get("data",""), "%Y-%m-%d").date()
            if hoje <= d <= limite:
                v["dias_restantes"] = (d - hoje).days
                voos.append(v)
        except:
            pass
    hoteis = []
    for h in wallet["hoteis"]:
        try:
            d = datetime.strptime(h.get("checkin",""), "%Y-%m-%d").date()
            if hoje <= d <= limite:
                h["dias_restantes"] = (d - hoje).days
                hoteis.append(h)
        except:
            pass
    voos.sort(key=lambda x: x.get("data",""))
    hoteis.sort(key=lambda x: x.get("checkin",""))
    return {"voos": voos, "hoteis": hoteis}

def gerar_link_checkin(companhia, localizador, data):
    c = companhia.upper()
    if not localizador:
        return ""
    if "LATAM" in c or "LA" in c:
        return f"https://www.latamairlines.com/br/pt/check-in?record={localizador}"
    elif "GOL" in c or "G3" in c:
        return f"https://checkin.voegol.com.br/?locator={localizador}"
    elif "AZUL" in c or "AD" in c:
        return f"https://checkin.voeazul.com.br/?locator={localizador}"
    elif "TAP" in c:
        return f"https://checkin.flytap.com/?locator={localizador}"
    elif "AMERICAN" in c or "AA" in c:
        return f"https://www.aa.com/checkin/main?recordLocator={localizador}"
    return ""

# ── GMAIL ──────────────────────────────────────────────────────
def get_gmail_service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"]
    )
    return build("gmail", "v1", credentials=creds)

def extract_email_body(msg):
    import base64
    body = ""
    payload = msg.get("payload", {})
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body[:3000]

async def scan_gmail_for_travel(max_results=20):
    if not GMAIL_REFRESH_TOKEN:
        return [{"erro": "Gmail nao configurado."}]
    try:
        import warnings
        warnings.filterwarnings("ignore")
        service = get_gmail_service()
        logger.info("Gmail service criado com sucesso")
        query = ("from:(latamairlines.com OR voegol.com OR voeazul.com OR tap.pt OR "
                 "american.com OR booking.com OR hotels.com OR expedia.com OR "
                 "smiles.com.br OR tudoazul.com OR livelo.com.br OR airbnb.com) "
                 "newer_than:90d")
        results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        messages = results.get("messages", [])
        logger.info(f"Gmail: {len(messages)} emails encontrados")
        emails = []
        for msg_ref in messages[:10]:
            msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg_ref["id"],
                "assunto": headers.get("Subject", ""),
                "de": headers.get("From", ""),
                "data": headers.get("Date", ""),
                "preview": extract_email_body(msg)[:500]
            })
        return emails
    except Exception as e:
        logger.error(f"Erro Gmail scan DETALHADO: {type(e).__name__}: {e}")
        return [{"erro": f"{type(e).__name__}: {str(e)}"}]

async def check_gmail_for_changes(app):
    if not AUTHORIZED_USERS or AUTHORIZED_USERS == [0] or not GMAIL_REFRESH_TOKEN:
        return
    user_id = AUTHORIZED_USERS[0]
    try:
        service = get_gmail_service()
        query = ("from:(latamairlines.com OR voegol.com OR voeazul.com OR tap.pt) "
                 "subject:(mudanca OR alteracao OR cancelado OR atraso OR change OR cancelled OR delayed) "
                 "newer_than:1d")
        results = service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        messages = results.get("messages", [])
        wallet = load_wallet()
        alertas = wallet.get("alertas_gmail", [])
        for msg_ref in messages[:3]:
            if msg_ref["id"] not in alertas:
                msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "")
                sender = headers.get("From", "")
                date = headers.get("Date", "")
                body = extract_email_body(msg)
                text = f"*Possivel mudanca de voo!*\n\nDe: {sender}\nAssunto: {subject}\nData: {date}\n\n{body[:300]}"
                await app.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
                alertas.append(msg_ref["id"])
        wallet["alertas_gmail"] = alertas[-50:]
        save_wallet(wallet)
    except Exception as e:
        logger.error(f"Erro Gmail monitor: {e}")

# ── ALERTS ─────────────────────────────────────────────────────
async def check_and_send_alerts(app):
    if not AUTHORIZED_USERS or AUTHORIZED_USERS == [0]:
        return
    wallet = load_wallet()
    agora = datetime.now()
    hoje = agora.date()
    user_id = AUTHORIZED_USERS[0]
    for voo in wallet["voos"]:
        try:
            data_str = voo.get("data", "")
            hora_str = voo.get("hora_partida", "00:00")
            data_voo = datetime.strptime(f"{data_str} {hora_str}", "%Y-%m-%d %H:%M")
            horas = (data_voo - agora).total_seconds() / 3600
            companhia = voo.get("companhia", "")
            localizador = voo.get("localizador", "")
            origem = voo.get("origem", "")
            destino = voo.get("destino", "")
            if 47 <= horas <= 49 and not voo.get("alerta_checkin_enviado"):
                link = gerar_link_checkin(companhia, localizador, data_str)
                if link:
                    text = f"Checkin aberto!\n{companhia} {origem} -> {destino}\nLocalizador: {localizador}\n{link}"
                    await app.bot.send_message(chat_id=user_id, text=text)
                    voo["alerta_checkin_enviado"] = True
                    save_wallet(wallet)
            elif 23 <= horas <= 25 and not voo.get("alerta_24h_enviado"):
                text = f"Voo amanha!\n{companhia} {origem} -> {destino}\n{data_voo.strftime('%d/%m/%Y %H:%M')}\nLocalizador: {localizador}"
                await app.bot.send_message(chat_id=user_id, text=text)
                voo["alerta_24h_enviado"] = True
                save_wallet(wallet)
        except Exception as e:
            logger.error(f"Erro alerta voo: {e}")
    for hotel in wallet["hoteis"]:
        try:
            checkin = datetime.strptime(hotel.get("checkin",""), "%Y-%m-%d").date()
            if (checkin - hoje).days == 1 and not hotel.get("alerta_checkin_enviado"):
                text = f"Checkin amanha!\n{hotel.get('nome','Hotel')}\n{hotel.get('endereco','')}\nConfirmacao: {hotel.get('confirmacao','')}"
                await app.bot.send_message(chat_id=user_id, text=text)
                hotel["alerta_checkin_enviado"] = True
                save_wallet(wallet)
        except Exception as e:
            logger.error(f"Erro alerta hotel: {e}")

async def scheduler_loop(app):
    while True:
        try:
            await check_and_send_alerts(app)
            await check_gmail_for_changes(app)
        except Exception as e:
            logger.error(f"Erro scheduler: {e}")
        await asyncio.sleep(900)

# ── SCRAPING ───────────────────────────────────────────────────
async def scrape_smiles(cpf_ou_email, senha):
    try:
        headers = {"User-Agent": "okhttp/4.9.0", "Content-Type": "application/json", "channel": "mobileAndroid"}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.post("https://api-auth.smiles.com.br/v1/auth/oauth/token",
                json={"username": cpf_ou_email, "password": senha, "grant_type": "password", "client_id": "smiles-mobile"},
                headers=headers)
            if resp.status_code != 200:
                return {"erro": f"Login Smiles falhou ({resp.status_code})"}
            token = resp.json().get("access_token", "")
            if not token:
                return {"erro": "Token Smiles nao obtido"}
            headers["Authorization"] = f"Bearer {token}"
            saldo_resp = await client.get("https://api.smiles.com.br/v1/member/balance", headers=headers)
            if saldo_resp.status_code == 200:
                d = saldo_resp.json()
                return {"programa": "Smiles", "saldo": d.get("miles", d.get("balance", 0)),
                        "categoria": d.get("tier", ""), "atualizado_em": datetime.now().isoformat()}
            return {"erro": f"Saldo Smiles erro ({saldo_resp.status_code})"}
    except Exception as e:
        return {"erro": str(e)}

async def scrape_latam(email, senha):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.post("https://auth.latamairlines.com/oauth/token",
                json={"username": email, "password": senha, "grant_type": "password", "client_id": "latam-app"})
            if resp.status_code != 200:
                return {"erro": f"Login LATAM falhou ({resp.status_code})"}
            token = resp.json().get("access_token", "")
            if not token:
                return {"erro": "Token LATAM nao obtido"}
            perfil = await client.get("https://api.latamairlines.com/v1/loyalty/member/profile",
                headers={"Authorization": f"Bearer {token}"})
            if perfil.status_code == 200:
                d = perfil.json()
                return {"programa": "LATAM Pass", "saldo": d.get("miles", 0),
                        "categoria": d.get("tier", ""), "atualizado_em": datetime.now().isoformat()}
            return {"erro": f"Saldo LATAM erro ({perfil.status_code})"}
    except Exception as e:
        return {"erro": str(e)}

# ── NEW TOOL EXECUTORS ─────────────────────────────────────────
async def tool_salvar_viagem(params, profile):
    tipo = params.get("tipo", "")
    dados = params.get("dados", {})
    if tipo == "voo":
        voo_id = wallet_add_voo(dados)
        link = gerar_link_checkin(dados.get("companhia",""), dados.get("localizador",""), dados.get("data",""))
        return json.dumps({"sucesso": True, "id": voo_id, "mensagem": f"Voo salvo! ID: {voo_id}",
            "alertas": ["48h antes: lembrete checkin", "24h antes: lembrete viagem"],
            "link_checkin": link or "Disponivel 48h antes"}, ensure_ascii=False)
    elif tipo == "hotel":
        hotel_id = wallet_add_hotel(dados)
        return json.dumps({"sucesso": True, "id": hotel_id, "mensagem": f"Hotel salvo! ID: {hotel_id}",
            "alertas": ["24h antes do checkin: lembrete automatico"]}, ensure_ascii=False)
    return json.dumps({"erro": "Tipo invalido. Use voo ou hotel."})

async def tool_ver_carteira(params, profile):
    dias = params.get("dias", 90)
    proximos = wallet_get_proximos(dias)
    wallet = load_wallet()
    voos = proximos["voos"]
    hoteis = proximos["hoteis"]
    if not voos and not hoteis:
        return json.dumps({"mensagem": f"Nenhuma viagem nos proximos {dias} dias.",
            "total": f"{len(wallet.get('voos',[]))} voos e {len(wallet.get('hoteis',[]))} hoteis no total."}, ensure_ascii=False)
    resultado = {"proximos_voos": [], "proximas_reservas_hotel": []}
    for v in voos:
        link = gerar_link_checkin(v.get("companhia",""), v.get("localizador",""), v.get("data",""))
        resultado["proximos_voos"].append({
            "id": v.get("id"), "companhia": v.get("companhia"), "rota": f"{v.get('origem','')} -> {v.get('destino','')}",
            "data": v.get("data"), "hora": v.get("hora_partida"), "localizador": v.get("localizador"),
            "assento": v.get("assento","A confirmar"), "dias_restantes": v.get("dias_restantes",0),
            "link_checkin": link or "Disponivel 48h antes"})
    for h in hoteis:
        resultado["proximas_reservas_hotel"].append({
            "id": h.get("id"), "hotel": h.get("nome"), "checkin": h.get("checkin"),
            "checkout": h.get("checkout"), "confirmacao": h.get("confirmacao"),
            "dias_restantes": h.get("dias_restantes",0)})
    return json.dumps(resultado, ensure_ascii=False, indent=2)

async def tool_atualizar_milhas_auto(params, profile):
    programa = params.get("programa", "ambos")
    resultados = {}
    if programa in ["smiles", "ambos"]:
        cpf = params.get("cpf_email_smiles","")
        senha = params.get("senha_smiles","")
        if not cpf or not senha:
            resultados["smiles"] = {"erro": "Preciso do CPF/email e senha do Smiles."}
        else:
            r = await scrape_smiles(cpf, senha)
            if "saldo" in r:
                profile["fidelidades"]["smiles"]["saldo_estimado"] = r["saldo"]
                if r.get("categoria"): profile["fidelidades"]["smiles"]["categoria"] = r["categoria"]
                save_profile(profile)
            resultados["smiles"] = r
    if programa in ["latam_pass", "ambos"]:
        email = params.get("email_latam","")
        senha = params.get("senha_latam","")
        if not email or not senha:
            resultados["latam_pass"] = {"erro": "Preciso do email e senha do LATAM Pass."}
        else:
            r = await scrape_latam(email, senha)
            if "saldo" in r:
                profile["fidelidades"]["latam_pass"]["saldo_estimado"] = r["saldo"]
                if r.get("categoria"): profile["fidelidades"]["latam_pass"]["categoria"] = r["categoria"]
                save_profile(profile)
            resultados["latam_pass"] = r
    resultados["nota"] = "Senhas usadas apenas nesta sessao e nao armazenadas."
    return json.dumps(resultados, ensure_ascii=False, indent=2)

async def tool_verificar_gmail(params, profile):
    acao = params.get("acao", "buscar_emails_viagem")
    max_emails = params.get("max_emails", 10)
    if not GMAIL_REFRESH_TOKEN:
        return json.dumps({"erro": "GMAIL_REFRESH_TOKEN nao encontrado nas variaveis de ambiente."})
    emails = await scan_gmail_for_travel(max_emails)
    # Check if returned an error
    if emails and isinstance(emails[0], dict) and "erro" in emails[0]:
        return json.dumps({"erro_gmail": emails[0]["erro"],
            "debug": f"GMAIL_REFRESH_TOKEN presente: {bool(GMAIL_REFRESH_TOKEN)}, CLIENT_ID presente: {bool(GMAIL_CLIENT_ID)}"
        })
    if not emails:
        return json.dumps({"resultado": "Nenhum email de viagem encontrado nos ultimos 90 dias.",
            "debug": "Busca executada com sucesso mas sem resultados."})
    if acao == "buscar_emails_viagem":
        return json.dumps({"total": len(emails), "emails": emails,
            "instrucao": "Apresente os emails encontrados. Pergunte se quer importar para a carteira."
        }, ensure_ascii=False, indent=2)
    elif acao == "importar_para_carteira":
        client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        emails_text = json.dumps(emails[:5], ensure_ascii=False)
        extraction = client_ai.messages.create(model="claude-opus-4-5", max_tokens=2000,
            messages=[{"role": "user", "content": f"Analise estes emails e extraia viagens. Retorne apenas JSON array com campos: tipo (voo/hotel), e para voo: companhia,localizador,origem,destino,data(YYYY-MM-DD),hora_partida. Para hotel: nome,checkin,checkout,confirmacao,endereco. Emails: {emails_text[:3000]}"}])
        try:
            extracted = json.loads(extraction.content[0].text)
            importados = []
            for item in extracted:
                if item.get("tipo") == "voo":
                    vid = wallet_add_voo(item)
                    importados.append(f"Voo {item.get('companhia')} {item.get('origem')}->{item.get('destino')} ({vid})")
                elif item.get("tipo") == "hotel":
                    hid = wallet_add_hotel(item)
                    importados.append(f"Hotel {item.get('nome')} checkin {item.get('checkin')} ({hid})")
            return json.dumps({"importados": importados, "total": len(importados),
                "mensagem": f"{len(importados)} viagens importadas com alertas ativados!"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"erro": f"Erro ao processar: {str(e)}"})
    return json.dumps({"erro": "Acao invalida."})


TOOLS = [
    {
        "name": "buscar_voos",
        "description": (
            "Busca e compara voos entre duas cidades. Retorna opções com preço, "
            "duração, escalas e disponibilidade em milhas. Use sempre que o usuário "
            "perguntar sobre passagens aéreas, cotação de voos ou comparação de preços."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origem": {"type": "string", "description": "Código IATA ou nome da cidade de origem. Ex: GRU, São Paulo"},
                "destino": {"type": "string", "description": "Código IATA ou nome da cidade de destino. Ex: LIS, Lisboa"},
                "data_ida": {"type": "string", "description": "Data de ida no formato YYYY-MM-DD"},
                "data_volta": {"type": "string", "description": "Data de volta no formato YYYY-MM-DD (opcional para só ida)"},
                "adultos": {"type": "integer", "description": "Número de passageiros adultos", "default": 1},
                "classe": {"type": "string", "enum": ["economica", "premium_economy", "executiva", "primeira"], "description": "Classe de viagem"},
                "apenas_diretos": {"type": "boolean", "description": "Se true, filtra apenas voos sem escala", "default": False}
            },
            "required": ["origem", "destino", "data_ida"]
        }
    },
    {
        "name": "buscar_voos_em_milhas",
        "description": (
            "Busca disponibilidade e custo de voos usando milhas/pontos nos programas "
            "Smiles, LATAM Pass, TudoAzul e Livelo. Ideal para planejar viagens em classe executiva. "
            "Use quando o usuário perguntar sobre usar milhas, pontos ou 'vale a pena usar milhas'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origem": {"type": "string", "description": "Cidade ou código IATA de origem"},
                "destino": {"type": "string", "description": "Cidade ou código IATA de destino"},
                "data_ida": {"type": "string", "description": "Data no formato YYYY-MM-DD"},
                "data_volta": {"type": "string", "description": "Data de volta (opcional)"},
                "classe": {"type": "string", "enum": ["economica", "executiva", "primeira"], "default": "executiva"},
                "programas": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["smiles", "latam_pass", "tudoazul", "livelo"]},
                    "description": "Programas para verificar. Se vazio, verifica todos."
                }
            },
            "required": ["origem", "destino", "data_ida"]
        }
    },
    {
        "name": "buscar_hoteis",
        "description": (
            "Busca e compara hotéis em uma cidade. Retorna opções com preço, "
            "localização, avaliação e benefícios. Use quando o usuário perguntar sobre "
            "hospedagem, hotel, pousada ou 'onde ficar'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destino": {"type": "string", "description": "Cidade de destino"},
                "checkin": {"type": "string", "description": "Data de check-in YYYY-MM-DD"},
                "checkout": {"type": "string", "description": "Data de check-out YYYY-MM-DD"},
                "adultos": {"type": "integer", "default": 1},
                "quartos": {"type": "integer", "default": 1},
                "categoria": {"type": "string", "enum": ["qualquer", "3_estrelas", "4_estrelas", "5_estrelas", "boutique"], "default": "4_estrelas"},
                "cafe_da_manha": {"type": "boolean", "description": "Filtrar apenas com café da manhã", "default": False},
                "cancelamento_gratis": {"type": "boolean", "description": "Filtrar apenas com cancelamento gratuito", "default": True}
            },
            "required": ["destino", "checkin", "checkout"]
        }
    },
    {
        "name": "conferir_milhas",
        "description": (
            "Consulta saldo de milhas, pontos acumulados, vencimentos próximos e "
            "oportunidades de transferência entre programas. Use quando o usuário perguntar "
            "sobre saldo, quantas milhas tem, vencimento de pontos ou status nos programas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "programa": {
                    "type": "string",
                    "enum": ["smiles", "latam_pass", "livelo", "tudoazul", "todos"],
                    "description": "Programa específico ou 'todos' para resumo geral"
                },
                "incluir_transferencias": {
                    "type": "boolean",
                    "description": "Se true, mostra opções de transferência entre programas",
                    "default": True
                }
            },
            "required": ["programa"]
        }
    },
    {
        "name": "calcular_valor_milhas",
        "description": (
            "Calcula se vale mais a pena pagar em dinheiro ou usar milhas para uma viagem. "
            "Compara CPM (custo por milha) e retorna recomendação. Use quando o usuário perguntar "
            "'vale a pena usar milhas?' ou quiser comparar opções."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "preco_passagem_dinheiro": {"type": "number", "description": "Preço da passagem em reais (R$)"},
                "milhas_necessarias": {"type": "number", "description": "Quantidade de milhas exigidas para o resgate"},
                "taxas_milhas": {"type": "number", "description": "Taxas a pagar mesmo usando milhas (R$)", "default": 0},
                "programa": {"type": "string", "description": "Programa de fidelidade da cotação em milhas"}
            },
            "required": ["preco_passagem_dinheiro", "milhas_necessarias"]
        }
    },
    {
        "name": "montar_itinerario",
        "description": (
            "Cria um itinerário completo de viagem com voo, hotel, transfers e dicas. "
            "Use quando o usuário quiser planejar uma viagem completa ou pedir um roteiro."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destino": {"type": "string"},
                "data_ida": {"type": "string"},
                "data_volta": {"type": "string"},
                "objetivo": {"type": "string", "description": "Lazer, negócios, lua de mel, etc."},
                "orcamento_total": {"type": "number", "description": "Orçamento total em reais (opcional)"},
                "usar_milhas": {"type": "boolean", "default": True}
            },
            "required": ["destino", "data_ida", "data_volta"]
        }
    },
    {
        "name": "atualizar_perfil",
        "description": (
            "Atualiza informações do perfil do viajante: saldo de milhas, preferências, "
            "dados do passaporte, números dos programas de fidelidade. Use quando o usuário "
            "informar dados pessoais, saldo ou quiser atualizar preferências."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campo": {"type": "string", "description": "Campo a atualizar. Ex: 'smiles.saldo_estimado', 'preferencias.assento'"},
                "valor": {"description": "Novo valor para o campo"}
            },
            "required": ["campo", "valor"]
        }
    },
    {
        "name": "verificar_gmail",
        "description": "Acessa o Gmail para buscar emails de viagem: passagens, hoteis, milhas e mudancas de voo. Use quando pedirem para verificar email ou importar viagens.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["buscar_emails_viagem", "importar_para_carteira"]},
                "max_emails": {"type": "integer", "default": 10}
            },
            "required": ["acao"]
        }
    },
    {
        "name": "salvar_viagem",
        "description": "Salva passagem ou reserva de hotel na carteira. Use quando usuario informar compra de passagem ou confirmacao de hotel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["voo", "hotel"]},
                "dados": {"type": "object"}
            },
            "required": ["tipo", "dados"]
        }
    },
    {
        "name": "ver_carteira",
        "description": "Mostra viagens salvas. Use para proximas viagens, passagens, hoteis reservados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "default": 90}
            }
        }
    },
    {
        "name": "atualizar_milhas_automatico",
        "description": "Acessa Smiles e LATAM Pass automaticamente para buscar saldo de milhas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "programa": {"type": "string", "enum": ["smiles", "latam_pass", "ambos"]},
                "cpf_email_smiles": {"type": "string"},
                "senha_smiles": {"type": "string"},
                "email_latam": {"type": "string"},
                "senha_latam": {"type": "string"}
            },
            "required": ["programa"]
        }
    },
    {
        "name": "alertas_e_monitoramento",
        "description": (
            "Configura alertas de preço para voos ou hotéis, monitora disponibilidade "
            "de assentos prêmio em milhas e alerta sobre vencimento de milhas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["queda_preco_voo", "disponibilidade_milhas", "vencimento_milhas", "promocao_companhia"]},
                "parametros": {"type": "object", "description": "Parâmetros específicos do alerta"}
            },
            "required": ["tipo"]
        }
    }
]


# ─────────────────────────────────────────────
# EXECUTORES DAS FERRAMENTAS
# ─────────────────────────────────────────────
async def execute_tool(tool_name: str, tool_input: dict, profile: dict) -> str:
    """Executa a ferramenta solicitada e retorna resultado como string."""

    if tool_name == "buscar_voos":
        return await tool_buscar_voos(tool_input, profile)
    elif tool_name == "buscar_voos_em_milhas":
        return await tool_buscar_milhas_voo(tool_input, profile)
    elif tool_name == "buscar_hoteis":
        return await tool_buscar_hoteis(tool_input, profile)
    elif tool_name == "conferir_milhas":
        return await tool_conferir_milhas(tool_input, profile)
    elif tool_name == "calcular_valor_milhas":
        return await tool_calcular_valor_milhas(tool_input, profile)
    elif tool_name == "montar_itinerario":
        return await tool_montar_itinerario(tool_input, profile)
    elif tool_name == "atualizar_perfil":
        return await tool_atualizar_perfil(tool_input, profile)
    elif tool_name == "alertas_e_monitoramento":
        return await tool_alertas(tool_input, profile)
    elif tool_name == "verificar_gmail":
        return await tool_verificar_gmail(tool_input, profile)
    elif tool_name == "salvar_viagem":
        return await tool_salvar_viagem(tool_input, profile)
    elif tool_name == "ver_carteira":
        return await tool_ver_carteira(tool_input, profile)
    elif tool_name == "atualizar_milhas_automatico":
        return await tool_atualizar_milhas_auto(tool_input, profile)
    return f"Ferramenta '{tool_name}' não reconhecida."


async def tool_buscar_voos(params: dict, profile: dict) -> str:
    """
    Busca voos via Amadeus API ou retorna dados simulados para demonstração.
    Em produção: integrar com amadeus-python SDK ou requests para /v2/shopping/flight-offers
    """
    origem = params.get("origem", "GRU")
    destino = params.get("destino", "")
    data_ida = params.get("data_ida", "")
    data_volta = params.get("data_volta")
    classe = params.get("classe", "economica")
    adultos = params.get("adultos", 1)

    # ── PRODUÇÃO: Substituir pelo código abaixo ──────────────────────────────
    # import amadeus
    # client = amadeus.Client(client_id=AMADEUS_CLIENT_ID, client_secret=AMADEUS_CLIENT_SECRET)
    # response = client.shopping.flight_offers_search.get(
    #     originLocationCode=origem, destinationLocationCode=destino,
    #     departureDate=data_ida, adults=adultos, travelClass=classe.upper()
    # )
    # Processar response.data e formatar resultado
    # ────────────────────────────────────────────────────────────────────────

    # Dados simulados realistas para demonstração
    results = {
        "busca": f"{origem} → {destino} | {data_ida}" + (f" → {data_volta}" if data_volta else " (só ida)"),
        "classe": classe,
        "opcoes": [
            {
                "companhia": "LATAM",
                "numero_voo": "LA3251",
                "saida": "06:30",
                "chegada": "08:15" if destino in ["GIG", "BSB"] else "14:45",
                "duracao": "1h45" if destino in ["GIG", "BSB"] else "10h15",
                "escalas": 0,
                "preco_pp": 689 if classe == "economica" else 4200,
                "preco_total": (689 if classe == "economica" else 4200) * adultos,
                "bagagem": "1 mala 23kg inclusa",
                "cancelamento": "Gratuito até 24h"
            },
            {
                "companhia": "GOL",
                "numero_voo": "G31085",
                "saida": "08:10",
                "chegada": "09:55" if destino in ["GIG", "BSB"] else "18:30",
                "duracao": "1h45" if destino in ["GIG", "BSB"] else "12h20",
                "escalas": 0 if destino in ["GIG", "BSB"] else 1,
                "preco_pp": 612 if classe == "economica" else 3890,
                "preco_total": (612 if classe == "economica" else 3890) * adultos,
                "bagagem": "Apenas bagagem de mão",
                "cancelamento": "Pago"
            },
            {
                "companhia": "Azul",
                "numero_voo": "AD4720",
                "saida": "11:40",
                "chegada": "13:30" if destino in ["GIG", "BSB"] else "20:10",
                "duracao": "1h50" if destino in ["GIG", "BSB"] else "10h30",
                "escalas": 0,
                "preco_pp": 731 if classe == "economica" else 4100,
                "preco_total": (731 if classe == "economica" else 4100) * adultos,
                "bagagem": "1 mala 23kg inclusa",
                "cancelamento": "Gratuito até 48h"
            }
        ],
        "moeda": "BRL",
        "nota": "⚠️ Preços simulados para demonstração. Em produção, conectar à API Amadeus."
    }
    return json.dumps(results, ensure_ascii=False, indent=2)


async def tool_buscar_milhas_voo(params: dict, profile: dict) -> str:
    """
    Busca disponibilidade de assentos prêmio nos programas de fidelidade.
    Em produção: usar web scraping via Playwright para Smiles, LATAM Pass, TudoAzul
    """
    origem = params.get("origem", "GRU")
    destino = params.get("destino", "")
    data_ida = params.get("data_ida", "")
    classe = params.get("classe", "executiva")
    programas = params.get("programas", ["smiles", "latam_pass", "tudoazul", "livelo"])

    fidelidades = profile.get("fidelidades", {})

    results = {
        "busca": f"{origem} → {destino} | {data_ida} | {classe}",
        "programas": {}
    }

    programa_dados = {
        "smiles": {
            "disponivel": True,
            "milhas": 35000,
            "taxas_brl": 185.40,
            "saldo_atual": fidelidades.get("smiles", {}).get("saldo_estimado", 0),
            "saldo_suficiente": fidelidades.get("smiles", {}).get("saldo_estimado", 0) >= 35000,
            "parceiros": ["GOL", "Air France", "KLM", "Delta"],
            "cpm_equivalente": "R$ 0,018/milha",
            "link": "https://www.smiles.com.br"
        },
        "latam_pass": {
            "disponivel": True,
            "milhas": 40000,
            "taxas_brl": 210.00,
            "saldo_atual": fidelidades.get("latam_pass", {}).get("saldo_estimado", 0),
            "saldo_suficiente": fidelidades.get("latam_pass", {}).get("saldo_estimado", 0) >= 40000,
            "parceiros": ["LATAM", "oneworld"],
            "cpm_equivalente": "R$ 0,016/milha",
            "link": "https://www.latamairlines.com/br/pt/latam-pass"
        },
        "tudoazul": {
            "disponivel": False,
            "motivo": "Sem disponibilidade nesta data",
            "saldo_atual": fidelidades.get("tudoazul", {}).get("saldo_estimado", 0),
            "link": "https://www.tudoazul.com"
        },
        "livelo": {
            "disponivel": True,
            "pontos": 45000,
            "taxas_brl": 0,
            "nota": "Transferir para Smiles ou LATAM Pass primeiro (ratio 1:1)",
            "saldo_atual": fidelidades.get("livelo", {}).get("saldo_estimado", 0),
            "saldo_suficiente": fidelidades.get("livelo", {}).get("saldo_estimado", 0) >= 45000,
            "link": "https://www.livelo.com.br"
        }
    }

    for prog in programas:
        if prog in programa_dados:
            results["programas"][prog] = programa_dados[prog]

    results["recomendacao"] = (
        "Smiles apresenta o melhor CPM (custo por milha). "
        "Se saldo insuficiente no Smiles, considere transferir do Livelo (ratio 1:1 sem bônus)."
    )
    results["nota"] = "⚠️ Disponibilidade simulada. Em produção: web scraping via Playwright."

    return json.dumps(results, ensure_ascii=False, indent=2)


async def tool_buscar_hoteis(params: dict, profile: dict) -> str:
    """
    Busca hotéis reais via RapidAPI (Booking.com).
    Retorna opções com preços reais, avaliações e link direto para reserva.
    """
    destino = params.get("destino", "")
    checkin = params.get("checkin", "")
    checkout = params.get("checkout", "")
    categoria = params.get("categoria", "4_estrelas")
    adultos = params.get("adultos", 1)
    quartos = params.get("quartos", 1)

    # Calcular noites
    try:
        d1 = datetime.strptime(checkin, "%Y-%m-%d")
        d2 = datetime.strptime(checkout, "%Y-%m-%d")
        noites = (d2 - d1).days
    except Exception:
        noites = 1

    if not RAPIDAPI_KEY:
        return json.dumps({"erro": "RAPIDAPI_KEY não configurada."})

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY.strip(),
        "x-rapidapi-host": "apidojo-booking-v1.p.rapidapi.com"
    }

    try:
        # Passo 1: buscar o dest_id da cidade
        async with httpx.AsyncClient(timeout=15) as client:
            loc_resp = await client.get(
                "https://apidojo-booking-v1.p.rapidapi.com/locations/auto-complete",
                headers=headers,
                params={"text": destino, "languagecode": "pt-br"}
            )
            loc_data = loc_resp.json()

        dest_id = None
        dest_type = "city"
        if loc_data and len(loc_data) > 0:
            for item in loc_data:
                if item.get("dest_type") in ["city", "region"]:
                    dest_id = str(item.get("dest_id", ""))
                    dest_type = item.get("dest_type", "city")
                    break
            if not dest_id:
                dest_id = str(loc_data[0].get("dest_id", ""))
                dest_type = loc_data[0].get("dest_type", "city")

        if not dest_id:
            return json.dumps({"erro": f"Destino '{destino}' não encontrado."})

        # Passo 2: buscar hotéis sem filtro de categoria para maximizar resultados
        search_params = {
            "dest_id": dest_id,
            "search_type": dest_type,
            "arrival_date": checkin,
            "departure_date": checkout,
            "adults": str(adultos),
            "room_qty": str(quartos),
            "units": "metric",
            "temperature_unit": "c",
            "languagecode": "pt-br",
            "currency_code": "BRL",
            "order_by": "popularity",
            "offset": "0"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            search_resp = await client.get(
                "https://apidojo-booking-v1.p.rapidapi.com/properties/list",
                headers=headers,
                params=search_params
            )
            search_data = search_resp.json()

        # Tenta diferentes chaves de resultado
        hoteis = (
            search_data.get("result") or
            search_data.get("data", {}).get("result") or
            search_data.get("hotels") or
            []
        )
        hoteis = list(hoteis)[:5] if hoteis else []

        if not hoteis:
            link_busca = (
                f"https://www.booking.com/searchresults.pt-br.html"
                f"?dest_id={dest_id}&dest_type={dest_type}"
                f"&checkin={checkin}&checkout={checkout}"
                f"&group_adults={adultos}&no_rooms={quartos}"
                f"&order=popularity"
            )
            return json.dumps({
                "busca": f"{destino} | {checkin} → {checkout}",
                "resultado": "Sem disponibilidade via API para estas datas.",
                "link_busca_direta": link_busca,
                "instrucao": f"Informe ao usuário que encontrou o link direto no Booking.com e forneça este link clicável: {link_busca}"
            }, ensure_ascii=False)

        opcoes = []
        for h in hoteis:
            preco_raw = h.get("price_breakdown", {}).get("gross_price", 0)
            try:
                preco_total = float(preco_raw)
                preco_noite = round(preco_total / noites, 2) if noites > 0 else preco_total
            except Exception:
                preco_total = 0
                preco_noite = 0

            avaliacao = h.get("review_score", 0)
            avaliacao_texto = h.get("review_score_word", "")
            stars = int(h.get("class", 0))
            estrelas = "⭐" * stars if stars else ""

            checkin_from = h.get("checkin", {}).get("from", "")
            checkout_until = h.get("checkout", {}).get("until", "")

            hotel_id = h.get("hotel_id", "")
            link_reserva = (
                f"https://www.booking.com/hotel/br/{h.get('url', '')}.pt-br.html"
                f"?checkin={checkin}&checkout={checkout}&group_adults={adultos}&no_rooms={quartos}"
                if h.get("url") else
                f"https://www.booking.com/searchresults.pt-br.html?dest_id={dest_id}&checkin={checkin}&checkout={checkout}"
            )

            opcoes.append({
                "nome": h.get("hotel_name", "Hotel"),
                "estrelas": estrelas,
                "bairro": h.get("district", h.get("city", destino)),
                "avaliacao": avaliacao,
                "avaliacao_texto": avaliacao_texto,
                "preco_noite_brl": preco_noite,
                "preco_total_brl": preco_total,
                "moeda": "BRL",
                "checkin_horario": checkin_from,
                "checkout_horario": checkout_until,
                "cancelamento": "Verificar no link de reserva",
                "link_reserva": link_reserva,
                "destaque": h.get("wishlist_count", "")
            })

        return json.dumps({
            "busca": f"{destino} | {checkin} → {checkout} ({noites} noite{'s' if noites > 1 else ''})",
            "adultos": adultos,
            "quartos": quartos,
            "opcoes": opcoes,
            "nota": "✅ Preços reais via Booking.com. Toque no link para confirmar reserva com 1 clique.",
            "instrucao": "Apresente as opções de forma clara com nome, preço por noite, avaliação e o link de reserva clicável."
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"Erro RapidAPI hotéis: {e}")
        return json.dumps({
            "erro": f"Erro ao buscar hotéis: {str(e)}",
            "sugestao": "Tente novamente em alguns instantes."
        })


async def tool_conferir_milhas(params: dict, profile: dict) -> str:
    """Consulta saldo e status dos programas de fidelidade."""
    programa = params.get("programa", "todos")
    incluir_transf = params.get("incluir_transferencias", True)
    fidelidades = profile.get("fidelidades", {})
    hoje = datetime.now()

    def status_vencimento(venc_str):
        if not venc_str:
            return "Não informado"
        try:
            venc = datetime.strptime(venc_str, "%Y-%m-%d")
            dias = (venc - hoje).days
            if dias < 0:
                return f"⛔ VENCIDO há {abs(dias)} dias"
            elif dias < 30:
                return f"🔴 Vence em {dias} dias — URGENTE"
            elif dias < 90:
                return f"🟡 Vence em {dias} dias"
            else:
                return f"🟢 Vence em {dias} dias ({venc.strftime('%d/%m/%Y')})"
        except Exception:
            return venc_str

    prog_info = {
        "smiles": {
            "nome": "Smiles (GOL)",
            "saldo": fidelidades.get("smiles", {}).get("saldo_estimado", 0),
            "categoria": fidelidades.get("smiles", {}).get("categoria", ""),
            "vencimento": status_vencimento(fidelidades.get("smiles", {}).get("vencimento_proximo")),
            "parceiros_resgate": ["GOL", "Air France", "KLM", "Delta", "Avianca"],
            "valor_estimado_brl": fidelidades.get("smiles", {}).get("saldo_estimado", 0) * 0.018,
            "link_extrato": "https://www.smiles.com.br/meu-extrato"
        },
        "latam_pass": {
            "nome": "LATAM Pass",
            "saldo": fidelidades.get("latam_pass", {}).get("saldo_estimado", 0),
            "categoria": fidelidades.get("latam_pass", {}).get("categoria", ""),
            "vencimento": status_vencimento(fidelidades.get("latam_pass", {}).get("vencimento_proximo")),
            "parceiros_resgate": ["LATAM", "American Airlines", "British Airways", "Iberia"],
            "valor_estimado_brl": fidelidades.get("latam_pass", {}).get("saldo_estimado", 0) * 0.016,
            "link_extrato": "https://www.latamairlines.com/br/pt/latam-pass/extrato"
        },
        "livelo": {
            "nome": "Livelo",
            "saldo": fidelidades.get("livelo", {}).get("saldo_estimado", 0),
            "vencimento": status_vencimento(fidelidades.get("livelo", {}).get("vencimento_proximo")),
            "parceiros_transferencia": ["Smiles (1:1)", "LATAM Pass (1:1)", "TudoAzul (1:1)", "Avios (1:1)"],
            "valor_estimado_brl": fidelidades.get("livelo", {}).get("saldo_estimado", 0) * 0.017,
            "nota": "Livelo é hub de pontos — transfira para o programa que tiver melhor disponibilidade.",
            "link_extrato": "https://www.livelo.com.br/extrato"
        },
        "tudoazul": {
            "nome": "TudoAzul (Azul)",
            "saldo": fidelidades.get("tudoazul", {}).get("saldo_estimado", 0),
            "categoria": fidelidades.get("tudoazul", {}).get("categoria", ""),
            "vencimento": status_vencimento(fidelidades.get("tudoazul", {}).get("vencimento_proximo")),
            "parceiros_resgate": ["Azul", "United", "Copa Airlines", "TAP"],
            "valor_estimado_brl": fidelidades.get("tudoazul", {}).get("saldo_estimado", 0) * 0.015,
            "link_extrato": "https://www.tudoazul.com.br/extrato"
        }
    }

    if programa == "todos":
        resultado = {"programas": prog_info}
        total_valor = sum(p.get("valor_estimado_brl", 0) for p in prog_info.values())
        resultado["resumo"] = {
            "total_milhas_smiles": prog_info["smiles"]["saldo"],
            "total_milhas_latam": prog_info["latam_pass"]["saldo"],
            "total_pontos_livelo": prog_info["livelo"]["saldo"],
            "total_milhas_azul": prog_info["tudoazul"]["saldo"],
            "valor_total_estimado_brl": round(total_valor, 2),
            "nota_valor": "Estimativa conservadora baseada em CPM médio de mercado"
        }
        if incluir_transf:
            resultado["oportunidades_transferencia"] = [
                "Livelo → Smiles: ratio 1:1 (bônus sazonais de até 100%)",
                "Livelo → LATAM Pass: ratio 1:1",
                "Itaú Personnalité → Livelo: 2,5 pts/R$",
            ]
    else:
        resultado = prog_info.get(programa, {"erro": f"Programa '{programa}' não encontrado"})

    resultado["nota"] = "⚠️ Saldos baseados nos dados do perfil. Atualize via /atualizar ou informe o saldo atual."
    return json.dumps(resultado, ensure_ascii=False, indent=2)


async def tool_calcular_valor_milhas(params: dict, profile: dict) -> str:
    """Calcula CPM e recomenda se vale usar milhas."""
    preco_dinheiro = params.get("preco_passagem_dinheiro", 0)
    milhas = params.get("milhas_necessarias", 0)
    taxas = params.get("taxas_milhas", 0)
    programa = params.get("programa", "Não informado")

    if milhas == 0:
        return json.dumps({"erro": "Informe a quantidade de milhas necessárias."})

    cpm = (preco_dinheiro - taxas) / milhas
    cpm_referencia_bom = 0.020   # R$ 0,020/milha = muito bom
    cpm_referencia_ok = 0.012    # R$ 0,012/milha = aceitável
    custo_real_milhas = taxas  # quanto você paga do bolso

    if cpm >= cpm_referencia_bom:
        avaliacao = "🟢 EXCELENTE — Vale muito a pena usar milhas"
        recomendacao = "Use as milhas. O CPM está acima da referência de mercado."
    elif cpm >= cpm_referencia_ok:
        avaliacao = "🟡 BOM — Vale a pena usar milhas"
        recomendacao = "Use as milhas se não tiver uso melhor para elas."
    else:
        avaliacao = "🔴 FRACO — Provavelmente não vale"
        recomendacao = f"Pague em dinheiro (R$ {preco_dinheiro:.2f}) e acumule milhas na compra."

    resultado = {
        "analise": {
            "preco_em_dinheiro": f"R$ {preco_dinheiro:.2f}",
            "milhas_necessarias": f"{milhas:,.0f} milhas",
            "taxas_a_pagar": f"R$ {taxas:.2f}",
            "custo_real_usando_milhas": f"R$ {custo_real_milhas:.2f}",
            "economia_real": f"R$ {preco_dinheiro - custo_real_milhas:.2f}",
            "cpm_calculado": f"R$ {cpm:.4f}/milha",
            "cpm_referencia_excelente": "R$ 0,0200/milha",
            "cpm_referencia_minimo": "R$ 0,0120/milha"
        },
        "avaliacao": avaliacao,
        "recomendacao": recomendacao,
        "programa": programa
    }
    return json.dumps(resultado, ensure_ascii=False, indent=2)


async def tool_montar_itinerario(params: dict, profile: dict) -> str:
    """Monta roteiro completo de viagem."""
    destino = params.get("destino", "")
    data_ida = params.get("data_ida", "")
    data_volta = params.get("data_volta", "")
    objetivo = params.get("objetivo", "lazer")
    usar_milhas = params.get("usar_milhas", True)

    try:
        d1 = datetime.strptime(data_ida, "%Y-%m-%d")
        d2 = datetime.strptime(data_volta, "%Y-%m-%d")
        noites = (d2 - d1).days
    except Exception:
        noites = 3

    itinerario = {
        "titulo": f"Viagem para {destino} — {objetivo.title()}",
        "periodo": f"{data_ida} → {data_volta} ({noites} noites)",
        "voo_recomendado": {
            "companhia": "LATAM (verificar Smiles para executiva em milhas)" if usar_milhas else "LATAM",
            "horario_sugerido": "Manhã cedo (06:30–08:00) — evita atrasos",
            "classe": "Executiva via milhas" if usar_milhas else "Econômica",
            "milhas_estimadas": "40.000–60.000 milhas" if usar_milhas else "N/A",
            "preco_estimado_economica": "R$ 600–900 ida e volta"
        },
        "hotel_recomendado": {
            "categoria": "4–5 estrelas",
            "bairro_sugerido": "Centro ou área de negócios" if objetivo == "negócios" else "Bairro histórico/turístico",
            "preco_estimado": f"R$ 400–800/noite (total: R$ {400 * noites:,}–{800 * noites:,})"
        },
        "checklist_documentos": [
            "✅ Passaporte (validade mínima 6 meses além da viagem)" if destino not in ["Rio de Janeiro", "Brasília", "São Paulo"] else "✅ RG ou CNH válidos",
            "✅ Visto (verificar necessidade para o destino)",
            "✅ Seguro viagem",
            "✅ Cartão de crédito internacional (Visa/Mastercard)"
        ],
        "dicas_pontos": [
            f"Use cartão Itaú Personnalité para pagar hotel e acumular Livelo",
            f"Registre a compra da passagem no programa de fidelidade correto",
            "Solicite cartão de embarque com número do programa para acumular milhas de voo"
        ] if usar_milhas else [],
        "custo_estimado_total": {
            "voo_economica": f"R$ {700 * 2:,}",
            "hotel": f"R$ {600 * noites:,}",
            "total_estimado": f"R$ {700 * 2 + 600 * noites:,}",
            "alternativa_milhas": f"Usando milhas: R$ {600 * noites + 400:,} + ~50.000 milhas" if usar_milhas else "N/A"
        },
        "proximo_passo": "Confirme as datas e eu faço a busca real de voos e hotéis para você."
    }
    return json.dumps(itinerario, ensure_ascii=False, indent=2)


async def tool_atualizar_perfil(params: dict, profile: dict) -> str:
    """Atualiza campo no perfil do viajante."""
    campo = params.get("campo", "")
    valor = params.get("valor")

    partes = campo.split(".")
    obj = profile
    try:
        for parte in partes[:-1]:
            obj = obj[parte]
        chave_final = partes[-1]
        valor_anterior = obj.get(chave_final, "não definido")
        obj[chave_final] = valor
        save_profile(profile)
        return json.dumps({
            "sucesso": True,
            "campo_atualizado": campo,
            "valor_anterior": str(valor_anterior),
            "novo_valor": str(valor),
            "mensagem": f"✅ Perfil atualizado: {campo} = {valor}"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"sucesso": False, "erro": str(e)})


async def tool_alertas(params: dict, profile: dict) -> str:
    """Configura alertas (stub — implementar com scheduler em produção)."""
    tipo = params.get("tipo", "")
    parametros = params.get("parametros", {})
    return json.dumps({
        "alerta_configurado": True,
        "tipo": tipo,
        "parametros": parametros,
        "nota": "⚠️ Alertas em produção requerem agendador (APScheduler ou Celery). "
                "Por ora, consulte manualmente via '/milhas' ou '/voos'."
    }, ensure_ascii=False)


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
def build_system_prompt(profile: dict) -> str:
    fid = profile.get("fidelidades", {})
    pref = profile.get("preferencias", {})
    cartoes = profile.get("cartoes", [])
    cartoes_str = ", ".join(f"{c['nome']} ({c['programa']}, {c['pontos_por_real']} pts/R$)" for c in cartoes)
    hoje = datetime.now().strftime("%d/%m/%Y")
    ano_atual = datetime.now().year

    return f"""Você é o agente de viagens pessoal de {profile.get('nome', 'Rodrigo')}, especializado em maximizar benefícios de fidelidade e encontrar as melhores opções de viagem.

## Data atual
- **Hoje é:** {hoje} (ano {ano_atual})
- **IMPORTANTE:** Sempre use o ano {ano_atual} como referência. Quando o usuário disser "em julho", "em agosto" etc sem especificar o ano, assuma {ano_atual}. Nunca use datas passadas nas buscas.

## Perfil do viajante
- **Nome:** {profile.get('nome')}
- **Base:** {profile.get('cidade_base')}
- **Destinos frequentes:** {', '.join(profile.get('destinos_frequentes', []))}
- **Assento preferido:** {pref.get('assento')}
- **Companhias preferidas:** {', '.join(pref.get('companhias_preferidas', []))}
- **Classe padrão:** {pref.get('classe_padrao')} (mas prefere executiva via milhas)
- **Notas:** {profile.get('notas', '')}

## Programas de fidelidade
- **Smiles (GOL):** {fid.get('smiles', {}).get('categoria', '')} — Saldo: {fid.get('smiles', {}).get('saldo_estimado', 0):,} milhas
- **LATAM Pass:** {fid.get('latam_pass', {}).get('categoria', '')} — Saldo: {fid.get('latam_pass', {}).get('saldo_estimado', 0):,} milhas
- **Livelo:** Saldo: {fid.get('livelo', {}).get('saldo_estimado', 0):,} pontos
- **TudoAzul:** {fid.get('tudoazul', {}).get('categoria', '')} — Saldo: {fid.get('tudoazul', {}).get('saldo_estimado', 0):,} milhas

## Cartões de crédito
{cartoes_str}

## Diretrizes de atuação
1. **Sempre** verifique opções em milhas antes de recomendar pagamento em dinheiro
2. **Priorize** voos diretos quando o custo adicional for razoável
3. **Calcule** CPM sempre que houver comparação milhas × dinheiro
4. **Avise** proativamente sobre milhas próximas do vencimento
5. **Formate** respostas de forma clara com emojis para facilitar leitura no celular
6. **Seja direto:** dê uma recomendação clara, não apenas opções
7. **Lembre** que o usuário viaja frequentemente a trabalho para Rio e Brasília
8. **Considere** sempre o programa Livelo como hub de transferência

## REGRAS OBRIGATÓRIAS DE USO DE FERRAMENTAS
- **HOTEL:** Qualquer pedido de hotel → chamar `buscar_hoteis` OBRIGATORIAMENTE.
- **VOO:** Qualquer pedido de voo → chamar `buscar_voos` OBRIGATORIAMENTE.
- **MILHAS:** Qualquer pedido sobre milhas → chamar `conferir_milhas` OBRIGATORIAMENTE.
- **REGISTRAR VIAGEM:** Usuário informou compra de passagem ou reserva → chamar `salvar_viagem` OBRIGATORIAMENTE.
- **VER CARTEIRA:** "minhas viagens", "próximas viagens", "o que tenho marcado" → chamar `ver_carteira` OBRIGATORIAMENTE.
- **GMAIL:** Qualquer pedido para verificar email, importar viagens do Gmail, checar inbox → chamar `verificar_gmail` OBRIGATORIAMENTE com acao="buscar_emails_viagem". NUNCA diga que o Gmail não está configurado sem chamar a ferramenta primeiro. NUNCA recuse chamar a ferramenta.
- **ATUALIZAR MILHAS AUTO:** "atualizar milhas automaticamente" → chamar `atualizar_milhas_automatico`.
- Se qualquer ferramenta retornar erro, mostre o erro exato ao usuário. NUNCA substitua por texto genérico.
- NUNCA responda "não está configurado" ou "não está disponível" sem antes chamar a ferramenta correspondente.

## Formato das respostas
- Use markdown com emojis ✈️ 🏨 🏅 💰
- Sempre termine com uma pergunta ou próximo passo sugerido
- Para cotações, apresente em formato de comparativo claro
- Seja conciso — estamos no Telegram, não em email
- Quando detectar oportunidade de usar milhas, destaque em negrito
- Para hotéis, sempre mostre: nome, estrelas, avaliação, preço/noite, preço total e **link clicável para reserva**

Responda sempre em português brasileiro."""


# ─────────────────────────────────────────────
# CORE DO AGENTE (loop agentic)
# ─────────────────────────────────────────────
async def run_agent(user_message: str, profile: dict, history: list) -> str:
    """Executa o loop agentic com suporte a múltiplas chamadas de ferramentas."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = history + [{"role": "user", "content": user_message}]
    system = build_system_prompt(profile)

    MAX_ITERATIONS = 5
    for iteration in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_result = await execute_tool(block.name, block.input, profile)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            return text

        else:
            break

    return "Desculpe, tive um problema ao processar sua solicitação. Tente novamente."


# ─────────────────────────────────────────────
# HANDLERS DO TELEGRAM
# ─────────────────────────────────────────────
def is_authorized(update: Update) -> bool:
    user_id = update.effective_user.id
    if AUTHORIZED_USERS == [0]:
        return True  # Sem restrição configurada
    return user_id in AUTHORIZED_USERS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ Acesso não autorizado.")
        return

    profile = load_profile()
    nome = profile.get("nome", "viajante")

    keyboard = [
        [InlineKeyboardButton("✈️ Buscar voos", callback_data="acao_voos"),
         InlineKeyboardButton("🏨 Buscar hotel", callback_data="acao_hotel")],
        [InlineKeyboardButton("🏅 Minhas milhas", callback_data="acao_milhas"),
         InlineKeyboardButton("📋 Montar roteiro", callback_data="acao_roteiro")],
        [InlineKeyboardButton("🗂 Minha carteira", callback_data="acao_carteira"),
         InlineKeyboardButton("⚙️ Meu perfil", callback_data="acao_perfil")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✈️ *Olá, {nome}!*\n\n"
        "Sou seu agente de viagens pessoal. Posso te ajudar com:\n\n"
        "• 🔍 Cotação e comparação de voos\n"
        "• 🏨 Busca de hotéis\n"
        "• 🏅 Gestão de milhas (Smiles, LATAM Pass, Livelo, TudoAzul)\n"
        "• 💡 Calcular se vale usar milhas\n"
        "• 📋 Montar itinerários completos\n\n"
        "Pode me escrever normalmente, como falaria com um agente humano!\n\n"
        "_Ex: 'Quero ir pra Lisboa em julho, de executiva usando milhas'_",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def cmd_milhas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("🔄 Consultando seus programas de fidelidade...")
    profile = load_profile()
    history = load_history()
    resp = await run_agent("Faça um resumo completo de todas as minhas milhas, saldos, vencimentos e oportunidades.", profile, history)
    await update.message.reply_text(resp, parse_mode="Markdown")


async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    profile = load_profile()
    fid = profile.get("fidelidades", {})
    pref = profile.get("preferencias", {})

    texto = (
        f"⚙️ *Seu Perfil*\n\n"
        f"👤 *{profile.get('nome')}* | {profile.get('cidade_base')}\n\n"
        f"*Preferências de voo:*\n"
        f"• Assento: {pref.get('assento')}\n"
        f"• Companhias: {', '.join(pref.get('companhias_preferidas', []))}\n\n"
        f"*Programas de fidelidade:*\n"
        f"• ✈️ Smiles: {fid.get('smiles', {}).get('saldo_estimado', '?'):,} milhas\n"
        f"• ✈️ LATAM Pass: {fid.get('latam_pass', {}).get('saldo_estimado', '?'):,} milhas\n"
        f"• 💳 Livelo: {fid.get('livelo', {}).get('saldo_estimado', '?'):,} pontos\n"
        f"• ✈️ TudoAzul: {fid.get('tudoazul', {}).get('saldo_estimado', '?'):,} milhas\n\n"
        f"_Para atualizar, diga: 'Meu saldo Smiles é 85.000 milhas'_"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🆘 *Comandos disponíveis:*\n\n"
        "/start — Menu principal\n"
        "/milhas — Resumo de todos os programas\n"
        "/perfil — Ver e editar seu perfil\n"
        "/ajuda — Esta mensagem\n\n"
        "*Exemplos do que você pode me pedir:*\n\n"
        "• _'Voos GRU→LIS em 15/07, executiva'_\n"
        "• _'Hotéis em Miami de 10 a 17/08'_\n"
        "• _'Vale a pena usar 40.000 milhas ou pagar R$1.200?'_\n"
        "• _'Monte um roteiro completo para Lisboa em julho'_\n"
        "• _'Meu saldo Smiles é 92.000 milhas'_\n"
        "• _'Quando vencem minhas milhas LATAM?'_",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ Acesso não autorizado.")
        return

    user_text = update.message.text
    profile = load_profile()
    history = load_history()

    thinking_msg = await update.message.reply_text("⏳ Processando...")

    try:
        response = await run_agent(user_text, profile, history)

        # Atualiza histórico
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": response})
        save_history(history)

        await thinking_msg.delete()

        # Telegram tem limite de 4096 chars por mensagem
        if len(response) > 4000:
            partes = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for parte in partes:
                await update.message.reply_text(parte, parse_mode="Markdown")
        else:
            await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        await thinking_msg.delete()
        logger.error(f"Erro no agente: {e}")
        await update.message.reply_text(
            f"⚠️ Erro ao processar sua solicitação.\n\nDetalhe: {str(e)}"
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    acoes = {
        "acao_voos": "Quero cotar voos. Me diga as opções disponíveis para os destinos mais comuns que viajo (Rio de Janeiro e Brasília) nos próximos 7 dias.",
        "acao_hotel": "Preciso buscar um hotel. Pode me ajudar?",
        "acao_milhas": "Faça um resumo completo de todas as minhas milhas, saldos e vencimentos.",
        "acao_roteiro": "Quero montar um roteiro de viagem completo. Pode me guiar?",
        "acao_carteira": "Mostre todas as minhas viagens marcadas, passagens e reservas de hotel salvas.",
        "acao_perfil": "/perfil"
    }

    data = query.data
    if data == "acao_perfil":
        profile = load_profile()
        fid = profile.get("fidelidades", {})
        pref = profile.get("preferencias", {})
        texto = (
            f"⚙️ *Seu Perfil*\n\n"
            f"👤 *{profile.get('nome')}* | {profile.get('cidade_base')}\n\n"
            f"*Programas de fidelidade:*\n"
            f"• Smiles: {fid.get('smiles', {}).get('saldo_estimado', '?'):,} milhas\n"
            f"• LATAM Pass: {fid.get('latam_pass', {}).get('saldo_estimado', '?'):,} milhas\n"
            f"• Livelo: {fid.get('livelo', {}).get('saldo_estimado', '?'):,} pontos\n"
            f"• TudoAzul: {fid.get('tudoazul', {}).get('saldo_estimado', '?'):,} milhas\n\n"
            f"_Para atualizar: 'Meu saldo Smiles é 85.000'_"
        )
        await query.message.reply_text(texto, parse_mode="Markdown")
    elif data in acoes:
        profile = load_profile()
        history = load_history()
        msg = await query.message.reply_text("⏳ Processando...")
        response = await run_agent(acoes[data], profile, history)
        await msg.delete()
        await query.message.reply_text(response, parse_mode="Markdown")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
async def cmd_carteira(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    profile = load_profile()
    history = load_history()
    resp = await run_agent("Mostre todas as minhas viagens marcadas e passagens salvas.", profile, history)
    await update.message.reply_text(resp, parse_mode="Markdown")


async def post_init(app):
    """Inicia o scheduler de alertas após o bot subir."""
    # scheduler_loop é definido abaixo — chamado via string para evitar erro de ordem
    async def _start_scheduler():
        await asyncio.sleep(2)
        await scheduler_loop(app)
    asyncio.create_task(_start_scheduler())
    logger.info("Scheduler de alertas iniciado.")


async def handle_voice(update, context):
    if not is_authorized(update):
        return
    if not OPENAI_API_KEY:
        await update.message.reply_text("OPENAI_API_KEY nao configurada.")
        return
    thinking = await update.message.reply_text("Transcrevendo audio...")
    try:
        import tempfile
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await file.download_to_drive(tmp_path)
        async with httpx.AsyncClient(timeout=30) as client:
            with open(tmp_path, "rb") as af:
                resp = await client.post("https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    data={"model": "whisper-1", "language": "pt"},
                    files={"file": ("audio.ogg", af, "audio/ogg")})
        os.unlink(tmp_path)
        if resp.status_code != 200:
            await thinking.delete()
            await update.message.reply_text(f"Erro transcricao: {resp.status_code}")
            return
        text = resp.json().get("text","").strip()
        if not text:
            await thinking.delete()
            await update.message.reply_text("Nao entendi o audio.")
            return
        await thinking.edit_text(f"Voce disse: {text}\n\nProcessando...")
        profile = load_profile()
        history = load_history()
        response = await run_agent(text, profile, history)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": response})
        save_history(history)
        await thinking.delete()
        if len(response) > 4000:
            for parte in [response[i:i+4000] for i in range(0, len(response), 4000)]:
                await update.message.reply_text(parte, parse_mode="Markdown")
        else:
            await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Erro voz: {e}")
        try:
            await thinking.delete()
        except:
            pass
        await update.message.reply_text(f"Erro ao processar audio: {str(e)}")

async def cmd_gmail(update, context):
    if not is_authorized(update):
        return
    profile = load_profile()
    history = load_history()
    resp = await run_agent("Verifique meu Gmail e busque emails de viagem.", profile, history)
    await update.message.reply_text(resp, parse_mode="Markdown")


def main():
    logger.info("Iniciando Agente de Viagens...")
    os.makedirs("data", exist_ok=True)

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("milhas", cmd_milhas))
    app.add_handler(CommandHandler("perfil", cmd_perfil))
    app.add_handler(CommandHandler("carteira", cmd_carteira))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot rodando. Pressione Ctrl+C para parar.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

