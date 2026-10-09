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
