"""0.8.3 : la hauteur d'une tuile se règle de 1 à 8 rangées (3 au plus avant : les grandes tuiles étaient rabotées)."""

from foulee import views


def test_tile_heights_go_from_1_to_8_rows():
    spec = views.clean_spec({"tuiles": [{"type": "agenda", "w": 12, "h": 6}, {"type": "agenda", "w": 7, "h": 20},
                                        {"type": "agenda", "w": 12, "h": 0}]})
    assert [(t["w"], t["h"]) for t in spec["tuiles"]] == [(12, 6), (6, 8), (12, 5)]  # 0 : la taille par défaut
    assert views.TILE_INDEX["seance_analyse"]["taille"]["h"] <= views.MAX_H
