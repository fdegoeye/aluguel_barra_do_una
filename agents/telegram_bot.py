"""
Agente Telegram — envia mensagens e lê respostas de aprovação de Francisco.

Modos de uso:
  python telegram_bot.py send "Mensagem qualquer"
  python telegram_bot.py poll-approvals   # processa botões pressionados
  python telegram_bot.py notify-handoff <post_id> <comentario>
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
PHOTOS_DIR = Path(__file__).parent.parent / "assets" / "photos"


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id() -> str:
    return os.environ["TELEGRAM_CHAT_ID"]


def _api(method: str, **kwargs) -> dict:
    url = TELEGRAM_API.format(token=_token(), method=method)
    resp = requests.post(url, json=kwargs, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_message(text: str, reply_markup: dict | None = None) -> dict:
    """Envia uma mensagem de texto simples para Francisco."""
    payload = {"chat_id": _chat_id(), "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _api("sendMessage", **payload)


def send_photo(image_path_or_url: str, caption: str, reply_markup: dict | None = None) -> dict:
    """Envia uma foto com legenda para Francisco. Aceita caminho local ou URL."""
    token = _token()
    url = TELEGRAM_API.format(token=token, method="sendPhoto")
    data = {
        "chat_id": _chat_id(),
        "caption": caption,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    path = Path(image_path_or_url)
    if path.exists():
        with open(path, "rb") as f:
            resp = requests.post(url, data=data, files={"photo": f}, timeout=30)
    else:
        data["photo"] = image_path_or_url
        resp = requests.post(url, data=data, timeout=30)

    resp.raise_for_status()
    return resp.json()


def send_post_for_approval(post: dict, index: int, total: int) -> None:
    """Envia um post proposto para aprovação de Francisco."""
    caption = (
        f"*Post {index}/{total} — {post['scheduled_date']}*\n\n"
        f"{post['caption']}\n\n"
        f"🕐 Horário: {post['scheduled_time']}"
    )

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar", "callback_data": f"approve:{post['id']}"},
            {"text": "✏️ Editar legenda", "callback_data": f"edit:{post['id']}"},
            {"text": "❌ Rejeitar", "callback_data": f"reject:{post['id']}"},
        ]]
    }

    photo_path = PHOTOS_DIR / post["photo"]
    if photo_path.exists():
        send_photo(str(photo_path), caption, reply_markup=keyboard)
    else:
        caption += f"\n\n📷 Foto: `{post['photo']}` _(adicione à pasta assets/photos/)_"
        send_message(caption, reply_markup=keyboard)


def send_approval_summary(posts: list[dict]) -> None:
    """Envia resumo mensal com opção de aprovar todos de uma vez."""
    lines = [f"🏠 *Posts de {datetime.now().strftime('%B/%Y')} — Casa Barra do Una*\n"]
    for i, p in enumerate(posts, 1):
        lines.append(f"*{i}.* {p['scheduled_date']} — {p['caption'][:60]}...")

    lines.append("\nVocê pode aprovar um a um ou:")
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Aprovar todos", "callback_data": "approve:all"},
            {"text": "🔁 Ver um a um", "callback_data": "review:individual"},
        ]]
    }
    send_message("\n".join(lines), reply_markup=keyboard)


def send_handoff_alert(comment: dict, post_permalink: str, suggested_reply: str) -> None:
    """Alerta Francisco quando alguém tem intenção real de reservar."""
    text = (
        "🔔 *Alguém quer reservar!*\n\n"
        f"*Post:* {post_permalink}\n"
        f"*@{comment['username']} escreveu:*\n_{comment['text']}_\n\n"
        f"*Sugestão de resposta:*\n{suggested_reply}\n\n"
        "Responda diretamente no Instagram ou mande DM."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "📲 Abrir no Instagram", "url": post_permalink},
        ]]
    }
    send_message(text, reply_markup=keyboard)


def send_publish_confirmation(post: dict, permalink: str) -> None:
    """Confirma que um post foi publicado com sucesso."""
    text = (
        f"✅ *Post publicado!*\n\n"
        f"{post['caption'][:100]}...\n\n"
        f"[Ver no Instagram]({permalink})"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "📲 Reshare no meu Story", "url": permalink},
        ]]
    }
    send_message(text, reply_markup=keyboard)


def get_updates(offset: int = 0) -> list[dict]:
    """Busca atualizações do bot (respostas de botões)."""
    result = _api("getUpdates", offset=offset, timeout=10)
    return result.get("result", [])


def process_callback_updates(queue: list[dict]) -> list[dict]:
    """
    Processa botões pressionados por Francisco e atualiza o status dos posts na queue.
    Retorna a queue atualizada.
    """
    updates = get_updates()
    changed = False

    for update in updates:
        callback = update.get("callback_query")
        if not callback:
            continue

        data = callback.get("data", "")
        action, post_id = data.split(":", 1)

        if action == "approve" and post_id == "all":
            for post in queue:
                if post["status"] == "pending":
                    post["status"] = "approved"
            changed = True
            _api("answerCallbackQuery",
                 callback_query_id=callback["id"],
                 text="✅ Todos os posts aprovados!")

        elif action == "approve":
            for post in queue:
                if post["id"] == post_id:
                    post["status"] = "approved"
                    changed = True
            _api("answerCallbackQuery",
                 callback_query_id=callback["id"],
                 text="✅ Post aprovado!")

        elif action == "reject":
            for post in queue:
                if post["id"] == post_id:
                    post["status"] = "rejected"
                    changed = True
            _api("answerCallbackQuery",
                 callback_query_id=callback["id"],
                 text="❌ Post rejeitado.")

        elif action == "review":
            # Envia posts um a um para revisão individual
            pending = [p for p in queue if p["status"] == "pending"]
            for i, post in enumerate(pending, 1):
                send_post_for_approval(post, i, len(pending))
            _api("answerCallbackQuery",
                 callback_query_id=callback["id"],
                 text="Enviando posts para revisão...")

    return queue, changed


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "send":
        msg = sys.argv[2] if len(sys.argv) > 2 else "Teste do bot 🏠"
        result = send_message(msg)
        print(f"Mensagem enviada. Message ID: {result['result']['message_id']}")

    elif cmd == "poll-approvals":
        from shared import state
        queue = state.read("queue.json")
        if not isinstance(queue, list):
            queue = []
        updated_queue, changed = process_callback_updates(queue)
        if changed:
            state.write("queue.json", updated_queue)
            state.commit_and_push("agente: atualiza status de aprovação dos posts")
            print("Queue atualizada e commitada.")
        else:
            print("Nenhuma atualização de aprovação encontrada.")

    elif cmd == "test":
        send_message(
            "🏠 *Olá, Francisco!*\n\nSeu agente de aluguel está funcionando. "
            "Aqui você receberá:\n• Posts para aprovar\n• Alertas de interessados\n"
            "• Confirmações de publicação"
        )
        print("Mensagem de teste enviada!")

    else:
        print("Uso: python telegram_bot.py [send|poll-approvals|test]")
