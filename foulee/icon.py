"""Le logo de Foulée, « Balise F » : un F dessiné avec les deux traits de la balise des sentiers,
blanc en haut, rouge au milieu, sur un carré sombre. Dessiné net à chaque taille.

C'est le logo fixe de l'application : icône près de l'horloge, Foulee.ico de l'installateur
(programme, raccourcis, barre des tâches), icônes de l'appli sur le téléphone (PNG du manifeste)
et, côté navigateur, l'icône de l'onglet et de la fenêtre (le même dessin en SVG, dans
static/js/logos.js). Les bords tombent pile sur les pixels : même en 16 × 16, le F reste net.

    python -m foulee.icon Foulee.ico          # l'icône Windows multi-tailles
    python -m foulee.icon --png foulee/static/icons   # les PNG du manifeste et de l'iPhone
    python -m foulee.icon --iconset Foulee.iconset    # l'icône Mac (puis : iconutil -c icns Foulee.iconset)
"""

from __future__ import annotations

from pathlib import Path

DARK = (24, 32, 32, 255)  # #182020
WHITE = (255, 255, 255, 255)
RED = (211, 38, 58, 255)  # #d3263a
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

# Le dessin, sur une grille de 512 (le SVG de logos.js est le même sur une grille de 32, × 16)
STEM = (128, 96, 216, 416)  # jambe du F, blanche
TOP = (128, 96, 392, 184)  # barre du haut, blanche
MIDDLE = (128, 232, 328, 320)  # barre du milieu, rouge (par-dessus la jambe)
# nom : (taille, fond jusqu'aux bords, taille du F) ; Android découpe l'icône « maskable » en cercle
PNG_ICONS = {"icon-192.png": (192, False, 1.0), "icon-512.png": (512, False, 1.0),
             "icon-maskable-512.png": (512, True, 0.72), "apple-touch-icon.png": (180, True, 0.86)}


def draw(size: int, full_bleed: bool = False, shrink: float | None = None):
    """Image Pillow (RGBA) du logo, de size × size pixels.

    full_bleed : fond carré jusqu'aux bords et F réduit au centre (shrink), pour les icônes que le
    téléphone découpe lui-même (icône « maskable » d'Android, icône de l'iPhone).
    """
    from PIL import Image, ImageDraw

    scale = 4  # dessin 4 fois plus grand, puis réduction : coins arrondis lissés
    if shrink is None:
        shrink = 0.72 if full_bleed else 1.0  # zone sûre d'Android : le cercle central de 80 %
    unit = size / 512

    def snap(value: float) -> int:
        return round((256 + (value - 256) * shrink) * unit)

    def box(rect):
        x0, y0, x1, y1 = (snap(v) for v in rect)
        return x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)

    stem, top, middle = box(STEM), box(TOP), box(MIDDLE)
    if middle[1] <= top[3]:  # toutes petites tailles : garder un pixel sombre entre les deux barres
        middle = (middle[0], top[3] + 1, middle[2], max(middle[3], top[3] + 1 + (top[3] - top[1])))
    picture = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    pen = ImageDraw.Draw(picture)
    corner = 0 if full_bleed else max(2, round(112 * unit * scale))
    pen.rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius=corner, fill=DARK)
    bar_radius = max(1, round(19 * unit * shrink * scale))
    for (x0, y0, x1, y1), color in ((stem, WHITE), (top, WHITE), (middle, RED)):
        pen.rounded_rectangle((x0 * scale, y0 * scale, x1 * scale - 1, y1 * scale - 1), radius=bar_radius, fill=color)
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def write_ico(path: str | Path) -> Path:
    """Fichier .ico multi-tailles (raccourcis, programme, installateur)."""
    images = [draw(size) for size in ICO_SIZES]
    path = Path(path)
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=images[:-1])
    return path


def write_png_icons(folder: str | Path) -> list[Path]:
    """Les icônes PNG de l'appli sur le téléphone (manifeste, iPhone), sans transparence quand il le faut."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (size, full_bleed, shrink) in PNG_ICONS.items():
        image = draw(size, full_bleed, shrink)
        if full_bleed:  # l'iPhone et Android remplissent la transparence de noir ou de blanc : fond plein
            image = image.convert("RGB")
        path = folder / name
        image.save(path, format="PNG", optimize=True)
        written.append(path)
    return written


def write_iconset(folder: str | Path) -> Path:
    """Le dossier .iconset de l'application Mac (iconutil en fait Foulee.icns). Les icônes du Mac remplissent un
    carré arrondi un peu plus petit que l'image : on laisse la marge habituelle."""
    from PIL import Image

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size * scale
            inner = round(pixels * 0.8)
            canvas = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
            logo = draw(inner)
            canvas.paste(logo, ((pixels - inner) // 2, (pixels - inner) // 2), logo)
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            canvas.save(folder / name, format="PNG")
    return folder


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if args[:1] == ["--iconset"]:
        print(write_iconset(args[1] if len(args) > 1 else "Foulee.iconset"))
    elif args[:1] == ["--png"]:
        for written in write_png_icons(args[1] if len(args) > 1 else "foulee/static/icons"):
            print(written)
    else:
        print(write_ico(args[0] if args else "Foulee.ico"))
