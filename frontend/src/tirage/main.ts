import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranTirage from "./EcranTirage.vue";
import "../commun/charte.css";
import "./style.css";

createApp(EcranTirage).use(createPinia()).mount("#app");
