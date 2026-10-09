export interface LigneCritere {
  critere: string;
  libelle: string;
  maximum: string;
  coefficient: string;
  valeur: string | null; // null = note MANQUANTE ; "0.00" = un zéro (RM-16)
}

export interface CorrectionListee {
  critere: string;
  ancienne: string;
  nouvelle: string;
  statut: "demandee" | "approuvee" | "refusee";
  motif: string;
}

export interface EvaluationEtat {
  statut: "non_commencee" | "brouillon" | "validee";
  observation: string;
  criteres: LigneCritere[];
  manquants: string[];
  complete: boolean;
  peut_saisir: boolean;
  peut_valider: boolean;
  prestation: { id: string; numero: number; prenom: string; epreuve: string; etat: string };
  corrections: CorrectionListee[];
}

export interface PrestationJure {
  id: string;
  rang: number;
  numero: number;
  prenom: string;
  epreuve: string;
  etat: string;
  evaluation: "non_commencee" | "brouillon" | "validee";
  active: boolean;
}
