const CLE = "quranova.jeton_tirage";

/**
 * Le jeton arrive dans le FRAGMENT de l'adresse (`/tirage/#jeton`) : un fragment n'est jamais envoyé
 * au serveur ni écrit dans ses journaux (D31). On le garde dans le stockage de la tablette puis on
 * efface l'adresse, pour que le jeton n'y reste pas affiché.
 */
export function chargerJeton(): string | null {
  const fragment = window.location.hash.replace(/^#/, "").trim();
  if (fragment) {
    try {
      window.localStorage.setItem(CLE, fragment);
    } catch {
      // stockage indisponible : le jeton ne vivra que le temps de la page
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return fragment;
  }
  try {
    return window.localStorage.getItem(CLE);
  } catch {
    return null;
  }
}

export function oublierJeton(): void {
  try {
    window.localStorage.removeItem(CLE);
  } catch {
    // rien à faire
  }
}
