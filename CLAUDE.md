# Casa Barra do Una — Agentes de Aluguel

## Contexto do projeto

Este repositório contém agentes IA que automatizam o marketing e atendimento inicial
para alugar a casa de Francisco em Barra do Una (litoral norte de SP).

**Dono:** Francisco (francisco@okena.eco.br)
**Caso de uso:** Instagram da casa → posts automáticos + resposta de comentários + handoff para Francisco

## Decisões técnicas fixadas

- **Modelo:** Claude Sonnet 4.6 (`claude-sonnet-4-6`) com prompt caching
- **Hospedagem:** GitHub Actions (cron jobs)
- **Canal de aprovação:** Telegram (botões inline)
- **Instagram:** Graph API oficial (NUNCA usar instagrapi/instabot — ToS violation)
- **Calendário:** Airbnb iCal feed (URL no secret `AIRBNB_ICAL_URL`)
- **Estado persistido:** arquivos JSON em `data/` commitados no repo
- **Ritmo:** 3 posts/mês planejados dia 25, publicados nos dias agendados às 08:00 BRT

## Setup do Instagram (já feito parcialmente)

- ✅ Conta IG da casa já é Profissional/Empresa
- ✅ IG vinculado à Página do Facebook "Casa Barra do Una" (criada por Francisco)
- ✅ App Meta for Developers criado: **"Agente Barra do Una-IG"**
  - ID do app do Instagram: `1548327803481037`
  - ID do app principal (URL): `930977369962655`
  - Permissões configuradas: `instagram_business_basic`, `instagram_content_publish`, `instagram_manage_comments`, `instagram_manage_messages`
  - Usando a **nova Instagram API** (graph.instagram.com) — não a API antiga via Página do FB
- 🔲 **Próximo passo:** obter o token de acesso
  1. Esposa faz login na conta do Instagram da casa em qualquer navegador
  2. Francisco acessa: developers.facebook.com/apps/930977369962655
  3. Vai em: Casos de uso → API do Instagram → "Configuração da API com login do Instagram" (a primeira, NÃO a de Facebook login)
  4. Clica em "Adicionar conta"
  5. Na janela que abrir, esposa autoriza (confirmar que é a conta da CASA, não a pessoal)
  6. Token gerado → salvar como `INSTAGRAM_ACCESS_TOKEN`
  7. Chamar `GET https://graph.instagram.com/me?fields=id,username` com o token → o `id` retornado é o `INSTAGRAM_USER_ID`

## Setup do Airbnb

- **Matrícula do imóvel:** no nome da esposa
- **Conta Airbnb:** criada no perfil dela (titular = esposa)
  - CPF dela no perfil fiscal ("Impostos" → contribuinte)
  - Conta bancária dela como método de payout
  - Ela declara o aluguel no carnê-leão dela (ou na declaração conjunta do casal)
- **Francisco entra como co-anfitrião** — gerencia calendário, mensagens, check-in, mas não é titular fiscal
- **Por que assim:** alinhar matrícula + titular Airbnb + conta bancária no mesmo CPF evita
  descasamento fiscal (risco de interposta pessoa, doação disfarçada, autuação Receita).
  Decidido em 2026-06-07 após análise PF vs PJ.
- **`AIRBNB_ICAL_URL`:** gerado pelo login dela no Airbnb
  (Calendário → Disponibilidade → Sincronizar calendários → Exportar calendário)
- 🔲 **Próximo passo:** esposa cria a conta no Airbnb e adiciona Francisco como co-anfitrião

## Setup do Airbnb

- **Matrícula do imóvel:** no nome da esposa
- **Conta Airbnb:** criada no perfil dela (titular = esposa)
  - CPF dela no perfil fiscal ("Impostos" → contribuinte)
  - Conta bancária dela como método de payout
  - Ela declara o aluguel no carnê-leão dela (ou na declaração conjunta do casal)
- **Francisco entra como co-anfitrião** — gerencia calendário, mensagens, check-in, mas não é titular fiscal
- **Por que assim:** alinhar matrícula + titular Airbnb + conta bancária no mesmo CPF evita
  descasamento fiscal (risco de interposta pessoa, doação disfarçada, autuação Receita).
  Decidido em 2026-06-07 após análise PF vs PJ.
- **`AIRBNB_ICAL_URL`:** gerado pelo login dela no Airbnb
  (Calendário → Disponibilidade → Sincronizar calendários → Exportar calendário)
- 🔲 **Próximo passo:** esposa cria a conta no Airbnb e adiciona Francisco como co-anfitrião

## Estrutura dos arquivos principais

```
agents/
  planner.py        — gera 3 posts/mês via Claude, envia pro Telegram
  publisher.py      — publica post do dia no Instagram
  engagement.py     — lê comentários, classifica, responde ou faz handoff
  telegram_bot.py   — toda a comunicação Telegram com Francisco
  shared/
    claude.py       — cliente Anthropic com cache
    instagram.py    — wrapper Graph API
    airbnb.py       — leitura iCal
    state.py        — ler/escrever JSON + commitar

knowledge_base/
  casa.md           — EDITE AQUI para mudar info da casa (afeta todos os agentes)
  precos.md         — tabela de preços por temporada
  faq.md            — perguntas e respostas frequentes
```

## Secrets necessários no GitHub

| Secret | Descrição |
|---|---|
| `ANTHROPIC_API_KEY` | API key da Anthropic |
| `TELEGRAM_BOT_TOKEN` | Token do bot criado via @BotFather |
| `TELEGRAM_CHAT_ID` | Chat ID pessoal de Francisco |
| `INSTAGRAM_ACCESS_TOKEN` | Long-Lived Page Access Token (60 dias, renovado automaticamente) |
| `INSTAGRAM_USER_ID` | ID numérico do perfil IG da casa |
| `AIRBNB_ICAL_URL` | URL .ics do calendário do Airbnb |
| `META_APP_ID` | ID do app na Meta for Developers |
| `META_APP_SECRET` | Secret do app na Meta |
| `GH_PAT_FOR_SECRETS` | Personal Access Token do GitHub com permissão `secrets:write` |

## Como testar localmente

```bash
# Crie um .env com os secrets (nunca commite este arquivo!)
cp .env.example .env
# edite .env com seus valores

# Instale dependências
pip install -r requirements.txt

# Teste o Telegram
python agents/telegram_bot.py test

# Rode o planejador manualmente
python agents/planner.py

# Rode o monitor de comentários
python agents/engagement.py
```

## Para alterar o conteúdo dos posts

Edite os arquivos em `knowledge_base/` — são markdown simples, sem código.
As mudanças entram em vigor na próxima vez que o planejador rodar (dia 25).

## Importante — o que NUNCA fazer

- Nunca usar `instagrapi`, `instabot` ou qualquer lib que faz login com usuário/senha no IG
- Nunca commitar o `.env` ou qualquer arquivo com secrets
- Nunca confirmar reservas automaticamente — sempre passar para Francisco
