/** Types et règles du protocole temps réel (docs/conception/protocole-temps-reel.md). */

export interface Diapositive {
  index: number;
  total: number;
  type: "intercalaire_question" | "verset" | "enonce" | "fin_question" | "fin_serie";
  question?: { rang: number; total: number; libelle: string };
  reference?: string;
  segment?: { rang: number; total: number };
  texte?: string; // absent pour un écran non autorisé (RM-14)
}

export interface EtatPresentation {
  type: "etat";
  instantane?: boolean;
  session: string;
  prestation: { id: string; candidat: { numero: number; prenom: string }; epreuve: string; serie: string } | null;
  version: number;
  phase: "preparee" | "affichage" | "pause" | "terminee" | null;
  rejeu: number;
  diapositive: Diapositive | null;
}

export interface Ack {
  type: "ack";
  id: string;
  statut: "appliquee" | "deja_traitee" | "rejetee";
  version: number;
  raison?: string;
}

export interface Ecrans {
  type: "ecrans";
  ecrans: { nom: string; type: string; connecte: boolean }[];
}

export type MessageServeur = EtatPresentation | Ack | Ecrans | { type: "pong" } | { type: "erreur"; code: string };

export interface Commande {
  type: "commande";
  id: string;
  version_attendue: number | null;
  action: string;
  prestation?: string;
}

export type Decision = "remplacer" | "appliquer" | "ignorer" | "snapshot";

/**
 * Que faire d'un message `etat` ? (protocole §5)
 * - instantané, premier état ou autre prestation : on REMPLACE, sans animation ;
 * - version suivante : on applique (avec animation) ;
 * - version déjà vue ou plus ancienne : on ignore ;
 * - trou de version : un message s'est perdu, on redemande un instantané.
 */
export function decider(local: EtatPresentation | null, recu: EtatPresentation): Decision {
  if (recu.instantane || local === null) return "remplacer";
  if ((local.prestation?.id ?? null) !== (recu.prestation?.id ?? null)) return "remplacer";
  if (recu.version === local.version + 1) return "appliquer";
  if (recu.version <= local.version) return "ignorer";
  return "snapshot";
}

export const RAISONS: Record<string, string> = {
  version_obsolete: "L'écran n'était pas à jour : l'action n'a pas été appliquée. Vérifiez l'affichage puis recommencez.",
  transition_interdite: "Cette action n'est pas possible dans l'état actuel.",
  non_autorise: "Action non autorisée.",
  commande_inconnue: "Commande inconnue.",
};
