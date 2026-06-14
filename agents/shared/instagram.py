"""
Wrapper da nova Instagram Graph API (graph.instagram.com).

Usa a API moderna do Instagram (2024+) com tokens de usuário Instagram,
NÃO a API antiga via Página do Facebook.

Token obtido via: Meta for Developers → Agente Barra do Una-IG →
  Casos de uso → Configuração da API com login do Instagram → Adicionar conta
"""

import os
import time
import requests

GRAPH_URL = "https://graph.instagram.com/v21.0"


def _token() -> str:
    return os.environ["INSTAGRAM_ACCESS_TOKEN"]


def _ig_user_id() -> str:
    return os.environ["INSTAGRAM_USER_ID"]


def get_user_info() -> dict:
    """Retorna id e username da conta conectada. Útil para verificar se o token está válido."""
    url = f"{GRAPH_URL}/me"
    params = {"fields": "id,username", "access_token": _token()}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_recent_posts(limit: int = 10) -> list[dict]:
    """Retorna os posts mais recentes da conta."""
    url = f"{GRAPH_URL}/{_ig_user_id()}/media"
    params = {
        "fields": "id,caption,permalink,timestamp,comments_count",
        "limit": limit,
        "access_token": _token(),
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_comments(media_id: str) -> list[dict]:
    """Retorna comentários de um post específico."""
    url = f"{GRAPH_URL}/{media_id}/comments"
    params = {
        "fields": "id,text,username,timestamp,replies{id,text,username,timestamp}",
        "access_token": _token(),
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def reply_to_comment(comment_id: str, message: str) -> dict:
    """Posta uma resposta a um comentário."""
    url = f"{GRAPH_URL}/{comment_id}/replies"
    data = {"message": message, "access_token": _token()}
    resp = requests.post(url, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def publish_photo(image_url: str, caption: str) -> str:
    """
    Publica uma foto no Instagram. Retorna o ID do post publicado.

    A imagem precisa ser uma URL pública.
    Usamos o raw URL do GitHub (assets/photos/ no repo).
    """
    ig_id = _ig_user_id()

    # Passo 1: criar container de mídia
    container_url = f"{GRAPH_URL}/{ig_id}/media"
    container_data = {
        "image_url": image_url,
        "caption": caption,
        "access_token": _token(),
    }
    resp = requests.post(container_url, data=container_data, timeout=30)
    if not resp.ok:
        print(f"Erro Instagram API (criar container): {resp.status_code} — {resp.text}")
    resp.raise_for_status()
    creation_id = resp.json()["id"]
    print(f"Container criado: {creation_id}")

    # Passo 1b: aguarda o Instagram processar a imagem (máx 30s)
    for attempt in range(10):
        status_resp = requests.get(
            f"{GRAPH_URL}/{creation_id}",
            params={"fields": "status_code", "access_token": _token()},
            timeout=30,
        )
        status = status_resp.json().get("status_code", "IN_PROGRESS")
        print(f"Status do container ({attempt + 1}/10): {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise Exception(f"Instagram recusou a imagem: {status_resp.text}")
        time.sleep(3)

    # Passo 2: publicar o container
    publish_url = f"{GRAPH_URL}/{ig_id}/media_publish"
    publish_data = {"creation_id": creation_id, "access_token": _token()}
    resp = requests.post(publish_url, data=publish_data, timeout=30)
    if not resp.ok:
        print(f"Erro Instagram API (publicar): {resp.status_code} — {resp.text}")
    resp.raise_for_status()
    media_id = resp.json()["id"]

    # Busca o permalink real (o ID numérico não funciona como URL do Instagram)
    permalink_resp = requests.get(
        f"{GRAPH_URL}/{media_id}",
        params={"fields": "permalink", "access_token": _token()},
        timeout=30,
    )
    permalink = permalink_resp.json().get("permalink", "") if permalink_resp.ok else ""
    print(f"Permalink: {permalink}")

    return media_id, permalink


def post_story(image_url: str, personal_token: str, personal_user_id: str) -> str:
    """
    Publica uma imagem no Story do Instagram pessoal de Francisco (@kikodegoeye).
    Retorna o ID do Story publicado.
    """
    # Passo 1: criar container de Story
    container_resp = requests.post(
        f"{GRAPH_URL}/{personal_user_id}/media",
        data={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": personal_token,
        },
        timeout=30,
    )
    if not container_resp.ok:
        print(f"Erro ao criar Story (container): {container_resp.status_code} — {container_resp.text}")
    container_resp.raise_for_status()
    creation_id = container_resp.json()["id"]

    # Passo 2: aguarda processamento
    for attempt in range(10):
        status_resp = requests.get(
            f"{GRAPH_URL}/{creation_id}",
            params={"fields": "status_code", "access_token": personal_token},
            timeout=30,
        )
        status = status_resp.json().get("status_code", "IN_PROGRESS")
        print(f"Status Story ({attempt + 1}/10): {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise Exception(f"Instagram recusou o Story: {status_resp.text}")
        time.sleep(3)

    # Passo 3: publicar
    publish_resp = requests.post(
        f"{GRAPH_URL}/{personal_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": personal_token},
        timeout=30,
    )
    if not publish_resp.ok:
        print(f"Erro ao publicar Story: {publish_resp.status_code} — {publish_resp.text}")
    publish_resp.raise_for_status()
    return publish_resp.json()["id"]


def refresh_token() -> str:
    """
    Renova o token de acesso antes de expirar (validade: 60 dias).
    A nova API do Instagram usa grant_type=ig_refresh_token.
    Chame este endpoint a cada 30 dias via workflow dedicado.
    """
    url = f"{GRAPH_URL}/refresh_access_token"
    params = {
        "grant_type": "ig_refresh_token",
        "access_token": _token(),
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]
