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
