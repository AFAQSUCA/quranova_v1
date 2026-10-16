"""Navigation latérale de l'administration (sidebar, recherche globale, profil).

Le menu est décrit ici, en clair, plutôt que déduit de `admin.site.get_app_list` : on choisit les
groupes, l'ordre, les libellés et les icônes. Chaque entrée n'apparaît que si le modèle est enregistré
dans l'administration ET si l'utilisateur a le droit de le consulter (règle absolue n°4 : la
permission se vérifie côté serveur ; masquer un lien ne protège rien, mais évite de proposer
des impasses).

Les compteurs passent par `get_queryset(request)` de l'administration du modèle : ils respectent donc
le cloisonnement par client (RM-20) — un opérateur ne voit jamais le nombre de candidats d'un autre client.
"""
from django.apps import apps
from django.contrib import admin
from django.urls import NoReverseMatch, reverse

# (clé du groupe, titre, [(app, modèle, libellé, icône, avec_compteur)])
GROUPES = (
    ("candidats", "Candidats", (
        ("candidats", "candidat", "Candidats", "users", True),
        ("candidats", "consentement", "Consentements", "shield", True),
        ("candidats", "participation", "Participations", "clipboard", True),
    )),
    ("clients", "Clients", (
        ("clients", "mission", "Missions", "briefcase", True),
        ("clients", "organisation", "Organisations", "building", True),
    )),
    ("concours", "Concours", (
        ("concours", "categorie", "Catégories", "tag", True),
        ("concours", "concours", "Concours", "trophy", True),
        ("concours", "session", "Sessions", "calendar", True),
        ("concours", "epreuve", "Épreuves", "flag", True),
    )),
    ("salle", "Salle", (
        ("prestations", "prestation", "Prestations", "mic", True),
        ("prestations", "tirage", "Tirages", "shuffle", False),
        ("prestations", "terminal", "Terminaux", "tablet", False),
        ("questions", "question", "Questions", "help", False),
        ("questions", "lot", "Lots", "layers", False),
        ("questions", "serie", "Séries", "list", False),
        ("jury", "jure", "Jurés", "scale", True),
        ("jury", "codeaccesjure", "Codes d'accès", "key", False),
        ("jury", "correctionnote", "Corrections de notes", "edit", False),
    )),
    ("resultats", "Résultats", (
        ("resultats", "classement", "Classements définitifs", "chart", False),
    )),
    ("corpus", "Corpus coranique", (
        ("coran", "versioncorpus", "Versions du corpus", "book", False),
        ("coran", "sourate", "Sourates", "book-open", False),
        ("coran", "verset", "Versets", "text", False),
    )),
    ("suivi", "Suivi", (
        ("incidents", "incident", "Incidents", "alert", True),
        ("audit", "entreeaudit", "Journal d'audit", "history", False),
    )),
    ("comptes", "Comptes", (
        ("utilisateurs", "utilisateur", "Utilisateurs", "user", False),
        ("utilisateurs", "affectationoperateur", "Affectations", "link", False),
    )),
)

LIBELLES_ROLES = {
    "administrateur": "Administrateur",
    "operateur": "Opérateur",
    "responsable_client": "Responsable client",
}


def _initiales(utilisateur) -> str:
    nom = (utilisateur.get_full_name() or utilisateur.get_username() or "?").strip()
    mots = nom.replace("-", " ").split()
    if len(mots) >= 2:
        return (mots[0][0] + mots[-1][0]).upper()
    return nom[:2].upper()


def _entree(request, app, nom_modele, libelle, icone, avec_compteur):
    """Une entrée du menu, ou None si le modèle n'est pas visible pour cet utilisateur."""
    try:
        modele = apps.get_model(app, nom_modele)
    except LookupError:
        return None
    gestionnaire = admin.site._registry.get(modele)
    if gestionnaire is None or not gestionnaire.has_view_or_change_permission(request):
        return None
    try:
        url = reverse(f"admin:{app}_{nom_modele}_changelist")
    except NoReverseMatch:
        return None
    compteur = gestionnaire.get_queryset(request).count() if avec_compteur else None
    return {
        "libelle": libelle,
        "icone": icone,
        "url": url,
        "compteur": compteur,
        "actif": request.path.startswith(url),
        "peut_ajouter": gestionnaire.has_add_permission(request),
    }


def navigation_admin(request):
    """Processeur de contexte : n'agit que sur les pages d'administration d'un utilisateur connecté."""
    utilisateur = getattr(request, "user", None)
    if not (utilisateur and utilisateur.is_authenticated and utilisateur.is_active and utilisateur.is_staff):
        return {}
    if not request.path.startswith("/admin/"):
        return {}
    groupes = []
    for cle, titre, entrees in GROUPES:
        visibles = [e for e in (_entree(request, *entree) for entree in entrees) if e]
        if visibles:
            groupes.append({
                "cle": cle,
                "titre": titre,
                "entrees": visibles,
                "actif": any(e["actif"] for e in visibles),
            })
    role = getattr(utilisateur, "role", "")
    return {
        "q_groupes": groupes,
        "q_profil": {
            "nom": utilisateur.get_full_name() or utilisateur.get_username(),
            "identifiant": utilisateur.get_username(),
            "initiales": _initiales(utilisateur),
            "role": LIBELLES_ROLES.get(role, role),
        },
        "q_candidats_url": next(
            (e["url"] for g in groupes for e in g["entrees"] if e["url"].endswith("/candidats/candidat/")), ""
        ),
    }
