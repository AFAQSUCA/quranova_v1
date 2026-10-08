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
