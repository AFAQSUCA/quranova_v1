"""Tests du modèle Sourate (cf. §12.2, §12.4 et REC-30).

Aucun texte coranique n'est saisi dans ces tests : les valeurs sont des
chaînes de test neutres.
"""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.coran.models import Sourate
from apps.coran.tests.outils import creer_sourate, creer_version


@pytest.mark.django_db
def test_numero_unique_par_version():
    version = creer_version()
    creer_sourate(version, numero=2, ordre_revelation=87)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(version, numero=2, ordre_revelation=88)


@pytest.mark.django_db
def test_meme_numero_possible_dans_deux_versions():
    creer_sourate(creer_version(), numero=2, ordre_revelation=87)
    creer_sourate(creer_version(), numero=2, ordre_revelation=87)

    assert Sourate.objects.filter(numero=2).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [0, 115])
def test_rec31_numero_de_sourate_hors_bornes_refuse(numero):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(numero=numero)


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [1, 114])
def test_numeros_limites_acceptes(numero):
    sourate = creer_sourate(numero=numero)

    assert sourate.numero == numero


@pytest.mark.django_db
def test_ordre_revelation_unique_par_version():
    version = creer_version()
    creer_sourate(version, numero=1, ordre_revelation=5)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(version, numero=2, ordre_revelation=5)


@pytest.mark.django_db
@pytest.mark.parametrize("ordre", [0, 115])
def test_ordre_revelation_hors_bornes_refuse(ordre):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(ordre_revelation=ordre)


@pytest.mark.django_db
def test_nombre_de_versets_doit_etre_au_moins_un():
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(nombre_versets=0)


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [1, 9])
def test_rm_sourates_1_et_9_sans_basmala_numerotee(numero):
    """§12.4 : la sourate 9 n'a pas de basmala et celle de la sourate 1 est le verset 1:1."""
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_sourate(numero=numero, basmala="basmala-de-test")


@pytest.mark.django_db
@pytest.mark.parametrize("numero", [1, 9])
def test_sourates_1_et_9_acceptees_sans_basmala(numero):
    sourate = creer_sourate(numero=numero)

    assert sourate.basmala == ""


@pytest.mark.django_db
def test_une_autre_sourate_peut_porter_une_basmala():
    sourate = creer_sourate(numero=2, basmala="basmala-de-test")

    assert sourate.basmala == "basmala-de-test"


@pytest.mark.django_db
def test_une_version_ne_peut_pas_etre_supprimee_si_elle_a_des_sourates():
    sourate = creer_sourate()

    with pytest.raises(ProtectedError):
        sourate.version.delete()
