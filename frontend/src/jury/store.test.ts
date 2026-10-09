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
