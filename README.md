# ✈️ Agente de Viagens Pessoal — Rodrigo Arruy

Bot Telegram com IA para cotação de voos, hotéis e gestão de milhas (Smiles, LATAM Pass, Livelo, TudoAzul).

---

## 🚀 Instalação em 5 passos

### 1. Pré-requisitos
- Python 3.11+
- Conta no Telegram
- Chave da API Anthropic (`claude.ai/settings/keys`)

### 2. Criar o Bot no Telegram
1. Abra o Telegram e procure por **@BotFather**
2. Envie `/newbot`
3. Escolha um nome: ex. `Arruy Travel Agent`
4. Escolha um username: ex. `arruy_travel_bot`
5. Copie o **token** fornecido

### 3. Descobrir seu ID do Telegram
1. Procure por **@userinfobot** no Telegram
2. Envie qualquer mensagem
3. Copie o número `Id:` exibido

### 4. Configurar variáveis de ambiente
```bash
cp .env.example .env
```
Edite o `.env` com seus dados:
```
TELEGRAM_TOKEN=1234567890:ABCdef...
ANTHROPIC_API_KEY=sk-ant-...
AUTHORIZED_USERS=123456789
```

### 5. Instalar e rodar
```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instalar dependências
pip install -r requirements.txt

# Carregar variáveis de ambiente
export $(cat .env | xargs)  # Linux/Mac
# ou use python-dotenv (já incluído)

# Rodar o agente
python agent.py
```

---

## 💬 Como usar o bot

Após iniciar, abra o Telegram e procure seu bot. Comandos disponíveis:

| Comando | Função |
|---------|--------|
| `/start` | Menu principal com botões |
| `/milhas` | Resumo completo de todos os programas |
| `/perfil` | Ver seus dados e saldos |
| `/ajuda` | Lista de exemplos de uso |

### Exemplos de conversas naturais

```
Você: Quero ir pra Lisboa em 15 de julho, classe executiva usando milhas
Bot: [busca disponibilidade em Smiles, LATAM Pass, TudoAzul e Livelo e compara]

Você: Hotéis em Miami de 10 a 17 de agosto, 4 ou 5 estrelas
Bot: [lista hotéis com preços, avaliações e benefícios]

Você: Vale a pena usar 45.000 milhas ou pagar R$1.400 na econômica?
Bot: [calcula CPM e dá recomendação clara]

Você: Meu saldo Smiles agora é 92.000 milhas, vence em março
Bot: [atualiza seu perfil automaticamente]

Você: Monte um roteiro completo pra Paris com minha esposa em outubro
Bot: [cria itinerário com voo, hotel, dicas e cálculo de milhas]
```

---

## 🔧 Atualizar seus saldos de milhas

O jeito mais fácil é simplesmente falar com o bot:

```
"Meu saldo Smiles é 85.000 milhas"
"Tenho 120.000 pontos Livelo, vencem em junho"
"Minha categoria LATAM Pass é Black"
```

O agente detecta e atualiza o arquivo `data/profile.json` automaticamente.

---

## 🏭 Integração com APIs reais (Produção)

### Voos — Amadeus for Developers
1. Cadastre-se em https://developers.amadeus.com (gratuito)
2. Crie uma aplicação e obtenha `client_id` e `client_secret`
3. Adicione ao `.env`
4. No `agent.py`, descomente o bloco da Amadeus API em `tool_buscar_voos()`

```python
# Instalar: pip install amadeus
import amadeus
client = amadeus.Client(
    client_id=AMADEUS_CLIENT_ID,
    client_secret=AMADEUS_CLIENT_SECRET
)
response = client.shopping.flight_offers_search.get(
    originLocationCode='GRU',
    destinationLocationCode='LIS',
    departureDate='2025-07-15',
    adults=1,
    travelClass='BUSINESS'
)
```

### Hotéis — Booking.com Affiliate
- Solicite acesso em: https://www.booking.com/affiliate-program/v2/
- Ou use a **Amadeus Hotel Search API** (mesmo cadastro dos voos)

### Milhas — Web Scraping (Playwright)
Como Smiles e LATAM Pass não têm APIs públicas:

```bash
pip install playwright
playwright install chromium
```

```python
from playwright.async_api import async_playwright

async def scrape_smiles_balance(numero, senha):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.smiles.com.br/login")
        await page.fill("#login", numero)
        await page.fill("#password", senha)
        await page.click("#btn-login")
        await page.wait_for_selector(".balance")
        saldo = await page.inner_text(".balance")
        await browser.close()
        return saldo
```

> ⚠️ Web scraping pode quebrar quando os sites atualizam. Monitore regularmente.

---

## 🔄 Rodar em segundo plano (Linux/Mac)

### Opção 1: Screen
```bash
screen -S travel-agent
python agent.py
# Ctrl+A, D para desconectar
# screen -r travel-agent para reconectar
```

### Opção 2: Systemd (servidor Linux)
```ini
# /etc/systemd/system/travel-agent.service
[Unit]
Description=Travel Agent Bot
After=network.target

[Service]
User=seu_usuario
WorkingDirectory=/home/seu_usuario/travel-agent
ExecStart=/home/seu_usuario/travel-agent/venv/bin/python agent.py
Restart=always
EnvironmentFile=/home/seu_usuario/travel-agent/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable travel-agent
sudo systemctl start travel-agent
```

### Opção 3: Railway.app ou Render.com (nuvem gratuita)
1. Crie conta em railway.app
2. Conecte ao GitHub com os arquivos
3. Adicione as variáveis de ambiente no painel
4. Deploy automático

---

## 📁 Estrutura de arquivos

```
travel-agent/
├── agent.py          # Bot principal + todas as ferramentas
├── requirements.txt  # Dependências Python
├── .env.example      # Template de configuração
├── .env              # Suas credenciais (NÃO commitar)
├── README.md         # Este guia
└── data/
    ├── profile.json  # Seu perfil (criado automaticamente)
    └── history.json  # Histórico de conversas (criado automaticamente)
```

---

## 🛡️ Segurança

- O `.env` **nunca** deve ir para o Git — adicione ao `.gitignore`
- Use `AUTHORIZED_USERS` para restringir acesso ao seu Telegram ID
- Senhas dos programas de fidelidade (para scraping) devem ficar apenas no `.env`
- Rotacione a chave Anthropic regularmente em `claude.ai/settings/keys`

---

## 💡 Próximos passos sugeridos

- [ ] Integrar Amadeus API para voos em tempo real
- [ ] Configurar alertas de queda de preço (APScheduler)
- [ ] Adicionar scraping de saldo Smiles e LATAM Pass
- [ ] Integrar Google Calendar para criar eventos de viagem
- [ ] Painel web para visualizar histórico e milhas
