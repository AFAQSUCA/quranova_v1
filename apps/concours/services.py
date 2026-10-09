"""Règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31)."""
import hashlib
import json
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from apps.audit.services import journaliser
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Categorie, Concours, CritereNotation, Epreuve
from apps.coran.models import VersionCorpus
from apps.utilisateurs.models import Utilisateur
from apps.utilisateurs.services import missions_accessibles


def _statut_actuel_du_corpus(version_id):
    """Statut lu dans la base : l'objet en mémoire peut être périmé."""
    return VersionCorpus.objects.filter(pk=version_id).values_list("statut", flat=True).first()


def _verifier_version_utilisable(version_id):
    if _statut_actuel_du_corpus(version_id) not in (
        VersionCorpus.Statut.VALIDEE,
        VersionCorpus.Statut.ACTIVE,
    ):
        raise ConfigurationInvalideError(
            "Seule une version du corpus validée ou active peut être utilisée par un concours (RM-09)."
        )


def definir_version_corpus(concours, version):
    """Rattache une version du corpus au concours ; impossible après l'ouverture (RM-27)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La version du corpus est figée à l'ouverture du concours (RM-27)."
        )
    _verifier_version_utilisable(version.pk)
    concours.version_corpus = version
    concours.save(update_fields=["version_corpus", "modifie_le"])


def problemes_de_configuration(concours):
    """Liste ce qui manque pour que la configuration soit validable (vide si tout est en ordre)."""
    categories = list(concours.categories.order_by("nom"))
    if not categories:
        return ["Le concours n'a aucune catégorie."]
    problemes = []
    for categorie in categories:
        epreuves = list(categorie.epreuves.order_by("ordre"))
        if not epreuves:
            problemes.append(f"La catégorie « {categorie.nom} » n'a aucune épreuve.")
        for epreuve in epreuves:
            if not epreuve.criteres.exists():
                problemes.append(f"L'épreuve « {epreuve.nom} » n'a aucun critère de notation.")
        for epreuve in epreuves:
            if categorie.regle_departage == Categorie.RegleDepartage.CRITERE_PRIORITAIRE and not epreuve.critere_prioritaire_id:
                problemes.append(
                    f"L'épreuve « {epreuve.nom} » : la règle de départage « critère prioritaire » exige de désigner ce critère."
                )
    return problemes


def empreinte_configuration(concours):
    """Empreinte SHA-256 de la configuration : catégories, épreuves, barème et réglages de tirage.

    Sert à détecter qu'une configuration a changé APRÈS avoir été validée (RM-31).
    """
    description = []
    for categorie in concours.categories.order_by("nom"):
        epreuves = []
        for epreuve in categorie.epreuves.order_by("ordre"):
            epreuves.append(
                {
                    "nom": epreuve.nom,
                    "ordre": epreuve.ordre,
                    "P": epreuve.questions_par_serie,
                    "T": epreuve.tirages_par_candidat,
                    "reutilisation_autre_candidat": epreuve.reutilisation_autre_candidat,
                    "reutilisation_meme_candidat_autre_epreuve": (
                        epreuve.reutilisation_meme_candidat_autre_epreuve
                    ),
                    "exclusion_definitive": epreuve.exclusion_definitive,
                    "mode_affichage": epreuve.mode_affichage,
                    "affichage_scene": epreuve.affichage_scene,
                    **({"critere_prioritaire": epreuve.critere_prioritaire.libelle} if epreuve.critere_prioritaire_id else {}),
                    "criteres": [
                        {
                            "libelle": critere.libelle,
                            "ordre": critere.ordre,
                            "maximum": str(critere.maximum),
                            "coefficient": str(critere.coefficient),
                        }
                        for critere in epreuve.criteres.order_by("ordre")
                    ],
                }
            )
        description.append(
            {
                "nom": categorie.nom,
                "discipline": categorie.discipline,
                "age_minimum": categorie.age_minimum,
                "age_maximum": categorie.age_maximum,
                "effectif_prevu": categorie.effectif_prevu,
                "regle_classement": categorie.regle_classement,
                "regle_departage": categorie.regle_departage,
                "epreuves": epreuves,
            }
        )
    texte = json.dumps(description, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def valider_configuration(concours, utilisateur):
    """Le responsable du client valide la configuration du concours (RM-31, §6.2).

    Le prestataire exécute, le client valide : ni l'opérateur ni l'administrateur ne peuvent le faire.
    """
    if (
        not utilisateur.is_active
        or utilisateur.role != Utilisateur.Role.RESPONSABLE_CLIENT
        or utilisateur.organisation_id != concours.organisation_id
    ):
        raise ValidationRefuseeError(
            "Seul le responsable du client concerné peut valider la configuration du concours."
        )
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            "La configuration ne se valide que pour un concours en brouillon."
        )
    problemes = problemes_de_configuration(concours)
    if problemes:
        raise ConfigurationInvalideError("Configuration incomplète : " + " ".join(problemes))
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError(
            "Aucune version du corpus n'est rattachée au concours (RM-27)."
        )
    concours.configuration_validee_par = utilisateur
    concours.configuration_validee_le = timezone.now()
    concours.configuration_empreinte = empreinte_configuration(concours)
    concours.save(
        update_fields=[
            "configuration_validee_par",
            "configuration_validee_le",
            "configuration_empreinte",
            "modifie_le",
        ]
    )
    journaliser(
        "concours.configuration_validee", organisation=concours.organisation, auteur=utilisateur, objet=concours,
        details={"empreinte": concours.configuration_empreinte},
    )


def ouvrir_concours(concours):
    """Ouvre un concours : configuration validée et inchangée, corpus validé ou actif (RM-27, RM-31)."""
    if concours.etat != Concours.Etat.BROUILLON:
        raise ConfigurationInvalideError(
            f"Seul un concours en brouillon peut être ouvert (état actuel : {concours.get_etat_display()})."
        )
    if concours.configuration_validee_le is None:
        raise ConfigurationInvalideError(
            "La configuration n'a pas été validée par le responsable du client (RM-31)."
        )
    if concours.version_corpus_id is None:
        raise ConfigurationInvalideError("Aucune version du corpus n'est rattachée au concours.")
    _verifier_version_utilisable(concours.version_corpus_id)
    if empreinte_configuration(concours) != concours.configuration_empreinte:
        raise ConfigurationInvalideError(
            "La configuration a changé depuis sa validation : "
            "le responsable du client doit la valider de nouveau (RM-31)."
        )
    concours.etat = Concours.Etat.OUVERT
    concours.save(update_fields=["etat", "modifie_le"])
    journaliser("concours.ouvert", organisation=concours.organisation, objet=concours)


def demarrer_concours(concours):
    """Passe un concours « ouvert » à « en cours » : les tirages deviennent possibles (D25)."""
    if concours.etat != Concours.Etat.OUVERT:
        raise ConfigurationInvalideError(
            f"Seul un concours ouvert peut démarrer (état actuel : {concours.get_etat_display()})."
        )
    concours.etat = Concours.Etat.EN_COURS
    concours.save(update_fields=["etat", "modifie_le"])


# --- Duplication d'un concours (§7, REC-02) -------------------------------------------------------------------------


@dataclass
class ResultatDuplication:
    concours: Concours
    categories: int = 0
    epreuves: int = 0
    criteres: int = 0
    series: int = 0
    series_ignorees: int = 0
    avertissements: list = field(default_factory=list)


def _verifier_droit_de_dupliquer(auteur, source, mission):
    droit = auteur.is_active and (
        auteur.role == Utilisateur.Role.ADMINISTRATEUR
        or (
            auteur.role == Utilisateur.Role.OPERATEUR
            and missions_accessibles(auteur).filter(pk__in=[source.mission_id, mission.pk]).count() == len({source.mission_id, mission.pk})
        )
    )
    if not droit:
        raise ConfigurationInvalideError(
            "Vous n'avez pas le droit de dupliquer ce concours : seul le personnel du prestataire affecté à la mission le peut (RM-20)."
        )


def _recopier_serie(serie, lot_copie, version, organisation, correspondance):
    """Recrée une série dans ``lot_copie`` ; renvoie ``False`` si elle ne peut pas l'être (sans rien écrire)."""
    from apps.coran.exceptions import ReferenceInvalideError
    from apps.questions import services as services_questions
    from apps.questions.models import Question

    questions = []
    try:
        for appartenance in serie.questions_ordonnees.select_related("question").order_by("rang"):
            ancienne = appartenance.question
            if ancienne.pk not in correspondance:
                if ancienne.type == Question.Type.PASSAGE_CORANIQUE:
                    if version is None:
                        return False
                    p = ancienne.passage
                    correspondance[ancienne.pk] = services_questions.creer_question_passage(
                        organisation, version, (p.sourate_debut, p.verset_debut), (p.sourate_fin, p.verset_fin)
                    )  # les références sont revérifiées dans la version de la copie (RM-23)
                else:
                    correspondance[ancienne.pk] = services_questions.creer_question_enonce(organisation, ancienne.enonce)
            questions.append(correspondance[ancienne.pk])
    except ReferenceInvalideError:
        return False
    services_questions.composer_serie(lot_copie, questions)
    return True


def dupliquer_concours(source, *, auteur, nom, edition, date_debut, date_fin, mission=None):
    """Prépare une nouvelle édition à partir de ``source`` : catégories, épreuves, barèmes et séries (REC-02).

    La copie repart en BROUILLON : configuration NON validée (RM-31), aucune session, aucun candidat, aucun tirage,
    épreuves « en préparation ». Les questions sont recréées (jamais partagées avec l'original). Si la version du
    corpus d'origine n'est plus utilisable, la copie n'en a pas et les séries à passages coraniques ne sont pas copiées
    (RM-23, RM-27) : l'avertissement le dit. Tout ou rien : une erreur n'enregistre rien.
    """
    mission = mission or source.mission
    if mission.organisation_id != source.organisation_id:
        raise ConfigurationInvalideError("La copie doit rester dans une mission du même client que l'original (RM-20).")
    _verifier_droit_de_dupliquer(auteur, source, mission)
    if date_fin < date_debut:
        raise ConfigurationInvalideError("La date de fin du concours ne peut pas précéder sa date de début.")
    if Concours.objects.filter(organisation_id=source.organisation_id, nom=nom, edition=edition).exists():
        raise ConfigurationInvalideError(f"Un concours « {nom} » (édition « {edition} ») existe déjà pour ce client.")

    version = None
    if source.version_corpus_id and _statut_actuel_du_corpus(source.version_corpus_id) in (
        VersionCorpus.Statut.VALIDEE, VersionCorpus.Statut.ACTIVE,
    ):
        version = source.version_corpus

    with transaction.atomic():
        copie = Concours.objects.create(
            mission=mission, nom=nom, edition=edition, format=source.format, date_debut=date_debut, date_fin=date_fin,
            version_corpus=version,
        )
        resultat = ResultatDuplication(concours=copie)
        correspondance_questions = {}
        for categorie in source.categories.order_by("nom"):
            nouvelle_categorie = Categorie.objects.create(
                concours=copie, nom=categorie.nom, discipline=categorie.discipline, age_minimum=categorie.age_minimum,
                age_maximum=categorie.age_maximum, effectif_prevu=categorie.effectif_prevu,
                regle_classement=categorie.regle_classement, regle_departage=categorie.regle_departage,
            )
            resultat.categories += 1
            for epreuve in categorie.epreuves.order_by("ordre"):
                nouvelle_epreuve = Epreuve.objects.create(
                    categorie=nouvelle_categorie, nom=epreuve.nom, ordre=epreuve.ordre,
                    questions_par_serie=epreuve.questions_par_serie, tirages_par_candidat=epreuve.tirages_par_candidat,
                    reutilisation_autre_candidat=epreuve.reutilisation_autre_candidat,
                    reutilisation_meme_candidat_autre_epreuve=epreuve.reutilisation_meme_candidat_autre_epreuve,
                    exclusion_definitive=epreuve.exclusion_definitive, mode_affichage=epreuve.mode_affichage,
                    affichage_scene=epreuve.affichage_scene, etat=Epreuve.Etat.EN_PREPARATION,
                )
                resultat.epreuves += 1
                criteres = {}
                for critere in epreuve.criteres.order_by("ordre"):
                    criteres[critere.pk] = CritereNotation.objects.create(
                        epreuve=nouvelle_epreuve, libelle=critere.libelle, ordre=critere.ordre,
                        maximum=critere.maximum, coefficient=critere.coefficient,
                    )
                    resultat.criteres += 1
                if epreuve.critere_prioritaire_id:  # le critère de la COPIE, pas celui de l'original
                    nouvelle_epreuve.critere_prioritaire = criteres[epreuve.critere_prioritaire_id]
                    nouvelle_epreuve.save(update_fields=["critere_prioritaire", "modifie_le"])
                lot = getattr(epreuve, "lot", None)
                if lot is not None:
                    from apps.questions import services as services_questions

                    lot_copie = services_questions.obtenir_lot(nouvelle_epreuve)
                    for serie in lot.series.order_by("numero"):
                        if _recopier_serie(serie, lot_copie, version, copie.organisation, correspondance_questions):
                            resultat.series += 1
                        else:
                            resultat.series_ignorees += 1
        if version is None:
            resultat.avertissements.append(
                "Le corpus du concours d'origine n'est plus utilisable : rattachez une version du corpus validée à la copie "
                f"avant de l'ouvrir. {resultat.series_ignorees} série(s) contenant des passages coraniques n'ont pas été copiées."
            )
        journaliser(
            "concours.duplique", organisation=copie.organisation, auteur=auteur, objet=copie,
            details={"source": source.pk, "categories": resultat.categories, "epreuves": resultat.epreuves,
                     "criteres": resultat.criteres, "series": resultat.series, "series_ignorees": resultat.series_ignorees},
        )
    return resultat
