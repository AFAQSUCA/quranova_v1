<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { usePresentationStore, type PrestationListee } from "../commun/store";

const props = defineProps<{ url: string; urlPrestations: string }>();
const store = usePresentationStore();

const prestations = ref<PrestationListee[]>([]);
const choix = ref("");

async function chargerPrestations(): Promise<void> {
  try {
    const reponse = await fetch(props.urlPrestations, { credentials: "same-origin" });
    if (reponse.ok) prestations.value = ((await reponse.json()) as { prestations: PrestationListee[] }).prestations;
  } catch {
    // liste indisponible : l'opérateur peut recharger la page
  }
}

onMounted(() => {
  store.demarrer(props.url, null); // l'opérateur est authentifié par son cookie de session
  void chargerPrestations();
});
onUnmounted(() => store.arreter());
watch(() => [store.etat?.version, store.etat?.phase], () => void chargerPrestations());

const phase = computed(() => store.etat?.phase ?? null);
const diapositive = computed(() => store.etat?.diapositive ?? null);
const tirees = computed(() => prestations.value.filter((p) => p.etat === "tire"));
const pret = computed(() => store.connexion === "ouverte" && !store.enAttente);

// Ces conditions ne font que griser des boutons : le SERVEUR décide, message par message (règle absolue n°4).
const peut = computed(() => ({
  preparer: pret.value && choix.value !== "" && phase.value !== "affichage" && phase.value !== "pause",
  demarrer: pret.value && phase.value === "preparee",
  suivante: pret.value && phase.value === "affichage" && (diapositive.value?.index ?? 0) < (diapositive.value?.total ?? 0) - 1,
  precedente: pret.value && phase.value === "affichage" && (diapositive.value?.index ?? 0) > 0,
  pause: pret.value && phase.value === "affichage",
  reprendre: pret.value && phase.value === "pause",
  reafficher: pret.value && phase.value === "affichage",
  terminer: pret.value && (phase.value === "affichage" || phase.value === "pause"),
}));

const LIBELLES_PHASE: Record<string, string> = { preparee: "Préparée", affichage: "En affichage", pause: "En pause", terminee: "Terminée" };
</script>

<template>
  <main class="commande">
    <header>
      <h1>Commande du diaporama</h1>
      <p class="etat-connexion" :data-connexion="store.connexion">
        {{ store.connexion === "ouverte" ? "Connecté" : "Connexion perdue — reconnexion…" }}
      </p>
      <ul class="ecrans" aria-label="Écrans de scène">
        <li v-for="ecran in store.ecrans" :key="ecran.nom" :class="{ coupe: !ecran.connecte }">
          {{ ecran.connecte ? "●" : "○" }} {{ ecran.nom }} {{ ecran.connecte ? "" : "(déconnecté)" }}
        </li>
      </ul>
    </header>

    <section class="preparation">
      <label for="choix-prestation">Prestation tirée</label>
      <select id="choix-prestation" v-model="choix">
        <option value="" disabled>— choisir —</option>
        <option v-for="p in tirees" :key="p.id" :value="p.id">n° {{ p.numero }} — {{ p.prenom }} ({{ p.epreuve }})</option>
      </select>
      <button type="button" :disabled="!peut.preparer" @click="store.commander('preparer', { prestation: choix })">Préparer l'affichage</button>
    </section>

    <section v-if="store.etat?.prestation" class="courant">
      <p>
        Candidat n° {{ store.etat.prestation.candidat.numero }} — {{ store.etat.prestation.candidat.prenom }} ·
        {{ store.etat.prestation.serie }} · <strong data-testid="phase">{{ LIBELLES_PHASE[phase ?? ""] }}</strong>
      </p>
      <div v-if="diapositive" class="apercu">
        <p class="rang" data-testid="rang">Diapositive {{ diapositive.index + 1 }} / {{ diapositive.total }}</p>
        <p v-if="diapositive.question">Question {{ diapositive.question.rang }}/{{ diapositive.question.total }} — {{ diapositive.question.libelle }}</p>
        <p v-if="diapositive.texte" class="texte" :lang="diapositive.type === 'verset' ? 'ar' : 'fr'" :dir="diapositive.type === 'verset' ? 'rtl' : 'ltr'">{{ diapositive.texte }}</p>
        <p v-if="diapositive.reference">{{ diapositive.reference }}</p>
      </div>
    </section>

    <section class="boutons">
      <button type="button" :disabled="!peut.demarrer" @click="store.commander('demarrer')">Démarrer la prestation</button>
      <button type="button" :disabled="!peut.precedente" @click="store.commander('precedente')">◀ Précédente</button>
      <button type="button" class="principal" :disabled="!peut.suivante" @click="store.commander('suivante')">Diapositive suivante ▶</button>
      <button type="button" :disabled="!peut.pause" @click="store.commander('pause')">Mettre en pause</button>
      <button type="button" :disabled="!peut.reprendre" @click="store.commander('reprendre')">Reprendre</button>
      <button type="button" :disabled="!peut.reafficher" @click="store.commander('reafficher')">Réafficher</button>
      <button type="button" :disabled="!peut.terminer" @click="store.commander('terminer')">Terminer la prestation</button>
    </section>

    <p v-if="store.message" class="message" role="alert">{{ store.message }}</p>
  </main>
</template>
