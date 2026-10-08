<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { useTirageStore } from "./stores/tirage";

const store = useTirageStore();

onMounted(() => void store.demarrer());
onUnmounted(() => store.arreter());

const appel = computed(() => store.etat?.appel ?? null);
const reessayable = computed(() => store.erreur?.code === "reseau");

// Animation DÉCORATIVE (§8.1) : le résultat est déjà connu et enregistré par le serveur quand on la
// lance. Elle ne décide de rien ; elle ne fait que retourner la carte.
const DUREE_ANIMATION_MS = 1200;
const reveleRang = ref<number | null>(null);
let temporisation: ReturnType<typeof setTimeout> | null = null;

watch(
  () => store.tirageRecent,
  (rang) => {
    reveleRang.value = null;
    if (temporisation) clearTimeout(temporisation);
    if (rang !== null) temporisation = setTimeout(() => (reveleRang.value = rang), DUREE_ANIMATION_MS);
  },
);

function carteRetournee(rang: number): boolean {
  // Un tirage déjà connu avant l'animation (écran rechargé) s'affiche directement.
  return store.tirageRecent !== rang || reveleRang.value === rang;
}
</script>

<template>
  <main class="ecran" :data-vue="store.vue">
    <p v-if="store.horsLigne" class="bandeau" role="status">Connexion au serveur perdue — nouvelle tentative…</p>

    <section v-if="store.vue === 'sans_jeton'" class="panneau">
      <h1>Terminal non configuré</h1>
      <p>Demandez à l'opérateur d'ouvrir l'adresse de ce terminal.</p>
    </section>

    <section v-else-if="store.vue === 'chargement'" class="panneau">
      <p>Chargement…</p>
    </section>

    <section v-else-if="store.vue === 'attente_appel'" class="panneau">
      <h1>En attente de l'appel du candidat</h1>
      <p>L'opérateur va appeler le prochain candidat.</p>
    </section>

    <section v-else-if="appel && (store.vue === 'pret' || store.vue === 'confirmation')" class="panneau">
      <p class="etiquette">Candidat n° {{ appel.numero_candidat }}</p>
      <h1>{{ appel.prenom }}</h1>
      <p>{{ appel.epreuve }}</p>
      <button v-if="store.vue === 'pret'" class="gros-bouton" type="button" @click="store.demanderConfirmation()">
        Effectuer mon tirage
      </button>
      <div v-else class="confirmation" role="alertdialog" aria-labelledby="question-confirmation">
        <p id="question-confirmation">Confirmez-vous votre tirage ?</p>
        <button class="gros-bouton" type="button" @click="store.confirmerTirage()">Oui, tirer</button>
        <button class="secondaire" type="button" @click="store.annulerConfirmation()">Annuler</button>
      </div>
    </section>

    <section v-else-if="store.vue === 'envoi'" class="panneau" aria-live="polite">
      <p class="chargement">Tirage en cours…</p>
    </section>

    <section v-else-if="appel && (store.vue === 'resultat' || store.vue === 'resultat_partiel')" class="panneau">
      <p class="etiquette">Candidat n° {{ appel.numero_candidat }}</p>
      <h1>{{ appel.prenom }}, votre tirage</h1>
      <ul class="cartes">
        <li v-for="tirage in appel.tirages" :key="tirage.rang" class="carte" :class="{ retournee: carteRetournee(tirage.rang) }">
          <span class="dos" aria-hidden="true">?</span>
          <span class="face" data-testid="serie">{{ tirage.serie }}</span>
        </li>
      </ul>
      <p v-if="store.vue === 'resultat'" class="consigne">Restez à votre place : l'opérateur lance la présentation.</p>
      <template v-else>
        <p class="consigne">Tirage {{ appel.tirages.length }} sur {{ appel.tirages_prevus }}.</p>
        <button class="gros-bouton" type="button" @click="store.demanderConfirmation()">Effectuer mon tirage suivant</button>
      </template>
    </section>

    <section v-else-if="store.vue === 'erreur' && store.erreur" class="panneau erreur" role="alert">
      <h1>Tirage impossible</h1>
      <p>{{ store.erreur.message }}</p>
      <button v-if="reessayable" class="gros-bouton" type="button" @click="store.confirmerTirage()">Réessayer</button>
      <button v-else class="secondaire" type="button" @click="store.fermerErreur()">Compris</button>
    </section>
  </main>
</template>
