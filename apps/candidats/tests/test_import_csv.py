"""Tests de l'import CSV des candidats (§7.3 : contrôle des doublons et rapport d'erreurs).

Principes :
- l'import est « tout ou rien » : s'il y a une erreur, RIEN n'est enregistré, et le rapport
  les liste TOUTES (l'opérateur corrige son fichier en une fois) ;
- on peut simuler (``simuler=True``) : mêmes contrôles, même rapport, rien d'enregistré ;
- le fichier d'un client ne touche jamais les données d'un autre client (RM-20).
"""
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.candidats.importation import importer_candidats
from apps.candidats.models import Candidat, Participation
from apps.commun.tests.outils import (
    creer_candidat,
    creer_categorie,
    creer_concours,
    creer_organisation,
    creer_participation,
    creer_utilisateur,
    creer_version_validee,
)
from apps.concours.models import Concours
from apps.utilisateurs.models import Utilisateur

EN_TETE = ["nom", "prenom", "date_naissance", "sexe", "ville", "structure", "categorie"]


def ecrire_csv(chemin, lignes, *, separateur=";", encodage="utf-8-sig", en_tete=EN_TETE):
    """Écrit un fichier CSV de test (par défaut : UTF-8 avec BOM, séparateur « ; », comme Excel)."""
    contenu = separateur.join(en_tete) + "\n"
    contenu += "".join(separateur.join(ligne) + "\n" for ligne in lignes)
    chemin.write_bytes(contenu.encode(encodage))
    return chemin


def ligne(nom="Diallo", prenom="Awa", naissance="05/03/2010", sexe="F", ville="Abidjan",
          structure="École Test", categorie="Juniors"):
    return [nom, prenom, naissance, sexe, ville, structure, categorie]


@pytest.fixture
def concours(db):
    concours = creer_concours()
    creer_categorie(concours, nom="Juniors")
    creer_categorie(concours, nom="Seniors")
    return concours


@pytest.fixture
def fichier(tmp_path):
    return tmp_path / "candidats.csv"


def messages(rapport):
    return " | ".join(e.message for e in rapport.erreurs)


# --- Cas nominal -------------------------------------------------------------


@pytest.mark.django_db
def test_import_de_deux_candidats(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008", "M", categorie="Seniors")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok and rapport.lignes_lues == 2
    assert Candidat.objects.count() == 2 and Participation.objects.count() == 2
    assert [(i.numero_candidat, i.categorie) for i in rapport.inscriptions] == [(1, "Juniors"), (2, "Seniors")]
    awa = Candidat.objects.get(nom="Diallo")
    assert (awa.prenom, awa.date_naissance, awa.sexe, awa.ville) == ("Awa", date(2010, 3, 5), "F", "Abidjan")
    assert awa.organisation_id == concours.organisation_id


@pytest.mark.django_db
def test_les_participations_sont_inscrites_et_numerotees_dans_l_ordre_du_fichier(concours, fichier):
    ecrire_csv(fichier, [ligne("A", "a"), ligne("B", "b"), ligne("C", "c")])

    importer_candidats(concours, fichier)

    participations = Participation.objects.filter(concours=concours).order_by("numero_candidat")
    assert [p.candidat.nom for p in participations] == ["A", "B", "C"]
    assert all(p.statut == Participation.Statut.INSCRIT for p in participations)


@pytest.mark.django_db
def test_la_numerotation_continue_apres_les_participations_existantes(concours, fichier):
    creer_participation(concours.categories.get(nom="Juniors"), numero_candidat=41)
    ecrire_csv(fichier, [ligne()])

    rapport = importer_candidats(concours, fichier)

    assert rapport.inscriptions[0].numero_candidat == 42


# --- Formats de fichier ------------------------------------------------------


@pytest.mark.django_db
def test_separateur_virgule_et_point_virgule_acceptes(concours, tmp_path):
    ecrire_csv(tmp_path / "a.csv", [ligne("Diallo", "Awa")], separateur=",")
    ecrire_csv(tmp_path / "b.csv", [ligne("Koné", "Ibrahim", "12/11/2008")], separateur=";")

    assert importer_candidats(concours, tmp_path / "a.csv").ok
    assert importer_candidats(concours, tmp_path / "b.csv").ok
    assert Candidat.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("encodage", ["utf-8", "utf-8-sig", "cp1252"])
def test_encodages_acceptes_et_accents_conserves(concours, fichier, encodage):
    """Excel français enregistre souvent en cp1252 (« CSV ANSI ») : les accents doivent survivre."""
    ecrire_csv(fichier, [ligne("Koné", "Élodie", ville="Bouaké")], encodage=encodage)

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    candidat = Candidat.objects.get()
    assert (candidat.nom, candidat.prenom, candidat.ville) == ("Koné", "Élodie", "Bouaké")


@pytest.mark.django_db
def test_en_tetes_tolerants_casse_accents_espaces_et_ordre_des_colonnes(concours, fichier):
    en_tete = ["Catégorie", "PRÉNOM", "Nom", "Date de naissance"]
    ecrire_csv(fichier, [["Juniors", "Awa", "Diallo", "05/03/2010"]], en_tete=en_tete)

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.get().nom == "Diallo"


@pytest.mark.django_db
def test_colonnes_facultatives_absentes(concours, fichier):
    ecrire_csv(fichier, [["Diallo", "Awa", "Juniors"]], en_tete=["nom", "prenom", "categorie"])

    assert importer_candidats(concours, fichier).ok
    candidat = Candidat.objects.get()
    assert candidat.date_naissance is None and candidat.sexe == "" and candidat.ville == ""


@pytest.mark.django_db
@pytest.mark.parametrize("manquante", ["nom", "prenom", "categorie"])
def test_colonne_obligatoire_manquante_refuse_tout_le_fichier(concours, fichier, manquante):
    en_tete = [c for c in EN_TETE if c != manquante]
    ecrire_csv(fichier, [[v for c, v in zip(EN_TETE, ligne()) if c != manquante]], en_tete=en_tete)

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok
    assert manquante in messages(rapport)
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_fichier_sans_aucune_ligne(concours, fichier):
    ecrire_csv(fichier, [])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "aucune ligne" in messages(rapport).lower()


@pytest.mark.django_db
def test_fichier_completement_vide(concours, fichier):
    fichier.write_bytes(b"")

    assert not importer_candidats(concours, fichier).ok


@pytest.mark.django_db
def test_les_lignes_vides_sont_ignorees(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), [";" * 6], ligne("Koné", "Ibrahim", "12/11/2008")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok and rapport.lignes_lues == 2


# --- Validation des lignes ---------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("champ, valeur", [("nom", ""), ("prenom", "  "), ("categorie", "")])
def test_champs_obligatoires_vides_refuses_avec_le_numero_de_ligne(concours, fichier, champ, valeur):
    donnees = dict(zip(EN_TETE, ligne()))
    donnees[champ] = valeur
    ecrire_csv(fichier, [ligne(), [donnees[c] for c in EN_TETE]])

    rapport = importer_candidats(concours, fichier)

    assert [e.ligne for e in rapport.erreurs] == [3]  # ligne 1 = en-tête, ligne 3 = 2e candidat
    assert champ in messages(rapport)


@pytest.mark.django_db
def test_categorie_inconnue_nommee_dans_l_erreur(concours, fichier):
    ecrire_csv(fichier, [ligne(categorie="Catégorie fantôme")])

    rapport = importer_candidats(concours, fichier)

    assert "Catégorie fantôme" in messages(rapport)
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_la_categorie_est_reconnue_sans_tenir_compte_de_la_casse(concours, fichier):
    ecrire_csv(fichier, [ligne(categorie="  juniors ")])

    assert importer_candidats(concours, fichier).ok


@pytest.mark.django_db
def test_la_categorie_d_un_autre_concours_n_est_pas_utilisee(concours, fichier):
    creer_categorie(creer_concours(), nom="Exclusive")  # n'existe pas dans NOTRE concours
    ecrire_csv(fichier, [ligne(categorie="Exclusive")])

    assert not importer_candidats(concours, fichier).ok


@pytest.mark.django_db
@pytest.mark.parametrize(
    "texte, attendu",
    [("05/03/2010", date(2010, 3, 5)), ("2010-03-05", date(2010, 3, 5)), ("", None)],
)
def test_formats_de_date_acceptes(concours, fichier, texte, attendu):
    ecrire_csv(fichier, [ligne(naissance=texte)])

    assert importer_candidats(concours, fichier).ok
    assert Candidat.objects.get().date_naissance == attendu


@pytest.mark.django_db
@pytest.mark.parametrize(
    "texte",
    [
        "31/02/2010",  # n'existe pas
        "abc",
        "2010/03/05",  # format non prévu
        "05-03-2010",
        "01/01/1850",  # trop ancien
        (timezone.now().date() + timedelta(days=1)).strftime("%d/%m/%Y"),  # dans le futur
    ],
)
def test_dates_invalides_refusees(concours, fichier, texte):
    ecrire_csv(fichier, [ligne(naissance=texte)])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "date" in messages(rapport).lower()


@pytest.mark.django_db
@pytest.mark.parametrize("texte, attendu", [("M", "M"), ("f", "F"), ("Féminin", "F"), ("masculin", "M"), ("", "")])
def test_sexe_normalise(concours, fichier, texte, attendu):
    ecrire_csv(fichier, [ligne(sexe=texte)])

    assert importer_candidats(concours, fichier).ok
    assert Candidat.objects.get().sexe == attendu


@pytest.mark.django_db
def test_sexe_inconnu_refuse(concours, fichier):
    ecrire_csv(fichier, [ligne(sexe="X")])

    assert "sexe" in messages(importer_candidats(concours, fichier)).lower()


@pytest.mark.django_db
def test_valeur_trop_longue_refusee(concours, fichier):
    ecrire_csv(fichier, [ligne(nom="N" * 101)])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "100" in messages(rapport)


@pytest.mark.django_db
def test_le_contenu_est_stocke_tel_quel_sans_etre_interprete(concours, fichier):
    """REC-26 : un nom contenant du code n'est jamais exécuté ; il est échappé à l'affichage."""
    nom_piege = "<script>alert(1)</script>"
    ecrire_csv(fichier, [ligne(nom=nom_piege)])

    assert importer_candidats(concours, fichier).ok
    assert Candidat.objects.get().nom == nom_piege


# --- Doublons ----------------------------------------------------------------


@pytest.mark.django_db
def test_doublon_dans_le_fichier_signale_les_deux_lignes(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008"), ligne("Diallo", "Awa")])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok
    erreur = rapport.erreurs[0]
    assert erreur.ligne == 4 and "doublon" in erreur.message.lower() and "2" in erreur.message


@pytest.mark.django_db
def test_doublon_sans_tenir_compte_de_la_casse(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("DIALLO", "awa")])

    assert "doublon" in messages(importer_candidats(concours, fichier)).lower()


@pytest.mark.django_db
def test_une_date_de_naissance_differente_designe_une_autre_personne(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010"), ligne("Diallo", "Awa", "17/08/2012")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok and Candidat.objects.count() == 2


@pytest.mark.django_db
def test_la_meme_personne_dans_deux_categories_est_acceptee_sans_doublon_de_candidat(concours, fichier):
    ecrire_csv(fichier, [ligne(categorie="Juniors"), ligne(categorie="Seniors")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.count() == 1 and Participation.objects.count() == 2


@pytest.mark.django_db
def test_candidat_deja_inscrit_dans_la_categorie_est_un_doublon_avec_son_numero(concours, fichier):
    categorie = concours.categories.get(nom="Juniors")
    candidat = creer_candidat(
        concours.organisation, nom="Diallo", prenom="Awa", date_naissance=date(2010, 3, 5)
    )
    creer_participation(categorie, candidat, numero_candidat=17)
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010", categorie="Juniors")])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok
    assert "déjà inscrit" in messages(rapport) and "17" in messages(rapport)
    assert Participation.objects.count() == 1


@pytest.mark.django_db
def test_un_candidat_existant_est_reutilise_pour_une_autre_categorie(concours, fichier):
    candidat = creer_candidat(
        concours.organisation, nom="Diallo", prenom="Awa", date_naissance=date(2010, 3, 5)
    )
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010", categorie="Seniors")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.count() == 1
    assert Participation.objects.get().candidat == candidat


@pytest.mark.django_db
def test_rm20_un_homonyme_d_un_autre_client_n_est_pas_reutilise(concours, fichier):
    creer_candidat(creer_organisation(), nom="Diallo", prenom="Awa", date_naissance=date(2010, 3, 5))
    ecrire_csv(fichier, [ligne("Diallo", "Awa", "05/03/2010")])

    rapport = importer_candidats(concours, fichier)

    assert rapport.ok
    assert Candidat.objects.count() == 2
    assert Participation.objects.get().candidat.organisation_id == concours.organisation_id


# --- Tout ou rien, simulation, état du concours ------------------------------


@pytest.mark.django_db
def test_une_erreur_empeche_tout_l_import_et_toutes_les_erreurs_sont_listees(concours, fichier):
    ecrire_csv(
        fichier,
        [
            ligne("Valide", "Un"),
            ligne("", "Sans nom"),  # erreur ligne 3
            ligne("Valide", "Deux", categorie="Inconnue"),  # erreur ligne 4
            ligne("Valide", "Trois", naissance="31/02/2010"),  # erreur ligne 5
        ],
    )

    rapport = importer_candidats(concours, fichier)

    assert [e.ligne for e in rapport.erreurs] == [3, 4, 5]
    assert Candidat.objects.count() == 0 and Participation.objects.count() == 0
    assert rapport.inscriptions == []


@pytest.mark.django_db
def test_la_simulation_donne_le_meme_rapport_sans_rien_enregistrer(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008")])

    simulation = importer_candidats(concours, fichier, simuler=True)

    assert simulation.ok and simulation.simulation
    assert [i.numero_candidat for i in simulation.inscriptions] == [1, 2]
    assert Candidat.objects.count() == 0 and Participation.objects.count() == 0

    reel = importer_candidats(concours, fichier)
    assert [i.numero_candidat for i in reel.inscriptions] == [1, 2]
    assert Participation.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("etat", [Concours.Etat.TERMINE, Concours.Etat.ARCHIVE])
def test_pas_d_import_dans_un_concours_termine_ou_archive(concours, fichier, etat):
    # D16 : un concours non brouillon exige un corpus figé et une configuration validée.
    responsable = creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=concours.organisation)
    Concours.objects.filter(pk=concours.pk).update(
        etat=etat,
        version_corpus=creer_version_validee(),
        configuration_validee_par=responsable,
        configuration_validee_le=timezone.now(),
        configuration_empreinte="a" * 64,
    )
    concours.refresh_from_db()
    ecrire_csv(fichier, [ligne()])

    rapport = importer_candidats(concours, fichier)

    assert not rapport.ok and "inscriptions" in messages(rapport).lower()
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_le_resume_du_rapport_est_lisible(concours, fichier):
    ecrire_csv(fichier, [ligne("", "X")])

    texte = importer_candidats(concours, fichier).texte()

    assert "Ligne 2" in texte and "nom" in texte


# --- Commande ----------------------------------------------------------------


@pytest.mark.django_db
def test_commande_importer_candidats(concours, fichier):
    ecrire_csv(fichier, [ligne("Diallo", "Awa"), ligne("Koné", "Ibrahim", "12/11/2008")])
    sortie = StringIO()

    call_command("importer_candidats", str(concours.pk), str(fichier), stdout=sortie)

    assert Participation.objects.count() == 2
    assert "2 candidats inscrits" in sortie.getvalue()


@pytest.mark.django_db
def test_commande_dry_run(concours, fichier):
    ecrire_csv(fichier, [ligne()])
    sortie = StringIO()

    call_command("importer_candidats", str(concours.pk), str(fichier), "--dry-run", stdout=sortie)

    assert Participation.objects.count() == 0
    assert "n'a été enregistré" in sortie.getvalue()


@pytest.mark.django_db
def test_commande_affiche_toutes_les_erreurs(concours, fichier):
    ecrire_csv(fichier, [ligne("", "A"), ligne("B", "", categorie="Inconnue")])

    with pytest.raises(CommandError) as erreur:
        call_command("importer_candidats", str(concours.pk), str(fichier))

    assert "Ligne 2" in str(erreur.value) and "Ligne 3" in str(erreur.value)
    assert Candidat.objects.count() == 0


@pytest.mark.django_db
def test_commande_concours_ou_fichier_introuvable(concours, tmp_path):
    with pytest.raises(CommandError, match="introuvable"):
        call_command("importer_candidats", str(concours.pk), str(tmp_path / "absent.csv"))
    ecrire_csv(tmp_path / "ok.csv", [ligne()])
    with pytest.raises(CommandError, match="Concours"):
        call_command("importer_candidats", "00000000-0000-0000-0000-000000000000", str(tmp_path / "ok.csv"))
    with pytest.raises(CommandError, match="Concours"):
        call_command("importer_candidats", "pas-un-uuid", str(tmp_path / "ok.csv"))
