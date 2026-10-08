"""Règles d'un concours : corpus figé (RM-27, RM-09) et validation de la configuration (RM-31)."""
import hashlib
import json

from django.utils import timezone

from apps.audit.services import journaliser
from apps.concours.exceptions import ConfigurationInvalideError, ValidationRefuseeError
from apps.concours.models import Categorie, Concours
from apps.coran.models import VersionCorpus
from apps.utilisateurs.models import Utilisateur


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
