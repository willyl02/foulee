"""0.8.2 : correctifs relevés par William et Jason (objectif par défaut, profils lus sans mise à niveau…)."""

import json

from foulee import __version__, analysis, db, views


def test_a_new_install_has_no_objective():
    with db.session() as conn:
        settings = db.get_settings(conn)
    assert not settings["objectif"]["nom"] and not settings["objectif"]["date"]
    assert "jours_restants" not in analysis.objective(settings)


def test_a_saved_objective_stays_and_the_old_default_is_gone():
    with db.session() as conn:  # une base d'avant la 0.8.2 : rien de saisi, on y voyait le semi de Paris
        assert not db.get_settings(conn)["objectif"]["nom"]
        db.set_setting(conn, "objectif", {"nom": "Semi-marathon de Paris", "date": "2027-03-07",
                                          "distance_km": 21.0975, "temps_cible": "1:25:00"})
    with db.session() as conn:  # celui qu'on a enregistré (le centre des objectifs l'écrit) reste
        assert db.get_settings(conn)["objectif"]["temps_cible"] == "1:25:00"


def test_a_profile_only_read_is_upgraded_first():
    """Un profil qu'on regarde sans le synchroniser (lecture seule) passe quand même par la mise à niveau :
    sinon il garde « Cap semi de Paris » (cas des deux autres profils de William, créés avant la 0.8.1)."""
    with db.session() as conn:
        conn.execute("DELETE FROM views WHERE id = 'objectifs'")
        old = {"tuiles": [views._tile("objectif", 4, 2), views._tile("fractions", 8, 2, periode="120")]}
        conn.execute("INSERT INTO views(id, name, icon, position, spec, builtin) VALUES ('cap-semi', "
                     "'Cap semi de Paris', 'flag', 5, ?, 1)", (json.dumps(old),))
        db.delete_meta(conn, "vue_objectifs")
        db.set_meta(conn, "init_version", "0.8.0")  # mise à niveau faite par une version plus ancienne
    with db.session(readonly=True) as conn:
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM views")}
        assert names.get("objectifs") == "Objectifs" and "cap-semi" not in names
        assert db.get_meta(conn, "init_version") == __version__
