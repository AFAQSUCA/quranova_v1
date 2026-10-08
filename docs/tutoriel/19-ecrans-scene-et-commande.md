# Chapitre 19 — Les écrans de scène et de commande (itération 3, étape 3d)

> **Commit de référence :** `c63d1dc` · **Durée :** 8 à 10 heures · **Résultat :** le diaporama fonctionne : l'opérateur commande, la scène suit, avec le balayage de droite à gauche, le texte arabe de droite à gauche, la reconnexion automatique. **9 tests Python** (pages) et **70 tests du front** au total.

## Objectif

| Règle | Où elle est appliquée |
|---|---|
| **RM-10, RM-11** : une diapositive à la fois, avancement manuel | le store n'avance que sur commande de l'opérateur |
| **RM-12** : balayage de droite à gauche | `<Transition name="balayage">` : la nouvelle diapositive entre par la droite |
| **§9.2** : texte arabe RTL | `lang="ar" dir="rtl"` ; le sens du balayage n'a **aucun** effet sur l'ordre du texte |
| **REC-24** : pas de double saut | une seule commande en attente à la fois ; les boutons se grisent |
| **REC-21, 23** : coupure et reprise | reconnexion 0,5 s → 1 s → 2 s → 5 s ; la diapositive reste affichée ; instantané sans animation |
| **RM-14, D15** : texte réservé | si l'épreuve n'affiche pas le texte à la scène : « Présentation en cours » |

## Ce qu'il faut comprendre

- **`ClientWS`** (`commun/client.ts`) : une connexion WebSocket qui se rétablit toute seule, avec un battement toutes les 15 s. Elle ne connaît rien du métier : le store lui donne ses fonctions de rappel.
- **`decider`** (`commun/protocole.ts`) : la table du §5 du protocole sous forme d'une **fonction pure**, testée cas par cas (version suivante, déjà vue, trou, instantané, autre prestation).
- **Le store** (`commun/store.ts`) : il applique `decider`, garde **une seule commande en attente** et la **renvoie avec le même identifiant** après une reconnexion.
- **Les composants** n'ont pas de logique métier : ils affichent l'état du store ; les boutons de la commande ne sont que **grisés** selon la phase, c'est le serveur qui décide.

## Étape A — Pages et liste des prestations côté Django

**Fichier `apps\presentation\tests\test_vues.py`**

```python
"""Tests des pages de scène et de commande et de la liste des prestations (§9, REC-25, REC-29)."""
import pytest
from django.urls import reverse

from apps.commun.tests.outils import creer_mission, creer_session, creer_utilisateur
from apps.presentation.tests.outils import creer_prestation_tiree, operateur_de
from apps.prestations.tests.outils import creer_prestation
from apps.utilisateurs.models import AffectationOperateur, Utilisateur


@pytest.fixture
def poste(db):
    prestation, epreuve, _ = creer_prestation_tiree()
    return prestation, prestation.session, operateur_de(epreuve)


def url(nom, session):
    return reverse(f"presentation:{nom}", args=[session.pk])


@pytest.mark.django_db
def test_la_page_de_scene_est_publique_et_vide(client, poste):
    _, session, _ = poste

    reponse = client.get(url("ecran_scene", session))

    contenu = reponse.content.decode()
    assert reponse.status_code == 200 and 'id="app"' in contenu and "scene.js" in contenu


@pytest.mark.django_db
def test_la_commande_renvoie_un_anonyme_vers_la_connexion(client, poste):
    _, session, _ = poste

    reponse = client.get(url("ecran_commande", session))

    assert reponse.status_code == 302 and "login" in reponse.url


@pytest.mark.django_db
def test_la_commande_s_ouvre_pour_l_operateur_affecte(client, poste):
    _, session, operateur = poste
    client.force_login(operateur)

    reponse = client.get(url("ecran_commande", session))

    assert reponse.status_code == 200 and "commande.js" in reponse.content.decode()


@pytest.mark.django_db
def test_rec29_un_operateur_sans_acces_a_la_mission_obtient_404(client, poste):
    _, session, _ = poste
    etranger = creer_utilisateur(Utilisateur.Role.OPERATEUR)
    AffectationOperateur.objects.create(mission=creer_mission(), utilisateur=etranger)
    client.force_login(etranger)

    assert client.get(url("ecran_commande", session)).status_code == 404
    assert client.get(url("prestations", session)).status_code == 404


@pytest.mark.django_db
def test_un_responsable_client_ne_commande_pas_le_diaporama(client, poste):
    _, session, _ = poste
    client.force_login(creer_utilisateur(Utilisateur.Role.RESPONSABLE_CLIENT, organisation=session.organisation))

    assert client.get(url("ecran_commande", session)).status_code == 404


@pytest.mark.django_db
def test_une_session_inexistante_donne_404(client, poste):
    _, _, operateur = poste
    client.force_login(operateur)

    reponse = client.get(reverse("presentation:ecran_commande", args=["00000000-0000-0000-0000-000000000000"]))

    assert reponse.status_code == 404


@pytest.mark.django_db
def test_la_liste_des_prestations_exige_une_connexion(client, poste):
    _, session, _ = poste

    assert client.get(url("prestations", session)).status_code == 401


@pytest.mark.django_db
def test_la_liste_des_prestations_donne_le_numero_et_le_prenom_sans_nom_de_famille(client, poste):
    prestation, session, operateur = poste
    client.force_login(operateur)

    reponse = client.get(url("prestations", session))

    (ligne,) = reponse.json()["prestations"]
    assert ligne["id"] == str(prestation.pk) and ligne["etat"] == "tire"
    assert ligne["prenom"] == prestation.participation.candidat.prenom
    assert prestation.participation.candidat.nom not in reponse.content.decode()
    assert "no-store" in reponse["Cache-Control"]


@pytest.mark.django_db
def test_la_liste_ne_contient_que_les_prestations_de_la_session(client, poste):
    prestation, session, operateur = poste
    creer_prestation(prestation.epreuve, session=creer_session(session.concours))  # autre session du même concours
    client.force_login(operateur)

    assert len(client.get(url("prestations", session)).json()["prestations"]) == 1
```

**Fichier `apps\presentation\views.py`**

```python
"""Pages des écrans de scène et de commande, et liste des prestations pour la commande (§9.3, §9.4).

La page de scène est publique et vide : ses données passent par le WebSocket, protégé par le jeton (D38). La page
de commande exige un opérateur connecté, affecté à la mission ; sinon elle répond « introuvable », sans rien révéler
d'une session d'un autre client (REC-25, REC-29).
"""
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.concours.models import Session
from apps.prestations.models import Prestation
from apps.presentation.services import peut_commander


def _session_commandable(request, session_id):
    session = get_object_or_404(Session.objects.select_related("concours"), pk=session_id)
    if not peut_commander(request.user, session):
        raise Http404  # ni 403 ni détail : on ne confirme pas l'existence de la session
    return session


@require_GET
def ecran_scene(request, session_id):
    return render(request, "scene.html", {"session_id": session_id})


@require_GET
def ecran_commande(request, session_id):
    if not request.user.is_authenticated:
        return redirect(f"{reverse('admin:login')}?next={request.path}")
    session = _session_commandable(request, session_id)
    return render(request, "commande.html", {"session_id": session.pk})


@require_GET
def prestations_de_la_session(request, session_id):
    if not request.user.is_authenticated:
        return JsonResponse({"code": "non_authentifie"}, status=401)
    session = _session_commandable(request, session_id)
    prestations = (
        Prestation.objects.filter(session=session)
        .select_related("participation__candidat", "epreuve")
        .order_by("rang_passage")
    )
    reponse = JsonResponse(
        {
            "prestations": [
                {
                    "id": str(p.pk),
                    "rang": p.rang_passage,
                    "numero": p.participation.numero_candidat,
                    "prenom": p.participation.candidat.prenom,  # jamais de nom de famille dans un écran partagé (D34)
                    "epreuve": p.epreuve.nom,
                    "etat": p.etat,
                }
                for p in prestations
            ]
        }
    )
    reponse["Cache-Control"] = "no-store"
    return reponse
```

**Fichier `apps\presentation\urls.py`**

```python
from django.urls import path

from apps.presentation import views

app_name = "presentation"

urlpatterns = [
    path("scene/<uuid:session_id>/", views.ecran_scene, name="ecran_scene"),
    path("commande/<uuid:session_id>/", views.ecran_commande, name="ecran_commande"),
    path("api/operateur/session/<uuid:session_id>/prestations/", views.prestations_de_la_session, name="prestations"),
]
```

**Fichier `config\urls.py`**

```python
"""Routes racine du projet QURANOVA."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="accueil.html"), name="accueil"),
    path("admin/", admin.site.urls),
    path("", include("apps.prestations.urls")),
    path("", include("apps.presentation.urls")),
]
```

Trois gabarits (le gabarit `tirage.html` change aussi : le fichier de style devient `frontend.css` et le `<body>` reçoit la classe `page-tirage`) :

**Fichier `templates\scene.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>QURANOVA — Scène</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="{% static 'frontend/frontend.css' %}">
</head>
<body>
  <div id="app"></div>
  <noscript>Cet écran nécessite JavaScript.</noscript>
  <script type="module" src="{% static 'frontend/scene.js' %}"></script>
</body>
</html>
```

**Fichier `templates\commande.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>QURANOVA — Commande</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="{% static 'frontend/frontend.css' %}">
</head>
<body>
  <div id="app"></div>
  <noscript>Cet écran nécessite JavaScript.</noscript>
  <script type="module" src="{% static 'frontend/commande.js' %}"></script>
</body>
</html>
```

**Fichier `templates\tirage.html`**

```html
{% load static %}<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
  <meta name="robots" content="noindex">
  <title>QURANOVA — Tirage</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="{% static 'frontend/frontend.css' %}">
</head>
<body class="page-tirage">
  <div id="app"></div>
  <noscript>Cet écran nécessite JavaScript.</noscript>
  <script type="module" src="{% static 'frontend/tirage.js' %}"></script>
</body>
</html>
```

L'administration affiche pour un terminal de scène l'adresse `/scene/<session>/#<jeton>` (fichier `apps\prestations\admin.py`, déjà fourni au chapitre 15, avec la branche `SCENE`).

**Fichier `apps\prestations\admin.py`**

```python
"""Administration des prestations et des tirages (§8.3, §14.2)."""
from django.contrib import admin, messages
from django.urls import reverse

from apps.commun.admin import AdminDuClient, ConsultationSeule, appliquer_action
from apps.prestations import terminaux
from apps.prestations.exceptions import AppelInvalideError
from apps.prestations.models import Prestation, Terminal, Tirage


@admin.register(Prestation)
class PrestationAdmin(AdminDuClient):
    list_display = ("rang_passage", "participation", "epreuve", "session", "etat")
    list_filter = ("etat", "epreuve", "session")
    readonly_fields = ("etat",)  # l'état ne change que par les services (tirage, diaporama, notation)
    actions = ["appeler_au_tirage"]

    @admin.action(description="Appeler au tirage (terminal de la session)")
    def appeler_au_tirage(self, request, queryset):
        def appeler(prestation):
            actifs = list(prestation.session.terminaux.filter(type=Terminal.Type.TIRAGE, revoque_le__isnull=True))
            if len(actifs) != 1:
                raise AppelInvalideError(
                    f"{len(actifs)} terminal(aux) actif(s) pour cette session : il en faut exactement un."
                )
            terminaux.appeler_prestation(actifs[0], prestation, request.user)

        appliquer_action(request, queryset, appeler, "candidat appelé sur le terminal de tirage")


@admin.register(Tirage)
class TirageAdmin(ConsultationSeule):
    """Un tirage ne se crée que par ``effectuer_tirage`` et ne s'annule que par ``annuler_tirage`` (§14.2)."""

    list_display = ("prestation", "serie", "rang", "statut", "terminal", "cree_le")
    list_filter = ("statut", "prestation__epreuve")


@admin.register(Terminal)
class TerminalAdmin(AdminDuClient):
    """Une tablette de tirage. Le jeton n'est affiché qu'une fois, à la création (D31)."""

    list_display = ("nom", "type", "session", "prestation_appelee", "revoque_le", "derniere_activite")
    list_filter = ("session",)
    actions = ["liberer", "revoquer"]

    def get_fields(self, request, obj=None):
        return ("session", "nom", "type") if obj is None else ("session", "nom", "type", "prestation_appelee", "revoque_le", "derniere_activite")

    def get_readonly_fields(self, request, obj=None):
        return ("session", "nom", "type", "prestation_appelee", "revoque_le", "derniere_activite") if obj else ()

    def has_change_permission(self, request, obj=None):
        return False if obj else super().has_change_permission(request, obj)

    def save_model(self, request, obj, form, change):
        def creer():
            terminal, jeton = terminaux.creer_terminal(obj.session, obj.nom, obj.type)
            obj.__dict__.update(terminal.__dict__)
            if terminal.type == Terminal.Type.SCENE:
                chemin = reverse("presentation:ecran_scene", args=[terminal.session_id])
            else:
                chemin = reverse("prestations:ecran_tirage")
            adresse = request.build_absolute_uri(chemin) + "#" + jeton
            messages.warning(
                request,
                f"Terminal créé. Ouvrez cette adresse sur la tablette (elle ne sera plus affichée) : {adresse}",
            )

        self.executer_metier(request, creer)

    @admin.action(description="Libérer le terminal (retirer le candidat appelé)")
    def liberer(self, request, queryset):
        appliquer_action(request, queryset, terminaux.liberer_terminal, "terminal libéré")

    @admin.action(description="Révoquer le terminal (le jeton cesse de fonctionner)")
    def revoquer(self, request, queryset):
        appliquer_action(request, queryset, terminaux.revoquer_terminal, "terminal révoqué")
```

## Étape B — Le front : réglages

**Fichier `frontend\vite.config.ts`**

```typescript
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// Le build écrit dans static/frontend/ avec des noms FIXES : le gabarit Django
// templates/tirage.html, scene.html et commande.html les référencent directement (pas de manifeste à lire).
export default defineConfig({
  plugins: [vue()],
  base: "/static/frontend/",
  build: {
    outDir: "../static/frontend",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: { tirage: "src/tirage/main.ts", scene: "src/scene/main.ts", commande: "src/commande/main.ts" },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "partage-[hash].js",
        assetFileNames: "frontend[extname]", // un seul fichier de style pour les trois écrans
      },
    },
  },
  server: {
    // En développement (npm run dev), l'API est celle de Django.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: { environment: "jsdom", globals: true, include: ["src/**/*.test.ts"] },
});
```

**Fichier `frontend\src\tirage\jeton.ts`**

```typescript
export const CLE_TIRAGE = "quranova.jeton_tirage";
export const CLE_SCENE = "quranova.jeton_scene";

/**
 * Le jeton arrive dans le FRAGMENT de l'adresse (`/tirage/#jeton`) : un fragment n'est jamais envoyé
 * au serveur ni écrit dans ses journaux (D31). On le garde dans le stockage de la tablette puis on
 * efface l'adresse, pour que le jeton n'y reste pas affiché.
 */
export function chargerJeton(cle: string = CLE_TIRAGE): string | null {
  const fragment = window.location.hash.replace(/^#/, "").trim();
  if (fragment) {
    try {
      window.localStorage.setItem(cle, fragment);
    } catch {
      // stockage indisponible : le jeton ne vivra que le temps de la page
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return fragment;
  }
  try {
    return window.localStorage.getItem(cle);
  } catch {
    return null;
  }
}

export function oublierJeton(cle: string = CLE_TIRAGE): void {
  try {
    window.localStorage.removeItem(cle);
  } catch {
    // rien à faire
  }
}
```

Dans `frontend\src\tirage\style.css`, la règle globale `html, body {…}` devient `body.page-tirage {…}` pour ne pas déteindre sur les autres écrans.

## Étape C — Le front : le cœur, tests d'abord

**Fichier `frontend\src\commun\outils-test.ts`**

```typescript
import type { EtatPresentation } from "./protocole";
import type { SocketMinimal } from "./client";

export class FauxSocket implements SocketMinimal {
  static instances: FauxSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  envoyes: unknown[] = [];

  constructor(public url: string) {
    FauxSocket.instances.push(this);
  }
  send(donnees: string): void {
    this.envoyes.push(JSON.parse(donnees));
  }
  close(): void {
    this.readyState = 3;
    this.onclose?.();
  }
  // --- côté « serveur » pour les tests ---
  ouvrir(): void {
    this.readyState = 1;
    this.onopen?.();
  }
  recevoir(message: unknown): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  static dernier(): FauxSocket {
    return FauxSocket.instances[FauxSocket.instances.length - 1]!;
  }
}

export function etat(champs: Partial<EtatPresentation> = {}): EtatPresentation {
  return {
    type: "etat",
    session: "s1",
    prestation: { id: "p1", candidat: { numero: 12, prenom: "Awa" }, epreuve: "Mémorisation", serie: "Série 4" },
    version: 1,
    phase: "affichage",
    rejeu: 0,
    diapositive: { index: 0, total: 10, type: "intercalaire_question", question: { rang: 1, total: 3, libelle: "Sourate 2, versets 142 à 150" } },
    ...champs,
  };
}
```

**Fichier `frontend\src\commun\protocole.test.ts`**

```typescript
import { describe, expect, it } from "vitest";

import { decider } from "./protocole";
import { etat } from "./outils-test";

describe("décision sur un message d'état (protocole §5)", () => {
  it("le premier état reçu remplace l'état local", () => {
    expect(decider(null, etat())).toBe("remplacer");
  });
  it("un instantané remplace, sans animation", () => {
    expect(decider(etat({ version: 5 }), etat({ version: 9, instantane: true }))).toBe("remplacer");
  });
  it("la version suivante est appliquée (avec animation)", () => {
    expect(decider(etat({ version: 5 }), etat({ version: 6 }))).toBe("appliquer");
  });
  it("une version déjà vue ou plus ancienne est ignorée", () => {
    expect(decider(etat({ version: 5 }), etat({ version: 5 }))).toBe("ignorer");
    expect(decider(etat({ version: 5 }), etat({ version: 3 }))).toBe("ignorer");
  });
  it("un trou de version déclenche une demande d'instantané", () => {
    expect(decider(etat({ version: 5 }), etat({ version: 8 }))).toBe("snapshot");
  });
  it("une autre prestation remplace, même avec une version plus petite", () => {
    const autre = etat({ version: 1, prestation: { id: "p2", candidat: { numero: 13, prenom: "Ali" }, epreuve: "E", serie: "S" } });
    expect(decider(etat({ version: 7 }), autre)).toBe("remplacer");
  });
});
```

**Fichier `frontend\src\commun\client.test.ts`**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ClientWS, type EtatConnexion } from "./client";
import { FauxSocket } from "./outils-test";

function creer(options: Partial<ConstructorParameters<typeof ClientWS>[0]> = {}) {
  const etats: EtatConnexion[] = [];
  const messages: unknown[] = [];
  const client = new ClientWS({
    url: "ws://test/ws/presentation/s1/",
    creerSocket: (url) => new FauxSocket(url),
    surEtat: (e) => etats.push(e),
    surMessage: (m) => messages.push(m),
    ...options,
  });
  return { client, etats, messages };
}

describe("client WebSocket", () => {
  beforeEach(() => {
    FauxSocket.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("envoie le message d'authentification dès l'ouverture (D38)", () => {
    const { client, etats } = creer({ authentification: () => ({ type: "auth", jeton: "secret" }) });

    client.connecter();
    FauxSocket.dernier().ouvrir();

    expect(FauxSocket.dernier().envoyes).toEqual([{ type: "auth", jeton: "secret" }]);
    expect(etats).toEqual(["connexion", "ouverte"]);
    client.fermer();
  });

  it("transmet les messages JSON et ignore ceux qui sont illisibles", () => {
    const { client, messages } = creer();
    client.connecter();
    const socket = FauxSocket.dernier();
    socket.ouvrir();

    socket.recevoir({ type: "pong" });
    socket.onmessage?.({ data: "pas du json" });

    expect(messages).toEqual([{ type: "pong" }]);
    client.fermer();
  });

  it("envoie un battement toutes les 15 secondes", () => {
    const { client } = creer();
    client.connecter();
    const socket = FauxSocket.dernier();
    socket.ouvrir();

    vi.advanceTimersByTime(15000);
    socket.recevoir({ type: "pong" });
    vi.advanceTimersByTime(15000);

    expect(socket.envoyes.filter((m) => (m as { type: string }).type === "ping")).toHaveLength(2);
    client.fermer();
  });

  it("se reconnecte avec des délais croissants : 0,5 s, 1 s, 2 s, puis 5 s", () => {
    const { client, etats } = creer();
    client.connecter();
    const delais = [500, 1000, 2000, 5000, 5000];

    for (const delai of delais) {
      const avant = FauxSocket.instances.length;
      FauxSocket.dernier().close(); // le réseau coupe, aucune ouverture n'aboutit
      vi.advanceTimersByTime(delai - 1);
      expect(FauxSocket.instances).toHaveLength(avant); // pas encore
      vi.advanceTimersByTime(1);
      expect(FauxSocket.instances).toHaveLength(avant + 1); // reconnexion après exactement ce délai
    }
    expect(etats.filter((e) => e === "perdue")).toHaveLength(5);
    client.fermer();
  });

  it("après une reconnexion réussie, les délais repartent de 0,5 s", () => {
    const { client } = creer();
    client.connecter();
    FauxSocket.dernier().close();
    vi.advanceTimersByTime(500);
    FauxSocket.dernier().close();
    vi.advanceTimersByTime(1000);
    FauxSocket.dernier().ouvrir(); // rétabli

    const avant = FauxSocket.instances.length;
    FauxSocket.dernier().close();
    vi.advanceTimersByTime(500);

    expect(FauxSocket.instances).toHaveLength(avant + 1);
    client.fermer();
  });

  it("sans aucun message pendant 30 secondes, la connexion est jugée perdue", () => {
    const { client, etats } = creer();
    client.connecter();
    FauxSocket.dernier().ouvrir();

    vi.advanceTimersByTime(29000);
    expect(etats).not.toContain("perdue");
    vi.advanceTimersByTime(2000);

    expect(etats).toContain("perdue");
    client.fermer();
  });

  it("un message reçu repousse l'échéance des 30 secondes", () => {
    const { client, etats } = creer();
    client.connecter();
    const socket = FauxSocket.dernier();
    socket.ouvrir();

    vi.advanceTimersByTime(20000);
    socket.recevoir({ type: "pong" });
    vi.advanceTimersByTime(20000);

    expect(etats).not.toContain("perdue");
    client.fermer();
  });

  it("une fois arrêté, il ne se reconnecte plus", () => {
    const { client } = creer();
    client.connecter();

    client.fermer();
    vi.advanceTimersByTime(60000);

    expect(FauxSocket.instances).toHaveLength(1);
  });

  it("envoyer renvoie faux quand la connexion n'est pas ouverte", () => {
    const { client } = creer();
    client.connecter();

    expect(client.envoyer({ type: "ping" })).toBe(false);
    FauxSocket.dernier().ouvrir();
    expect(client.envoyer({ type: "ping" })).toBe(true);
    client.fermer();
  });
});
```

**Fichier `frontend\src\commun\store.test.ts`**

```typescript
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { etat, FauxSocket } from "./outils-test";
import { usePresentationStore } from "./store";

function demarre(jeton: string | null = null) {
  const store = usePresentationStore();
  vi.stubGlobal("WebSocket", FauxSocket);
  store.demarrer("ws://test/ws/presentation/s1/", jeton);
  const socket = FauxSocket.dernier();
  socket.ouvrir();
  return { store, socket };
}

const commandes = (socket: FauxSocket) => socket.envoyes.filter((m) => (m as { type: string }).type === "commande") as { id: string; version_attendue: number | null; action: string }[];

describe("store de présentation", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    FauxSocket.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("un instantané reconstruit l'écran sans animation", () => {
    const { store, socket } = demarre();

    socket.recevoir(etat({ version: 17, instantane: true }));

    expect(store.etat?.version).toBe(17);
    expect(store.animer).toBe(false);
    store.arreter();
  });

  it("une diffusion à la version suivante est appliquée avec animation", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));

    socket.recevoir(etat({ version: 18 }));

    expect(store.etat?.version).toBe(18);
    expect(store.animer).toBe(true);
    store.arreter();
  });

  it("une version déjà vue est ignorée", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));
    socket.recevoir(etat({ version: 18 }));

    socket.recevoir(etat({ version: 17 }));

    expect(store.etat?.version).toBe(18);
    store.arreter();
  });

  it("un trou de version demande un instantané et n'applique rien (message perdu)", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 18, instantane: true }));

    socket.recevoir(etat({ version: 20 })); // la 19 s'est perdue

    expect(store.etat?.version).toBe(18);
    expect(socket.envoyes).toContainEqual({ type: "snapshot" });
    socket.recevoir(etat({ version: 20, instantane: true }));
    expect(store.etat?.version).toBe(20);
    expect(store.animer).toBe(false);
    store.arreter();
  });

  it("commande : la version attendue est celle de l'état courant", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));

    store.commander("suivante");

    expect(commandes(socket)).toEqual([expect.objectContaining({ action: "suivante", version_attendue: 17 })]);
    store.arreter();
  });

  it("REC-24 : un deuxième clic pendant l'attente de la réponse n'envoie rien", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));

    store.commander("suivante");
    store.commander("suivante");

    expect(commandes(socket)).toHaveLength(1);
    store.arreter();
  });

  it("l'accusé de réception libère les boutons", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));
    store.commander("suivante");
    const id = commandes(socket)[0]!.id;

    socket.recevoir({ type: "ack", id, statut: "appliquee", version: 18 });

    expect(store.enAttente).toBeNull();
    expect(store.message).toBeNull();
    store.commander("pause");
    expect(commandes(socket)).toHaveLength(2);
    store.arreter();
  });

  it("un refus pour version obsolète affiche un message et ne renvoie rien tout seul", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));
    store.commander("suivante");
    const id = commandes(socket)[0]!.id;

    socket.recevoir({ type: "ack", id, statut: "rejetee", raison: "version_obsolete", version: 18 });

    expect(store.enAttente).toBeNull();
    expect(store.message).toContain("pas à jour");
    expect(commandes(socket)).toHaveLength(1);
    store.arreter();
  });

  it("REC-21 : une commande sans réponse est renvoyée avec le MÊME identifiant après la reconnexion", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));
    store.commander("suivante");
    const premiere = commandes(socket)[0]!;

    socket.close(); // le Wi-Fi coupe avant l'accusé de réception
    vi.advanceTimersByTime(500);
    const nouveau = FauxSocket.dernier();
    nouveau.ouvrir();

    expect(commandes(nouveau)).toEqual([premiere]); // même id, même version attendue
    nouveau.recevoir({ type: "ack", id: premiere.id, statut: "deja_traitee", version: 18 });
    expect(store.enAttente).toBeNull();
    store.arreter();
  });

  it("préparer n'exige pas de version attendue et désigne la prestation", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 3, instantane: true }));

    store.commander("preparer", { prestation: "p9" });

    expect(socket.envoyes.at(-1)).toMatchObject({ action: "preparer", version_attendue: null, prestation: "p9" });
    store.arreter();
  });

  it("mémorise la liste des écrans reçue de l'opérateur", () => {
    const { store, socket } = demarre();

    socket.recevoir({ type: "ecrans", ecrans: [{ nom: "Scène 1", type: "scene", connecte: true }] });

    expect(store.ecrans).toEqual([{ nom: "Scène 1", type: "scene", connecte: true }]);
    store.arreter();
  });

  it("l'état local est conservé quand la connexion est perdue (mieux vaut une diapositive figée)", () => {
    const { store, socket } = demarre();
    socket.recevoir(etat({ version: 17, instantane: true }));

    socket.close();

    expect(store.connexion).toBe("perdue");
    expect(store.etat?.version).toBe(17);
    store.arreter();
  });
});
```

**Fichier `frontend\src\commun\protocole.ts`**

```typescript
/** Types et règles du protocole temps réel (docs/conception/protocole-temps-reel.md). */

export interface Diapositive {
  index: number;
  total: number;
  type: "intercalaire_question" | "verset" | "enonce" | "fin_question" | "fin_serie";
  question?: { rang: number; total: number; libelle: string };
  reference?: string;
  segment?: { rang: number; total: number };
  texte?: string; // absent pour un écran non autorisé (RM-14)
}

export interface EtatPresentation {
  type: "etat";
  instantane?: boolean;
  session: string;
  prestation: { id: string; candidat: { numero: number; prenom: string }; epreuve: string; serie: string } | null;
  version: number;
  phase: "preparee" | "affichage" | "pause" | "terminee" | null;
  rejeu: number;
  diapositive: Diapositive | null;
}

export interface Ack {
  type: "ack";
  id: string;
  statut: "appliquee" | "deja_traitee" | "rejetee";
  version: number;
  raison?: string;
}

export interface Ecrans {
  type: "ecrans";
  ecrans: { nom: string; type: string; connecte: boolean }[];
}

export type MessageServeur = EtatPresentation | Ack | Ecrans | { type: "pong" } | { type: "erreur"; code: string };

export interface Commande {
  type: "commande";
  id: string;
  version_attendue: number | null;
  action: string;
  prestation?: string;
}

export type Decision = "remplacer" | "appliquer" | "ignorer" | "snapshot";

/**
 * Que faire d'un message `etat` ? (protocole §5)
 * - instantané, premier état ou autre prestation : on REMPLACE, sans animation ;
 * - version suivante : on applique (avec animation) ;
 * - version déjà vue ou plus ancienne : on ignore ;
 * - trou de version : un message s'est perdu, on redemande un instantané.
 */
export function decider(local: EtatPresentation | null, recu: EtatPresentation): Decision {
  if (recu.instantane || local === null) return "remplacer";
  if ((local.prestation?.id ?? null) !== (recu.prestation?.id ?? null)) return "remplacer";
  if (recu.version === local.version + 1) return "appliquer";
  if (recu.version <= local.version) return "ignorer";
  return "snapshot";
}

export const RAISONS: Record<string, string> = {
  version_obsolete: "L'écran n'était pas à jour : l'action n'a pas été appliquée. Vérifiez l'affichage puis recommencez.",
  transition_interdite: "Cette action n'est pas possible dans l'état actuel.",
  non_autorise: "Action non autorisée.",
  commande_inconnue: "Commande inconnue.",
};
```

**Fichier `frontend\src\commun\client.ts`**

```typescript
export type EtatConnexion = "connexion" | "ouverte" | "perdue";

export interface SocketMinimal {
  onopen: (() => void) | null;
  onmessage: ((e: { data: unknown }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  send(donnees: string): void;
  close(): void;
  readyState: number;
}

export interface OptionsClient {
  url: string;
  surMessage: (message: unknown) => void;
  surEtat: (etat: EtatConnexion) => void;
  /** Message à envoyer dès l'ouverture (authentification de la scène, D38). */
  authentification?: () => object | null;
  creerSocket?: (url: string) => SocketMinimal;
  delais?: number[];
  intervallePing?: number;
  delaiPerte?: number;
}

const OUVERT = 1;

/**
 * Connexion WebSocket qui se rétablit toute seule (protocole §4.2, §7 ; REC-21).
 * - battement (ping) toutes les 15 s ; sans AUCUN message reçu pendant 30 s, la connexion est jugée perdue ;
 * - reconnexion avec des délais croissants : 0,5 s, 1 s, 2 s, puis 5 s au maximum.
 */
export class ClientWS {
  private socket: SocketMinimal | null = null;
  private tentative = 0;
  private derniereReception = 0;
  private minuteurPing: ReturnType<typeof setInterval> | null = null;
  private minuteurSurveillance: ReturnType<typeof setInterval> | null = null;
  private minuteurReconnexion: ReturnType<typeof setTimeout> | null = null;
  private arrete = false;
  private readonly delais: number[];
  private readonly intervallePing: number;
  private readonly delaiPerte: number;

  constructor(private options: OptionsClient) {
    this.delais = options.delais ?? [500, 1000, 2000, 5000];
    this.intervallePing = options.intervallePing ?? 15000;
    this.delaiPerte = options.delaiPerte ?? 30000;
  }

  connecter(): void {
    this.arrete = false;
    this.options.surEtat("connexion");
    const creer = this.options.creerSocket ?? ((url: string) => new WebSocket(url) as unknown as SocketMinimal);
    const socket = creer(this.options.url);
    this.socket = socket;
    socket.onopen = () => {
      this.tentative = 0;
      this.derniereReception = Date.now();
      const auth = this.options.authentification?.();
      if (auth) socket.send(JSON.stringify(auth));
      this.options.surEtat("ouverte");
      this.demarrerSurveillance();
    };
    socket.onmessage = (evenement) => {
      this.derniereReception = Date.now();
      try {
        this.options.surMessage(JSON.parse(String(evenement.data)));
      } catch {
        // message illisible : ignoré, la connexion continue
      }
    };
    socket.onclose = () => this.perdue(socket);
    socket.onerror = () => this.perdue(socket);
  }

  envoyer(message: object): boolean {
    if (this.socket && this.socket.readyState === OUVERT) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  fermer(): void {
    this.arrete = true;
    this.arreterSurveillance();
    if (this.minuteurReconnexion) clearTimeout(this.minuteurReconnexion);
    this.socket?.close();
    this.socket = null;
  }

  private demarrerSurveillance(): void {
    this.arreterSurveillance();
    this.minuteurPing = setInterval(() => this.envoyer({ type: "ping" }), this.intervallePing);
    this.minuteurSurveillance = setInterval(() => {
      if (Date.now() - this.derniereReception > this.delaiPerte && this.socket) {
        const socket = this.socket;
        socket.close(); // le serveur ne répond plus : on bascule en reconnexion
        this.perdue(socket);
      }
    }, 1000);
  }

  private arreterSurveillance(): void {
    if (this.minuteurPing) clearInterval(this.minuteurPing);
    if (this.minuteurSurveillance) clearInterval(this.minuteurSurveillance);
    this.minuteurPing = this.minuteurSurveillance = null;
  }

  private perdue(socket: SocketMinimal): void {
    if (this.arrete || socket !== this.socket) return; // un ancien socket ne déclenche rien
    this.socket = null;
    this.arreterSurveillance();
    this.options.surEtat("perdue");
    const delai = this.delais[Math.min(this.tentative, this.delais.length - 1)] ?? 5000;
    this.tentative += 1;
    this.minuteurReconnexion = setTimeout(() => this.connecter(), delai);
  }
}
```

**Fichier `frontend\src\commun\store.ts`**

```typescript
import { defineStore } from "pinia";
import { ref } from "vue";

import { ClientWS, type EtatConnexion } from "./client";
import { decider, RAISONS, type Ack, type Commande, type EtatPresentation, type Ecrans } from "./protocole";

export interface PrestationListee {
  id: string;
  rang: number;
  numero: number;
  prenom: string;
  epreuve: string;
  etat: string;
}

/**
 * État de présentation côté écran. Le SERVEUR détient la vérité : ce store n'est qu'un reflet qui applique
 * les règles du protocole (versions, instantanés) et ne calcule jamais une diapositive lui-même.
 */
export const usePresentationStore = defineStore("presentation", () => {
  const connexion = ref<EtatConnexion>("connexion");
  const etat = ref<EtatPresentation | null>(null);
  /** Vrai quand la transition doit être animée (diffusion), faux pour un instantané (reconstruction). */
  const animer = ref(false);
  const ecrans = ref<Ecrans["ecrans"]>([]);
  const enAttente = ref<Commande | null>(null);
  const message = ref<string | null>(null);
  let client: ClientWS | null = null;

  function demarrer(url: string, jeton: string | null): void {
    client = new ClientWS({
      url,
      authentification: jeton ? () => ({ type: "auth", jeton }) : undefined,
      surEtat: (nouvelEtat) => {
        connexion.value = nouvelEtat;
        // Reconnexion : une commande restée sans réponse repart avec le MÊME identifiant (idempotence, RM-30).
        if (nouvelEtat === "ouverte" && enAttente.value) client?.envoyer(enAttente.value);
      },
      surMessage: recevoir,
    });
    client.connecter();
  }

  function arreter(): void {
    client?.fermer();
    client = null;
  }

  function recevoir(brut: unknown): void {
    const recu = brut as { type?: string };
    if (recu.type === "etat") {
      const nouveau = brut as EtatPresentation;
      const decision = decider(etat.value, nouveau);
      if (decision === "snapshot") {
        client?.envoyer({ type: "snapshot" });
      } else if (decision !== "ignorer") {
        animer.value = decision === "appliquer";
        etat.value = nouveau;
      }
    } else if (recu.type === "ack") {
      const ack = brut as Ack;
      if (enAttente.value?.id !== ack.id) return;
      enAttente.value = null;
      message.value = ack.statut === "rejetee" ? (RAISONS[ack.raison ?? ""] ?? "Action refusée.") : null;
    } else if (recu.type === "ecrans") {
      ecrans.value = (brut as Ecrans).ecrans;
    }
  }

  /** Envoie une commande. Une seule à la fois : un deuxième clic pendant l'attente est ignoré (REC-24). */
  function commander(action: string, supplement: { prestation?: string } = {}): void {
    if (enAttente.value || !client) return;
    message.value = null;
    const commande: Commande = {
      type: "commande",
      id: crypto.randomUUID(),
      version_attendue: action === "preparer" ? null : (etat.value?.version ?? null),
      action,
      ...supplement,
    };
    enAttente.value = commande;
    client.envoyer(commande); // si la connexion est coupée, elle partira à la reconnexion
  }

  return { connexion, etat, animer, ecrans, enAttente, message, demarrer, arreter, recevoir, commander };
});
```

```powershell
cd frontend
npm test
```

## Étape D — L'écran de scène

**Fichier `frontend\src\scene\EcranScene.test.ts`**

```typescript
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { etat, FauxSocket } from "../commun/outils-test";
import type { Diapositive } from "../commun/protocole";
import EcranScene from "./EcranScene.vue";

function monte(jeton: string | null = "jeton-scene") {
  const pinia = createPinia();
  setActivePinia(pinia);
  vi.stubGlobal("WebSocket", FauxSocket);
  const roue = mount(EcranScene, { props: { url: "ws://test/ws/presentation/s1/", jeton }, global: { plugins: [pinia] } });
  const socket = FauxSocket.dernier();
  socket.ouvrir();
  return { roue, socket };
}

const verset = (champs: Partial<Diapositive> = {}): Diapositive => ({
  index: 3, total: 10, type: "verset", reference: "2:144", segment: { rang: 1, total: 1 },
  question: { rang: 1, total: 2, libelle: "Sourate 2, versets 142 à 150" }, texte: "texte-neutre-de-test", ...champs,
});

describe("écran de scène", () => {
  beforeEach(() => {
    FauxSocket.instances = [];
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("s'authentifie avec le jeton dès l'ouverture (D38)", () => {
    const { socket, roue } = monte("secret");

    expect(socket.envoyes[0]).toEqual({ type: "auth", jeton: "secret" });
    roue.unmount();
  });

  it("attend la prochaine prestation tant qu'aucune n'est active", async () => {
    const { roue, socket } = monte();

    socket.recevoir(etat({ prestation: null, phase: null, diapositive: null, version: 0, instantane: true }));
    await flushPromises();

    expect(roue.text()).toContain("En attente de la prochaine prestation");
    roue.unmount();
  });

  it("un verset s'affiche en arabe, de droite à gauche, avec sa référence", async () => {
    const { roue, socket } = monte();

    socket.recevoir(etat({ diapositive: verset(), instantane: true }));
    await flushPromises();

    const texte = roue.get("[data-testid=verset]");
    expect(texte.attributes("lang")).toBe("ar");
    expect(texte.attributes("dir")).toBe("rtl");
    expect(texte.text()).toBe("texte-neutre-de-test");
    expect(roue.text()).toContain("2:144");
    roue.unmount();
  });

  it("indique le rang du segment d'un verset découpé", async () => {
    const { roue, socket } = monte();

    socket.recevoir(etat({ diapositive: verset({ segment: { rang: 2, total: 3 } }), instantane: true }));
    await flushPromises();

    expect(roue.text()).toContain("2:144 — 2/3");
    roue.unmount();
  });

  it("RM-14 / D15 : sans texte autorisé, la scène n'affiche que « Présentation en cours »", async () => {
    const { roue, socket } = monte();

    socket.recevoir(etat({ diapositive: verset({ texte: undefined }), instantane: true }));
    await flushPromises();

    expect(roue.find("[data-testid=verset]").exists()).toBe(false);
    expect(roue.text()).toContain("Présentation en cours");
    roue.unmount();
  });

  it("les diapositives intercalaires annoncent la question, la fin de question et la fin de série", async () => {
    const { roue, socket } = monte();
    const intercalaire: Diapositive = { index: 0, total: 10, type: "intercalaire_question", question: { rang: 1, total: 3, libelle: "Sourate 2, versets 142 à 150" } };

    socket.recevoir(etat({ diapositive: intercalaire, instantane: true }));
    await flushPromises();
    expect(roue.text()).toContain("Question 1/3");
    expect(roue.text()).toContain("Sourate 2, versets 142 à 150");

    socket.recevoir(etat({ version: 2, diapositive: { index: 4, total: 10, type: "fin_question" } }));
    await flushPromises();
    expect(roue.text()).toContain("Fin de la question");

    socket.recevoir(etat({ version: 3, diapositive: { index: 9, total: 10, type: "fin_serie" } }));
    await flushPromises();
    expect(roue.text()).toContain("Fin de la série");
    roue.unmount();
  });

  it("RM-12 : une diffusion est animée (balayage), un instantané ne l'est pas", async () => {
    const { roue, socket } = monte();
    socket.recevoir(etat({ version: 5, diapositive: verset(), instantane: true }));
    await flushPromises();

    socket.recevoir(etat({ version: 6, diapositive: verset({ index: 4, reference: "2:145" }) }));
    await flushPromises();
    const transition = roue.findComponent({ name: "Transition" });
    expect(transition.props("name")).toBe("balayage");

    socket.recevoir(etat({ version: 9, instantane: true, diapositive: verset({ index: 7 }) }));
    await flushPromises();
    expect(roue.findComponent({ name: "Transition" }).props("name")).toBe("sans");
    roue.unmount();
  });

  it("affiche la pause par-dessus la diapositive courante", async () => {
    const { roue, socket } = monte();

    socket.recevoir(etat({ phase: "pause", diapositive: verset(), instantane: true }));
    await flushPromises();

    expect(roue.text()).toContain("Pause");
    expect(roue.find("[data-testid=verset]").exists()).toBe(true);
    roue.unmount();
  });

  it("REC-21 : la connexion perdue affiche un bandeau mais GARDE la diapositive à l'écran", async () => {
    const { roue, socket } = monte();
    socket.recevoir(etat({ diapositive: verset(), instantane: true }));
    await flushPromises();

    socket.close();
    await flushPromises();

    expect(roue.text()).toContain("Connexion perdue");
    expect(roue.get("[data-testid=verset]").text()).toBe("texte-neutre-de-test");
    roue.unmount();
  });

  it("REC-23 : après une reconnexion, l'instantané remet l'écran à la diapositive courante", async () => {
    vi.useFakeTimers();
    const { roue, socket } = monte();
    socket.recevoir(etat({ version: 5, diapositive: verset({ index: 4 }), instantane: true }));
    socket.close();
    vi.advanceTimersByTime(500);
    const nouveau = FauxSocket.dernier();
    nouveau.ouvrir();

    nouveau.recevoir(etat({ version: 12, instantane: true, diapositive: verset({ index: 8, reference: "2:149" }) }));
    await flushPromises();

    expect(roue.text()).toContain("2:149");
    expect(roue.text()).not.toContain("Connexion perdue");
    roue.unmount();
    vi.useRealTimers();
  });

  it("la touche + agrandit le texte, la touche - le réduit", async () => {
    const { roue, socket } = monte();
    socket.recevoir(etat({ diapositive: verset(), instantane: true }));
    await flushPromises();

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "+" }));
    await flushPromises();
    expect(roue.get("main").attributes("style")).toContain("1.1");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "-" }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "-" }));
    await flushPromises();
    expect(roue.get("main").attributes("style")).toContain("0.9");
    roue.unmount();
  });
});
```

**Fichier `frontend\src\scene\EcranScene.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import { usePresentationStore } from "../commun/store";

const props = defineProps<{ url: string; jeton: string | null }>();
const store = usePresentationStore();

onMounted(() => {
  store.demarrer(props.url, props.jeton);
  window.addEventListener("keydown", clavier);
});
onUnmounted(() => {
  store.arreter();
  window.removeEventListener("keydown", clavier);
});

const diapositive = computed(() => store.etat?.diapositive ?? null);
const phase = computed(() => store.etat?.phase ?? null);
// Une clé qui change à chaque diapositive ET à chaque « réafficher » : Vue rejoue alors la transition.
const cle = computed(() => (store.etat ? `${diapositive.value?.index ?? "x"}-${store.etat.rejeu}-${store.etat.prestation?.id}` : "vide"));

// Taille du texte réglable au clavier (§9.2), gardée par l'écran.
const taille = ref(Number(window.localStorage.getItem("quranova.taille_scene")) || 100);
function clavier(e: KeyboardEvent): void {
  if (e.key === "+" || e.key === "-") {
    taille.value = Math.min(200, Math.max(50, taille.value + (e.key === "+" ? 10 : -10)));
    try {
      window.localStorage.setItem("quranova.taille_scene", String(taille.value));
    } catch {
      // stockage indisponible : réglage non conservé
    }
  }
}

async function pleinEcran(): Promise<void> {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await document.documentElement.requestFullscreen();
}
</script>

<template>
  <main class="scene" :style="{ '--taille': taille / 100 }">
    <p v-if="store.connexion !== 'ouverte'" class="bandeau" role="status">Connexion perdue — reconnexion en cours…</p>

    <div class="cadre">
      <section v-if="!store.etat?.prestation" key="attente" class="attente">
        <h1>En attente de la prochaine prestation</h1>
      </section>

      <Transition v-else :name="store.animer ? 'balayage' : 'sans'">
        <section v-if="phase === 'preparee'" :key="cle" class="diapo">
          <p class="etiquette">Candidat n° {{ store.etat.prestation.candidat.numero }}</p>
          <h1>{{ store.etat.prestation.epreuve }}</h1>
        </section>

        <section v-else-if="phase === 'terminee'" :key="cle" class="diapo">
          <h1>Fin de la prestation</h1>
        </section>

        <section v-else-if="diapositive" :key="cle" class="diapo" :data-type="diapositive.type">
          <template v-if="diapositive.type === 'intercalaire_question'">
            <p class="etiquette">Question {{ diapositive.question?.rang }}/{{ diapositive.question?.total }}</p>
            <h1>{{ diapositive.question?.libelle }}</h1>
          </template>

          <template v-else-if="diapositive.type === 'verset'">
            <p v-if="diapositive.texte" class="verset" lang="ar" dir="rtl" data-testid="verset">{{ diapositive.texte }}</p>
            <p v-else class="attente-texte">Présentation en cours</p>
            <p class="reference">
              {{ diapositive.reference }}<template v-if="diapositive.segment && diapositive.segment.total > 1"> — {{ diapositive.segment.rang }}/{{ diapositive.segment.total }}</template>
            </p>
          </template>

          <template v-else-if="diapositive.type === 'enonce'">
            <p class="enonce" lang="fr">{{ diapositive.texte }}</p>
          </template>

          <template v-else-if="diapositive.type === 'fin_question'"><h1>Fin de la question</h1></template>
          <template v-else-if="diapositive.type === 'fin_serie'"><h1>Fin de la série</h1></template>
        </section>
      </Transition>
    </div>

    <div v-if="phase === 'pause'" class="pause" role="status">Pause</div>
    <button class="plein-ecran" type="button" aria-label="Plein écran" @click="pleinEcran">⛶</button>
  </main>
</template>
```

**Fichier `frontend\src\scene\style.css`**

```css
.scene { position: fixed; inset: 0; background: #0b2f30; color: #fbf7ee; overflow: hidden; font-family: system-ui, "Segoe UI", sans-serif; }
.scene .cadre { position: absolute; inset: 0; overflow: hidden; }
.scene .diapo, .scene .attente { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center; padding: 6vh 8vw; }
.scene h1 { font-size: calc(5vw * var(--taille)); margin: .2em 0; }
.scene .etiquette { font-size: calc(2.2vw * var(--taille)); letter-spacing: .08em; text-transform: uppercase; opacity: .8; margin: 0; }
/* Le texte arabe se lit de droite à gauche (dir="rtl") ; cela n'a rien à voir avec le sens du balayage. */
.scene .verset { font-family: "Amiri Quran", "Scheherazade New", "Traditional Arabic", serif; font-size: calc(6vw * var(--taille));
  line-height: 1.9; margin: 0; max-width: 90vw; }
.scene .reference { font-size: calc(2.2vw * var(--taille)); opacity: .85; margin-top: 2vh; }
.scene .enonce { font-size: calc(4vw * var(--taille)); max-width: 85vw; }
.scene .attente-texte { font-size: calc(4vw * var(--taille)); opacity: .8; }
.scene .bandeau { position: fixed; top: 0; left: 0; right: 0; z-index: 5; margin: 0; padding: .5rem; text-align: center; background: #8a5a00; color: #fff; }
.scene .pause { position: fixed; right: 2vw; top: 2vh; z-index: 4; background: #c9a227; color: #1d2b2b; padding: .4em 1em; border-radius: 1em; font-size: 2vw; font-weight: 700; }
.scene .plein-ecran { position: fixed; right: 1vw; bottom: 1vh; z-index: 4; background: transparent; color: #fbf7ee; border: 0; font-size: 1.6rem; opacity: .25; cursor: pointer; }
.scene .plein-ecran:hover, .scene .plein-ecran:focus-visible { opacity: 1; }

/* Balayage de DROITE à GAUCHE (RM-12) : la nouvelle diapositive entre par la droite, l'ancienne sort par la gauche. */
.balayage-enter-active, .balayage-leave-active { transition: transform .5s ease; }
.balayage-enter-from { transform: translateX(100%); }
.balayage-leave-to { transform: translateX(-100%); }
.sans-enter-active, .sans-leave-active { transition: none; }
@media (prefers-reduced-motion: reduce) { .balayage-enter-active, .balayage-leave-active { transition: none; } }
```

**Fichier `frontend\src\scene\main.ts`**

```typescript
import { createPinia } from "pinia";
import { createApp } from "vue";

import { chargerJeton, CLE_SCENE } from "../tirage/jeton";
import EcranScene from "./EcranScene.vue";
import "./style.css";

// L'adresse est /scene/<session>/#<jeton> : la session dans le chemin, le jeton dans le fragment (D31, D38).
const session = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const protocole = window.location.protocol === "https:" ? "wss" : "ws";
const url = `${protocole}://${window.location.host}/ws/presentation/${session}/`;

createApp(EcranScene, { url, jeton: chargerJeton(CLE_SCENE) }).use(createPinia()).mount("#app");
```

## Étape E — L'écran de commande

**Fichier `frontend\src\commande\EcranCommande.test.ts`**

```typescript
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { etat, FauxSocket } from "../commun/outils-test";
import type { Diapositive } from "../commun/protocole";
import EcranCommande from "./EcranCommande.vue";

const PRESTATIONS = { prestations: [{ id: "p1", rang: 1, numero: 12, prenom: "Awa", epreuve: "Mémorisation", etat: "tire" }, { id: "p2", rang: 2, numero: 13, prenom: "Ali", epreuve: "Mémorisation", etat: "en_attente" }] };

async function monte() {
  const pinia = createPinia();
  setActivePinia(pinia);
  vi.stubGlobal("WebSocket", FauxSocket);
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(PRESTATIONS), { status: 200 })));
  const roue = mount(EcranCommande, { props: { url: "ws://test/", urlPrestations: "/api/operateur/session/s1/prestations/" }, global: { plugins: [pinia] } });
  const socket = FauxSocket.dernier();
  socket.ouvrir();
  await flushPromises();
  return { roue, socket };
}

const bouton = (roue: ReturnType<typeof mount>, texte: string) => roue.findAll("button").find((b) => b.text().includes(texte))!;
const diapo = (champs: Partial<Diapositive> = {}): Diapositive => ({ index: 3, total: 10, type: "verset", reference: "2:144", segment: { rang: 1, total: 1 }, question: { rang: 1, total: 2, libelle: "Sourate 2, versets 142 à 150" }, texte: "texte-neutre-de-test", ...champs });
const commandes = (socket: FauxSocket) => socket.envoyes.filter((m) => (m as { type: string }).type === "commande") as { action: string; version_attendue: number | null; prestation?: string }[];

describe("écran de commande", () => {
  beforeEach(() => {
    FauxSocket.instances = [];
  });
  afterEach(() => vi.unstubAllGlobals());

  it("ne propose à la préparation que les prestations tirées", async () => {
    const { roue } = await monte();

    const options = roue.findAll("#choix-prestation option").map((o) => o.text());

    expect(options.some((o) => o.includes("Awa"))).toBe(true);
    expect(options.some((o) => o.includes("Ali"))).toBe(false);
    roue.unmount();
  });

  it("prépare l'affichage de la prestation choisie, sans version attendue", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ prestation: null, phase: null, diapositive: null, version: 0, instantane: true }));
    await roue.get("#choix-prestation").setValue("p1");

    await bouton(roue, "Préparer").trigger("click");

    expect(commandes(socket)).toEqual([expect.objectContaining({ action: "preparer", version_attendue: null, prestation: "p1" })]);
    roue.unmount();
  });

  it("les boutons suivent la phase : préparée, seul « Démarrer » est actif", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ phase: "preparee", diapositive: null, instantane: true }));
    await flushPromises();

    expect(bouton(roue, "Démarrer").attributes("disabled")).toBeUndefined();
    for (const texte of ["suivante", "Précédente", "pause", "Terminer"]) {
      expect(bouton(roue, texte).attributes("disabled")).toBeDefined();
    }
    roue.unmount();
  });

  it("RM-11 : « suivante » envoie la version attendue ; pas de défilement automatique", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ version: 17, diapositive: diapo(), instantane: true }));
    await flushPromises();

    await bouton(roue, "suivante").trigger("click");

    expect(commandes(socket)).toEqual([expect.objectContaining({ action: "suivante", version_attendue: 17 })]);
    roue.unmount();
  });

  it("REC-24 : tous les boutons sont désactivés tant que la réponse n'est pas arrivée", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ version: 17, diapositive: diapo(), instantane: true }));
    await flushPromises();

    await bouton(roue, "suivante").trigger("click");
    await bouton(roue, "suivante").trigger("click"); // double clic

    expect(commandes(socket)).toHaveLength(1);
    expect(bouton(roue, "suivante").attributes("disabled")).toBeDefined();
    roue.unmount();
  });

  it("à la dernière diapositive, « suivante » est grisée : il faut « Terminer »", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ diapositive: diapo({ index: 9, total: 10 }), instantane: true }));
    await flushPromises();

    expect(bouton(roue, "suivante").attributes("disabled")).toBeDefined();
    expect(bouton(roue, "Terminer").attributes("disabled")).toBeUndefined();
    roue.unmount();
  });

  it("montre la diapositive courante avec son texte (l'opérateur y a droit) et son rang", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ diapositive: diapo(), instantane: true }));
    await flushPromises();

    expect(roue.get("[data-testid=rang]").text()).toBe("Diapositive 4 / 10");
    expect(roue.text()).toContain("texte-neutre-de-test");
    roue.unmount();
  });

  it("signale un écran de scène déconnecté", async () => {
    const { roue, socket } = await monte();

    socket.recevoir({ type: "ecrans", ecrans: [{ nom: "Scène 1", type: "scene", connecte: false }] });
    await flushPromises();

    expect(roue.get(".ecrans").text()).toContain("Scène 1");
    expect(roue.get(".ecrans").text()).toContain("déconnecté");
    roue.unmount();
  });

  it("affiche le message quand le serveur refuse une commande", async () => {
    const { roue, socket } = await monte();
    socket.recevoir(etat({ version: 17, diapositive: diapo(), instantane: true }));
    await flushPromises();
    await bouton(roue, "suivante").trigger("click");
    const { id } = socket.envoyes.at(-1) as { id: string };

    socket.recevoir({ type: "ack", id, statut: "rejetee", raison: "version_obsolete", version: 18 });
    await flushPromises();

    expect(roue.get("[role=alert]").text()).toContain("pas à jour");
    expect(bouton(roue, "suivante").attributes("disabled")).toBeUndefined(); // les boutons sont libérés
    roue.unmount();
  });
});
```

**Fichier `frontend\src\commande\EcranCommande.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { usePresentationStore, type PrestationListee } from "../commun/store";

const props = defineProps<{ url: string; urlPrestations: string }>();
const store = usePresentationStore();

const prestations = ref<PrestationListee[]>([]);
const choix = ref("");

async function chargerPrestations(): Promise<void> {
  try {
    const reponse = await fetch(props.urlPrestations, { credentials: "same-origin" });
    if (reponse.ok) prestations.value = ((await reponse.json()) as { prestations: PrestationListee[] }).prestations;
  } catch {
    // liste indisponible : l'opérateur peut recharger la page
  }
}

onMounted(() => {
  store.demarrer(props.url, null); // l'opérateur est authentifié par son cookie de session
  void chargerPrestations();
});
onUnmounted(() => store.arreter());
watch(() => [store.etat?.version, store.etat?.phase], () => void chargerPrestations());

const phase = computed(() => store.etat?.phase ?? null);
const diapositive = computed(() => store.etat?.diapositive ?? null);
const tirees = computed(() => prestations.value.filter((p) => p.etat === "tire"));
const pret = computed(() => store.connexion === "ouverte" && !store.enAttente);

// Ces conditions ne font que griser des boutons : le SERVEUR décide, message par message (règle absolue n°4).
const peut = computed(() => ({
  preparer: pret.value && choix.value !== "" && phase.value !== "affichage" && phase.value !== "pause",
  demarrer: pret.value && phase.value === "preparee",
  suivante: pret.value && phase.value === "affichage" && (diapositive.value?.index ?? 0) < (diapositive.value?.total ?? 0) - 1,
  precedente: pret.value && phase.value === "affichage" && (diapositive.value?.index ?? 0) > 0,
  pause: pret.value && phase.value === "affichage",
  reprendre: pret.value && phase.value === "pause",
  reafficher: pret.value && phase.value === "affichage",
  terminer: pret.value && (phase.value === "affichage" || phase.value === "pause"),
}));

const LIBELLES_PHASE: Record<string, string> = { preparee: "Préparée", affichage: "En affichage", pause: "En pause", terminee: "Terminée" };
</script>

<template>
  <main class="commande">
    <header>
      <h1>Commande du diaporama</h1>
      <p class="etat-connexion" :data-connexion="store.connexion">
        {{ store.connexion === "ouverte" ? "Connecté" : "Connexion perdue — reconnexion…" }}
      </p>
      <ul class="ecrans" aria-label="Écrans de scène">
        <li v-for="ecran in store.ecrans" :key="ecran.nom" :class="{ coupe: !ecran.connecte }">
          {{ ecran.connecte ? "●" : "○" }} {{ ecran.nom }} {{ ecran.connecte ? "" : "(déconnecté)" }}
        </li>
      </ul>
    </header>

    <section class="preparation">
      <label for="choix-prestation">Prestation tirée</label>
      <select id="choix-prestation" v-model="choix">
        <option value="" disabled>— choisir —</option>
        <option v-for="p in tirees" :key="p.id" :value="p.id">n° {{ p.numero }} — {{ p.prenom }} ({{ p.epreuve }})</option>
      </select>
      <button type="button" :disabled="!peut.preparer" @click="store.commander('preparer', { prestation: choix })">Préparer l'affichage</button>
    </section>

    <section v-if="store.etat?.prestation" class="courant">
      <p>
        Candidat n° {{ store.etat.prestation.candidat.numero }} — {{ store.etat.prestation.candidat.prenom }} ·
        {{ store.etat.prestation.serie }} · <strong data-testid="phase">{{ LIBELLES_PHASE[phase ?? ""] }}</strong>
      </p>
      <div v-if="diapositive" class="apercu">
        <p class="rang" data-testid="rang">Diapositive {{ diapositive.index + 1 }} / {{ diapositive.total }}</p>
        <p v-if="diapositive.question">Question {{ diapositive.question.rang }}/{{ diapositive.question.total }} — {{ diapositive.question.libelle }}</p>
        <p v-if="diapositive.texte" class="texte" :lang="diapositive.type === 'verset' ? 'ar' : 'fr'" :dir="diapositive.type === 'verset' ? 'rtl' : 'ltr'">{{ diapositive.texte }}</p>
        <p v-if="diapositive.reference">{{ diapositive.reference }}</p>
      </div>
    </section>

    <section class="boutons">
      <button type="button" :disabled="!peut.demarrer" @click="store.commander('demarrer')">Démarrer la prestation</button>
      <button type="button" :disabled="!peut.precedente" @click="store.commander('precedente')">◀ Précédente</button>
      <button type="button" class="principal" :disabled="!peut.suivante" @click="store.commander('suivante')">Diapositive suivante ▶</button>
      <button type="button" :disabled="!peut.pause" @click="store.commander('pause')">Mettre en pause</button>
      <button type="button" :disabled="!peut.reprendre" @click="store.commander('reprendre')">Reprendre</button>
      <button type="button" :disabled="!peut.reafficher" @click="store.commander('reafficher')">Réafficher</button>
      <button type="button" :disabled="!peut.terminer" @click="store.commander('terminer')">Terminer la prestation</button>
    </section>

    <p v-if="store.message" class="message" role="alert">{{ store.message }}</p>
  </main>
</template>
```

**Fichier `frontend\src\commande\style.css`**

```css
.commande { max-width: 60rem; margin: 0 auto; padding: 1.5rem; font-family: system-ui, "Segoe UI", sans-serif; color: #1d2b2b; background: #fbf7ee; min-height: 100vh; }
.commande h1 { margin: 0 0 .3em; }
.commande .etat-connexion { margin: 0; font-weight: 600; color: #1d6b3a; }
.commande .etat-connexion[data-connexion="perdue"], .commande .etat-connexion[data-connexion="connexion"] { color: #8a5a00; }
.commande .ecrans { list-style: none; padding: 0; margin: .5rem 0 1rem; display: flex; gap: 1rem; flex-wrap: wrap; }
.commande .ecrans .coupe { color: #a12; font-weight: 600; }
.commande section { margin: 1rem 0; }
.commande .preparation { display: flex; gap: .75rem; align-items: center; flex-wrap: wrap; }
.commande select, .commande button { font: inherit; padding: .8rem 1.2rem; min-height: 3.2rem; border-radius: .6rem; border: 2px solid #1d2b2b; background: #fff; }
.commande button { cursor: pointer; background: #0f3d3e; color: #fbf7ee; border-color: #0f3d3e; }
.commande button.principal { background: #c9a227; color: #1d2b2b; border-color: #c9a227; font-weight: 700; font-size: 1.2rem; }
.commande button:disabled { opacity: .35; cursor: not-allowed; }
.commande .boutons { display: grid; grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: .75rem; }
.commande .apercu { background: #fff; border: 2px solid #ddd; border-radius: .6rem; padding: 1rem; }
.commande .apercu .texte[dir="rtl"] { font-size: 2rem; line-height: 1.9; font-family: "Amiri Quran", "Scheherazade New", "Traditional Arabic", serif; }
.commande .message { background: #fde8e8; border: 2px solid #a12; padding: .8rem 1rem; border-radius: .6rem; }
```

**Fichier `frontend\src\commande\main.ts`**

```typescript
import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranCommande from "./EcranCommande.vue";
import "./style.css";

// L'adresse est /commande/<session>/ ; l'opérateur est identifié par son cookie de session Django.
const session = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const protocole = window.location.protocol === "https:" ? "wss" : "ws";
const url = `${protocole}://${window.location.host}/ws/presentation/${session}/`;
const urlPrestations = `/api/operateur/session/${session}/prestations/`;

createApp(EcranCommande, { url, urlPrestations }).use(createPinia()).mount("#app");
```

```powershell
npm test
npm run typecheck
npm run build
cd ..
```

Attendu : `70 passed`, aucune erreur de types, et dans `static\frontend\` : `tirage.js`, `scene.js`, `commande.js`, `frontend.css` (plus des fichiers `partage-….js`).

## Étape F — Voir le diaporama

```powershell
python manage.py runserver
```

1. Dans l'administration, **Terminaux** → ajouter un terminal de **type « Écran de scène »** pour la session : le message affiche l'adresse `/scene/<session>/#<jeton>` (une seule fois). Ouvrez-la dans un onglet (ou sur un autre écran).
2. Dans l'administration, activez **« affichage scène »** sur l'épreuve (sinon la scène n'affiche pas le texte, D15).
3. Il faut une prestation **tirée** (chapitre 15 : appelez un candidat sur la tablette de tirage et tirez).
4. Ouvrez `http://127.0.0.1:8000/commande/<uuid de la session>/` (connectez-vous avec un compte opérateur), choisissez la prestation, **Préparer l'affichage**, **Démarrer la prestation**, puis **Diapositive suivante** : la scène suit, avec le balayage. Essayez le double clic, la pause, « Réafficher », « Précédente ».
5. **Coupez le serveur** (Ctrl+C) quelques secondes, relancez-le : la scène affiche un bandeau « connexion perdue », **garde la diapositive**, puis se reconnecte seule.
6. Touches `+` et `-` sur la scène : taille du texte. Le petit bouton en bas à droite : plein écran.

## Questions de compréhension

1. Le balayage va de droite à gauche et le texte arabe se lit de droite à gauche. Pourquoi ces deux sens n'ont-ils rien à voir ?
2. Pourquoi la scène **garde-t-elle** la diapositive quand la connexion est perdue ?
3. Après une reconnexion, pourquoi l'écran se reconstruit-il **sans** rejouer les diapositives manquées ?

<details>
<summary>Réponses</summary>

1. Le balayage est un effet visuel de transition entre deux diapositives (CSS `translateX`). La direction de lecture d'un texte est une propriété du texte (`dir="rtl"`). Le §9.2 les distingue explicitement.
2. Un écran vide devant le public est pire qu'une diapositive figée : la salle voit au moins le dernier contenu, et le bandeau signale le problème à l'opérateur.
3. L'instantané donne l'état courant ; rejouer l'historique ferait défiler des diapositives que personne n'a besoin de revoir, et prendrait du temps (objectif : moins de 2 s).
</details>

## Journal d'apprentissage

Faites le test de coupure (étape F, point 5) et notez le temps de reconnexion observé.

## Commit proposé

```text
Itération 3 : écrans de scène et de commande
```
