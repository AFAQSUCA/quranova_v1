"""Procès-verbal de validation du corpus (§12.2 point 7, livrable L-07) : le document que le référent coranique relit et signe.

Même principe que pour le procès-verbal d'un concours : un seul HTML, imprimable tel quel ou converti en PDF (WeasyPrint). Le texte coranique est
AFFICHÉ tel qu'il est en base (``lang="ar" dir="rtl"``), jamais modifié ni retapé (règle absolue n° 1).
"""
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.services import journaliser
from apps.coran import validation
from apps.resultats import pdf


def _contexte(version, auteur):
    echantillon = validation.echantillon_de_relecture(version)
    controles = validation.controles_automatiques(version)
    groupes = []
    for ligne in echantillon:
        if not groupes or groupes[-1]["motif"] != ligne.motif:
            groupes.append({"motif": ligne.motif, "lignes": []})
        groupes[-1]["lignes"].append(ligne)
    return {
        "version": version, "controles": controles, "tous_ok": all(c.ok for c in controles), "groupes": groupes,
        "nombre_echantillon": len(echantillon), "empreinte_echantillon": validation.empreinte_echantillon(version, echantillon),
        "validation": getattr(version, "validation", None),  # RelatedObjectDoesNotExist est un AttributeError : getattr rend None
        "genere_le": timezone.now(), "auteur": auteur,
    }


def proces_verbal_corpus(version, auteur=None):
    html = render_to_string("documents/pv_corpus.html", _contexte(version, auteur))
    journaliser("document.pv_corpus_genere", auteur=auteur, objet=version, details={"version": version.pk, "format": "html"})
    return html


def proces_verbal_corpus_pdf(version, auteur=None):
    contenu = pdf.html_vers_pdf(render_to_string("documents/pv_corpus.html", _contexte(version, auteur)))
    journaliser("document.pv_corpus_genere", auteur=auteur, objet=version, details={"version": version.pk, "format": "pdf", "octets": len(contenu)})
    return contenu
