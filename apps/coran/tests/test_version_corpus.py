"""Tests du modèle VersionCorpus (cf. §12.3 : versionnement du corpus)."""
import pytest
from django.db import IntegrityError, transaction

from apps.coran.models import VersionCorpus
from apps.coran.tests.outils import creer_version


@pytest.mark.django_db
def test_statut_initial_est_importee():
    version = creer_version()

    assert version.statut == VersionCorpus.Statut.IMPORTEE


@pytest.mark.django_db
def test_riwaya_par_defaut_est_hafs():
    version = creer_version()

    assert version.riwaya == VersionCorpus.Riwaya.HAFS


@pytest.mark.django_db
def test_empreinte_unique():
    version = creer_version()

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(empreinte_sha256=version.empreinte_sha256)


@pytest.mark.django_db
@pytest.mark.parametrize("empreinte", ["abc", "g" * 64, "A" * 64, "a" * 63])
def test_empreinte_doit_etre_un_sha256_hexadecimal_minuscule(empreinte):
    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(empreinte_sha256=empreinte)


@pytest.mark.django_db
def test_une_seule_version_active_par_riwaya():
    creer_version(statut=VersionCorpus.Statut.ACTIVE)

    with pytest.raises(IntegrityError), transaction.atomic():
        creer_version(statut=VersionCorpus.Statut.ACTIVE)


@pytest.mark.django_db
def test_une_nouvelle_version_peut_etre_active_apres_retrait_de_l_ancienne():
    ancienne = creer_version(statut=VersionCorpus.Statut.ACTIVE)
    ancienne.statut = VersionCorpus.Statut.RETIREE
    ancienne.save()

    nouvelle = creer_version(statut=VersionCorpus.Statut.ACTIVE)

    assert nouvelle.statut == VersionCorpus.Statut.ACTIVE


@pytest.mark.django_db
def test_plusieurs_versions_validees_peuvent_coexister():
    creer_version(statut=VersionCorpus.Statut.VALIDEE)
    creer_version(statut=VersionCorpus.Statut.VALIDEE)

    assert VersionCorpus.objects.filter(statut=VersionCorpus.Statut.VALIDEE).count() == 2
