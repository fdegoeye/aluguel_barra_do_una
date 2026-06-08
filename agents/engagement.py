"""
Agente de Engajamento — lê comentários, classifica e responde automaticamente.

Roda a cada 15 minutos via GitHub Actions.
Classifica cada comentário em: simples | disponibilidade | handoff | spam
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.claude import ask, load_knowledge_base
from shared.instagram import get_recent_posts, get_comments, reply_to_comment
from shared.airbnb import is_available, next_available_windows
from shared import state
from telegram_bot import send_handoff_alert, send_message

SYSTEM_PROMPT_BASE = """Você é o assistente virtual da Casa Barra do Una, uma casa de temporada no litoral norte de SP.
Seu trabalho é responder comentários do Instagram de forma calorosa, útil e natural — como a própria dona da casa.

Regras importantes:
- Seja breve nos comentários (máx. 3 linhas) — Instagram não é lugar de texto longo
- Sempre assine como "Casa Barra do Una" ou use "nós" (nunca "eu, robô" ou "agente")
- Se não souber a resposta exata, diga para mandar DM ou perguntar no privado
- Nunca confirme uma reserva — apenas direcione para o WhatsApp/DM

BASE DE CONHECIMENTO:
{knowledge}"""


def already_replied(comment_id: str, conversations: list[dict]) -> bool:
    """Verifica se já respondemos este comentário antes."""
    return any(c.get("comment_id") == comment_id for c in conversations)


def classify_and_respond(comment: dict, knowledge: str, available_windows: list[dict]) -> dict:
    """
    Usa Claude para classificar o comentário e gerar resposta.
    Retorna dict com: classification, reply, suggested_handoff_reply
    """
    system = SYSTEM_PROMPT_BASE.format(knowledge=knowledge)

    user_msg = f"""Analise este comentário do Instagram da Casa Barra do Una:

Comentário de @{comment['username']}: "{comment['text']}"

Janelas disponíveis no calendário (próximos 90 dias):
{json.dumps(available_windows[:5], ensure_ascii=False)}

Classifique em UMA das categorias e responda em JSON:
{{
  "classification": "simples|disponibilidade|handoff|spam",
  "confidence": 0.0 a 1.0,
  "reply": "Texto da resposta pública (máx 3 linhas, ou null se spam/handoff)",
  "reason": "Por que essa classificação",
  "handoff_summary": "Resumo do interesse para Francisco (apenas se handoff, senão null)"
}}

Categorias:
- "simples": pergunta sobre comodidades, localização, regras, elogio — responde direto
- "disponibilidade": pergunta sobre datas específicas — verifique a agenda e responda
- "handoff": intenção clara de reservar (menciona família, datas concretas, perguntas sobre pagamento) — NÃO responda, avise Francisco
- "spam": comentário irrelevante, bot, promoção — ignore"""

    response = ask(system, user_msg, use_cache=True)
    start = response.find("{")
    end = response.rfind("}") + 1
    return json.loads(response[start:end])


def generate_suggested_reply(comment: dict, knowledge: str) -> str:
    """Gera sugestão de resposta para Francisco usar no handoff."""
    system = SYSTEM_PROMPT_BASE.format(knowledge=knowledge)
    msg = f"""@{comment['username']} quer saber mais sobre reserva: "{comment['text']}"

    Escreva uma resposta CURTA (2-3 linhas) que Francisco pode usar para iniciar a conversa.
    Tom: pessoal e acolhedor, como se Francisco fosse responder diretamente."""
    return ask(system, msg, use_cache=True)


def run():
    knowledge = load_knowledge_base()
    available_windows = next_available_windows(days_ahead=90)
    conversations = state.read("conversations.json")
    if not isinstance(conversations, list):
        conversations = []

    posts = get_recent_posts(limit=5)
    new_replies = 0
    handoffs = 0

    for post in posts:
        comments = get_comments(post["id"])

        for comment in comments:
            comment_id = comment["id"]

            if already_replied(comment_id, conversations):
                continue

            print(f"Processando comentário de @{comment['username']}: {comment['text'][:50]}...")

            result = classify_and_respond(comment, knowledge, available_windows)
            classification = result.get("classification", "spam")

            log_entry = {
                "comment_id": comment_id,
                "post_id": post["id"],
                "username": comment["username"],
                "text": comment["text"],
                "classification": classification,
                "timestamp": datetime.now().isoformat(),
                "replied": False,
                "handoff": False,
            }

            if classification == "spam":
                print(f"  → Spam, ignorando.")

            elif classification == "handoff":
                suggested = generate_suggested_reply(comment, knowledge)
                send_handoff_alert(
                    comment=comment,
                    post_permalink=post.get("permalink", "https://instagram.com"),
                    suggested_reply=suggested,
                )
                log_entry["handoff"] = True
                log_entry["suggested_reply"] = suggested
                handoffs += 1
                print(f"  → Handoff enviado para Francisco no Telegram.")

            elif classification in ("simples", "disponibilidade"):
                reply_text = result.get("reply")
                if reply_text:
                    reply_to_comment(comment_id, reply_text)
                    log_entry["replied"] = True
                    log_entry["reply_text"] = reply_text
                    new_replies += 1
                    print(f"  → Respondido: {reply_text[:60]}...")

            conversations.append(log_entry)

    if new_replies > 0 or handoffs > 0:
        state.write("conversations.json", conversations)
        state.commit_and_push(
            f"agente: {new_replies} respostas + {handoffs} handoffs"
        )

    print(f"Resumo: {new_replies} respostas automáticas, {handoffs} handoffs para Francisco.")


if __name__ == "__main__":
    run()
