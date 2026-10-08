import type { EvaluationEtat, PrestationJure } from "./types";

export class ErreurJury extends Error {
  constructor(
    public statut: number,
    public code: string,
    message: string,
    public manquants: string[] = [],
  ) {
    super(message);
  }
}

export class ErreurReseauJury extends Error {}

async function appeler(url: string, jeton: string | null, methode = "GET", corps?: unknown): Promise<any> {
  let reponse: Response;
  try {
    reponse = await fetch(url, {
      method: methode,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(jeton ? { Authorization: `Bearer ${jeton}` } : {}) },
      body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch {
    throw new ErreurReseauJury("Connexion au serveur impossible.");
  }
  let donnees: any = null;
  try {
    donnees = await reponse.json();
  } catch {
    // corps absent
  }
  if (!reponse.ok) {
    throw new ErreurJury(reponse.status, donnees?.code ?? "erreur", donnees?.message ?? "Erreur inattendue.", donnees?.manquants ?? []);
  }
  return donnees;
}

export const base = (session: string) => `/api/jury/${session}`;

export async function ouvrirConnexion(session: string, code: string): Promise<{ jeton: string; jure: { prenom: string; nom: string } }> {
  return appeler(`${base(session)}/connexion/`, null, "POST", { code });
}
export async function lirePrestations(session: string, jeton: string): Promise<PrestationJure[]> {
  return (await appeler(`${base(session)}/prestations/`, jeton)).prestations;
}
export async function lireEvaluation(session: string, jeton: string, prestation: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/`, jeton);
}
export async function enregistrer(session: string, jeton: string, prestation: string, notes: Record<string, string | null>, observation?: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/`, jeton, "PUT", { notes, ...(observation === undefined ? {} : { observation }) });
}
export async function valider(session: string, jeton: string, prestation: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/valider/`, jeton, "POST", {});
}
export async function demanderCorrection(session: string, jeton: string, prestation: string, critere: string, valeur: string, motif: string): Promise<EvaluationEtat> {
  return appeler(`${base(session)}/prestations/${prestation}/evaluation/correction/`, jeton, "POST", { critere, valeur, motif });
}
