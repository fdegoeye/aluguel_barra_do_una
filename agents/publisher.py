"""
Agente Publicador — verifica a queue diariamente e publica o post do dia no Instagram.

Roda todos os dias às 08:00 (BRT) via GitHub Actions.
"""

import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

from shared import state
from shared.instagram import publish_photo, post_story
from telegram_bot import send_publish_confirmation, send_message

# URL base pública das fotos no GitHub (substitua pelo seu usuário/repo)
GITHUB_RAW_BASE = os.environ.get(
    "GITHUB_RAW_BASE",
    "https://raw.githubusercontent.com/SEU_USUARIO/aluguel-barra-do-una/main/assets/photos"
)


def get_todays_post(queue: list[dict]) -> dict | None:
    """Encontra o post aprovado agendado para hoje."""
    today = date.today().isoformat()
    for post in queue:
        if post.get("status") == "approved" and post.get("scheduled_date") == today:
            return post
    return None


def run():
    queue = state.read("queue.json")
    if not isinstance(queue, list):
        queue = []

    post = get_todays_post(queue)

    if not post:
        print("Nenhum post agendado para hoje.")
        return

    print(f"Publicando post: {post['id']} — {post['theme']}")

    photo_url = f"{GITHUB_RAW_BASE}/{quote(post['photo'])}"
    print(f"URL da foto: {photo_url}")

    try:
        media_id = publish_photo(image_url=photo_url, caption=post["caption"])
        print(f"Post publicado! Media ID: {media_id}")

        # Atualiza o status na queue
        for p in queue:
            if p["id"] == post["id"]:
                p["status"] = "published"
                p["published_at"] = date.today().isoformat()
                p["media_id"] = media_id
                break

        state.write("queue.json", queue)

        # Move para o histórico
        posted = state.read("posted.json")
        if not isinstance(posted, list):
            posted = []
        posted.append({**post, "status": "published", "media_id": media_id})
        state.write("posted.json", posted)

        state.commit_and_push(f"agente: publica post {post['id']} ({post['theme']})")

        # Repost automático no Story pessoal de Francisco (@kikodegoeye)
        personal_token = os.environ.get("PERSONAL_INSTAGRAM_ACCESS_TOKEN", "")
        personal_user_id = os.environ.get("PERSONAL_INSTAGRAM_USER_ID", "")
        if personal_token and personal_user_id:
            try:
                story_id = post_story(photo_url, personal_token, personal_user_id)
                print(f"Story publicado no @kikodegoeye! ID: {story_id}")
            except Exception as story_err:
                print(f"Aviso: não foi possível postar Story pessoal: {story_err}")

        # Notifica Francisco
        permalink = f"https://www.instagram.com/p/{media_id}/"
        send_publish_confirmation(post, permalink)

    except Exception as e:
        error_msg = f"❌ *Erro ao publicar post* `{post['id']}`\n\nErro: `{str(e)}`\n\nPublique manualmente se necessário."
        send_message(error_msg)
        print(f"Erro ao publicar: {e}")
        raise


if __name__ == "__main__":
    run()
