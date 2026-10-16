"""Instantané de l'état de présentation envoyé aux écrans (protocole §3.1), projeté selon le rôle (RM-14).

La projection est faite ICI, côté serveur, avant tout envoi : un écran non autorisé ne reçoit jamais le texte.
"""
from apps.presentation import diapositives
from apps.presentation.services import etat_actif

OPERATEUR, SCENE, JURY = "operateur", "scene", "jury"


def texte_autorise(role, epreuve):
    """L'opérateur et les jurés voient toujours le texte (D44, §9.1) ; la scène seulement si l'épreuve l'a activé (D15)."""
    return role in (OPERATEUR, JURY) or (role == SCENE and epreuve.affichage_scene)


def construire_instantane(session, role, *, instantane=True):
    """Le dictionnaire de ``type: "etat"`` pour la session, tel que défini dans le protocole."""
    etat = etat_actif(session)
    message = {"type": "etat", "instantane": instantane, "session": str(session.pk)}
    if etat is None:
        return {**message, "prestation": None, "version": 0, "phase": None, "rejeu": 0, "diapositive": None}

    prestation = etat.prestation
    participation = prestation.participation
    message.update(
        prestation={
            "id": str(prestation.pk),
            "candidat": {"numero": participation.numero_candidat, "prenom": participation.candidat.prenom},
            "epreuve": prestation.epreuve.nom,
            "serie": " · ".join(dict.fromkeys(d["serie"] for d in etat.plan)),
        },
        version=etat.version,
        phase=etat.phase,
        rejeu=etat.rejeu,
        diapositive=None,
    )
    if etat.index is not None:
        brute = etat.plan[etat.index]
        diapositive = {"index": brute["index"], "total": brute["total"], "type": brute["type"]}
        if brute["type"] != "fin_serie":
            diapositive["question"] = {
                "rang": brute["question_rang"], "total": brute["question_total"], "libelle": brute["libelle"],
            }
        if brute["type"] == "verset":
            diapositive["reference"] = brute["reference"]
            diapositive["segment"] = {"rang": brute["segment_rang"], "total": brute["segment_total"]}
        if brute["type"] in ("verset", "enonce") and texte_autorise(role, prestation.epreuve):
            diapositive["texte"] = diapositives.texte_de(brute)
        message["diapositive"] = diapositive
    return message
