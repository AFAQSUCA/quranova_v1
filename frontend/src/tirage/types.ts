/** Ce que l'API de tirage renvoie (voir apps/prestations/terminaux.py). Jamais de verset (RM-14). */
export interface TirageEffectue {
  rang: number;
  serie: string;
}

export interface AppelEnCours {
  numero_candidat: number;
  prenom: string;
  epreuve: string;
  etat: string;
  tirages_prevus: number;
  tirages: TirageEffectue[];
  peut_tirer: boolean;
}

export interface EtatTerminal {
  terminal: string;
  appel: AppelEnCours | null;
}

export interface ErreurApi {
  code: string;
  message: string;
}
