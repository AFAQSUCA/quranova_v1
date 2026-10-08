<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

import { usePresentationStore } from "../commun/store";

const props = defineProps<{ url: string; jeton: string | null }>();
const store = usePresentationStore();

onMounted(() => {
  store.demarrer(props.url, props.jeton);
  window.addEventListener("keydown", clavier);
});
onUnmounted(() => {
  store.arreter();
  window.removeEventListener("keydown", clavier);
});

const diapositive = computed(() => store.etat?.diapositive ?? null);
const phase = computed(() => store.etat?.phase ?? null);
// Une clé qui change à chaque diapositive ET à chaque « réafficher » : Vue rejoue alors la transition.
const cle = computed(() => (store.etat ? `${diapositive.value?.index ?? "x"}-${store.etat.rejeu}-${store.etat.prestation?.id}` : "vide"));

// Taille du texte réglable au clavier (§9.2), gardée par l'écran.
const taille = ref(Number(window.localStorage.getItem("quranova.taille_scene")) || 100);
function clavier(e: KeyboardEvent): void {
  if (e.key === "+" || e.key === "-") {
    taille.value = Math.min(200, Math.max(50, taille.value + (e.key === "+" ? 10 : -10)));
    try {
      window.localStorage.setItem("quranova.taille_scene", String(taille.value));
    } catch {
      // stockage indisponible : réglage non conservé
    }
  }
}

async function pleinEcran(): Promise<void> {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await document.documentElement.requestFullscreen();
}
</script>

<template>
  <main class="scene" :style="{ '--taille': taille / 100 }">
    <p v-if="store.connexion !== 'ouverte'" class="bandeau" role="status">Connexion perdue — reconnexion en cours…</p>

    <div class="cadre">
      <section v-if="!store.etat?.prestation" key="attente" class="attente">
        <h1>En attente de la prochaine prestation</h1>
      </section>

      <Transition v-else :name="store.animer ? 'balayage' : 'sans'">
        <section v-if="phase === 'preparee'" :key="cle" class="diapo">
          <p class="etiquette">Candidat n° {{ store.etat.prestation.candidat.numero }}</p>
          <h1>{{ store.etat.prestation.epreuve }}</h1>
        </section>

        <section v-else-if="phase === 'terminee'" :key="cle" class="diapo">
          <h1>Fin de la prestation</h1>
        </section>

        <section v-else-if="diapositive" :key="cle" class="diapo" :data-type="diapositive.type">
          <template v-if="diapositive.type === 'intercalaire_question'">
            <p class="etiquette">Question {{ diapositive.question?.rang }}/{{ diapositive.question?.total }}</p>
            <h1>{{ diapositive.question?.libelle }}</h1>
          </template>

          <template v-else-if="diapositive.type === 'verset'">
            <p v-if="diapositive.texte" class="verset" lang="ar" dir="rtl" data-testid="verset">{{ diapositive.texte }}</p>
            <p v-else class="attente-texte">Présentation en cours</p>
            <p class="reference">
              {{ diapositive.reference }}<template v-if="diapositive.segment && diapositive.segment.total > 1"> — {{ diapositive.segment.rang }}/{{ diapositive.segment.total }}</template>
            </p>
          </template>

          <template v-else-if="diapositive.type === 'enonce'">
            <p class="enonce" lang="fr">{{ diapositive.texte }}</p>
          </template>

          <template v-else-if="diapositive.type === 'fin_question'"><h1>Fin de la question</h1></template>
          <template v-else-if="diapositive.type === 'fin_serie'"><h1>Fin de la série</h1></template>
        </section>
      </Transition>
    </div>

    <div v-if="phase === 'pause'" class="pause" role="status">Pause</div>
    <button class="plein-ecran" type="button" aria-label="Plein écran" @click="pleinEcran">⛶</button>
  </main>
</template>
