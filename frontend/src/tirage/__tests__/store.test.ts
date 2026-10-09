import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { INTERVALLE_INTERROGATION_MS, useTirageStore } from "../stores/tirage";
import { etat, fauxServeur, reponseJson } from "./outils";

const ETAT = "GET /api/tirage/etat/";
const TIRER = "POST /api/tirage/";

async function demarre(routes: Parameters<typeof fauxServeur>[0]) {
  window.localStorage.setItem("quranova.jeton_tirage", "jeton-test");
  const serveur = fauxServeur(routes);
  const store = useTirageStore();
  await store.demarrer();
  return { store, ...serveur };
}

describe("store de tirage", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    window.localStorage.clear();
    window.history.replaceState(null, "", "/tirage/");
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("sans jeton, le terminal n'est pas configuré et n'appelle pas le serveur", async () => {
    const serveur = fauxServeur({});
    const store = useTirageStore();

    await store.demarrer();

    expect(store.vue).toBe("sans_jeton");
    expect(serveur.faux).not.toHaveBeenCalled();
  });

  it("envoie le jeton dans l'en-tête Authorization", async () => {
    const { appels } = await demarre({ [ETAT]: () => reponseJson(etat(null)) });

    const en_tetes = appels[0]?.options?.headers as Record<string, string>;
    expect(en_tetes["Authorization"]).toBe("Bearer jeton-test");
  });

  it("attend l'appel de l'opérateur, puis propose le tirage quand un candidat est appelé", async () => {
    let courant = etat(null);
    const { store } = await demarre({ [ETAT]: () => reponseJson(courant) });
    expect(store.vue).toBe("attente_appel");

    courant = etat({});
    await vi.advanceTimersByTimeAsync(INTERVALLE_INTERROGATION_MS);

    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("demande une confirmation avant de tirer, et permet d'annuler", async () => {
    const { store } = await demarre({ [ETAT]: () => reponseJson(etat({})) });

    store.demanderConfirmation();
    expect(store.vue).toBe("confirmation");
    store.annulerConfirmation();

    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("REC-07 : deux clics rapides n'envoient qu'une seule demande", async () => {
    let appelsTirage = 0;
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: async () => {
        appelsTirage += 1;
        return reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false, etat: "tire" }),
        });
      },
    });

    await Promise.all([store.confirmerTirage(), store.confirmerTirage()]);

    expect(appelsTirage).toBe(1);
    expect(store.vue).toBe("resultat");
    store.arreter();
  });

  it("le résultat vient du serveur et ne contient que le libellé de la série", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () =>
        reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false }),
        }),
    });

    await store.confirmerTirage();

    expect(store.etat?.appel?.tirages).toEqual([{ rang: 1, serie: "Série 4" }]);
    expect(store.tirageRecent).toBe(1);
    store.arreter();
  });

  it("REC-07 : après une coupure réseau, le nouvel essai réutilise le même identifiant de demande", async () => {
    const identifiants: string[] = [];
    let coupure = true;
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: async () => {
        if (coupure) throw new TypeError("réseau coupé");
        return reponseJson({ tirage: { rang: 1, serie: "Série 2" }, etat: etat({ tirages: [{ rang: 1, serie: "Série 2" }], peut_tirer: false }) });
      },
    });
    const faux = vi.mocked(fetch);
    const originale = faux.getMockImplementation()!;
    faux.mockImplementation(async (chemin, options) => {
      if (options?.method === "POST") identifiants.push(JSON.parse(options.body as string).id_demande);
      return originale(chemin, options);
    });

    await store.confirmerTirage();
    expect(store.vue).toBe("erreur");
    expect(store.erreur?.code).toBe("reseau");

    coupure = false;
    await store.confirmerTirage();

    expect(identifiants).toHaveLength(2);
    expect(identifiants[0]).toBe(identifiants[1]);
    expect(store.vue).toBe("resultat");
    store.arreter();
  });

  it("un refus du serveur (409) affiche son message et n'impose pas de réessayer", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () => reponseJson({ code: "lot_epuise", message: "Le lot est épuisé." }, 409),
    });

    await store.confirmerTirage();

    expect(store.vue).toBe("erreur");
    expect(store.erreur).toEqual({ code: "lot_epuise", message: "Le lot est épuisé." });
    store.fermerErreur();
    await vi.advanceTimersByTimeAsync(0);
    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("un jeton refusé (401) efface le jeton et ramène à l'écran de configuration", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson({ code: "terminal_inconnu", message: "Terminal non reconnu." }, 401),
    });

    expect(store.vue).toBe("sans_jeton");
    expect(window.localStorage.getItem("quranova.jeton_tirage")).toBeNull();
  });

  it("garde le dernier état connu quand le serveur ne répond plus", async () => {
    let coupure = false;
    const { store } = await demarre({
      [ETAT]: () => {
        if (coupure) throw new TypeError("réseau coupé");
        return reponseJson(etat({}));
      },
    });
    coupure = true;

    await vi.advanceTimersByTimeAsync(INTERVALLE_INTERROGATION_MS);

    expect(store.horsLigne).toBe(true);
    expect(store.vue).toBe("pret");
    store.arreter();
  });

  it("T > 1 : après le premier tirage, le candidat peut tirer de nouveau", async () => {
    const { store } = await demarre({
      [ETAT]: () => reponseJson(etat({ tirages_prevus: 2, tirages: [{ rang: 1, serie: "Série 1" }], peut_tirer: true })),
    });

    expect(store.vue).toBe("resultat_partiel");
    store.arreter();
  });
});
