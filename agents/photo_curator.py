"""
Agente Curador de Fotos — seleciona e melhora fotos para cada post.

Fluxo:
  1. Cataloga todas as fotos usando Claude Vision (salva em data/photo_catalog.json)
  2. Para cada post, escolhe a foto mais adequada ao tema
  3. Recorta para 4:5 (formato Instagram), melhora brilho/contraste/cor
  4. Salva em assets/photos/enhanced/{post_id}.jpg
"""

import base64
import json
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

from shared.claude import get_client
from shared import state

PHOTOS_DIR = Path(__file__).parent.parent / "assets" / "photos"
ENHANCED_DIR = PHOTOS_DIR / "enhanced"
CATALOG_FILE = "photo_catalog.json"


def _encode(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _media_type(path: Path) -> str:
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")


def _list_originals() -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return [f for f in PHOTOS_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in exts and f.parent == PHOTOS_DIR]


def catalog_photos() -> dict:
    """
    Analisa fotos novas com Claude Vision e atualiza o catálogo.
    Fotos já catalogadas são ignoradas (sem custo extra).
    """
    catalog = state.read(CATALOG_FILE)
    if not isinstance(catalog, dict):
        catalog = {}

    client = get_client()
    updated = False

    for photo in _list_originals():
        if photo.name in catalog:
            continue

        print(f"  Catalogando {photo.name}...")
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": _media_type(photo),
                                "data": _encode(photo),
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Descreva esta foto em uma linha.\n"
                                "Responda em JSON:\n"
                                '{"subjects": ["item1", "item2"], "suitable": true, "description": "..."}\n'
                                "suitable=false se mostrar banheiro, área de serviço, foto desfocada ou sem interesse turístico."
                            ),
                        },
                    ],
                }],
            )
            text = resp.content[0].text
            data = json.loads(text[text.find("{"):text.rfind("}") + 1])
            catalog[photo.name] = data
            updated = True
        except Exception as e:
            print(f"  Aviso: não foi possível catalogar {photo.name}: {e}")
            catalog[photo.name] = {"subjects": [], "suitable": True, "description": ""}

    if updated:
        state.write(CATALOG_FILE, catalog)

    return catalog


def select_best_photo(caption: str, theme: str, catalog: dict) -> str:
    """Usa o Claude para escolher a foto mais adequada ao post."""
    suitable = {
        name: info for name, info in catalog.items()
        if info.get("suitable", True) and (PHOTOS_DIR / name).exists()
    }
    if not suitable:
        return ""

    photo_list = [{"name": n, "description": i.get("description", "")}
                  for n, i in suitable.items()]

    client = get_client()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=80,
        messages=[{
            "role": "user",
            "content": (
                f"Escolha a melhor foto para este post do Instagram.\n\n"
                f"TEMA: {theme}\n"
                f"LEGENDA: {caption[:300]}\n\n"
                f"FOTOS DISPONÍVEIS:\n{json.dumps(photo_list, ensure_ascii=False)}\n\n"
                "Prefira: praia, piscina, pôr do sol, área externa, vista do mar, churrasqueira, deck.\n"
                "Evite: banheiro, área de serviço, interiores sem destaque visual.\n\n"
                "Responda APENAS com o nome do arquivo escolhido."
            ),
        }],
    )

    chosen = resp.content[0].text.strip().strip('"').strip("'")
    if chosen in suitable:
        return chosen
    return next(iter(suitable.keys()))


def enhance_photo(photo_name: str, post_id: str) -> str:
    """
    Recorta para 4:5, melhora brilho/contraste/saturação e salva em enhanced/.
    Retorna o caminho absoluto da foto melhorada.
    """
    ENHANCED_DIR.mkdir(parents=True, exist_ok=True)
    source = PHOTOS_DIR / photo_name
    output = ENHANCED_DIR / f"{post_id}.jpg"

    if not source.exists():
        return ""

    with Image.open(source) as img:
        # Corrige rotação baseada nos dados EXIF (resolve fotos tiradas na vertical)
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Recorte central para proporção 4:5 (ideal para Instagram)
        w, h = img.size
        target_ratio = 4 / 5
        if (w / h) > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))

        # Resolução padrão Instagram (1080×1350)
        img = img.resize((1080, 1350), Image.LANCZOS)

        # Melhorias sutis
        img = ImageEnhance.Brightness(img).enhance(1.05)
        img = ImageEnhance.Contrast(img).enhance(1.08)
        img = ImageEnhance.Color(img).enhance(1.06)

        img.save(output, "JPEG", quality=92, optimize=True)

    return str(output)


def create_story_image(photo_name: str, post_id: str, cta_text: str) -> Path:
    """
    Cria imagem 9:16 para Story com texto CTA sobreposto.
    Salva em assets/photos/stories/{post_id}.jpg e retorna o caminho.
    """
    from PIL import ImageDraw, ImageFont

    stories_dir = PHOTOS_DIR / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)
    output = stories_dir / f"{post_id}.jpg"

    source = PHOTOS_DIR / photo_name
    if not source.exists():
        return output

    W, H = 1080, 1920

    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img).convert("RGBA")

        # Escala para preencher a largura
        scale = W / img.width
        new_h = int(img.height * scale)
        img = img.resize((W, new_h), Image.LANCZOS)

        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        y_offset = (H - new_h) // 2 if new_h < H else -((new_h - H) // 2)
        canvas.paste(img, (0, y_offset))

    # Faixa escura semitransparente na base para o texto ficar legível
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([(0, H - 500), (W, H)], fill=(0, 0, 0, 190))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)

    try:
        font_cta = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        font_handle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 56)
    except Exception:
        font_cta = ImageFont.load_default(size=80)
        font_handle = ImageFont.load_default(size=56)

    # CTA em branco
    draw.text((W // 2, H - 320), cta_text, font=font_cta, fill=(255, 255, 255, 255), anchor="mm", align="center")
    # Menção ao perfil da casa
    draw.text((W // 2, H - 190), "@nossa_casa_no_una", font=font_handle, fill=(210, 210, 210, 255), anchor="mm")

    canvas.convert("RGB").save(str(output), "JPEG", quality=92, optimize=True)
    print(f"  Story image criada: {output}")
    return output


def process_post(post: dict) -> dict:
    """Seleciona e melhora a foto para um post. Retorna o post atualizado."""
    print(f"  Processando foto para post {post['id']} ({post.get('theme', '')})...")
    catalog = catalog_photos()
    best = select_best_photo(post["caption"], post.get("theme", ""), catalog)
    if not best:
        return post
    enhanced = enhance_photo(best, post["id"])
    return {**post, "photo": best, "photo_enhanced": enhanced}
