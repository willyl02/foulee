"""Le logo de Foulée (carré brun, barre blanche, barre rouge), dessiné net à chaque taille.

Sert à l'icône près de l'horloge et au fichier Foulee.ico de l'installateur. Les
bords des barres tombent pile sur les pixels de la taille demandée : même en 16 × 16,
l'icône reste nette.
"""

from __future__ import annotations

from pathlib import Path

BROWN = (75, 62, 52, 255)
WHITE = (255, 255, 255, 255)
RED = (211, 38, 58, 255)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def draw(size: int):
    """Image Pillow (RGBA) du logo, de size × size pixels."""
    from PIL import Image, ImageDraw

    scale = 4  # dessin 4 fois plus grand, puis réduction : coins arrondis lissés
    unit = size / 512

    def snap(value: float) -> int:
        return round(value * unit)

    left, right = snap(96), snap(416)
    white_top, white_bottom = snap(150), snap(246)
    red_top, red_bottom = snap(266), snap(362)
    if red_top <= white_bottom:  # toutes petites tailles : garder un pixel entre les barres
        red_top = white_bottom + 1
        red_bottom = max(red_bottom, red_top + (white_bottom - white_top))
    picture = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    pen = ImageDraw.Draw(picture)
    pen.rounded_rectangle((0, 0, size * scale - 1, size * scale - 1), radius=max(2, round(112 * unit * scale)),
                          fill=BROWN)
    bar_radius = max(1, round(12 * unit * scale))
    for top, bottom, color in ((white_top, white_bottom, WHITE), (red_top, red_bottom, RED)):
        pen.rounded_rectangle((left * scale, top * scale, right * scale - 1, bottom * scale - 1),
                              radius=bar_radius, fill=color)
    return picture.resize((size, size), Image.Resampling.LANCZOS)


def write_ico(path: str | Path) -> Path:
    """Fichier .ico multi-tailles (raccourcis, programme, installateur)."""
    images = [draw(size) for size in ICO_SIZES]
    path = Path(path)
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=images[:-1])
    return path


if __name__ == "__main__":  # python -m foulee.icon Foulee.ico
    import sys

    print(write_ico(sys.argv[1] if len(sys.argv) > 1 else "Foulee.ico"))
