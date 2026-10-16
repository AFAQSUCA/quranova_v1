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
