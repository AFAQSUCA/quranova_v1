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
