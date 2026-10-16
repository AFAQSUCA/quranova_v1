import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as api from "./api";
import type { EvaluationEtat, PrestationJure } from "./types";

export const DELAI_ENREGISTREMENT_MS = 800;
const cleJeton = (session: string) => `quranova.jeton_jure.${session}`;

/**
 * Tablette du juré. Le brouillon vit côté SERVEUR : chaque saisie est envoyée après une courte pause (REC-23 :
 * une tablette redémarrée retrouve ses notes). Une case vide = note manquante (envoyée « null ») ; « 0 » est
 * une vraie note (RM-16).
 */
export const useJuryStore = defineStore("jury", () => {
  const session = ref("");
  const jeton = ref<string | null>(null);
  const jure = ref<{ prenom: string; nom: string } | null>(null);
  const prestations = ref<PrestationJure[]>([]);
  const choisie = ref<string | null>(null);
  const evaluation = ref<EvaluationEtat | null>(null);
  /** Valeurs en cours de saisie, par critère (texte tel que tapé). */
  const saisies = ref<Record<string, string>>({});
  const erreurs = ref<Record<string, string>>({});
  const observation = ref("");
  const message = ref<string | null>(null);
  const etatEnregistrement = ref<"propre" | "en_attente" | "enregistre" | "echec">("propre");
  const heureEnregistrement = ref<Date | null>(null);
  const erreurConnexion = ref<string | null>(null);
  let sale = new Set<string>();
  let observationSale = false;
  let minuteur: ReturnType<typeof setTimeout> | null = null;

  const connecte = computed(() => jeton.value !== null);

  function initialiser(idSession: string): void {
    session.value = idSession;
    try {
      jeton.value = window.localStorage.getItem(cleJeton(idSession));
    } catch {
      jeton.value = null;
    }
  }

  async function seConnecter(code: string): Promise<void> {
    erreurConnexion.value = null;
    try {
      const reponse = await api.ouvrirConnexion(session.value, code);
      jeton.value = reponse.jeton;
      jure.value = reponse.jure;
      try {
        window.localStorage.setItem(cleJeton(session.value), reponse.jeton);
      } catch {
        // stockage indisponible : le jeton ne vivra que le temps de la page
      }
      await chargerPrestations();
    } catch (e) {
      erreurConnexion.value =
        e instanceof api.ErreurJury && e.code === "trop_d_essais"
          ? e.message
          : e instanceof api.ErreurJury
            ? "Code invalide ou expiré."
            : "Connexion au serveur impossible.";
    }
  }

  function oublierConnexion(): void {
    try {
      window.localStorage.removeItem(cleJeton(session.value));
    } catch {
      // rien à faire
    }
    jeton.value = null;
  }

  async function protege<T>(action: () => Promise<T>): Promise<T | undefined> {
    try {
      return await action();
    } catch (e) {
      if (e instanceof api.ErreurJury && e.statut === 401) oublierConnexion();
      throw e;
    }
  }

  async function chargerPrestations(): Promise<void> {
    if (!jeton.value) return;
    try {
      const liste = await protege(() => api.lirePrestations(session.value, jeton.value!));
      if (!liste) return;
      prestations.value = liste;
      if (!choisie.value || !liste.some((p) => p.id === choisie.value)) {
        const preferee = liste.find((p) => p.active) ?? liste.find((p) => p.evaluation !== "validee") ?? liste[0];
        if (preferee) await choisir(preferee.id);
      }
    } catch {
      message.value = "Liste indisponible : vérifiez la connexion.";
    }
  }

  async function choisir(idPrestation: string): Promise<void> {
    if (sale.size || observationSale) await enregistrerMaintenant(); // on n'abandonne jamais une saisie en cours
    choisie.value = idPrestation;
    await recharger();
  }

  function appliquer(etat: EvaluationEtat, conserverSaisie = false): void {
    const encours = conserverSaisie ? { saisies: saisies.value, sale, observation: observation.value, observationSale } : null;
    evaluation.value = etat;
    saisies.value = Object.fromEntries(etat.criteres.map((c) => [c.critere, c.valeur === null ? "" : formater(c.valeur)]));
    observation.value = etat.observation;
    erreurs.value = {};
    sale = new Set();
    observationSale = false;
    if (encours) {
      // Une saisie tapée pendant le chargement n'est JAMAIS écrasée par la réponse du serveur.
      for (const critere of encours.sale) {
        saisies.value = { ...saisies.value, [critere]: encours.saisies[critere] ?? "" };
        sale.add(critere);
      }
      if (encours.observationSale) {
        observation.value = encours.observation;
        observationSale = true;
      }
    }
  }

  /** « 7.50 » s'affiche « 7.5 » : on ne montre pas de décimales inutiles, mais « 0 » reste « 0 ». */
  function formater(valeur: string): string {
    return String(Number(valeur));
  }

  async function recharger(): Promise<void> {
    if (!jeton.value || !choisie.value) return;
    if (sale.size || observationSale) await enregistrerMaintenant(); // d'abord envoyer ce qui est en cours de saisie
    try {
      const etat = await protege(() => api.lireEvaluation(session.value, jeton.value!, choisie.value!));
      if (etat) appliquer(etat, true);
    } catch {
      message.value = "Évaluation indisponible : vérifiez la connexion.";
    }
  }

  function valeurLocaleValide(critere: string, texte: string): boolean {
    const ligne = evaluation.value?.criteres.find((c) => c.critere === critere);
    if (!ligne || texte.trim() === "") return true;
    const nombre = Number(texte.trim().replace(",", "."));
    if (Number.isNaN(nombre) || nombre < 0 || nombre > Number(ligne.maximum)) {
      erreurs.value = { ...erreurs.value, [critere]: `Entre 0 et ${Number(ligne.maximum)}` };
      return false;
    }
    const { [critere]: _retire, ...reste } = erreurs.value;
    erreurs.value = reste;
    return true;
  }

  function saisir(critere: string, texte: string): void {
    if (!evaluation.value?.peut_saisir) return;
    saisies.value = { ...saisies.value, [critere]: texte };
    if (!valeurLocaleValide(critere, texte)) {
      sale.delete(critere); // une valeur hors barème n'est jamais envoyée
      return;
    }
    sale.add(critere);
    planifier();
  }

  function saisirObservation(texte: string): void {
    if (!evaluation.value?.peut_saisir) return;
    observation.value = texte;
    observationSale = true;
    planifier();
  }

  function planifier(): void {
    etatEnregistrement.value = "en_attente";
    if (minuteur) clearTimeout(minuteur);
    minuteur = setTimeout(() => void enregistrerMaintenant(), DELAI_ENREGISTREMENT_MS);
  }

  async function enregistrerMaintenant(): Promise<void> {
    if (minuteur) clearTimeout(minuteur);
    minuteur = null;
    if (!jeton.value || !choisie.value || (!sale.size && !observationSale)) return;
    const notes: Record<string, string | null> = {};
    for (const critere of sale) {
      const texte = (saisies.value[critere] ?? "").trim();
      notes[critere] = texte === "" ? null : texte; // vide = manquante, jamais zéro
    }
    const envoyes = new Set(sale);
    const observationEnvoyee = observationSale ? observation.value : undefined;
    try {
      const etat = await protege(() => api.enregistrer(session.value, jeton.value!, choisie.value!, notes, observationEnvoyee));
      if (!etat) return;
      sale = new Set([...sale].filter((c) => !envoyes.has(c)));
      if (observationEnvoyee !== undefined && observation.value === observationEnvoyee) observationSale = false;
      evaluation.value = { ...etat }; // statut, manquants, peut_valider : mais on garde ce que le juré est en train de taper
      etatEnregistrement.value = sale.size || observationSale ? "en_attente" : "enregistre";
      heureEnregistrement.value = new Date();
      message.value = null;
    } catch (e) {
      etatEnregistrement.value = "echec";
      if (e instanceof api.ErreurJury && e.code === "note_invalide") message.value = e.message;
      else if (e instanceof api.ErreurJury && e.code === "evaluation_validee") {
        message.value = e.message;
        await recharger();
      } else message.value = "Non enregistré : connexion perdue. Vos notes restent à l'écran, nouvel essai à la prochaine saisie.";
    }
  }

  async function validerEvaluation(): Promise<void> {
    await enregistrerMaintenant();
    if (!jeton.value || !choisie.value) return;
    try {
      const etat = await protege(() => api.valider(session.value, jeton.value!, choisie.value!));
      if (etat) {
        appliquer(etat);
        message.value = null;
        await chargerPrestations();
      }
    } catch (e) {
      message.value = e instanceof api.ErreurJury ? (e.manquants.length ? `Il manque : ${e.manquants.join(", ")}.` : e.message) : "Validation impossible : connexion perdue.";
    }
  }

  async function demanderCorrection(critere: string, valeur: string, motif: string): Promise<boolean> {
    if (!jeton.value || !choisie.value) return false;
    try {
      const etat = await protege(() => api.demanderCorrection(session.value, jeton.value!, choisie.value!, critere, valeur, motif));
      if (etat) evaluation.value = etat;
      message.value = "Demande de correction envoyée au responsable du client.";
      return true;
    } catch (e) {
      message.value = e instanceof api.ErreurJury ? e.message : "Demande impossible : connexion perdue.";
      return false;
    }
  }

  return {
    session, jeton, jure, prestations, choisie, evaluation, saisies, erreurs, observation, message, etatEnregistrement,
    heureEnregistrement, erreurConnexion, connecte,
    initialiser, seConnecter, oublierConnexion, chargerPrestations, choisir, recharger, saisir, saisirObservation,
    enregistrerMaintenant, validerEvaluation, demanderCorrection,
  };
});
