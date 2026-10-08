import { defineStore } from "pinia";
import { ref } from "vue";

import { ClientWS, type EtatConnexion } from "./client";
import { decider, RAISONS, type Ack, type Commande, type EtatPresentation, type Ecrans } from "./protocole";

export interface PrestationListee {
  id: string;
  rang: number;
  numero: number;
  prenom: string;
  epreuve: string;
  etat: string;
}

/**
 * État de présentation côté écran. Le SERVEUR détient la vérité : ce store n'est qu'un reflet qui applique
 * les règles du protocole (versions, instantanés) et ne calcule jamais une diapositive lui-même.
 */
export const usePresentationStore = defineStore("presentation", () => {
  const connexion = ref<EtatConnexion>("connexion");
  const etat = ref<EtatPresentation | null>(null);
  /** Vrai quand la transition doit être animée (diffusion), faux pour un instantané (reconstruction). */
  const animer = ref(false);
  const ecrans = ref<Ecrans["ecrans"]>([]);
  const enAttente = ref<Commande | null>(null);
  const message = ref<string | null>(null);
  let client: ClientWS | null = null;

  function demarrer(url: string, jeton: string | null): void {
    client = new ClientWS({
      url,
      authentification: jeton ? () => ({ type: "auth", jeton }) : undefined,
      surEtat: (nouvelEtat) => {
        connexion.value = nouvelEtat;
        // Reconnexion : une commande restée sans réponse repart avec le MÊME identifiant (idempotence, RM-30).
        if (nouvelEtat === "ouverte" && enAttente.value) client?.envoyer(enAttente.value);
      },
      surMessage: recevoir,
    });
    client.connecter();
  }

  function arreter(): void {
    client?.fermer();
    client = null;
  }

  function recevoir(brut: unknown): void {
    const recu = brut as { type?: string };
    if (recu.type === "etat") {
      const nouveau = brut as EtatPresentation;
      const decision = decider(etat.value, nouveau);
      if (decision === "snapshot") {
        client?.envoyer({ type: "snapshot" });
      } else if (decision !== "ignorer") {
        animer.value = decision === "appliquer";
        etat.value = nouveau;
      }
    } else if (recu.type === "ack") {
      const ack = brut as Ack;
      if (enAttente.value?.id !== ack.id) return;
      enAttente.value = null;
      message.value = ack.statut === "rejetee" ? (RAISONS[ack.raison ?? ""] ?? "Action refusée.") : null;
    } else if (recu.type === "ecrans") {
      ecrans.value = (brut as Ecrans).ecrans;
    }
  }

  /** Envoie une commande. Une seule à la fois : un deuxième clic pendant l'attente est ignoré (REC-24). */
  function commander(action: string, supplement: { prestation?: string } = {}): void {
    if (enAttente.value || !client) return;
    message.value = null;
    const commande: Commande = {
      type: "commande",
      id: crypto.randomUUID(),
      version_attendue: action === "preparer" ? null : (etat.value?.version ?? null),
      action,
      ...supplement,
    };
    enAttente.value = commande;
    client.envoyer(commande); // si la connexion est coupée, elle partira à la reconnexion
  }

  return { connexion, etat, animer, ecrans, enAttente, message, demarrer, arreter, recevoir, commander };
});
