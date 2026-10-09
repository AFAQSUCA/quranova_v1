<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { usePresentationStore } from "../commun/store";
import { useJuryStore } from "./store";

const props = defineProps<{ session: string; urlWs: string }>();
const jury = useJuryStore();
const direct = usePresentationStore();
const code = ref("");
const correction = ref<{ critere: string; valeur: string; motif: string } | null>(null);

onMounted(async () => {
  jury.initialiser(props.session);
  if (jury.connecte) await demarrer();
});
onUnmounted(() => direct.arreter());
watch(() => jury.connecte, (oui) => oui && void demarrer());

let demarre = false;
async function demarrer(): Promise<void> {
  await jury.chargerPrestations();
  if (!demarre && jury.jeton) {
    demarre = true;
    direct.demarrer(props.urlWs, jury.jeton, "jeton_jure"); // le juré suit le diaporama (D44)
  }
}
// Quand la présentation change d'état (fin de prestation, nouvelle prestation), on met à jour la liste et la fiche.
watch(() => [direct.etat?.phase, direct.etat?.prestation?.id], () => void jury.chargerPrestations().then(() => jury.recharger()));

const diapo = computed(() => direct.etat?.diapositive ?? null);
const lectureSeule = computed(() => jury.evaluation !== null && !jury.evaluation.peut_saisir);
const LIBELLES: Record<string, string> = { non_commencee: "Pas commencée", brouillon: "Brouillon", validee: "Validée" };
const heure = computed(() => jury.heureEnregistrement?.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) ?? "");

function envoyerCorrection(): void {
  if (!correction.value) return;
  void jury.demanderCorrection(correction.value.critere, correction.value.valeur, correction.value.motif).then((ok) => {
    if (ok) correction.value = null;
  });
}
</script>

<template>
  <main class="jury">
    <!-- Connexion par code (D4) -->
    <section v-if="!jury.connecte" class="connexion">
      <h1>Espace du jury</h1>
      <label for="code">Votre code personnel</label>
      <input id="code" v-model="code" autocomplete="off" autocapitalize="characters" inputmode="text" placeholder="XXXX-XXXX" @keyup.enter="jury.seConnecter(code)" />
      <button type="button" :disabled="code.trim() === ''" @click="jury.seConnecter(code)">Se connecter</button>
      <p v-if="jury.erreurConnexion" class="erreur" role="alert">{{ jury.erreurConnexion }}</p>
    </section>

    <template v-else>
      <header>
        <h1>Notation</h1>
        <p class="etat" :data-connexion="direct.connexion">{{ direct.connexion === "ouverte" ? "En direct" : "Hors ligne — reconnexion…" }}</p>
      </header>

      <nav class="prestations" aria-label="Prestations à noter">
        <button v-for="p in jury.prestations" :key="p.id" type="button" :class="{ choisie: p.id === jury.choisie, active: p.active }" :data-evaluation="p.evaluation" @click="jury.choisir(p.id)">
          n° {{ p.numero }} — {{ p.prenom }}<small>{{ LIBELLES[p.evaluation] }}</small>
        </button>
        <p v-if="!jury.prestations.length" class="vide">Aucune prestation à noter pour le moment.</p>
      </nav>

      <!-- Suivi du verset courant (§10.2) -->
      <section v-if="diapo" class="direct" aria-live="polite">
        <p class="rang">Diapositive {{ diapo.index + 1 }} / {{ diapo.total }}<template v-if="diapo.question"> · Question {{ diapo.question.rang }}/{{ diapo.question.total }} — {{ diapo.question.libelle }}</template></p>
        <p v-if="diapo.texte" class="verset" lang="ar" dir="rtl" data-testid="verset">{{ diapo.texte }}</p>
        <p v-if="diapo.reference" class="reference">{{ diapo.reference }}</p>
      </section>

      <section v-if="jury.evaluation" class="evaluation">
        <h2>
          Candidat n° {{ jury.evaluation.prestation.numero }} — {{ jury.evaluation.prestation.prenom }}
          <span class="statut" :data-statut="jury.evaluation.statut">{{ LIBELLES[jury.evaluation.statut] }}</span>
        </h2>

        <div v-for="ligne in jury.evaluation.criteres" :key="ligne.critere" class="critere">
          <label :for="`c-${ligne.critere}`">{{ ligne.libelle }} <small>/ {{ Number(ligne.maximum) }} (coef. {{ Number(ligne.coefficient) }})</small></label>
          <input :id="`c-${ligne.critere}`" type="text" inputmode="decimal" autocomplete="off" :value="jury.saisies[ligne.critere]" :disabled="lectureSeule" :aria-invalid="!!jury.erreurs[ligne.critere]" placeholder="—" @input="jury.saisir(ligne.critere, ($event.target as HTMLInputElement).value)" />
          <span v-if="jury.erreurs[ligne.critere]" class="erreur">{{ jury.erreurs[ligne.critere] }}</span>
          <button v-if="lectureSeule && jury.evaluation.statut === 'validee'" type="button" class="lien" @click="correction = { critere: ligne.critere, valeur: '', motif: '' }">Corriger…</button>
        </div>

        <label for="observation">Observation</label>
        <textarea id="observation" :value="jury.observation" :disabled="lectureSeule" rows="3" @input="jury.saisirObservation(($event.target as HTMLTextAreaElement).value)" />

        <p class="enregistrement" :data-etat="jury.etatEnregistrement" role="status">
          <template v-if="jury.etatEnregistrement === 'en_attente'">Enregistrement…</template>
          <template v-else-if="jury.etatEnregistrement === 'enregistre'">Brouillon enregistré à {{ heure }}</template>
          <template v-else-if="jury.etatEnregistrement === 'echec'">Non enregistré</template>
        </p>

        <p v-if="jury.evaluation.manquants.length && jury.evaluation.statut !== 'validee'" class="manquants" data-testid="manquants">
          Notes manquantes : {{ jury.evaluation.manquants.join(", ") }}
        </p>
        <p v-if="jury.evaluation.statut !== 'validee' && jury.evaluation.prestation.etat !== 'en_notation'" class="aide">La validation sera possible après la fin de la prestation.</p>

        <button v-if="jury.evaluation.statut !== 'validee'" type="button" class="valider" :disabled="!jury.evaluation.peut_valider || jury.etatEnregistrement === 'en_attente'" @click="jury.validerEvaluation()">Valider mon évaluation</button>
        <p v-else class="validee">Évaluation validée. Une modification passe par une demande de correction motivée.</p>
      </section>

      <p v-if="jury.message" class="message" role="alert">{{ jury.message }}</p>

      <div v-if="correction" class="dialogue" role="dialog" aria-label="Demande de correction">
        <h3>Demande de correction</h3>
        <label for="nouvelle">Nouvelle valeur</label>
        <input id="nouvelle" v-model="correction.valeur" inputmode="decimal" />
        <label for="motif">Motif (obligatoire)</label>
        <textarea id="motif" v-model="correction.motif" rows="3" />
        <button type="button" :disabled="!correction.motif.trim() || !correction.valeur.trim()" @click="envoyerCorrection">Envoyer au responsable du client</button>
        <button type="button" class="lien" @click="correction = null">Annuler</button>
      </div>
    </template>
  </main>
</template>
