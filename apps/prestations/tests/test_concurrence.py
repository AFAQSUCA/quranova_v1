"""Test de concurrence du tirage : le verrou sur le lot sérialise les tirages (règle absolue n°2).

Nécessite une vraie base PostgreSQL et de vraies transactions (``transaction=True``).
"""
import threading
import uuid

import pytest
from django.db import connection

from apps.prestations import services
from apps.prestations.exceptions import LotEpuiseError
from apps.prestations.models import Tirage
from apps.prestations.tests.outils import creer_epreuve_ouverte, creer_prestation


def lancer_en_parallele(taches):
    """Exécute chaque tâche dans son thread, démarrage simultané ; renvoie les résultats ou exceptions."""
    barriere = threading.Barrier(len(taches))
    resultats = [None] * len(taches)

    def executer(i, tache):
        try:
            barriere.wait()
            resultats[i] = tache()
        except Exception as erreur:  # noqa: BLE001 - on veut observer l'erreur, quelle qu'elle soit
            resultats[i] = erreur
        finally:
            connection.close()

    threads = [threading.Thread(target=executer, args=(i, t)) for i, t in enumerate(taches)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return resultats


@pytest.mark.django_db(transaction=True)
def test_deux_tirages_simultanes_sur_un_lot_d_une_serie_un_seul_reussit():
    epreuve = creer_epreuve_ouverte(series=1)
    prestations = [creer_prestation(epreuve), creer_prestation(epreuve)]

    resultats = lancer_en_parallele(
        [lambda p=p: services.effectuer_tirage(p, uuid.uuid4()) for p in prestations]
    )

    reussis = [r for r in resultats if isinstance(r, Tirage)]
    refuses = [r for r in resultats if isinstance(r, LotEpuiseError)]
    assert len(reussis) == 1 and len(refuses) == 1
    assert Tirage.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_rec07_deux_clics_simultanes_avec_la_meme_demande_creent_un_seul_tirage():
    epreuve = creer_epreuve_ouverte(series=3)
    prestation = creer_prestation(epreuve)
    demande = uuid.uuid4()

    resultats = lancer_en_parallele([lambda: services.effectuer_tirage(prestation, demande) for _ in range(2)])

    assert all(isinstance(r, Tirage) for r in resultats), resultats
    assert resultats[0].pk == resultats[1].pk
    assert Tirage.objects.count() == 1
