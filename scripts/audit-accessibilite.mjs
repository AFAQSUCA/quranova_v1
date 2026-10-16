// Audit d'accessibilité des écrans QURANOVA (REC-34, §18.2 : WCAG 2.1 AA).
// Aucune dépendance n'est ajoutée au projet : les outils s'installent dans un dossier temporaire (voir docs\recette\accessibilite.md).
//
//   node scripts\audit-accessibilite.mjs <fichier-parametres.json>
//
// Fichier de paramètres : {"base":"http://127.0.0.1:8000","outils":"C:\\Temp\\outils-a11y","jetonTirage":"…","session":"<uuid>",
//   "jetonScene":"…","codeJure":"XXXX-XXXX","operateur":"operateur","motDePasse":"…","chromium":"(optionnel) chemin de chrome.exe"}
// Contrôles : axe-core (critique/sérieux/modéré), cibles tactiles ≥ 44 px, focus visible, débordement horizontal à 320 px et à 200 %,
// attributs de langue du texte coranique. Code de sortie 1 si un contrôle échoue.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const p = JSON.parse(readFileSync(process.argv[2], "utf8"));
const require = createRequire(path.join(p.outils, "x.js"));
const { chromium } = require("playwright-core");
const axeSource = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const B = p.base;
let echecs = 0;
const ko = (m) => { echecs++; console.log("  ÉCHEC : " + m); };

const b = await chromium.launch({ executablePath: p.chromium, channel: p.chromium ? undefined : "chrome" });
const ctx = await b.newContext({ viewport: { width: 1024, height: 768 }, locale: "fr-FR" });

async function axeur(page, nom) {
  await page.addScriptTag({ content: axeSource });
  const r = await page.evaluate(async () => await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] } }));
  console.log(`axe — ${nom} : ${r.violations.length} violation(s)`);
  for (const v of r.violations) ko(`[${v.impact}] ${v.id} — ${v.help} (${v.nodes.length}) ${v.nodes[0].target.join(" ")}`);
}
async function cibles(page, nom) {
  const petits = await page.evaluate(() => [...document.querySelectorAll("button, a, input, select, textarea")].filter(e => e.offsetParent !== null || getComputedStyle(e).position === "fixed")
    .map(e => { const r = e.getBoundingClientRect(); return { t: (e.innerText || e.getAttribute("aria-label") || e.id || e.tagName).slice(0, 30), w: Math.round(r.width), h: Math.round(r.height) }; }).filter(x => (x.w < 44 || x.h < 44) && x.w > 0));
  console.log(`cibles tactiles — ${nom} : ${petits.length} sous 44 px`);
  if (petits.length) ko(JSON.stringify(petits));
}
async function debordement(page, nom, largeur) {
  await page.setViewportSize({ width: largeur, height: 800 }); await page.waitForTimeout(300);
  const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  console.log(`débordement — ${nom} à ${largeur} px : ${o.sw > o.cw + 1 ? "OUI" : "non"}`);
  if (o.sw > o.cw + 1) ko(`${nom} défile horizontalement à ${largeur} px`);
  await page.setViewportSize({ width: 1024, height: 768 });
}
async function focus(page, nom) {
  const invisibles = [];
  await page.keyboard.press("Tab");
  for (let i = 0; i < 25; i++) {
    const r = await page.evaluate(() => { const e = document.activeElement; if (!e || e === document.body) return null; const s = getComputedStyle(e); return { t: (e.innerText || e.id || e.tagName).slice(0, 25), ok: (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== "none" }; });
    if (r && !r.ok) invisibles.push(r.t);
    await page.keyboard.press("Tab");
  }
  console.log(`focus visible — ${nom} : ${invisibles.length} élément(s) sans indicateur`);
  if (invisibles.length) ko(JSON.stringify([...new Set(invisibles)]));
}

const op = await ctx.newPage();
await op.goto(`${B}/`); await axeur(op, "accueil");
await op.goto(`${B}/admin/login/`); await axeur(op, "administration : connexion");
await op.fill("#id_username", p.operateur); await op.fill("#id_password", p.motDePasse); await op.click("input[type=submit]"); await op.waitForLoadState("networkidle");
await axeur(op, "administration : accueil");
await op.goto(`${B}/admin/prestations/prestation/`); await axeur(op, "administration : prestations");

const t = await ctx.newPage(); await t.goto(`${B}/tirage/#${p.jetonTirage}`); await t.waitForTimeout(1500);
await axeur(t, "tirage"); await cibles(t, "tirage"); await focus(t, "tirage"); await debordement(t, "tirage", 320); await debordement(t, "tirage (zoom 200 %)", 512);

const c = op; await c.goto(`${B}/commande/${p.session}/`); await c.waitForSelector("#choix-prestation");
const s = await ctx.newPage(); await s.goto(`${B}/scene/${p.session}/#${p.jetonScene}`); await s.waitForTimeout(1200);
if (await c.locator("#choix-prestation option").count() > 1) {
  await c.selectOption("#choix-prestation", { index: 1 });
  await c.click("button:has-text('Préparer')"); await c.waitForTimeout(500);
  await c.click("button:has-text('Démarrer la prestation')"); await c.waitForTimeout(400);
  await c.click("button:has-text('Diapositive suivante')"); await c.waitForTimeout(400);
  await c.click("button:has-text('Diapositive suivante')"); await c.waitForTimeout(900);
} else console.log("(aucune prestation tirée : la commande est auditée sans diaporama)");
await axeur(c, "commande"); await cibles(c, "commande"); await focus(c, "commande"); await debordement(c, "commande", 320);
await axeur(s, "scène");
const verset = await s.evaluate(() => { const v = document.querySelector(".verset"); return v && { lang: v.getAttribute("lang"), dir: v.getAttribute("dir") }; });
if (verset && (verset.lang !== "ar" || verset.dir !== "rtl")) ko(`verset sans lang="ar" dir="rtl" : ${JSON.stringify(verset)}`); else console.log("langue du verset : " + JSON.stringify(verset));
await debordement(s, "scène", 320);

const j = await ctx.newPage(); await j.goto(`${B}/jury/${p.session}/`); await j.fill("#code", p.codeJure); await j.click("button:has-text('Se connecter')"); await j.waitForTimeout(1500);
await axeur(j, "jury : liste");
if (await j.locator("[data-evaluation]").count()) { await j.click("[data-evaluation]"); await j.waitForTimeout(1200); }
await axeur(j, "jury : évaluation"); await cibles(j, "jury"); await focus(j, "jury"); await debordement(j, "jury", 320);

await b.close();
console.log(echecs ? `\n${echecs} échec(s) : voir les lignes ÉCHEC.` : "\nAucune violation : audit réussi.");
process.exit(echecs ? 1 : 0);
