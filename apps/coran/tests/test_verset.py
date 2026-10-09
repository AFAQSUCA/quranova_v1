"""Tests du modèle Verset (cf. §12.2, §12.4, REC-30 et REC-31).

Aucun texte coranique n'est saisi dans ces tests : les valeurs sont des
chaînes de test neutres.
"""
import unicodedata

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.coran.models import Verset
from apps.coran.tests.outils import creer_sourate, creer_verset


@pytest.mark.django_db
def test_numero_de_verset_unique_par_sourate():
    sourate = creer_sourate()
    creer_verset(sourate, numero=255)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_verset(sourate, numero=255)


@pytest.mark.django_db
def test_meme_numero_possible_dans_deux_sourates():
    creer_verset(creer_sourate(), numero=1)
    creer_verset(creer_sourate(), numero=1)

    assert Verset.objects.filter(numero=1).count() == 2


@pytest.mark.django_db
def test_rec31_verset_numero_zero_refuse():
    """REC-31 : « 1:0 » est refusé."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_verset(numero=0)


@pytest.mark.django_db
@pytest.mark.parametrize("texte", ["", " ", "   ", "\t", "\n"])
def test_rec30_verset_vide_refuse(texte):
    """REC-30 : absence de verset vide (y compris composé uniquement d'espaces)."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_verset(texte=texte)


@pytest.mark.django_db
def test_regle_absolue_1_texte_stocke_sans_normalisation_unicode():
    """Le texte est conservé octet pour octet : aucune normalisation Unicode (§12.2).

    « e » suivi de l'accent combinant (forme NFD) ne doit pas devenir « é » (NFC).
    """
    texte_nfd = "é texte de test "
    assert unicodedata.normalize("NFC", texte_nfd) != texte_nfd

    verset = creer_verset(texte=texte_nfd)
    verset.refresh_from_db()

    assert verset.texte == texte_nfd
    assert verset.texte.encode("utf-8") == texte_nfd.encode("utf-8")


@pytest.mark.django_db
def test_une_sourate_ne_peut_pas_etre_supprimee_si_elle_a_des_versets():
    verset = creer_verset()

    with pytest.raises(ProtectedError):
        verset.sourate.delete()


@pytest.mark.django_db
def test_versets_ordonnes_dans_l_ordre_canonique():
    sourate_2 = creer_sourate(numero=2, ordre_revelation=87)
    sourate_1 = creer_sourate(sourate_2.version, numero=1, ordre_revelation=5)
    creer_verset(sourate_2, numero=1)
    creer_verset(sourate_1, numero=3)
    creer_verset(sourate_2, numero=2)
    creer_verset(sourate_1, numero=1)

    references = [(v.sourate.numero, v.numero) for v in Verset.objects.all()]

    assert references == [(1, 1), (1, 3), (2, 1), (2, 2)]


@pytest.mark.django_db
def test_reference_au_format_sourate_verset():
    verset = creer_verset(creer_sourate(numero=2, ordre_revelation=87), numero=255)

    assert verset.reference == "2:255"
