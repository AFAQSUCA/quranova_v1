import type { AppelEnCours, EtatTerminal } from "../types";

export function appel(champs: Partial<AppelEnCours> = {}): AppelEnCours {
  return {
    numero_candidat: 12,
    prenom: "Awa",
    epreuve: "Mémorisation",
    etat: "en_attente",
    tirages_prevus: 1,
    tirages: [],
    peut_tirer: true,
    ...champs,
  };
}

export function etat(champs: Partial<AppelEnCours> | null = {}): EtatTerminal {
  return { terminal: "Tablette 1", appel: champs === null ? null : appel(champs) };
}

export function reponseJson(corps: unknown, statut = 200): Response {
  return new Response(JSON.stringify(corps), { status: statut, headers: { "Content-Type": "application/json" } });
}

/** Un faux serveur : répond selon la route et garde la trace des appels. */
export function fauxServeur(routes: Record<string, () => Response | Promise<Response>>) {
  const appels: { chemin: string; options?: RequestInit }[] = [];
  const faux = vi.fn(async (chemin: string, options?: RequestInit) => {
    appels.push({ chemin, options });
    const route = routes[`${options?.method ?? "GET"} ${chemin}`];
    if (!route) throw new Error(`Route non prévue : ${options?.method ?? "GET"} ${chemin}`);
    return route();
  });
  vi.stubGlobal("fetch", faux);
  return { appels, faux };
}
