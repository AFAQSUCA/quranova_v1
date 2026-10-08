import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranJury from "./EcranJury.vue";
import "./style.css";

// L'adresse est /jury/<session>/ : le juré se connecte avec son code, puis tout passe par son jeton.
const session = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const protocole = window.location.protocol === "https:" ? "wss" : "ws";
const urlWs = `${protocole}://${window.location.host}/ws/presentation/${session}/`;

createApp(EcranJury, { session, urlWs }).use(createPinia()).mount("#app");
