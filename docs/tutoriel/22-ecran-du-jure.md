# Chapitre 22 — L'écran du juré en Vue (itération 4, étape 4d)

> **Commit de référence :** `47061de` · **Durée :** 6 à 8 heures · **Résultat :** la tablette du juré : connexion par code, grille de critères, brouillon enregistré côté serveur, validation, demande de correction, suivi du verset en direct. **24 tests** du front.

## Objectif

| Règle | Où elle est appliquée |
|---|---|
| **REC-23** : un redémarrage ne perd pas le brouillon | chaque saisie part au serveur après une courte pause (800 ms) ; au retour, on relit l'évaluation |
| **RM-16, REC-12** | une case vidée est envoyée `null` (manquante), un « 0 » est envoyé « 0 » ; « Valider » reste grisé tant que c'est incomplet |
| **Barème** | une valeur hors barème est signalée sur place et **jamais envoyée** |
| **§10.2** | le verset courant et sa référence suivent le diaporama (WebSocket, rôle `jury`) |
| **Coupure Wi-Fi** | la saisie reste à l'écran et repart avec la saisie suivante ; rien n'est perdu |

## Un bug trouvé avec Chromium

Une première version rechargeait l'évaluation à chaque changement de phase du diaporama, ce qui **écrasait la saisie en cours**. Le store envoie désormais d'abord ce qui est en cours de saisie, puis recharge, et ne remplace jamais une saisie tapée pendant le chargement (deux tests le vérifient).

## Étape A — Les fichiers

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
      input: { tirage: "src/tirage/main.ts", scene: "src/scene/main.ts", commande: "src/commande/main.ts", jury: "src/jury/main.ts" },
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

  function demarrer(url: string, jeton: string | null, cleJeton = "jeton"): void {
    client = new ClientWS({
      url,
      authentification: jeton ? () => ({ type: "auth", [cleJeton]: jeton }) : undefined,
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

**Fichier `frontend\src\jury\types.ts`**

```typescript
export interface LigneCritere {
  critere: string;
  libelle: string;
  maximum: string;
  coefficient: string;
  valeur: string | null; // null = note MANQUANTE ; "0.00" = un zéro (RM-16)
}

export interface CorrectionListee {
  critere: string;
  ancienne: string;
  nouvelle: string;
  statut: "demandee" | "approuvee" | "refusee";
  motif: string;
}

export interface EvaluationEtat {
  statut: "non_commencee" | "brouillon" | "validee";
  observation: string;
  criteres: LigneCritere[];
  manquants: string[];
  complete: boolean;
  peut_saisir: boolean;
  peut_valider: boolean;
  prestation: { id: string; numero: number; prenom: string; epreuve: string; etat: string };
  corrections: CorrectionListee[];
}

export interface PrestationJure {
  id: string;
  rang: number;
  numero: number;
  prenom: string;
  epreuve: string;
  etat: string;
  evaluation: "non_commencee" | "brouillon" | "validee";
  active: boolean;
}
```

**Fichier `frontend\src\jury\api.ts`**

```typescript
import type { EvaluationEtat, PrestationJure } from "./types";

export class ErreurJury extends Error {
  constructor(
    public statut: number,
    public code: string,
    message: string,
    public manquants: string[] = [],
  ) {
    super(message);
  }
}

export class ErreurReseauJury extends Error {}

async function appeler(url: string, jeton: string | null, methode = "GET", corps?: unknown): Promise<any> {
  let reponse: Response;
  try {
    reponse = await fetch(url, {
      method: methode,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(jeton ? { Authorization: `Bearer ${jeton}` } : {}) },
      body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch {
    throw new ErreurReseauJury("Connexion au serveur impossible.");
  }
  let donnees: any = null;
  try {
    donnees = await reponse.json();
  } catch {
    // corps absent
  }
  if (!reponse.ok) {
    throw new ErreurJury(reponse.status, donnees?.code ?? "erreur", donnees?.message ?? "Erreur inattendue.", donnees?.manquants ?? []);
  }
  return donnees;
}

export const base = (session: string) => `/api/jury/${session}`;

export async function ouvrirConnexion(session: string, code: string): Promise<{ jeton: string; jure: { prenom: string; nom: string } }> {
  return appeler(`${base(session)}/connexion/`, null, "POST", { code });
}
export async function lirePrestations(session: string, jeton: string): Promise<PrestationJure[]> {
  return (await appeler(`${base(session)}/prestations/`, jeton)).prestations;
}
export async function lireEvaluation(session: string, jeton: string, prestation: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/`, jeton);
}
export async function enregistrer(session: string, jeton: string, prestation: string, notes: Record<string, string | null>, observation?: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/`, jeton, "PUT", { notes, ...(observation === undefined ? {} : { observation }) });
}
export async function valider(session: string, jeton: string, prestation: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/valider/`, jeton, "POST", {});
}
export async function demanderCorrection(session: string, jeton: string, prestation: string, critere: string, valeur: string, motif: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/correction/`, jeton, "POST", { critere, valeur, motif });
}
```

**Fichier `frontend\src\jury\outils-test.ts`**

```typescript
import type { EvaluationEtat, LigneCritere, PrestationJure } from "./types";

export const CRITERES: LigneCritere[] = [
  { critere: "c1", libelle: "Mémorisation", maximum: "10.00", coefficient: "2.00", valeur: null },
  { critere: "c2", libelle: "Tajwid", maximum: "10.00", coefficient: "1.00", valeur: null },
  { critere: "c3", libelle: "Voix", maximum: "5.00", coefficient: "1.00", valeur: null },
];

export function evaluation(champs: Partial<EvaluationEtat> = {}, valeurs: Record<string, string | null> = {}): EvaluationEtat {
  const criteres = CRITERES.map((c) => ({ ...c, valeur: valeurs[c.critere] ?? null }));
  const manquants = criteres.filter((c) => c.valeur === null).map((c) => c.libelle);
  const statut = champs.statut ?? "brouillon";
  return {
    statut, observation: "", criteres, manquants, complete: manquants.length === 0,
    peut_saisir: statut !== "validee", peut_valider: statut !== "validee" && manquants.length === 0,
    prestation: { id: "p1", numero: 12, prenom: "Awa", epreuve: "Mémorisation", etat: "en_notation" },
    corrections: [], ...champs,
  };
}

export const PRESTATIONS: PrestationJure[] = [
  { id: "p1", rang: 1, numero: 12, prenom: "Awa", epreuve: "Mémorisation", etat: "en_notation", evaluation: "brouillon", active: true },
  { id: "p2", rang: 2, numero: 13, prenom: "Ali", epreuve: "Mémorisation", etat: "en_affichage", evaluation: "non_commencee", active: false },
];

export type Reponse = { statut?: number; corps: unknown } | Error;

/** Faux serveur : une file de réponses par « METHODE chemin » ; garde la trace des appels. */
export function serveur(routes: Record<string, Reponse | (() => Reponse)>) {
  const appels: { methode: string; chemin: string; corps: any; entetes: any }[] = [];
  const faux = vi.fn(async (chemin: string, options: RequestInit = {}) => {
    const methode = options.method ?? "GET";
    appels.push({ methode, chemin, corps: options.body ? JSON.parse(String(options.body)) : undefined, entetes: options.headers });
    // Une route s'écrit « METHODE fin-du-chemin » : le début (/api/jury/<session>) n'a pas à être répété.
    const cle = Object.keys(routes).find((k) => {
      const [m, fin] = [k.split(" ")[0], k.split(" ")[1]!];
      return m === methode && chemin.endsWith(fin);
    });
    if (!cle) throw new Error(`Route non prévue : ${methode} ${chemin}`);
    const route = routes[cle]!;
    const reponse = typeof route === "function" ? route() : route;
    if (reponse instanceof Error) throw reponse;
    return new Response(JSON.stringify(reponse.corps), { status: reponse.statut ?? 200 });
  });
  vi.stubGlobal("fetch", faux);
  return { appels, faux };
}
```

**Fichier `frontend\src\jury\store.test.ts`**

```typescript
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { evaluation, PRESTATIONS, serveur } from "./outils-test";
import { DELAI_ENREGISTREMENT_MS, useJuryStore } from "./store";

const EVAL = "/prestations/p1/evaluation/";
const PUT = `PUT ${EVAL}`;

async function connecte(routes: Parameters<typeof serveur>[0] = {}, etat = evaluation()) {
  window.localStorage.setItem("quranova.jeton_jure.s1", "jeton-jure");
  const s = serveur({
    "GET /prestations/": { corps: { prestations: PRESTATIONS } },
    [`GET ${EVAL}`]: { corps: etat },
    ...routes,
  });
  const store = useJuryStore();
  store.initialiser("s1");
  await store.chargerPrestations();
  return { store, ...s };
}

const puts = (appels: ReturnType<typeof serveur>["appels"]) => appels.filter((a) => a.methode === "PUT");

describe("store du juré", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    window.localStorage.clear();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("se connecte avec le code, garde le jeton et charge les prestations", async () => {
    serveur({
      "POST /api/jury/s1/connexion/": { corps: { jeton: "j123", jure: { prenom: "Awa", nom: "Diallo" } } },
      "GET /prestations/": { corps: { prestations: PRESTATIONS } },
      [`GET ${EVAL}`]: { corps: evaluation() },
    });
    const store = useJuryStore();
    store.initialiser("s1");

    await store.seConnecter("k7mq-4xtr");

    expect(store.connecte).toBe(true);
    expect(window.localStorage.getItem("quranova.jeton_jure.s1")).toBe("j123");
    expect(store.prestations).toHaveLength(2);
    expect(store.choisie).toBe("p1"); // la prestation active est choisie par défaut
  });

  it("un code refusé affiche un message vague, un blocage affiche l'attente", async () => {
    serveur({ "POST /api/jury/s1/connexion/": { statut: 401, corps: { code: "code_invalide", message: "Code invalide ou expiré." } } });
    const store = useJuryStore();
    store.initialiser("s1");
    await store.seConnecter("zzzz");
    expect(store.erreurConnexion).toBe("Code invalide ou expiré.");
    expect(store.connecte).toBe(false);

    serveur({ "POST /api/jury/s1/connexion/": { statut: 429, corps: { code: "trop_d_essais", message: "Trop d'essais. Réessayez dans 120 secondes." } } });
    await store.seConnecter("zzzz");
    expect(store.erreurConnexion).toContain("120 secondes");
  });

  it("reprend le jeton gardé : une tablette redémarrée n'a pas à ressaisir son code (REC-23)", async () => {
    const { store } = await connecte();

    expect(store.connecte).toBe(true);
    expect(store.evaluation?.prestation.prenom).toBe("Awa");
  });

  it("l'enregistrement du brouillon attend une pause dans la saisie, puis n'envoie que le critère modifié", async () => {
    const { store, appels } = await connecte({ [PUT]: { corps: evaluation({}, { c1: "8.00" }) } });

    store.saisir("c1", "8");
    store.saisir("c1", "8,5");
    expect(puts(appels)).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS);

    expect(puts(appels)).toHaveLength(1);
    expect(puts(appels)[0]!.corps).toEqual({ notes: { c1: "8,5" } });
    expect(puts(appels)[0]!.entetes.Authorization).toBe("Bearer jeton-jure");
    expect(store.etatEnregistrement).toBe("enregistre");
  });

  it("RM-16 : une case vidée est envoyée « null » (manquante), un « 0 » est envoyé « 0 »", async () => {
    const { store, appels } = await connecte({ [PUT]: { corps: evaluation() } });

    store.saisir("c1", "0");
    store.saisir("c2", "   ");
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS);

    expect(puts(appels)[0]!.corps.notes).toEqual({ c1: "0", c2: null });
  });

  it("une valeur hors barème est signalée sur place et n'est jamais envoyée", async () => {
    const { store, appels } = await connecte({ [PUT]: { corps: evaluation() } });

    store.saisir("c3", "6"); // maximum 5
    store.saisir("c1", "abc");
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS * 2);

    expect(store.erreurs["c3"]).toBe("Entre 0 et 5");
    expect(store.erreurs["c1"]).toBeDefined();
    expect(puts(appels)).toHaveLength(0);
    store.saisir("c2", "7"); // une saisie valide déclenche l'envoi : les valeurs invalides n'en font PAS partie
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS);
    expect(puts(appels)[0]!.corps.notes).toEqual({ c2: "7" });
    store.saisir("c3", "4");
    expect(store.erreurs["c3"]).toBeUndefined();
  });

  it("coupure réseau : la saisie reste à l'écran et repart avec la saisie suivante", async () => {
    let coupure = true;
    const { store, appels } = await connecte({
      [PUT]: () => (coupure ? new TypeError("réseau coupé") : { corps: evaluation({}, { c1: "7.00", c2: "6.00" }) }),
    });

    store.saisir("c1", "7");
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS);
    expect(store.etatEnregistrement).toBe("echec");
    expect(store.message).toContain("Non enregistré");
    expect(store.saisies["c1"]).toBe("7");

    coupure = false;
    store.saisir("c2", "6");
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS);

    expect(puts(appels).at(-1)!.corps.notes).toEqual({ c1: "7", c2: "6" }); // rien n'a été perdu
    expect(store.etatEnregistrement).toBe("enregistre");
  });

  it("un rechargement (changement de phase du diaporama) n'écrase jamais une saisie en cours", async () => {
    // Le serveur « se souvient » de la note envoyée : après la PUT, la lecture la renvoie.
    const { store, appels } = await connecte({
      [PUT]: { corps: evaluation({}, { c1: "8.00" }) },
      [`GET ${EVAL}`]: { corps: evaluation({}, { c1: "8.00" }) },
    });
    store.saisir("c1", "8");

    await store.recharger();

    expect(puts(appels)).toHaveLength(1); // la saisie est d'abord envoyée
    expect(store.saisies["c1"]).toBe("8");
  });

  it("une saisie tapée pendant le chargement est conservée", async () => {
    let liberer: () => void = () => {};
    const { store } = await connecte({
      [`GET ${EVAL}`]: () => ({ corps: evaluation() }),
    });
    const lecture = store.recharger();
    store.saisir("c2", "6"); // le juré tape pendant que la réponse arrive
    await lecture;
    liberer();

    expect(store.saisies["c2"]).toBe("6");
  });

  it("changer de prestation enregistre d'abord la saisie en cours", async () => {
    const { store, appels } = await connecte({
      [PUT]: { corps: evaluation() },
      "GET /prestations/p2/evaluation/": { corps: evaluation({ prestation: { id: "p2", numero: 13, prenom: "Ali", epreuve: "M", etat: "en_affichage" } }) },
    });
    store.saisir("c1", "9");

    await store.choisir("p2");

    expect(puts(appels)).toHaveLength(1);
    expect(store.choisie).toBe("p2");
    expect(store.evaluation?.prestation.prenom).toBe("Ali");
  });

  it("valider : enregistre d'abord, puis valide ; une évaluation validée n'est plus modifiable", async () => {
    const complete = { c1: "9.00", c2: "8.00", c3: "4.00" };
    const { store, appels } = await connecte({
      [PUT]: { corps: evaluation({}, complete) },
      "POST /prestations/p1/evaluation/valider/": { corps: evaluation({ statut: "validee" }, complete) },
    });
    store.saisir("c1", "9");

    await store.validerEvaluation();

    expect(appels.map((a) => a.methode)).toContain("POST");
    expect(appels.findIndex((a) => a.methode === "PUT")).toBeLessThan(appels.findIndex((a) => a.methode === "POST"));
    expect(store.evaluation?.statut).toBe("validee");
    store.saisir("c1", "1"); // sans effet : lecture seule
    await vi.advanceTimersByTimeAsync(DELAI_ENREGISTREMENT_MS);
    expect(puts(appels)).toHaveLength(1);
  });

  it("REC-12 : le refus de valider une évaluation incomplète liste ce qui manque", async () => {
    const { store } = await connecte({
      "POST /prestations/p1/evaluation/valider/": { statut: 409, corps: { code: "evaluation_incomplete", message: "x", manquants: ["Tajwid", "Voix"] } },
    });

    await store.validerEvaluation();

    expect(store.message).toBe("Il manque : Tajwid, Voix.");
  });

  it("un jeton refusé (401) ramène à l'écran de connexion", async () => {
    const { store } = await connecte({ [`GET ${EVAL}`]: { statut: 401, corps: { code: "connexion_inconnue" } } });

    await store.recharger();

    expect(store.connecte).toBe(false);
    expect(window.localStorage.getItem("quranova.jeton_jure.s1")).toBeNull();
  });

  it("demande de correction : succès ferme la demande et prévient le juré", async () => {
    const { store, appels } = await connecte({
      "POST /prestations/p1/evaluation/correction/": { statut: 201, corps: evaluation({ statut: "validee", corrections: [{ critere: "c1", ancienne: "9.00", nouvelle: "7.00", statut: "demandee", motif: "Erreur" }] }) },
    });

    const ok = await store.demanderCorrection("c1", "7", "Erreur de saisie");

    expect(ok).toBe(true);
    expect(appels.at(-1)!.corps).toEqual({ critere: "c1", valeur: "7", motif: "Erreur de saisie" });
    expect(store.message).toContain("responsable");
  });
});
```

**Fichier `frontend\src\jury\store.ts`**

```typescript
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "./api";
import type { EvaluationEtat, PrestationJure } from "./types";

export const DELAI_ENREGISTREMENT_MS = 800;
const cleJeton = (session: string) => `quranova.jeton_jure.${session}`;

/**
 * Tablette du juré. Le brouillon vit côté SERVEUR : chaque saisie est envoyée après une courte pause (REC-23 :
 * une tablette redémarrée retrouve ses notes). Une case vide = note manquante (envoyée « null ») ; « 0 » est
 * une vraie note (RM-16).
 */
export const useJuryStore = defineStore("jury", () => {
  const session = ref("");
  const jeton = ref<string | null>(null);
  const jure = ref<{ prenom: string; nom: string } | null>(null);
  const prestations = ref<PrestationJure[]>([]);
  const choisie = ref<string | null>(null);
  const evaluation = ref<EvaluationEtat | null>(null);
  /** Valeurs en cours de saisie, par critère (texte tel que tapé). */
  const saisies = ref<Record<string, string>>({});
  const erreurs = ref<Record<string, string>>({});
  const observation = ref("");
  const message = ref<string | null>(null);
  const etatEnregistrement = ref<"propre" | "en_attente" | "enregistre" | "echec">("propre");
  const heureEnregistrement = ref<Date | null>(null);
  const erreurConnexion = ref<string | null>(null);
  let sale = new Set<string>();
  let observationSale = false;
  let minuteur: ReturnType<typeof setTimeout> | null = null;

  const connecte = computed(() => jeton.value !== null);

  function initialiser(idSession: string): void {
    session.value = idSession;
    try {
      jeton.value = window.localStorage.getItem(cleJeton(idSession));
    } catch {
      jeton.value = null;
    }
  }

  async function seConnecter(code: string): Promise<void> {
    erreurConnexion.value = null;
    try {
      const reponse = await api.ouvrirConnexion(session.value, code);
      jeton.value = reponse.jeton;
      jure.value = reponse.jure;
      try {
        window.localStorage.setItem(cleJeton(session.value), reponse.jeton);
      } catch {
        // stockage indisponible : le jeton ne vivra que le temps de la page
      }
      await chargerPrestations();
    } catch (e) {
      erreurConnexion.value =
        e instanceof api.ErreurJury && e.code === "trop_d_essais"
          ? e.message
          : e instanceof api.ErreurJury
            ? "Code invalide ou expiré."
            : "Connexion au serveur impossible.";
    }
  }

  function oublierConnexion(): void {
    try {
      window.localStorage.removeItem(cleJeton(session.value));
    } catch {
      // rien à faire
    }
    jeton.value = null;
  }

  async function protege<T>(action: () => Promise<T>): Promise<T | undefined> {
    try {
      return await action();
    } catch (e) {
      if (e instanceof api.ErreurJury && e.statut === 401) oublierConnexion();
      throw e;
    }
  }

  async function chargerPrestations(): Promise<void> {
    if (!jeton.value) return;
    try {
      const liste = await protege(() => api.lirePrestations(session.value, jeton.value!));
      if (!liste) return;
      prestations.value = liste;
      if (!choisie.value || !liste.some((p) => p.id === choisie.value)) {
        const preferee = liste.find((p) => p.active) ?? liste.find((p) => p.evaluation !== "validee") ?? liste[0];
        if (preferee) await choisir(preferee.id);
      }
    } catch {
      message.value = "Liste indisponible : vérifiez la connexion.";
    }
  }

  async function choisir(idPrestation: string): Promise<void> {
    if (sale.size || observationSale) await enregistrerMaintenant(); // on n'abandonne jamais une saisie en cours
    choisie.value = idPrestation;
    await recharger();
  }

  function appliquer(etat: EvaluationEtat, conserverSaisie = false): void {
    const encours = conserverSaisie ? { saisies: saisies.value, sale, observation: observation.value, observationSale } : null;
    evaluation.value = etat;
    saisies.value = Object.fromEntries(etat.criteres.map((c) => [c.critere, c.valeur === null ? "" : formater(c.valeur)]));
    observation.value = etat.observation;
    erreurs.value = {};
    sale = new Set();
    observationSale = false;
    if (encours) {
      // Une saisie tapée pendant le chargement n'est JAMAIS écrasée par la réponse du serveur.
      for (const critere of encours.sale) {
        saisies.value = { ...saisies.value, [critere]: encours.saisies[critere] ?? "" };
        sale.add(critere);
      }
      if (encours.observationSale) {
        observation.value = encours.observation;
        observationSale = true;
      }
    }
  }

  /** « 7.50 » s'affiche « 7.5 » : on ne montre pas de décimales inutiles, mais « 0 » reste « 0 ». */
  function formater(valeur: string): string {
    return String(Number(valeur));
  }

  async function recharger(): Promise<void> {
    if (!jeton.value || !choisie.value) return;
    if (sale.size || observationSale) await enregistrerMaintenant(); // d'abord envoyer ce qui est en cours de saisie
    try {
      const etat = await protege(() => api.lireEvaluation(session.value, jeton.value!, choisie.value!));
      if (etat) appliquer(etat, true);
    } catch {
      message.value = "Évaluation indisponible : vérifiez la connexion.";
    }
  }

  function valeurLocaleValide(critere: string, texte: string): boolean {
    const ligne = evaluation.value?.criteres.find((c) => c.critere === critere);
    if (!ligne || texte.trim() === "") return true;
    const nombre = Number(texte.trim().replace(",", "."));
    if (Number.isNaN(nombre) || nombre < 0 || nombre > Number(ligne.maximum)) {
      erreurs.value = { ...erreurs.value, [critere]: `Entre 0 et ${Number(ligne.maximum)}` };
      return false;
    }
    const { [critere]: _retire, ...reste } = erreurs.value;
    erreurs.value = reste;
    return true;
  }

  function saisir(critere: string, texte: string): void {
    if (!evaluation.value?.peut_saisir) return;
    saisies.value = { ...saisies.value, [critere]: texte };
    if (!valeurLocaleValide(critere, texte)) {
      sale.delete(critere); // une valeur hors barème n'est jamais envoyée
      return;
    }
    sale.add(critere);
    planifier();
  }

  function saisirObservation(texte: string): void {
    if (!evaluation.value?.peut_saisir) return;
    observation.value = texte;
    observationSale = true;
    planifier();
  }

  function planifier(): void {
    etatEnregistrement.value = "en_attente";
    if (minuteur) clearTimeout(minuteur);
    minuteur = setTimeout(() => void enregistrerMaintenant(), DELAI_ENREGISTREMENT_MS);
  }

  async function enregistrerMaintenant(): Promise<void> {
    if (minuteur) clearTimeout(minuteur);
    minuteur = null;
    if (!jeton.value || !choisie.value || (!sale.size && !observationSale)) return;
    const notes: Record<string, string | null> = {};
    for (const critere of sale) {
      const texte = (saisies.value[critere] ?? "").trim();
      notes[critere] = texte === "" ? null : texte; // vide = manquante, jamais zéro
    }
    const envoyes = new Set(sale);
    const observationEnvoyee = observationSale ? observation.value : undefined;
    try {
      const etat = await protege(() => api.enregistrer(session.value, jeton.value!, choisie.value!, notes, observationEnvoyee));
      if (!etat) return;
      sale = new Set([...sale].filter((c) => !envoyes.has(c)));
      if (observationEnvoyee !== undefined && observation.value === observationEnvoyee) observationSale = false;
      evaluation.value = { ...etat }; // statut, manquants, peut_valider : mais on garde ce que le juré est en train de taper
      etatEnregistrement.value = sale.size || observationSale ? "en_attente" : "enregistre";
      heureEnregistrement.value = new Date();
      message.value = null;
    } catch (e) {
      etatEnregistrement.value = "echec";
      if (e instanceof api.ErreurJury && e.code === "note_invalide") message.value = e.message;
      else if (e instanceof api.ErreurJury && e.code === "evaluation_validee") {
        message.value = e.message;
        await recharger();
      } else message.value = "Non enregistré : connexion perdue. Vos notes restent à l'écran, nouvel essai à la prochaine saisie.";
    }
  }

  async function validerEvaluation(): Promise<void> {
    await enregistrerMaintenant();
    if (!jeton.value || !choisie.value) return;
    try {
      const etat = await protege(() => api.valider(session.value, jeton.value!, choisie.value!));
      if (etat) {
        appliquer(etat);
        message.value = null;
        await chargerPrestations();
      }
    } catch (e) {
      message.value = e instanceof api.ErreurJury ? (e.manquants.length ? `Il manque : ${e.manquants.join(", ")}.` : e.message) : "Validation impossible : connexion perdue.";
    }
  }

  async function demanderCorrection(critere: string, valeur: string, motif: string): Promise<boolean> {
    if (!jeton.value || !choisie.value) return false;
    try {
      const etat = await protege(() => api.demanderCorrection(session.value, jeton.value!, choisie.value!, critere, valeur, motif));
      if (etat) evaluation.value = etat;
      message.value = "Demande de correction envoyée au responsable du client.";
      return true;
    } catch (e) {
      message.value = e instanceof api.ErreurJury ? e.message : "Demande impossible : connexion perdue.";
      return false;
    }
  }

  return {
    session, jeton, jure, prestations, choisie, evaluation, saisies, erreurs, observation, message, etatEnregistrement,
    heureEnregistrement, erreurConnexion, connecte,
    initialiser, seConnecter, oublierConnexion, chargerPrestations, choisir, recharger, saisir, saisirObservation,
    enregistrerMaintenant, validerEvaluation, demanderCorrection,
  };
});
```

**Fichier `frontend\src\jury\EcranJury.test.ts`**

```typescript
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { etat as etatDirect, FauxSocket } from "../commun/outils-test";
import EcranJury from "./EcranJury.vue";
import { evaluation, PRESTATIONS, serveur } from "./outils-test";

const EVAL = "/prestations/p1/evaluation/";

async function monte(etat = evaluation(), connecte = true, routes: Parameters<typeof serveur>[0] = {}) {
  if (connecte) window.localStorage.setItem("quranova.jeton_jure.s1", "jeton-jure");
  const s = serveur({ "GET /prestations/": { corps: { prestations: PRESTATIONS } }, [`GET ${EVAL}`]: { corps: etat }, ...routes });
  vi.stubGlobal("WebSocket", FauxSocket);
  const pinia = createPinia();
  setActivePinia(pinia);
  const roue = mount(EcranJury, { props: { session: "s1", urlWs: "ws://test/ws/presentation/s1/" }, global: { plugins: [pinia] } });
  await flushPromises();
  return { roue, ...s };
}

describe("écran du juré", () => {
  beforeEach(() => {
    FauxSocket.instances = [];
    window.localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sans jeton, demande le code ; le bouton reste grisé tant que le champ est vide", async () => {
    const { roue } = await monte(evaluation(), false);

    expect(roue.text()).toContain("Votre code personnel");
    expect(roue.get("button").attributes("disabled")).toBeDefined();
    await roue.get("#code").setValue("K7MQ-4XTR");
    expect(roue.get("button").attributes("disabled")).toBeUndefined();
    roue.unmount();
  });

  it("s'authentifie au WebSocket avec le jeton du juré (D44)", async () => {
    const { roue } = await monte();

    expect(FauxSocket.dernier().url).toContain("/ws/presentation/s1/");
    FauxSocket.dernier().ouvrir();
    expect(FauxSocket.dernier().envoyes[0]).toEqual({ type: "auth", jeton_jure: "jeton-jure" });
    roue.unmount();
  });

  it("affiche les critères avec leur barème ; une note manquante est une case vide, un zéro est « 0 »", async () => {
    const { roue } = await monte(evaluation({}, { c1: "0.00", c2: "7.50" }));

    const champs = roue.findAll(".critere input").map((i) => (i.element as HTMLInputElement).value);

    expect(champs).toEqual(["0", "7.5", ""]);
    expect(roue.text()).toContain("/ 10 (coef. 2)");
    expect(roue.get("[data-testid=manquants]").text()).toContain("Voix");
    roue.unmount();
  });

  it("REC-12 : « Valider » est grisé tant que l'évaluation est incomplète", async () => {
    const { roue } = await monte(evaluation({}, { c1: "9.00" }));

    expect(roue.get(".valider").attributes("disabled")).toBeDefined();
    roue.unmount();
  });

  it("« Valider » est actif quand tout est rempli et la prestation terminée", async () => {
    const { roue } = await monte(evaluation({}, { c1: "9.00", c2: "8.00", c3: "4.00" }));

    expect(roue.get(".valider").attributes("disabled")).toBeUndefined();
    roue.unmount();
  });

  it("avant la fin de la prestation, la validation n'est pas proposée comme possible", async () => {
    const e = evaluation({ peut_valider: false, prestation: { id: "p1", numero: 12, prenom: "Awa", epreuve: "M", etat: "en_affichage" } }, { c1: "9.00", c2: "8.00", c3: "4.00" });
    const { roue } = await monte(e);

    expect(roue.text()).toContain("après la fin de la prestation");
    expect(roue.get(".valider").attributes("disabled")).toBeDefined();
    roue.unmount();
  });

  it("une évaluation validée est en lecture seule et propose « Corriger… »", async () => {
    const { roue } = await monte(evaluation({ statut: "validee" }, { c1: "9.00", c2: "8.00", c3: "4.00" }));

    expect(roue.findAll(".critere input").every((i) => i.attributes("disabled") !== undefined)).toBe(true);
    expect(roue.text()).toContain("Évaluation validée");
    expect(roue.findAll("button.lien").length).toBeGreaterThanOrEqual(3);
    roue.unmount();
  });

  it("la demande de correction exige un motif", async () => {
    const { roue } = await monte(evaluation({ statut: "validee" }, { c1: "9.00", c2: "8.00", c3: "4.00" }));

    await roue.findAll("button.lien")[0]!.trigger("click");
    const envoyer = () => roue.findAll("[role=dialog] button").find((b) => b.text().includes("Envoyer"))!;
    expect(envoyer().attributes("disabled")).toBeDefined();
    await roue.get("#nouvelle").setValue("7");
    await roue.get("#motif").setValue("Erreur de saisie");
    expect(envoyer().attributes("disabled")).toBeUndefined();
    roue.unmount();
  });

  it("suit le verset courant en direct, en arabe de droite à gauche, avec sa référence (§10.2)", async () => {
    const { roue } = await monte();
    const socket = FauxSocket.dernier();
    socket.ouvrir();

    socket.recevoir(etatDirect({ instantane: true, diapositive: { index: 3, total: 10, type: "verset", reference: "2:144", segment: { rang: 1, total: 1 }, question: { rang: 1, total: 2, libelle: "Sourate 2, versets 142 à 150" }, texte: "texte-neutre" } }));
    await flushPromises();

    const verset = roue.get("[data-testid=verset]");
    expect(verset.attributes("dir")).toBe("rtl");
    expect(roue.text()).toContain("2:144");
    roue.unmount();
  });

  it("liste les prestations avec l'état de l'évaluation de CE juré", async () => {
    const { roue } = await monte();

    const puces = roue.findAll(".prestations button").map((b) => b.text().replace(/\s+/g, " "));

    expect(puces[0]).toContain("n° 12 — Awa");
    expect(puces[0]).toContain("Brouillon");
    expect(puces[1]).toContain("Pas commencée");
    roue.unmount();
  });
});
```

**Fichier `frontend\src\jury\EcranJury.vue`**

```vue
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { usePresentationStore } from "../commun/store";
import { useJuryStore } from "./store";

const props = defineProps<{ session: string; urlWs: string }>();
const jury = useJuryStore();
const direct = usePresentationStore();
const code = ref("");
const correction = ref<{ critere: string; valeur: string; motif: string } | null>(null);

onMounted(async () => {
  jury.initialiser(props.session);
  if (jury.connecte) await demarrer();
});
onUnmounted(() => direct.arreter());
watch(() => jury.connecte, (oui) => oui && void demarrer());

let demarre = false;
async function demarrer(): Promise<void> {
  await jury.chargerPrestations();
  if (!demarre && jury.jeton) {
    demarre = true;
    direct.demarrer(props.urlWs, jury.jeton, "jeton_jure"); // le juré suit le diaporama (D44)
  }
}
// Quand la présentation change d'état (fin de prestation, nouvelle prestation), on met à jour la liste et la fiche.
watch(() => [direct.etat?.phase, direct.etat?.prestation?.id], () => void jury.chargerPrestations().then(() => jury.recharger()));

const diapo = computed(() => direct.etat?.diapositive ?? null);
const lectureSeule = computed(() => jury.evaluation !== null && !jury.evaluation.peut_saisir);
const LIBELLES: Record<string, string> = { non_commencee: "Pas commencée", brouillon: "Brouillon", validee: "Validée" };
const heure = computed(() => jury.heureEnregistrement?.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) ?? "");

function envoyerCorrection(): void {
  if (!correction.value) return;
  void jury.demanderCorrection(correction.value.critere, correction.value.valeur, correction.value.motif).then((ok) => {
    if (ok) correction.value = null;
  });
}
</script>

<template>
  <main class="jury">
    <!-- Connexion par code (D4) -->
    <section v-if="!jury.connecte" class="connexion">
      <h1>Espace du jury</h1>
      <label for="code">Votre code personnel</label>
      <input id="code" v-model="code" autocomplete="off" autocapitalize="characters" inputmode="text" placeholder="XXXX-XXXX" @keyup.enter="jury.seConnecter(code)" />
      <button type="button" :disabled="code.trim() === ''" @click="jury.seConnecter(code)">Se connecter</button>
      <p v-if="jury.erreurConnexion" class="erreur" role="alert">{{ jury.erreurConnexion }}</p>
    </section>

    <template v-else>
      <header>
        <h1>Notation</h1>
        <p class="etat" :data-connexion="direct.connexion">{{ direct.connexion === "ouverte" ? "En direct" : "Hors ligne — reconnexion…" }}</p>
      </header>

      <nav class="prestations" aria-label="Prestations à noter">
        <button v-for="p in jury.prestations" :key="p.id" type="button" :class="{ choisie: p.id === jury.choisie, active: p.active }" :data-evaluation="p.evaluation" @click="jury.choisir(p.id)">
          n° {{ p.numero }} — {{ p.prenom }}<small>{{ LIBELLES[p.evaluation] }}</small>
        </button>
        <p v-if="!jury.prestations.length" class="vide">Aucune prestation à noter pour le moment.</p>
      </nav>

      <!-- Suivi du verset courant (§10.2) -->
      <section v-if="diapo" class="direct" aria-live="polite">
        <p class="rang">Diapositive {{ diapo.index + 1 }} / {{ diapo.total }}<template v-if="diapo.question"> · Question {{ diapo.question.rang }}/{{ diapo.question.total }} — {{ diapo.question.libelle }}</template></p>
        <p v-if="diapo.texte" class="verset" lang="ar" dir="rtl" data-testid="verset">{{ diapo.texte }}</p>
        <p v-if="diapo.reference" class="reference">{{ diapo.reference }}</p>
      </section>

      <section v-if="jury.evaluation" class="evaluation">
        <h2>
          Candidat n° {{ jury.evaluation.prestation.numero }} — {{ jury.evaluation.prestation.prenom }}
          <span class="statut" :data-statut="jury.evaluation.statut">{{ LIBELLES[jury.evaluation.statut] }}</span>
        </h2>

        <div v-for="ligne in jury.evaluation.criteres" :key="ligne.critere" class="critere">
          <label :for="`c-${ligne.critere}`">{{ ligne.libelle }} <small>/ {{ Number(ligne.maximum) }} (coef. {{ Number(ligne.coefficient) }})</small></label>
          <input :id="`c-${ligne.critere}`" type="text" inputmode="decimal" autocomplete="off" :value="jury.saisies[ligne.critere]" :disabled="lectureSeule" :aria-invalid="!!jury.erreurs[ligne.critere]" placeholder="—" @input="jury.saisir(ligne.critere, ($event.target as HTMLInputElement).value)" />
          <span v-if="jury.erreurs[ligne.critere]" class="erreur">{{ jury.erreurs[ligne.critere] }}</span>
          <button v-if="lectureSeule && jury.evaluation.statut === 'validee'" type="button" class="lien" @click="correction = { critere: ligne.critere, valeur: '', motif: '' }">Corriger…</button>
        </div>

        <label for="observation">Observation</label>
        <textarea id="observation" :value="jury.observation" :disabled="lectureSeule" rows="3" @input="jury.saisirObservation(($event.target as HTMLTextAreaElement).value)" />

        <p class="enregistrement" :data-etat="jury.etatEnregistrement" role="status">
          <template v-if="jury.etatEnregistrement === 'en_attente'">Enregistrement…</template>
          <template v-else-if="jury.etatEnregistrement === 'enregistre'">Brouillon enregistré à {{ heure }}</template>
          <template v-else-if="jury.etatEnregistrement === 'echec'">Non enregistré</template>
        </p>

        <p v-if="jury.evaluation.manquants.length && jury.evaluation.statut !== 'validee'" class="manquants" data-testid="manquants">
          Notes manquantes : {{ jury.evaluation.manquants.join(", ") }}
        </p>
        <p v-if="jury.evaluation.statut !== 'validee' && jury.evaluation.prestation.etat !== 'en_notation'" class="aide">La validation sera possible après la fin de la prestation.</p>

        <button v-if="jury.evaluation.statut !== 'validee'" type="button" class="valider" :disabled="!jury.evaluation.peut_valider || jury.etatEnregistrement === 'en_attente'" @click="jury.validerEvaluation()">Valider mon évaluation</button>
        <p v-else class="validee">Évaluation validée. Une modification passe par une demande de correction motivée.</p>
      </section>

      <p v-if="jury.message" class="message" role="alert">{{ jury.message }}</p>

      <div v-if="correction" class="dialogue" role="dialog" aria-label="Demande de correction">
        <h3>Demande de correction</h3>
        <label for="nouvelle">Nouvelle valeur</label>
        <input id="nouvelle" v-model="correction.valeur" inputmode="decimal" />
        <label for="motif">Motif (obligatoire)</label>
        <textarea id="motif" v-model="correction.motif" rows="3" />
        <button type="button" :disabled="!correction.motif.trim() || !correction.valeur.trim()" @click="envoyerCorrection">Envoyer au responsable du client</button>
        <button type="button" class="lien" @click="correction = null">Annuler</button>
      </div>
    </template>
  </main>
</template>
```

**Fichier `frontend\src\jury\style.css`**

```css
.jury { max-width: 44rem; margin: 0 auto; padding: 1rem; font-family: system-ui, "Segoe UI", sans-serif; color: #1d2b2b; background: #fbf7ee; min-height: 100vh; font-size: 1.1rem; }
.jury h1 { margin: .2em 0; }
.jury .etat { margin: 0 0 .5rem; font-weight: 600; color: #1d6b3a; }
.jury .etat[data-connexion="perdue"], .jury .etat[data-connexion="connexion"] { color: #8a5a00; }
.jury input[type="text"], .jury input:not([type]), .jury textarea { font: inherit; padding: .8rem; border: 2px solid #1d2b2b; border-radius: .6rem; width: 100%; box-sizing: border-box; background: #fff; }
.jury input[aria-invalid="true"] { border-color: #a12; background: #fde8e8; }
.jury input:disabled, .jury textarea:disabled { background: #eee; color: #555; }
.jury label { display: block; font-weight: 600; margin: .8rem 0 .2rem; }
.jury button { font: inherit; padding: .8rem 1.2rem; min-height: 3.2rem; border-radius: .6rem; border: 2px solid #0f3d3e; background: #0f3d3e; color: #fbf7ee; cursor: pointer; }
.jury button:disabled { opacity: .35; cursor: not-allowed; }
.jury button.lien { background: transparent; color: #0f3d3e; border: 0; text-decoration: underline; min-height: 2rem; padding: .2rem .4rem; }
.jury .connexion { margin-top: 3rem; display: grid; gap: .5rem; }
.jury .prestations { display: flex; gap: .5rem; flex-wrap: wrap; margin: .5rem 0; }
.jury .prestations button { background: #fff; color: #1d2b2b; border-color: #bbb; display: grid; text-align: left; }
.jury .prestations button.choisie { border-color: #0f3d3e; box-shadow: 0 0 0 2px #0f3d3e; }
.jury .prestations button.active { border-left: 6px solid #c9a227; }
.jury .prestations small { opacity: .7; }
.jury .direct { background: #0b2f30; color: #fbf7ee; border-radius: .8rem; padding: 1rem; margin: .5rem 0 1rem; text-align: center; }
.jury .direct .rang, .jury .direct .reference { margin: .2rem 0; opacity: .85; font-size: .95rem; }
.jury .direct .verset { font-family: "Amiri Quran", "Scheherazade New", "Traditional Arabic", serif; font-size: 2rem; line-height: 1.9; margin: .4rem 0; }
.jury .evaluation h2 { font-size: 1.2rem; display: flex; justify-content: space-between; align-items: center; gap: .5rem; }
.jury .statut { font-size: .8rem; padding: .2rem .6rem; border-radius: 1rem; background: #ddd; }
.jury .statut[data-statut="validee"] { background: #cfe8d6; color: #1d6b3a; }
.jury .statut[data-statut="brouillon"] { background: #f3e2b3; }
.jury .critere { margin-bottom: .4rem; }
.jury .erreur { color: #a12; font-size: .9rem; }
.jury .manquants { background: #fff4d6; border: 2px solid #c9a227; padding: .5rem .8rem; border-radius: .6rem; }
.jury .aide, .jury .enregistrement { font-size: .9rem; opacity: .8; }
.jury .enregistrement[data-etat="echec"] { color: #a12; opacity: 1; font-weight: 600; }
.jury .valider { width: 100%; margin-top: .5rem; background: #c9a227; border-color: #c9a227; color: #1d2b2b; font-weight: 700; }
.jury .validee { background: #e3f1e7; padding: .6rem .8rem; border-radius: .6rem; }
.jury .message { background: #fde8e8; border: 2px solid #a12; padding: .6rem .8rem; border-radius: .6rem; }
.jury .dialogue { position: fixed; inset: auto 1rem 1rem 1rem; background: #fff; border: 3px solid #0f3d3e; border-radius: .8rem; padding: 1rem; box-shadow: 0 8px 30px rgba(0,0,0,.3); max-width: 40rem; margin: 0 auto; }
```

**Fichier `frontend\src\jury\main.ts`**

```typescript
import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranJury from "./EcranJury.vue";
import "./style.css";

// L'adresse est /jury/<session>/ : le juré se connecte avec son code, puis tout passe par son jeton.
const session = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const protocole = window.location.protocol === "https:" ? "wss" : "ws";
const urlWs = `${protocole}://${window.location.host}/ws/presentation/${session}/`;

createApp(EcranJury, { session, urlWs }).use(createPinia()).mount("#app");
```

```powershell
cd frontend
npm test
npm run typecheck
npm run build
cd ..
```

Attendu : `94 passed` (tous les écrans), aucune erreur de types, et `static\frontend\jury.js`.

## Étape B — Essayer

1. Dans l'administration : créez un **juré**, affectez-le à l'épreuve (tableau en bas de sa fiche).
2. Générez son **code de session** (service `generer_code`, par exemple depuis `python manage.py shell`) :

```powershell
python manage.py shell
```
```python
from apps.jury.models import Jure
from apps.concours.models import Session
from apps.jury import services
code = services.generer_code(Jure.objects.get(nom="Traoré"), Session.objects.get())[1]
print(code)
```

3. Ouvrez `http://127.0.0.1:8000/jury/<uuid de la session>/` sur une tablette (ou un autre onglet), saisissez le code.
4. Pendant que l'opérateur déroule le diaporama, notez. Rechargez la page : vos notes sont là. Laissez un critère vide, mettez un « 0 » : constatez la différence.
5. Quand l'opérateur clique « Terminer la prestation », « Valider mon évaluation » devient actif.

## Questions de compréhension

1. Pourquoi enregistrer après une pause de 800 ms plutôt qu'à chaque frappe ?
2. Pourquoi la tablette envoie-t-elle `null` pour une case vidée plutôt que de ne rien envoyer ?
3. Que se passe-t-il si le Wi-Fi coupe pendant que le juré tape ?

<details>
<summary>Réponses</summary>

1. Pour ne pas envoyer une requête par touche (charge inutile) tout en perdant au plus 0,8 s de saisie.
2. « Ne rien envoyer » veut dire « ne change pas ». Pour **effacer** une note déjà enregistrée, il faut le dire explicitement : `null` la rend manquante (pas zéro).
3. La saisie reste à l'écran, l'indicateur passe à « Non enregistré », et tout part avec la saisie suivante ; rien n'est perdu ni dupliqué.
</details>

## Journal d'apprentissage

Notez trois comportements de l'écran qui protègent le juré d'une erreur de saisie.

## Commit proposé

```text
Itération 4d : écran du juré en Vue
```
