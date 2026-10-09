import type { ErreurApi, EtatTerminal, TirageEffectue } from "./types";

const DELAI_MAX_MS = 8000;

/** Le serveur a répondu mais refuse (401, 409, 400...). */
export class ErreurServeur extends Error {
  constructor(
    public statut: number,
    public erreur: ErreurApi,
  ) {
    super(erreur.message);
  }
}

/** Le serveur n'a pas répondu (Wi-Fi coupé, délai dépassé) : on peut réessayer. */
export class ErreurReseau extends Error {}

async function appeler(jeton: string, chemin: string, options: RequestInit = {}): Promise<unknown> {
  const controle = new AbortController();
  const minuteur = setTimeout(() => controle.abort(), DELAI_MAX_MS);
  let reponse: Response;
  try {
    reponse = await fetch(chemin, {
      ...options,
      signal: controle.signal,
      cache: "no-store",
      headers: { Authorization: `Bearer ${jeton}`, "Content-Type": "application/json" },
    });
  } catch {
    throw new ErreurReseau("Connexion au serveur impossible.");
  } finally {
    clearTimeout(minuteur);
  }
  let corps: unknown = null;
  try {
    corps = await reponse.json();
  } catch {
    // corps absent ou illisible : traité ci-dessous
  }
  if (!reponse.ok) {
    const erreur = (corps ?? {}) as Partial<ErreurApi>;
    throw new ErreurServeur(reponse.status, {
      code: erreur.code ?? "erreur_inconnue",
      message: erreur.message ?? "Erreur inattendue.",
    });
  }
  return corps;
}

export async function lireEtat(jeton: string): Promise<EtatTerminal> {
  return (await appeler(jeton, "/api/tirage/etat/")) as EtatTerminal;
}

export interface ReponseTirage {
  tirage: TirageEffectue;
  etat: EtatTerminal;
}

/** `idDemande` est généré par l'appelant et REPRIS à l'identique en cas de nouvel essai (REC-07). */
export async function demanderTirage(jeton: string, idDemande: string): Promise<ReponseTirage> {
  return (await appeler(jeton, "/api/tirage/", {
    method: "POST",
    body: JSON.stringify({ id_demande: idDemande }),
  })) as ReponseTirage;
}
