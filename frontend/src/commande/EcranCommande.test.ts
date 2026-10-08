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
