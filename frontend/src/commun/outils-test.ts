import type { EtatPresentation } from "./protocole";
import type { SocketMinimal } from "./client";

export class FauxSocket implements SocketMinimal {
  static instances: FauxSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  envoyes: unknown[] = [];

  constructor(public url: string) {
    FauxSocket.instances.push(this);
  }
  send(donnees: string): void {
    this.envoyes.push(JSON.parse(donnees));
  }
  close(): void {
    this.readyState = 3;
    this.onclose?.();
  }
  // --- côté « serveur » pour les tests ---
  ouvrir(): void {
    this.readyState = 1;
    this.onopen?.();
  }
  recevoir(message: unknown): void {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  static dernier(): FauxSocket {
    return FauxSocket.instances[FauxSocket.instances.length - 1]!;
  }
}

export function etat(champs: Partial<EtatPresentation> = {}): EtatPresentation {
  return {
    type: "etat",
    session: "s1",
    prestation: { id: "p1", candidat: { numero: 12, prenom: "Awa" }, epreuve: "Mémorisation", serie: "Série 4" },
    version: 1,
    phase: "affichage",
    rejeu: 0,
    diapositive: { index: 0, total: 10, type: "intercalaire_question", question: { rang: 1, total: 3, libelle: "Sourate 2, versets 142 à 150" } },
    ...champs,
  };
}
