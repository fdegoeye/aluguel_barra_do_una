"""
Agente Planejador — cria 3 posts para o próximo mês e envia para aprovação no Telegram.

Roda uma vez por mês (dia 25) via GitHub Actions.
"""

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.claude import ask, load_knowledge_base
from shared.airbnb import next_available_windows
from shared import state
from telegram_bot import send_approval_summary, send_post_for_approval, send_message
from photo_curator import process_post


PHOTOS_DIR = Path(__file__).parent.parent / "assets" / "photos"
POSTS_PER_MONTH = int(os.environ.get("POSTS_PER_MONTH", "3"))
INTERVAL_DAYS = 10  # 1 post a cada 10 dias


def list_available_photos() -> list[str]:
    """Lista fotos disponíveis no acervo."""
    if not PHOTOS_DIR.exists():
        return []
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    return [f.name for f in PHOTOS_DIR.iterdir() if f.suffix.lower() in extensions]


def get_posted_captions() -> list[str]:
    """Retorna as últimas legendas publicadas para evitar repetição."""
    posted = state.read("posted.json")
    return [p.get("caption", "")[:100] for p in posted[-10:]]


def build_system_prompt(knowledge: str, photos: list[str], available_windows: list[dict]) -> str:
    return f"""Você é um especialista em marketing de aluguel de temporada no Brasil.
Cria posts para o Instagram de uma casa em Barra do Una (litoral norte de SP).

OBJETIVO: converter seguidores em hóspedes. Cada post deve gerar desejo e ter um CTA claro.

REGRAS DE ESCRITA:
- Português brasileiro correto, sem erros ortográficos ou gramaticais
- Texto curto e direto: máximo 150 palavras na legenda (sem contar hashtags)
- Tom natural, como uma pessoa escrevendo — não marketing corporativo
- Proibido: "incrível", "perfeito", "paraíso", "sonho", "maravilhoso", adjetivos vagos
- Use detalhes concretos e específicos da casa e da região
- NUNCA mencione preços na legenda — quem quiser saber o valor manda DM
- Sempre termine com um CTA objetivo: "Quer saber mais? Chama aqui." ou "Manda uma DM com as datas."
- Revise toda a legenda antes de entregar para garantir que não há erros de português

BASE DE CONHECIMENTO DA CASA:
{knowledge}

FOTOS DISPONÍVEIS NO ACERVO:
{json.dumps(photos, ensure_ascii=False)}

JANELAS DISPONÍVEIS NO CALENDÁRIO (próximos 90 dias):
{json.dumps(available_windows, ensure_ascii=False)}

Responda SEMPRE em JSON válido, exatamente no formato pedido."""


def generate_posts(next_month_start: date) -> list[dict]:
    """Usa Claude para criar 3 posts para o mês."""
    knowledge = load_knowledge_base()
    photos = list_available_photos()
    available_windows = next_available_windows(days_ahead=90)
    posted_captions = get_posted_captions()

    system_prompt = build_system_prompt(knowledge, photos, available_windows)

    # Mês que queremos alugar = mês seguinte ao dos posts
    if next_month_start.month == 12:
        rental_month = date(next_month_start.year + 1, 1, 1)
    else:
        rental_month = date(next_month_start.year, next_month_start.month + 1, 1)
    rental_month_name = rental_month.strftime("%B/%Y")

    user_message = f"""Crie exatamente {POSTS_PER_MONTH} posts para publicar em {next_month_start.strftime('%B/%Y')}.

OBJETIVO DESTE MÊS: atrair hóspedes para alugar a casa em {rental_month_name}.
Todos os posts devem criar desejo e urgência em torno de {rental_month_name}.
Use frases como "Julho ainda sem planos?", "Férias em julho na praia?", "Vagas limitadas para julho."
Mencione que julho é alta temporada no litoral norte de SP — quem deixa para última hora não encontra.

Posts anteriores (evite repetir os mesmos temas):
{json.dumps(posted_captions, ensure_ascii=False)}

Distribua as datas com intervalo de {INTERVAL_DAYS} dias a partir de {next_month_start.isoformat()}.
Horário sugerido: entre 09:00 e 19:00, preferencialmente 10:00, 14:00 ou 18:00.

Para cada post, responda em JSON com este formato:
{{
  "posts": [
    {{
      "caption": "Legenda com hashtags no final (máximo 150 palavras + hashtags)",
      "photo": "nome_do_arquivo_da_foto.jpg",
      "scheduled_date": "YYYY-MM-DD",
      "scheduled_time": "HH:MM",
      "theme": "Tema do post (ex: urgência julho, estrutura da casa, localização)"
    }}
  ]
}}

Regras:
- Varie os temas entre os posts mas mantenha o foco em converter para {rental_month_name}
- Inclua 5-8 hashtags relevantes no final de cada legenda
- Use a foto mais adequada para o tema (considere o nome do arquivo como dica)
- Se não houver fotos, use "placeholder.jpg"
- Termine sempre com um CTA claro: "Chama aqui.", "Link na bio.", "Datas disponíveis? Me chama."
- A legenda deve parecer escrita por uma pessoa, não por um robô"""

    response = ask(system_prompt, user_message, use_cache=True)

    # Extrai o JSON da resposta (o Claude pode adicionar texto antes/depois)
    start = response.find("{")
    end = response.rfind("}") + 1
    data = json.loads(response[start:end])

    posts = []
    for p in data["posts"]:
        posts.append({
            "id": str(uuid.uuid4())[:8],
            "caption": p["caption"],
            "photo": p["photo"],
            "scheduled_date": p["scheduled_date"],
            "scheduled_time": p["scheduled_time"],
            "theme": p.get("theme", ""),
            "status": "pending",  # pending → approved → published
            "created_at": date.today().isoformat(),
        })
    return posts


def run():
    today = date.today()
    # Permite sobrescrever o mês alvo via variável de ambiente (formato: YYYY-MM)
    target_month_env = os.environ.get("TARGET_MONTH", "")
    if target_month_env:
        year, month = map(int, target_month_env.split("-"))
        next_month_start = date(year, month, 1)
    elif today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
    else:
        next_month_start = date(today.year, today.month + 1, 1)

    print(f"Gerando posts para {next_month_start.strftime('%B/%Y')}...")

    # Remove posts pendentes antigos (não aprovados do mês anterior)
    queue = state.read("queue.json")
    if not isinstance(queue, list):
        queue = []
    queue = [p for p in queue if p.get("status") == "approved"]

    # Gera novos posts e processa fotos
    new_posts = generate_posts(next_month_start)
    print("Selecionando e melhorando fotos...")
    new_posts = [process_post(p) for p in new_posts]
    queue.extend(new_posts)

    state.write("queue.json", queue)
    state.commit_and_push(f"agente: planeja posts para {next_month_start.strftime('%B/%Y')}")

    # Envia para aprovação no Telegram
    send_message(f"🏠 *Posts de {next_month_start.strftime('%B/%Y')} prontos para aprovação!*\n\nGerei {len(new_posts)} posts. Veja abaixo:")
    send_approval_summary(new_posts)
    for i, post in enumerate(new_posts, 1):
        send_post_for_approval(post, i, len(new_posts))

    print(f"{len(new_posts)} posts enviados para aprovação no Telegram.")


if __name__ == "__main__":
    run()
