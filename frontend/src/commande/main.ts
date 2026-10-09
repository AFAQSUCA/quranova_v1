import { createPinia } from "pinia";
import { createApp } from "vue";

import EcranCommande from "./EcranCommande.vue";
import "./style.css";

// L'adresse est /commande/<session>/ ; l'opérateur est identifié par son cookie de session Django.
const session = window.location.pathname.split("/").filter(Boolean)[1] ?? "";
const protocole = window.location.protocol === "https:" ? "wss" : "ws";
const url = `${protocole}://${window.location.host}/ws/presentation/${session}/`;
const urlPrestations = `/api/operateur/session/${session}/prestations/`;

createApp(EcranCommande, { url, urlPrestations }).use(createPinia()).mount("#app");
