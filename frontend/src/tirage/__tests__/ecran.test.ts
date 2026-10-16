import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EcranTirage from "../EcranTirage.vue";
import { INTERVALLE_INTERROGATION_MS } from "../stores/tirage";
import { etat, fauxServeur, reponseJson } from "./outils";

const ETAT = "GET /api/tirage/etat/";
const TIRER = "POST /api/tirage/";

async function monte(routes: Parameters<typeof fauxServeur>[0]) {
  window.localStorage.setItem("quranova.jeton_tirage", "jeton-test");
  const serveur = fauxServeur(routes);
  const pinia = createPinia();
  setActivePinia(pinia);
  const roue = mount(EcranTirage, { global: { plugins: [pinia] } });
  await flushPromises();
  return { roue, ...serveur };
}

describe("écran de tirage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/tirage/");
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("attend l'appel : aucun bouton de tirage", async () => {
    const { roue } = await monte({ [ETAT]: () => reponseJson(etat(null)) });

    expect(roue.text()).toContain("En attente de l'appel");
    expect(roue.find("button").exists()).toBe(false);
    roue.unmount();
  });

  it("affiche le numéro et le prénom du candidat appelé, jamais son nom", async () => {
    const { roue } = await monte({ [ETAT]: () => reponseJson(etat({})) });

    expect(roue.text()).toContain("Candidat n° 12");
    expect(roue.text()).toContain("Awa");
    roue.unmount();
  });

  it("parcours complet : bouton, confirmation, résultat « Série 4 »", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () =>
        reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false }),
        }),
    });

    await roue.get("button").trigger("click"); // « Effectuer mon tirage »
    expect(roue.text()).toContain("Confirmez-vous votre tirage ?");
    const boutons = roue.findAll("button");
    await boutons[0]!.trigger("click"); // « Oui, tirer »
    await flushPromises();

    expect(roue.get("[data-testid=serie]").text()).toBe("Série 4");
    expect(roue.find("button").exists()).toBe(false); // plus de bouton de tirage
    roue.unmount();
  });

  it("l'animation est décorative : la carte se retourne après l'arrivée du résultat", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () =>
        reponseJson({
          tirage: { rang: 1, serie: "Série 4" },
          etat: etat({ tirages: [{ rang: 1, serie: "Série 4" }], peut_tirer: false }),
        }),
    });
    await roue.get("button").trigger("click");
    await roue.findAll("button")[0]!.trigger("click");
    await flushPromises();

    expect(roue.get(".carte").classes()).not.toContain("retournee"); // résultat connu, pas encore révélé
    await vi.advanceTimersByTimeAsync(1300);
    expect(roue.get(".carte").classes()).toContain("retournee");
    roue.unmount();
  });

  it("un écran rechargé retrouve directement le résultat, sans animation", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({ tirages: [{ rang: 1, serie: "Série 2" }], peut_tirer: false })),
    });

    expect(roue.get(".carte").classes()).toContain("retournee");
    expect(roue.get("[data-testid=serie]").text()).toBe("Série 2");
    roue.unmount();
  });

  it("affiche le message du serveur en cas de refus", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () => reponseJson({ code: "lot_epuise", message: "Le lot est épuisé : prévenez l'opérateur." }, 409),
    });
    await roue.get("button").trigger("click");
    await roue.findAll("button")[0]!.trigger("click");
    await flushPromises();

    expect(roue.get("[role=alert]").text()).toContain("Le lot est épuisé");
    roue.unmount();
  });

  it("propose « Réessayer » après une coupure réseau", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({})),
      [TIRER]: () => {
        throw new TypeError("réseau coupé");
      },
    });
    await roue.get("button").trigger("click");
    await roue.findAll("button")[0]!.trigger("click");
    await flushPromises();

    expect(roue.get("[role=alert]").text()).toContain("Connexion perdue");
    expect(roue.get("button").text()).toBe("Réessayer");
    roue.unmount();
  });

  it("n'affiche jamais de texte de verset : seul le libellé de la série est rendu", async () => {
    const { roue } = await monte({
      [ETAT]: () => reponseJson(etat({ tirages: [{ rang: 1, serie: "Série 7" }], peut_tirer: false })),
    });

    expect(roue.text()).not.toMatch(/[؀-ۿ]/); // aucun caractère arabe
    roue.unmount();
    void INTERVALLE_INTERROGATION_MS;
  });
});
