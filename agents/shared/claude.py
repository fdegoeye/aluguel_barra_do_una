"""Cliente Anthropic com prompt caching para baratear chamadas repetidas."""

import os
import anthropic

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def load_knowledge_base() -> str:
    """Carrega os 3 arquivos da base de conhecimento em uma string única."""
    base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base")
    parts = []
    for filename in ("casa.md", "precos.md", "faq.md"):
        path = os.path.join(base_dir, filename)
        with open(path, encoding="utf-8") as f:
            parts.append(f"## {filename}\n\n{f.read()}")
    return "\n\n---\n\n".join(parts)


def ask(system_prompt: str, user_message: str, use_cache: bool = True) -> str:
    """
    Envia uma pergunta ao Claude e retorna a resposta em texto.

    use_cache=True marca o system_prompt para cache — reduz custo em ~90%
    quando o mesmo system_prompt é reutilizado várias vezes seguidas.
    """
    client = get_client()

    system = [{"type": "text", "text": system_prompt}]
    if use_cache:
        system[0]["cache_control"] = {"type": "ephemeral"}

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
