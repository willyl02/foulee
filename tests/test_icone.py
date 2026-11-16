"""Le logo fixe de Foulée (« Balise F ») : net à chaque taille, et des icônes de téléphone sans transparence."""

from PIL import Image

from foulee import icon


def test_logo_at_every_size():
    for size in icon.ICO_SIZES:
        image = icon.draw(size)
        assert image.size == (size, size) and image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] < 255  # coins arrondis
        assert image.getpixel((size // 2, size // 2))[3] == 255


def test_phone_icons(tmp_path):
    written = {p.name: p for p in icon.write_png_icons(tmp_path)}
    assert set(written) == set(icon.PNG_ICONS)
    for name, (size, full_bleed, _) in icon.PNG_ICONS.items():
        image = Image.open(written[name])
        assert image.size == (size, size)
        if full_bleed:  # Android et l'iPhone découpent eux-mêmes : fond plein jusqu'aux bords
            assert image.mode == "RGB" and image.getpixel((0, 0)) == icon.DARK[:3]


def test_ico_file(tmp_path):
    path = icon.write_ico(tmp_path / "Foulee.ico")
    assert path.read_bytes()[:4] == b"\x00\x00\x01\x00"
