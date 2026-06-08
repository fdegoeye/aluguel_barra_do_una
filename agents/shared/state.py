"""Leitura e escrita do estado persistido em arquivos JSON no repositório."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data"


def read(filename: str) -> list | dict:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(filename: str, data: list | dict) -> None:
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def commit_and_push(message: str) -> None:
    """
    Commita e faz push das mudanças nos arquivos data/*.json.
    Chamado pelos agentes após atualizar o estado.
    Só funciona no ambiente do GitHub Actions (git configurado automaticamente).
    """
    try:
        subprocess.run(
            ["git", "config", "user.email", "agente@barra-do-una.bot"],
            check=True, cwd=ROOT,
        )
        subprocess.run(
            ["git", "config", "user.name", "Agente Barra do Una"],
            check=True, cwd=ROOT,
        )
        subprocess.run(
            ["git", "add", "data/"],
            check=True, cwd=ROOT,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=ROOT,
        )
        if result.returncode != 0:  # há mudanças staged
            subprocess.run(
                ["git", "commit", "-m", message],
                check=True, cwd=ROOT,
            )
            subprocess.run(
                ["git", "push"],
                check=True, cwd=ROOT,
            )
    except subprocess.CalledProcessError as e:
        print(f"Aviso: não foi possível commitar estado: {e}")
