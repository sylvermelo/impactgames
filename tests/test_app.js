/*
Test de rendu de l'application autonome.
============================================================================
On extrait le <script> du fichier HTML généré, on l'exécute dans Node avec un
DOM minimal, et on vérifie que le montage se termine SANS exception et que le
HTML produit contient bien ce qu'on attend.

C'est le seul moyen de savoir si l'application s'affiche vraiment : une erreur
de frappe dans une fonction de rendu ne se voit pas à la lecture, elle plante
silencieusement le navigateur de l'utilisateur.

Lancer :  node tests/test_app.js [chemin/vers/impactgames-autonome.html]
*/
const fs = require("fs");
const path = require("path");

const fichier = process.argv[2] || path.join(__dirname, "..", "impactgames-autonome.html");
const html = fs.readFileSync(fichier, "utf-8");

const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error("ÉCHEC : aucun <script> trouvé"); process.exit(1); }
const script = m[1];

if (!/const DATA = \{/.test(script)) {
  console.error("ÉCHEC : les données ne sont pas injectées (/*__DATA__*/ intact)");
  process.exit(1);
}

// ---------------------------------------------------------------- DOM minimal
let inseres = [];
function noeud(tag) {
  return {
    tagName: tag, className: "", dataset: {}, textContent: "", _html: "",
    onclick: null,
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      toggle(c, on) { if (on === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); }
                      else { on ? this._s.add(c) : this._s.delete(c); } },
      contains(c) { return this._s.has(c); }
    },
    insertAdjacentHTML(_pos, h) { this._html += h; inseres.push(h); },
    appendChild(c) { (this._enfants = this._enfants || []).push(c); },
    querySelectorAll() { return []; }
  };
}
const parId = {};
const boutons = [];
const document = {
  getElementById(id) { return parId[id] || (parId[id] = noeud("div")); },
  createElement(t) { const n = noeud(t); if (t === "button") boutons.push(n); return n; },
  querySelector(sel) {
    // "nav button" : le premier onglet créé — c'est lui que l'app sélectionne
    return sel === "nav button" ? (boutons[0] || null) : null;
  },
  querySelectorAll(sel) {
    // "nav button" renvoie tous les onglets, "main section" tous les panneaux
    return sel === "nav button" ? boutons : [];
  }
};

// ------------------------------------------------------------------ exécution
try {
  new Function("document", "window", script)(document, {});
} catch (e) {
  console.error("ÉCHEC : le script de l'application a levé une exception :");
  console.error("   " + e.stack.split("\n").slice(0, 4).join("\n   "));
  process.exit(1);
}

const rendu = inseres.join("\n");
const erreurs = [];
function attend(re, msg) { if (!re.test(rendu)) erreurs.push(msg); }

// Le JSON est écrit sur UNE ligne (compact) : on prend la ligne entière, pas
// une regex gourmande qui irait jusqu'au dernier "}" du fichier.
const ligne = script.split("\n").find(l => l.startsWith("const DATA = "));
if (!ligne) { console.error("ÉCHEC : ligne `const DATA = ` introuvable"); process.exit(1); }
const DATA = JSON.parse(ligne.slice("const DATA = ".length).replace(/;$/, "")
  .replace(/<\\\//g, "</"));

if (DATA.modeles.tennis) {
  attend(/id="s-tennis"/, "onglet tennis absent");
  attend(/Elo par surface/, "description du moteur tennis absente");
  attend(/Classement du moteur/, "classement tennis absent");
}
if (DATA.modeles.hockey) {
  attend(/id="s-hockey"/, "onglet hockey absent");
  attend(/Force nette des équipes/, "classement hockey absent");
  attend(/Prolongation \/ fusillade/, "détail prolongation hockey absent");
}
if (DATA.modeles.basket) {
  attend(/id="s-basket"/, "onglet basket absent");
  attend(/Force nette et rythme/, "classement basket absent");
  attend(/Écart le plus probable/, "détail basket absent");
}
attend(/id="s-fiabilite"/, "onglet fiabilité absent");
attend(/walk-forward/i, "explication du backtest absente");

// un onglet ET un panneau doivent être marqués actifs, sinon rien ne s'affiche
const ongletActif = boutons.filter(b => b.classList.contains("on"));
if (!ongletActif.length) erreurs.push("aucun onglet de navigation actif : écran vide");
if (boutons.length < 2) erreurs.push("moins de 2 onglets de navigation créés");

// chaque événement analysé doit avoir produit une ligne de détail dépliable
const nEvs = (DATA.calendrier.evenements || []).length;
const nDet = (rendu.match(/class="det"/g) || []).length;
if (nEvs && nDet !== nEvs)
  erreurs.push(`${nEvs} événements mais ${nDet} blocs de détail`);

if (erreurs.length) {
  console.error("ÉCHEC :\n  - " + erreurs.join("\n  - "));
  process.exit(1);
}
console.log(`OK — rendu sans exception : ${rendu.length} caractères HTML, ` +
            `${nEvs} événements, ${nDet} blocs de détail, ${boutons.length} onglets dont ${ongletActif.length} actif`);
