"""Mesures de la simulation de charge : percentiles et verdict par objectif (§18.1, REC-19, REC-20)."""
import math
from dataclasses import dataclass, field


def percentile(valeurs, p):
    """Percentile « rang le plus proche » (nearest-rank) : la plus petite valeur telle qu'au moins p % des mesures lui sont ≤.

    Pas d'interpolation : un objectif « 95 % en moins de 300 ms » se lit exactement ainsi. Vide : ``None``.
    """
    if not valeurs:
        return None
    triees = sorted(valeurs)
    rang = max(1, math.ceil(p / 100 * len(triees)))
    return triees[rang - 1]


@dataclass
class Mesures:
    """Les durées (en secondes) d'une famille d'opérations, plus le nombre d'échecs."""

    nom: str
    durees: list = field(default_factory=list)
    echecs: int = 0

    def ajouter(self, duree):
        self.durees.append(duree)

    def echec(self):
        self.echecs += 1

    def resume(self):
        d = self.durees
        return {
            "nom": self.nom, "n": len(d), "echecs": self.echecs,
            "moyenne": (sum(d) / len(d)) if d else None,
            "p50": percentile(d, 50), "p95": percentile(d, 95), "p99": percentile(d, 99), "max": max(d) if d else None,
        }


@dataclass
class Objectif:
    """« Au moins ``p`` % des mesures de ``mesures`` sont sous ``seuil`` secondes, sans aucun échec »."""

    libelle: str
    mesures: Mesures
    seuil: float
    p: float = 95

    def verdict(self):
        valeur = percentile(self.mesures.durees, self.p)
        atteint = valeur is not None and valeur < self.seuil and self.mesures.echecs == 0
        return {"libelle": self.libelle, "valeur": valeur, "seuil": self.seuil, "p": self.p,
                "n": len(self.mesures.durees), "echecs": self.mesures.echecs, "atteint": atteint}


def ms(secondes):
    return "—" if secondes is None else f"{secondes * 1000:.0f} ms"


def rapport_texte(objectifs, mesures):
    """Rapport Markdown : tableau des mesures puis verdict de chaque objectif."""
    lignes = ["| Opération | n | échecs | moyenne | p50 | p95 | p99 | max |", "|---|---|---|---|---|---|---|---|"]
    for m in mesures:
        r = m.resume()
        lignes.append(f"| {r['nom']} | {r['n']} | {r['echecs']} | {ms(r['moyenne'])} | {ms(r['p50'])} | {ms(r['p95'])} | {ms(r['p99'])} | {ms(r['max'])} |")
    lignes += ["", "| Objectif | mesuré | seuil | échecs | verdict |", "|---|---|---|---|---|"]
    for objectif in objectifs:
        v = objectif.verdict()
        lignes.append(f"| {v['libelle']} | p{v['p']:g} = {ms(v['valeur'])} (n={v['n']}) | < {ms(v['seuil'])} | {v['echecs']} | {'ATTEINT' if v['atteint'] else 'NON ATTEINT'} |")
    return "\n".join(lignes)
