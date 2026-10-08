export const CLE_TIRAGE = "quranova.jeton_tirage";
export const CLE_SCENE = "quranova.jeton_scene";

/**
 * Le jeton arrive dans le FRAGMENT de l'adresse (`/tirage/#jeton`) : un fragment n'est jamais envoyé
 * au serveur ni écrit dans ses journaux (D31). On le garde dans le stockage de la tablette puis on
 * efface l'adresse, pour que le jeton n'y reste pas affiché.
 */
export function chargerJeton(cle: string = CLE_TIRAGE): string | null {
  const fragment = window.location.hash.replace(/^#/, "").trim();
  if (fragment) {
    try {
      window.localStorage.setItem(cle, fragment);
    } catch {
      // stockage indisponible : le jeton ne vivra que le temps de la page
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return fragment;
  }
  try {
    return window.localStorage.getItem(cle);
  } catch {
    return null;
  }
}

export function oublierJeton(cle: string = CLE_TIRAGE): void {
  try {
    window.localStorage.removeItem(cle);
  } catch {
    // rien à faire
  }
}
