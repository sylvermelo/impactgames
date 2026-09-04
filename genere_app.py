"""
GÉNÉRATEUR D'APPLICATION — un seul fichier HTML autonome
================================================================================
Produit `impactgames-autonome.html` : une application complète qui tient dans
UN fichier, données comprises. Aucune installation, aucun serveur, aucune
connexion — on l'ouvre dans un navigateur, y compris sur téléphone, et elle
fonctionne.

C'est le même principe que le projet foot, et ce n'est pas un choix esthétique :
c'est ce qui permet de publier sur GitHub Pages gratuitement, de partager le
fichier par message, et de le consulter dans un avion.

Usage :  python3 genere_app.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DATA = RACINE / "data"
SORTIE = RACINE / "impactgames-autonome.html"


def _lire(nom: str):
    p = DATA / nom
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ! {nom} illisible ({e}) : section omise")
        return None


def generer() -> int:
    modeles_doc = _lire("modeles.json")
    calendrier = _lire("calendrier.json")
    backtests = {s: _lire(f"backtest_{s}.json") for s in ("tennis", "hockey", "basket")}
    backtests = {k: v for k, v in backtests.items() if v}

    if not modeles_doc:
        print("ERREUR : data/modeles.json absent — lance d'abord entraine.py")
        return 1
    modeles = modeles_doc.get("modeles", {})
    if not modeles:
        print("ERREUR : aucun modèle dans data/modeles.json")
        return 1

    payload = {
        "genere_le": modeles_doc.get("genere_le"),
        "modeles": modeles,
        "calendrier": calendrier or {"evenements": [], "n_evenements": 0},
        "backtests": backtests,
    }

    # `</script>` dans les données casserait le fichier : on l'échappe
    donnees = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    html = MODELE.replace("/*__DATA__*/", f"const DATA = {donnees};")
    SORTIE.write_text(html, encoding="utf-8")
    taille = SORTIE.stat().st_size
    print(f"→ {SORTIE.name} écrit ({taille / 1024:.0f} Ko) "
          f"pour {len(modeles)} sport(s) : {', '.join(modeles)}")
    print(f"  {payload['calendrier'].get('n_evenements', 0)} événements au calendrier, "
          f"{payload['calendrier'].get('n_analyses', 0)} analysés")
    return 0


MODELE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Impact Games — moteur multi-sports</title>
<style>
:root{--f:#0d1117;--c:#161b22;--b:#30363d;--t:#e6edf3;--m:#8b949e;--a:#58a6ff;
--v:#3fb950;--r:#f85149;--o:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--f);color:var(--t);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:22px 20px 14px;border-bottom:1px solid var(--b);
background:linear-gradient(180deg,#131a24,#0d1117)}
h1{margin:0;font-size:22px;letter-spacing:.3px}
h1 span{color:var(--a)}
.sub{color:var(--m);font-size:13px;margin-top:4px}
nav{display:flex;gap:6px;padding:12px 20px;border-bottom:1px solid var(--b);
flex-wrap:wrap;position:sticky;top:0;background:var(--f);z-index:5}
nav button{background:var(--c);color:var(--m);border:1px solid var(--b);
padding:8px 16px;border-radius:20px;cursor:pointer;font-size:14px}
nav button.on{background:var(--a);color:#04121f;border-color:var(--a);font-weight:600}
main{padding:16px 20px 60px;max-width:1200px;margin:0 auto}
section{display:none}section.on{display:block}
table{width:100%;border-collapse:collapse;font-size:14px;margin:8px 0 22px}
th{text-align:left;color:var(--m);font-weight:500;font-size:12px;
text-transform:uppercase;letter-spacing:.5px;padding:7px 8px;border-bottom:1px solid var(--b)}
td{padding:9px 8px;border-bottom:1px solid #21262d;vertical-align:top}
tr.e{cursor:pointer}tr.e:hover{background:#1a2029}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pct{display:inline-block;min-width:44px;text-align:right;font-variant-numeric:tabular-nums}
.hi{color:var(--v);font-weight:600}.mid{color:var(--o)}.lo{color:var(--m)}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:9px;
background:#21262d;color:var(--m);margin-left:6px}
.card{background:var(--c);border:1px solid var(--b);border-radius:10px;
padding:14px 16px;margin:12px 0}
.card h3{margin:0 0 8px;font-size:15px}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:8px}
.k div{background:#0d1117;border:1px solid var(--b);border-radius:8px;padding:9px 11px}
.k b{display:block;font-size:19px;font-variant-numeric:tabular-nums}
.k small{color:var(--m);font-size:11px;text-transform:uppercase;letter-spacing:.4px}
.det{display:none;background:#0d1117}
.det td{padding:14px 18px;border-bottom:1px solid var(--b)}
.det.on{display:table-row}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px}
.g div{background:var(--c);border:1px solid var(--b);border-radius:7px;padding:7px 10px;font-size:13px}
.g span{color:var(--m);display:block;font-size:11px}
.note{color:var(--m);font-size:13px;border-left:3px solid var(--o);padding:6px 0 6px 12px;margin:14px 0}
footer{color:var(--m);font-size:12px;padding:20px;text-align:center;border-top:1px solid var(--b)}
@media(max-width:640px){.num,th{font-size:12px}main{padding:12px}}
</style>
</head>
<body>
<header>
  <h1>Impact<span>Games</span> — moteur multi-sports</h1>
  <div class="sub" id="maj"></div>
</header>
<nav id="nav"></nav>
<main id="main"></main>
<footer>
  Probabilités statistiques, pas des certitudes. Aucun pari n'est pris sur ce site.
  Le jeu peut créer une dépendance.
</footer>
<script>
/*__DATA__*/

const SPORTS = {
  tennis:{nom:"Tennis", cle:"tennis"},
  hockey:{nom:"Hockey", cle:"hockey"},
  basket:{nom:"Basket", cle:"basket"}
};
const P = v => v==null ? "—" : (v*100).toFixed(1)+"%";
const cls = v => v==null ? "lo" : v>=.60 ? "hi" : v>=.45 ? "mid" : "lo";
const esc = s => String(s??"").replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function entete(){
  const d = DATA.genere_le ? new Date(DATA.genere_le) : null;
  const n = DATA.calendrier?.n_evenements ?? 0;
  const a = DATA.calendrier?.n_analyses ?? 0;
  document.getElementById("maj").textContent =
    (d ? "Modèles entraînés le "+d.toLocaleString("fr-FR") : "Modèles entraînés")
    + " · "+n+" événements à venir, "+a+" analysés"
    + " · tennis "+(DATA.modeles.tennis?.n_matchs??"—")+" matchs"
    + " · hockey "+(DATA.modeles.hockey?.n_matchs??"—")+" matchs"
    + " · basket "+(DATA.modeles.basket?.n_matchs??"—")+" matchs";
}

function nav(){
  const el = document.getElementById("nav");
  Object.entries(SPORTS).forEach(([k,s],i)=>{
    if(!DATA.modeles[k]) return;
    const b = document.createElement("button");
    b.textContent = s.nom + (i===0?"":"");
    b.className = ""; b.dataset.k = k;
    b.onclick = ()=>choisir(k);
    el.appendChild(b);
  });
  const r = document.createElement("button");
  r.textContent = "Fiabilité"; r.dataset.k = "fiabilite";
  r.onclick = ()=>choisir("fiabilite"); el.appendChild(r);
}

function choisir(k){
  document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("on", b.dataset.k===k));
  document.querySelectorAll("main section").forEach(s=>s.classList.toggle("on", s.id==="s-"+k));
}

/* ------------------------------------------------------------------ tennis */
function secTennis(m){
  const evs = (DATA.calendrier?.evenements??[]).filter(e=>e.sport==="tennis");
  let h = `<section id="s-tennis">
  <div class="card"><h3>${esc(m.moteur)}</h3>
  <div class="k">
    <div><b>${m.n_matchs.toLocaleString("fr-FR")}</b><small>matchs entraînés</small></div>
    <div><b>${m.beta.toFixed(3)}</b><small>β (sensibilité au classement)</small></div>
    <div><b>${Object.keys(m.notes_globales).length}</b><small>joueurs suivis</small></div>
    <div><b>${esc(m.periode[0].slice(0,4))}→${esc(m.periode[1].slice(0,4))}</b><small>période</small></div>
  </div></div>`;

  h += `<h3 style="margin:20px 0 4px">Matchs à venir</h3>`;
  if(!evs.length) h += `<p class="note">Aucun match ATP reçu pour les 8 prochains jours
    (hors saison, ou source injoignable lors de la dernière mise à jour).</p>`;
  else {
    h += `<table><thead><tr><th>Heure</th><th>Rencontre</th><th class="num">A gagne</th>
      <th class="num">B gagne</th><th class="num">Jeux</th><th>Surface</th></tr></thead><tbody>`;
    evs.forEach((e,i)=>{
      const p = e.pronostic;
      h += `<tr class="e" onclick="tg('t${i}')"><td>${esc(e.heure)}</td>
        <td>${esc(e.nom_a)} <span class="tag">${esc(e.competition||"")}</span><br>
            <span style="color:var(--m)">vs ${esc(e.nom_b)}</span></td>
        <td class="num ${p?cls(p.p_a):""}">${p?P(p.p_a):"—"}</td>
        <td class="num ${p?cls(p.p_b):""}">${p?P(p.p_b):"—"}</td>
        <td class="num">${p?p.jeux_attendus.toFixed(1):"—"}</td>
        <td>${esc(e.surface||"")}${e.best_of===5?' <span class="tag">5 sets</span>':""}</td></tr>`;
      h += `<tr class="det" id="t${i}"><td colspan="6">${p?detTennis(p,e):
        `<span style="color:var(--o)">Joueur sans historique suffisant — non analysé.</span>`}</td></tr>`;
    });
    h += `</tbody></table>`;
  }

  h += `<h3 style="margin:20px 0 4px">Classement du moteur</h3><table>
    <thead><tr><th>#</th><th>Joueur</th><th class="num">Elo</th></tr></thead><tbody>`;
  (m.classement||[]).slice(0,40).forEach((r,i)=>{
    h += `<tr><td>${i+1}</td><td>${esc(r.nom)}</td><td class="num">${r.elo.toFixed(0)}</td></tr>`;
  });
  return h + `</tbody></table></section>`;
}

function detTennis(p,e){
  const sc = Object.entries(p.scores||{}).slice(0,4)
    .map(([k,v])=>`<div><span>${esc(k)} en sets</span>${P(v)}</div>`).join("");
  const hnd = [2.5,3.5,4.5].map(x=>`<div><span>${esc(e.nom_a)} −${x} jeux</span>${P(p["A_moins_"+x])}</div>`).join("");
  const tot = [19.5,21.5,22.5,23.5].map(x=>`<div><span>Plus de ${x} jeux</span>${P(p["O"+x])}</div>`).join("");
  return `<div class="g">
    <div><span>Service A gagné</span>${P(p.p_service_a)}</div>
    <div><span>Retour A gagné</span>${P(p.p_retour_a)}</div>
    <div><span>Jeux attendus</span>${p.jeux_attendus.toFixed(1)}</div>
    <div><span>Écart de jeux</span>${p.ecart_attendu>0?"+":""}${p.ecart_attendu.toFixed(1)}</div>
    <div><span>Sans perdre de set</span>${P(p.sans_perdre_set)}</div>
    ${sc}${hnd}${tot}</div>`;
}

/* ------------------------------------------------------------------ hockey */
function secHockey(m){
  const evs = (DATA.calendrier?.evenements??[]).filter(e=>e.sport==="hockey");
  let h = `<section id="s-hockey">
  <div class="card"><h3>${esc(m.moteur)}</h3>
  <div class="k">
    <div><b>${m.n_matchs.toLocaleString("fr-FR")}</b><small>matchs entraînés</small></div>
    <div><b>×${Math.exp(m.gamma).toFixed(3)}</b><small>avantage du domicile</small></div>
    <div><b>${m.rho>0?"+":""}${m.rho.toFixed(3)}</b><small>correction Dixon-Coles ρ</small></div>
    <div><b>${m.equipes.length}</b><small>équipes</small></div>
  </div></div>`;

  h += `<h3 style="margin:20px 0 4px">Matchs à venir</h3>`;
  if(!evs.length) h += `<p class="note">Aucun match NHL reçu (intersaison, ou source
    injoignable lors de la dernière mise à jour). La saison régulière NHL démarre début octobre.</p>`;
  else {
    h += `<table><thead><tr><th>Heure</th><th>Rencontre</th><th class="num">1</th>
      <th class="num">X</th><th class="num">2</th><th class="num">Vainqueur (prol. incl.)</th>
      <th class="num">+5,5</th><th class="num">Buts</th></tr></thead><tbody>`;
    evs.forEach((e,i)=>{
      const p = e.pronostic;
      h += `<tr class="e" onclick="tg('h${i}')"><td>${esc(e.heure)}</td>
        <td>${esc(e.domicile)} <span class="tag">dom</span><br>
            <span style="color:var(--m)">${esc(e.exterieur)}</span></td>
        <td class="num ${p?cls(p["1"]):""}">${p?P(p["1"]):"—"}</td>
        <td class="num lo">${p?P(p["X"]):"—"}</td>
        <td class="num ${p?cls(p["2"]):""}">${p?P(p["2"]):"—"}</td>
        <td class="num">${p?esc(e.domicile)+" "+P(p.ml_dom):"—"}</td>
        <td class="num">${p?P(p["O5.5"]):"—"}</td>
        <td class="num">${p?p.buts_attendus.toFixed(2):"—"}</td></tr>`;
      h += `<tr class="det" id="h${i}"><td colspan="8">${p?detHockey(p,e):
        `<span style="color:var(--o)">Équipe inconnue du modèle.</span>`}</td></tr>`;
    });
    h += `</tbody></table>`;
  }

  h += `<h3 style="margin:20px 0 4px">Force nette des équipes (buts/match)</h3><table>
    <thead><tr><th>#</th><th>Équipe</th><th class="num">Attaque</th>
    <th class="num">Faiblesse déf.</th><th class="num">Force nette</th></tr></thead><tbody>`;
  (m.classement||[]).forEach(r=>{
    h += `<tr><td>${r.rang}</td><td>${esc(r.equipe)}</td>
      <td class="num">${r.attaque.toFixed(2)}</td>
      <td class="num">${r.faiblesse_defensive.toFixed(2)}</td>
      <td class="num ${r.force>0?"hi":"lo"}">${r.force>0?"+":""}${r.force.toFixed(2)}</td></tr>`;
  });
  return h + `</tbody></table></section>`;
}

function detHockey(p,e){
  const sc = (p.scores_probables||[]).map(([k,v])=>`<div><span>Score ${esc(k)}</span>${P(v)}</div>`).join("");
  const tot = [3.5,4.5,5.5,6.5,7.5].map(x=>`<div><span>Plus de ${x} buts</span>${P(p["O"+x])}</div>`).join("");
  const hnd = [0.5,1.5,2.5].map(x=>`<div><span>${esc(e.domicile)} −${x}</span>${P(p["handicap_dom_"+x])}</div>`).join("");
  return `<div class="g">
    <div><span>Prolongation / fusillade</span>${P(p.p_prolongation)}</div>
    <div><span>Buts attendus (dom)</span>${p.buts_dom_attendus.toFixed(2)}</div>
    <div><span>Buts attendus (ext)</span>${p.buts_ext_attendus.toFixed(2)}</div>
    <div><span>Les deux marquent</span>${P(p.les_deux_marquent)}</div>
    <div><span>Blanchissage</span>${P(p.blanchissage)}</div>
    <div><span>Double chance 1X</span>${P(p.double_chance_1X)}</div>
    <div><span>Double chance X2</span>${P(p.double_chance_X2)}</div>
    ${sc}${tot}${hnd}</div>`;
}

/* ------------------------------------------------------------------ basket */
function secBasket(m){
  const evs = (DATA.calendrier?.evenements??[]).filter(e=>e.sport==="basket");
  let h = `<section id="s-basket">
  <div class="card"><h3>${esc(m.moteur)}</h3>
  <div class="k">
    <div><b>${m.n_matchs.toLocaleString("fr-FR")}</b><small>matchs entraînés</small></div>
    <div><b>${m.hfa>0?"+":""}${m.hfa.toFixed(2)}</b><small>avantage domicile (points)</small></div>
    <div><b>${m.sigma_ecart.toFixed(1)}</b><small>σ de l'écart</small></div>
    <div><b>${m.equipes.length}</b><small>équipes</small></div>
  </div></div>`;

  h += `<h3 style="margin:20px 0 4px">Matchs à venir</h3>`;
  if(!evs.length) h += `<p class="note">Aucun match NBA reçu (intersaison, ou source
    injoignable lors de la dernière mise à jour). La saison NBA démarre fin octobre.</p>`;
  else {
    h += `<table><thead><tr><th>Heure</th><th>Rencontre</th><th class="num">Dom</th>
      <th class="num">Ext</th><th class="num">Écart</th><th class="num">Total</th>
      <th class="num">+225,5</th></tr></thead><tbody>`;
    evs.forEach((e,i)=>{
      const p = e.pronostic;
      h += `<tr class="e" onclick="tg('b${i}')"><td>${esc(e.heure)}</td>
        <td>${esc(e.domicile)} <span class="tag">dom</span><br>
            <span style="color:var(--m)">${esc(e.exterieur)}</span></td>
        <td class="num ${p?cls(p.dom_gagne):""}">${p?P(p.dom_gagne):"—"}</td>
        <td class="num ${p?cls(p.ext_gagne):""}">${p?P(p.ext_gagne):"—"}</td>
        <td class="num">${p?(p.ecart_attendu>0?"+":"")+p.ecart_attendu.toFixed(1):"—"}</td>
        <td class="num">${p?p.total_attendu.toFixed(1):"—"}</td>
        <td class="num">${p?P(p["O225.5"]):"—"}</td></tr>`;
      h += `<tr class="det" id="b${i}"><td colspan="7">${p?detBasket(p,e):
        `<span style="color:var(--o)">Équipe inconnue du modèle.</span>`}</td></tr>`;
    });
    h += `</tbody></table>`;
  }

  h += `<h3 style="margin:20px 0 4px">Force nette et rythme</h3><table>
    <thead><tr><th>#</th><th>Équipe</th><th class="num">Force nette</th>
    <th class="num">Rythme</th></tr></thead><tbody>`;
  (m.classement||[]).forEach(r=>{
    h += `<tr><td>${r.rang}</td><td>${esc(r.equipe)}</td>
      <td class="num ${r.force_nette>0?"hi":"lo"}">${r.force_nette>0?"+":""}${r.force_nette.toFixed(2)}</td>
      <td class="num ${r.rythme>0?"hi":"lo"}">${r.rythme>0?"+":""}${r.rythme.toFixed(2)}</td></tr>`;
  });
  return h + `</tbody></table></section>`;
}

function detBasket(p,e){
  const tot = [205.5,215.5,220.5,225.5,230.5,240.5]
    .map(x=>`<div><span>Plus de ${x} points</span>${P(p["O"+x])}</div>`).join("");
  const hnd = [2.5,4.5,6.5,8.5,10.5,12.5]
    .map(x=>`<div><span>${esc(e.domicile)} −${x}</span>${P(p["dom_moins_"+x])}</div>`).join("");
  return `<div class="g">
    <div><span>Total attendu</span>${p.total_attendu.toFixed(1)}</div>
    <div><span>Écart attendu</span>${(p.ecart_attendu>0?"+":"")+p.ecart_attendu.toFixed(1)}</div>
    <div><span>Écart le plus probable</span>${p.ecart_le_plus_probable>0?"+":""}${p.ecart_le_plus_probable}</div>
    <div><span>Prolongation</span>${P(p.p_prolongation)}</div>
    ${tot}${hnd}</div>`;
}

/* --------------------------------------------------------------- fiabilité */
function secFiabilite(){
  let h = `<section id="s-fiabilite">
  <div class="card"><h3>Ce que le moteur vaut réellement</h3>
  <p style="color:var(--m);margin:6px 0 0">Chiffres issus d'un backtest
  <b>walk-forward</b> : pour prédire une année, le modèle n'a vu QUE les années
  précédentes. Aucune donnée future ne filtre — c'est la seule façon honnête
  de mesurer.</p></div>`;

  const b = DATA.backtests||{};
  if(b.tennis){
    const t = b.tennis;
    h += `<div class="card"><h3>Tennis ATP — ${t.n_matchs.toLocaleString("fr-FR")} matchs de contrôle</h3>
      <div class="k">
        <div><b>${t.logloss_modele.toFixed(4)}</b><small>log-loss du moteur</small></div>
        <div><b>${t.logloss_elo.toFixed(4)}</b><small>log-loss Elo seul</small></div>
        <div><b>${t.logloss_hasard.toFixed(4)}</b><small>log-loss du hasard</small></div>
        <div><b>${(t.precision_favori*100).toFixed(1)}%</b><small>favori gagne</small></div>
      </div>
      <p style="color:var(--m);font-size:13px;margin-bottom:0">Lecture honnête : sur le
      seul marché « qui gagne le match », le moteur fait jeu égal avec un Elo par
      surface bien réglé. Sa valeur ajoutée est ailleurs : il produit de façon
      cohérente les scores en sets, les totaux de jeux et les handicaps, qu'un
      Elo seul ne sait pas calculer. Années évaluées : ${t.annees.join(", ")}.</p></div>`;

    const d = (t.detail||[]).slice(-1)[0];
    if(d && d.calibration && d.calibration.length){
      h += `<div class="card"><h3>Calibration — ${d.annee}</h3>
        <p style="color:var(--m);font-size:13px;margin-top:0">« Quand le moteur dit 70 %,
        ça arrive 70 % du temps ? » Un écart faible signifie que les probabilités
        sont utilisables telles quelles.</p>
        <table><thead><tr><th>Probabilité prédite</th><th class="num">Matchs</th>
        <th class="num">Taux réel</th><th class="num">Écart</th></tr></thead><tbody>`;
      d.calibration.forEach(c=>{
        h += `<tr><td>${(c.de*100).toFixed(0)}–${(c.a*100).toFixed(0)}%</td>
          <td class="num">${c.n}</td><td class="num">${(c.reel*100).toFixed(1)}%</td>
          <td class="num" style="color:${Math.abs(c.ecart)<.05?"var(--v)":"var(--o)"}">
          ${c.ecart>0?"+":""}${(c.ecart*100).toFixed(1)} pts</td></tr>`;
      });
      h += `</tbody></table></div>`;
    }
  } else {
    h += `<p class="note">Aucun backtest tennis enregistré.</p>`;
  }

  h += `<div class="card"><h3>Hockey et basket — ce qui n'est PAS encore mesuré</h3>
  <p style="color:var(--m);font-size:13px;margin-top:0">Les deux moteurs sont
  entraînés et leurs estimateurs sont validés sur données synthétiques à vérité
  connue (l'estimateur retrouve les paramètres injectés). En revanche il
  n'existe <b>aucune source gratuite de cotes historiques</b> pour la NHL ni
  pour la NBA : on ne peut donc pas encore les comparer à un bookmaker,
  contrairement au football où les cotes de clôture Pinnacle servent de juge de
  paix. Un backtest walk-forward sur ces deux sports est l'étape suivante.</p></div>`;

  h += `<div class="card"><h3>Ce qu'aucun modèle ne peut faire</h3>
  <ul style="color:var(--m);font-size:13px;margin:0;padding-left:18px">
    <li>Connaître une blessure annoncée il y a une heure.</li>
    <li>Garantir un résultat : 65 % de réussite, c'est 35 % d'échecs.</li>
    <li>Battre durablement un bookmaker sans avantage mesuré (CLV positif).</li>
    <li>Se substituer à un jugement : ces chiffres informent, ils ne décident pas.</li>
  </ul></div></section>`;
  return h;
}

/* ------------------------------------------------------------------ montage */
function tg(id){ document.getElementById(id).classList.toggle("on"); }

(function(){
  entete(); nav();
  const main = document.getElementById("main");
  if(DATA.modeles.tennis) main.insertAdjacentHTML("beforeend", secTennis(DATA.modeles.tennis));
  if(DATA.modeles.hockey) main.insertAdjacentHTML("beforeend", secHockey(DATA.modeles.hockey));
  if(DATA.modeles.basket) main.insertAdjacentHTML("beforeend", secBasket(DATA.modeles.basket));
  main.insertAdjacentHTML("beforeend", secFiabilite());
  const premier = document.querySelector("nav button");
  if(premier) choisir(premier.dataset.k);
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(generer())
