import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranTirage from "./EcranTirage.vue";
import "./style.css";

createApp(EcranTirage).use(createPinia()).mount("#app");
