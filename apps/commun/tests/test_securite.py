"""Tests de sécurité transverses (REC-26 à REC-28) : CSRF, injection SQL, charges de script importées."""
import pytest
from django.test import Client
from django.urls import reverse

from apps.candidats.importation import importer_candidats
from apps.candidats.models import Candidat
from apps.commun.tests.outils import creer_categorie, creer_concours, creer_utilisateur
from apps.concours.models import Concours
from apps.utilisateurs.models import Utilisateur

CHARGE_SCRIPT = "<script>alert(1)</script>"
CHARGE_SQL = "Robert') DROP TABLE candidats_candidat --"  # sans « ; » : c'est le séparateur du CSV


@pytest.mark.django_db
def test_rec27_une_requete_post_forgee_sans_jeton_csrf_est_rejetee():
    """Un site tiers fait poster le navigateur d'un administrateur connecté : sans jeton CSRF, c'est un 403."""
    administrateur = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True)
    navigateur = Client(enforce_csrf_checks=True)
    navigateur.force_login(administrateur)
    concours = creer_concours()

    reponse = navigateur.post(
        reverse("admin:concours_concours_delete", args=[concours.pk]), {"post": "yes"}
    )

    assert reponse.status_code == 403
    assert Concours.objects.filter(pk=concours.pk).exists()


@pytest.mark.django_db
def test_rec27_les_api_a_jeton_ignorent_les_cookies_de_session():
    """Les API tablette sont exemptées de CSRF parce qu'elles n'utilisent pas de cookie : un cookie de session
    seul ne doit donc ouvrir aucune de leurs portes."""
    operateur = creer_utilisateur(Utilisateur.Role.OPERATEUR, is_staff=True)
    navigateur = Client(enforce_csrf_checks=True)
    navigateur.force_login(operateur)

    reponse = navigateur.post("/api/tirage/prestations/00000000-0000-0000-0000-000000000000/tirer/", {})

    assert reponse.status_code in (401, 403, 404)
    assert reponse.status_code != 200


@pytest.mark.django_db
def test_rec26_rec28_un_fichier_importe_avec_script_et_sql_est_stocke_comme_du_texte(tmp_path):
    """Le contenu hostile est conservé tel quel (c'est une donnée), la table n'est pas touchée,
    et l'échappement se fait à l'affichage (testé sur le procès-verbal)."""
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    fichier = tmp_path / "candidats.csv"
    fichier.write_bytes(
        (
            "nom;prenom;date_naissance;sexe;ville;structure;categorie\n"
            f"{CHARGE_SQL};Awa;05/03/1990;F;Abidjan;{CHARGE_SCRIPT};Juniors\n"
        ).encode("utf-8-sig")
    )

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok, rapport.texte()
    candidat = Candidat.objects.get()
    assert candidat.nom == CHARGE_SQL
    assert Candidat.objects.count() == 1  # la table existe toujours


@pytest.mark.django_db
def test_rec28_la_recherche_de_l_administration_traite_une_injection_comme_du_texte():
    administrateur = creer_utilisateur(Utilisateur.Role.ADMINISTRATEUR, is_staff=True, is_superuser=True)
    navigateur = Client()
    navigateur.force_login(administrateur)
    Candidat.objects.create(
        organisation=creer_concours().mission.organisation, nom="Diallo", prenom="Awa", sexe="F"
    )

    for charge in (CHARGE_SQL, "' OR '1'='1", "%' UNION SELECT 1--"):
        reponse = navigateur.get(reverse("admin:candidats_candidat_changelist"), {"q": charge})
        assert reponse.status_code == 200
    assert Candidat.objects.count() == 1


def test_rec28_l_analyse_statique_bandit_ne_signale_aucune_alerte():
    """Garde-fou : une alerte de sécurité nouvelle (shell, SQL construit à la main, XML non protégé…) fait échouer les tests.

    Une alerte justifiée se marque ``# nosec Bxxx`` avec l'explication sur la ligne précédente (voir apps/commun/sauvegarde.py).
    """
    import subprocess
    import sys
    from pathlib import Path

    racine = Path(__file__).resolve().parents[3]
    try:
        import bandit  # noqa: F401
    except ImportError:
        pytest.skip("bandit n'est pas installé (pip install -r requirements/dev.txt)")
    resultat = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", "apps", "config", "-c", "bandit.yaml", "-q"], cwd=racine, capture_output=True, text=True,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
