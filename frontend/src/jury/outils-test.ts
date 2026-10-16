import type { EvaluationEtat, LigneCritere, PrestationJure } from "./types";

export const CRITERES: LigneCritere[] = [
  { critere: "c1", libelle: "Mémorisation", maximum: "10.00", coefficient: "2.00", valeur: null },
  { critere: "c2", libelle: "Tajwid", maximum: "10.00", coefficient: "1.00", valeur: null },
  { critere: "c3", libelle: "Voix", maximum: "5.00", coefficient: "1.00", valeur: null },
];

export function evaluation(champs: Partial<EvaluationEtat> = {}, valeurs: Record<string, string | null> = {}): EvaluationEtat {
  const criteres = CRITERES.map((c) => ({ ...c, valeur: valeurs[c.critere] ?? null }));
  const manquants = criteres.filter((c) => c.valeur === null).map((c) => c.libelle);
  const statut = champs.statut ?? "brouillon";
  return {
    statut, observation: "", criteres, manquants, complete: manquants.length === 0,
    peut_saisir: statut !== "validee", peut_valider: statut !== "validee" && manquants.length === 0,
    prestation: { id: "p1", numero: 12, prenom: "Awa", epreuve: "Mémorisation", etat: "en_notation" },
    corrections: [], ...champs,
  };
}

export const PRESTATIONS: PrestationJure[] = [
  { id: "p1", rang: 1, numero: 12, prenom: "Awa", epreuve: "Mémorisation", etat: "en_notation", evaluation: "brouillon", active: true },
  { id: "p2", rang: 2, numero: 13, prenom: "Ali", epreuve: "Mémorisation", etat: "en_affichage", evaluation: "non_commencee", active: false },
];

export type Reponse = { statut?: number; corps: unknown } | Error;

/** Faux serveur : une file de réponses par « METHODE chemin » ; garde la trace des appels. */
export function serveur(routes: Record<string, Reponse | (() => Reponse)>) {
  const appels: { methode: string; chemin: string; corps: any; entetes: any }[] = [];
  const faux = vi.fn(async (chemin: string, options: RequestInit = {}) => {
    const methode = options.method ?? "GET";
    appels.push({ methode, chemin, corps: options.body ? JSON.parse(String(options.body)) : undefined, entetes: options.headers });
    // Une route s'écrit « METHODE fin-du-chemin » : le début (/api/jury/<session>) n'a pas à être répété.
    const cle = Object.keys(routes).find((k) => {
      const [m, fin] = [k.split(" ")[0], k.split(" ")[1]!];
      return m === methode && chemin.endsWith(fin);
    });
    if (!cle) throw new Error(`Route non prévue : ${methode} ${chemin}`);
    const route = routes[cle]!;
    const reponse = typeof route === "function" ? route() : route;
    if (reponse instanceof Error) throw reponse;
    return new Response(JSON.stringify(reponse.corps), { status: reponse.statut ?? 200 });
  });
  vi.stubGlobal("fetch", faux);
  return { appels, faux };
}
