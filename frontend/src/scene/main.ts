import { createPinia } from "pinia";
import { createApp } from "vue";

import { chargerJeton, CLE_SCENE } from "../tirage/jeton";
import EcranScene from "./EcranScene.vue";
import "./style.css";

// L'adresse est /scene/<session>/#<jeton> : la session dans le chemin, le jeton dans le fragment (D31, D38).
const session = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const protocole = window.location.protocol === "https:" ? "wss" : "ws";
const url = `${protocole}://${window.location.host}/ws/presentation/${session}/`;

createApp(EcranScene, { url, jeton: chargerJeton(CLE_SCENE) }).use(createPinia()).mount("#app");
