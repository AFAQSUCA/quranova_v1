import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { demanderTirage, ErreurReseau, ErreurServeur, lireEtat } from "../api";
import { chargerJeton, oublierJeton } from "../jeton";
import type { ErreurApi, EtatTerminal } from "../types";

export type Vue =
  | "sans_jeton"
  | "chargement"
  | "attente_appel"
  | "pret"
  | "confirmation"
  | "envoi"
  | "resultat"
  | "resultat_partiel"
  | "erreur";

export const INTERVALLE_INTERROGATION_MS = 2000;

/**
 * L'état affiché est celui du SERVEUR (interrogé toutes les 2 secondes, D32) : si la tablette est
 * rechargée, elle retrouve le résultat. Seuls le choix « confirmer ? », l'envoi en cours et les erreurs
 * sont locaux. Le composant ne connaît pas la source des données : on pourra la remplacer par un
 * WebSocket (itération 3) sans le toucher.
 */
export const useTirageStore = defineStore("tirage", () => {
  const jeton = ref<string | null>(null);
  const etat = ref<EtatTerminal | null>(null);
  const horsLigne = ref(false);
  const confirmation = ref(false);
  const envoiEnCours = ref(false);
  const erreur = ref<ErreurApi | null>(null);
  /** Rang du tirage qui vient d'être reçu : sert uniquement à l'animation décorative. */
  const tirageRecent = ref<number | null>(null);
  // Identifiant de la demande en cours. Gardé tant que l'issue est inconnue (réseau coupé) :
  // le nouvel essai le réutilise, donc le serveur ne crée jamais deux tirages (REC-07).
  let idDemande: string | null = null;
  let minuteur: ReturnType<typeof setInterval> | null = null;

  const vue = computed<Vue>(() => {
    if (!jeton.value) return "sans_jeton";
    if (envoiEnCours.value) return "envoi";
    if (erreur.value) return "erreur";
    if (!etat.value) return "chargement";
    const appel = etat.value.appel;
    if (!appel) return "attente_appel";
    if (appel.tirages.length > 0) return appel.peut_tirer ? "resultat_partiel" : "resultat";
    return confirmation.value ? "confirmation" : "pret";
  });

  async function rafraichir(): Promise<void> {
    if (!jeton.value || envoiEnCours.value) return;
    try {
      etat.value = await lireEtat(jeton.value);
      horsLigne.value = false;
    } catch (e) {
      if (e instanceof ErreurServeur && e.statut === 401) {
        arreter();
        oublierJeton();
        jeton.value = null;
        etat.value = null;
      } else {
        horsLigne.value = true; // on garde le dernier état connu
      }
    }
  }

  async function demarrer(): Promise<void> {
    jeton.value = chargerJeton();
    if (!jeton.value) return;
    await rafraichir();
    minuteur = setInterval(() => void rafraichir(), INTERVALLE_INTERROGATION_MS);
  }

  function arreter(): void {
    if (minuteur) clearInterval(minuteur);
    minuteur = null;
  }

  function demanderConfirmation(): void {
    erreur.value = null;
    confirmation.value = true;
  }

  function annulerConfirmation(): void {
    confirmation.value = false;
  }

  async function confirmerTirage(): Promise<void> {
    if (!jeton.value || envoiEnCours.value) return; // un deuxième clic pendant l'envoi est ignoré
    envoiEnCours.value = true;
    erreur.value = null;
    confirmation.value = false;
    idDemande ??= crypto.randomUUID();
    try {
      const reponse = await demanderTirage(jeton.value, idDemande);
      etat.value = reponse.etat;
      tirageRecent.value = reponse.tirage.rang;
      idDemande = null; // issue connue : la prochaine demande (tirage suivant) aura un nouvel identifiant
    } catch (e) {
      if (e instanceof ErreurServeur) {
        idDemande = null; // refus définitif de cette demande
        if (e.statut === 401) {
          arreter();
          oublierJeton();
          jeton.value = null;
        } else {
          erreur.value = e.erreur;
        }
      } else if (e instanceof ErreurReseau) {
        // issue inconnue : on garde idDemande pour réessayer sans risque de double tirage
        erreur.value = { code: "reseau", message: "Connexion perdue. Appuyez sur « Réessayer »." };
      } else {
        throw e;
      }
    } finally {
      envoiEnCours.value = false;
    }
  }

  function fermerErreur(): void {
    erreur.value = null;
    void rafraichir();
  }

  return {
    jeton, etat, horsLigne, erreur, tirageRecent, vue,
    demarrer, arreter, rafraichir, demanderConfirmation, annulerConfirmation, confirmerTirage, fermerErreur,
  };
});
