"""
Génère la version autonome : un seul HTML, sans serveur, sans internet.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["PRONOS_SANS_CALENDRIER"] = "1"
import serveur as S

RACINE = Path(__file__).resolve().parent
SORTIE = RACINE / "impactgames-autonome.html"

MOTEUR_JS = r"""
function erf(x){const s=x<0?-1:1;x=Math.abs(x);const a1=0.254829592,a2=-0.284496736,a3=1.421413741,a4=-1.453152027,a5=1.061405429,p=0.3275911;const t=1/(1+p*x);const y=1-((((a5*t+a4)*t+a3)*t+a2)*t+a1)*t*Math.exp(-x*x);return s*y;}
function normCdf(x){return 0.5*(1+erf(x/Math.SQRT2));}
function logFact(n){let s=0;for(let i=2;i<=n;i++)s+=Math.log(i);return s;}
function poissonPmf(k,lam){if(lam<=0)return k===0?1:0;return Math.exp(-lam+k*Math.log(lam)-logFact(k));}
function clip(x,a,b){return x<a?a:x>b?b:x;}
function arr4(x){return Math.round(x*1e4)/1e4;}
function arr2(x){return Math.round(x*1e2)/1e2;}
function arr1(x){return Math.round(x*10)/10;}

function pronosticBasket(L,h,a){
  const F=L.forces||{}; if(!F[h]||!F[a]) return null;
  let mu_h=clip(F[h].att*F[a].dfn*L.mu_home,70,160);
  let mu_a=clip(F[a].att*F[h].dfn*L.mu_away,70,160);
  const margin=mu_h-mu_a, total=mu_h+mu_a;
  const sm=Math.max(L.sigma_margin||12,6), st=Math.max(L.sigma_total||12,6);
  const p1=clip(normCdf(margin/sm),0.02,0.98);
  const over={}, under={};
  for(let x=Math.round(total)-12;x<=Math.round(total)+12;x+=2){
    const line=x+0.5; if(line<180||line>260) continue;
    const po=clip(1-normCdf((line-total)/st),0.02,0.98);
    over[String(line)]=arr4(po); under[String(line)]=arr4(1-po);
  }
  let line_ref=Math.round(total*2)/2; if(line_ref===Math.floor(line_ref)) line_ref+=0.5;
  const over_ref=clip(1-normCdf((line_ref-total)/st),0.02,0.98);
  const spreads={}; [-9.5,-7.5,-5.5,-3.5,-1.5,1.5,3.5,5.5,7.5,9.5].forEach(s=>{
    spreads[String(s)]=arr4(clip(1-normCdf(((-s)-margin)/sm),0.02,0.98));
  });
  const ne_h=F[h].n_eff||0, ne_a=F[a].n_eff||0;
  const mini=Math.min(ne_h,ne_a);
  const conf=mini>=40?"haute":mini>=18?"moyenne":"faible";
  return {sport:"basket",home:h,away:a,ligue:L.nom,
    lambda_home:arr2(mu_h),lambda_away:arr2(mu_a),points_attendus:arr2(total),marge:arr2(margin),
    victoire_1:arr4(p1),nul:0,victoire_2:arr4(1-p1),
    over,under,spread:spreads,line_totale:line_ref,over_ref:arr4(over_ref),under_ref:arr4(1-over_ref),
    sigma_margin:arr2(sm),sigma_total:arr2(st),
    fiabilite:{niveau:conf,home_n_eff:ne_h,away_n_eff:ne_a,home_n_brut:F[h].n_brut||0,away_n_brut:F[a].n_brut||0}};
}

function pronosticHockey(L,h,a){
  const F=L.forces||{}; if(!F[h]||!F[a]) return null;
  const MAXG=10;
  let lam=clip(F[h].att*F[a].dfn*L.gamma,0.15,8);
  let mu=clip(F[a].att*F[h].dfn*L.s_away,0.15,8);
  const rho=clip(L.rho||0,-0.2,0.2);
  const ph=[],pa=[]; for(let i=0;i<=MAXG;i++){ph.push(poissonPmf(i,lam));pa.push(poissonPmf(i,mu));}
  const M=[]; let s=0;
  for(let i=0;i<=MAXG;i++){M.push([]);for(let j=0;j<=MAXG;j++){M[i].push(ph[i]*pa[j]);}}
  M[0][0]*=Math.max(1-lam*mu*rho,1e-9); M[0][1]*=Math.max(1+lam*rho,1e-9);
  M[1][0]*=Math.max(1+mu*rho,1e-9); M[1][1]*=Math.max(1-rho,1e-9);
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++){M[i][j]=Math.max(M[i][j],0);s+=M[i][j];}
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++) M[i][j]/=Math.max(s,1e-12);
  let p1=0,pX=0,p2=0,btts=0,puck=0;
  const over={},under={}; [3.5,4.5,5.5,6.5,7.5].forEach(x=>{over[String(x)]=0;under[String(x)]=0;});
  const cases=[];
  for(let i=0;i<=MAXG;i++)for(let j=0;j<=MAXG;j++){
    const p=M[i][j]; if(i>j)p1+=p; else if(i===j)pX+=p; else p2+=p;
    const tot=i+j; [3.5,4.5,5.5,6.5,7.5].forEach(x=>{ if(tot>x)over[String(x)]+=p; else if(tot<x)under[String(x)]+=p; });
    if(i>=1&&j>=1)btts+=p; if(i-j>=2)puck+=p;
    cases.push([i,j,p]);
  }
  cases.sort((x,y)=>y[2]-x[2]);
  const ml1=p1+0.5*pX, ml2=p2+0.5*pX;
  const ne_h=F[h].n_eff||0, ne_a=F[a].n_eff||0, mini=Math.min(ne_h,ne_a);
  const conf=mini>=40?"haute":mini>=18?"moyenne":"faible";
  const oo={},uu={}; Object.keys(over).forEach(k=>{oo[k]=arr4(over[k]);uu[k]=arr4(under[k]);});
  return {sport:"hockey",home:h,away:a,ligue:L.nom,
    lambda_home:arr4(lam)*1?+(lam.toFixed(3)):lam,lambda_away:+mu.toFixed(3),buts_attendus:+(lam+mu).toFixed(2),
    victoire_1:arr4(ml1),nul:arr4(pX),victoire_2:arr4(ml2),
    regulation_1:arr4(p1),regulation_X:arr4(pX),regulation_2:arr4(p2),
    over:oo,under:uu,btts_oui:arr4(btts),btts_non:arr4(1-btts),puck_home:arr4(puck),
    scores_top:cases.slice(0,8).map(t=>({score:t[0]+"-"+t[1],p:arr4(t[2])})),
    matrice:Array.from({length:8},(_,i)=>Array.from({length:8},(_,j)=>arr4(M[i][j]))),
    fiabilite:{niveau:conf,home_n_eff:ne_h,away_n_eff:ne_a,home_n_brut:F[h].n_brut||0,away_n_brut:F[a].n_brut||0}};
}

function eloExpect(a,b){return 1/(1+Math.pow(10,(b-a)/400));}
function pMatchFromSet(p,bo){p=clip(p,0.02,0.98);const q=1-p;return bo>=5?p*p*p*(1+3*q+6*q*q):p*p*(1+2*q);}
function pSetFromMatch(pm,bo){let lo=0.02,hi=0.98;for(let i=0;i<40;i++){const mid=0.5*(lo+hi);if(pMatchFromSet(mid,bo)<pm)lo=mid;else hi=mid;}return 0.5*(lo+hi);}
function pronosticTennis(L,p1,p2,surface,bestOf){
  const J=L.joueurs||{}; if(!J[p1]||!J[p2]) return null;
  const surf=(surface||"Hard"); const key=surf==="Clay"?"elo_clay":surf==="Grass"?"elo_grass":"elo_hard";
  const shrink=(nom,e)=>{const n=J[nom].n||0; const w=Math.min(1,n/25); return w*e+(1-w)*1500;};
  let e1=shrink(p1,0.65*J[p1].elo+0.35*(J[p1][key]||J[p1].elo));
  let e2=shrink(p2,0.65*J[p2].elo+0.35*(J[p2][key]||J[p2].elo));
  const p1w=clip(eloExpect(e1,e2),0.03,0.97);
  const bo=bestOf>=5?5:3; const ps=pSetFromMatch(p1w,bo); const q=1-ps;
  let sets={}, eSets;
  if(bo>=5){sets={"3-0":ps**3,"3-1":3*ps**3*q,"3-2":6*ps**3*q*q,"0-3":q**3,"1-3":3*q**3*ps,"2-3":6*q**3*ps*ps};
    eSets=3*(sets["3-0"]+sets["0-3"])+4*(sets["3-1"]+sets["1-3"])+5*(sets["3-2"]+sets["2-3"]);}
  else{sets={"2-0":ps*ps,"2-1":2*ps*ps*q,"0-2":q*q,"1-2":2*q*q*ps};
    eSets=2*(sets["2-0"]+sets["0-2"])+3*(sets["2-1"]+sets["1-2"]);}
  const eJeux=eSets*9.7, sig=4.4;
  const over={},under={}; [19.5,20.5,21.5,22.5,23.5,24.5,25.5,26.5].forEach(x=>{
    const po=clip(1-normCdf((x-eJeux)/sig),0.03,0.97); over[String(x)]=arr4(po); under[String(x)]=arr4(1-po);
  });
  const n1=J[p1].n||0,n2=J[p2].n||0,mini=Math.min(n1,n2);
  const conf=mini>=40?"haute":mini>=15?"moyenne":"faible";
  const so={}; Object.keys(sets).forEach(k=>so[k]=arr4(sets[k]));
  return {sport:"tennis",home:p1,away:p2,ligue:L.nom,surface:surf,best_of:bo,
    elo_1:arr1(e1),elo_2:arr1(e2),victoire_1:arr4(p1w),nul:0,victoire_2:arr4(1-p1w),
    p_set:arr4(ps),sets:so,sets_attendus:arr2(eSets),jeux_attendus:arr1(eJeux),over,under,
    straight_sets_1:arr4(sets["2-0"]||sets["3-0"]||0),
    straight_sets_2:arr4(sets["0-2"]||sets["0-3"]||0),
    fiabilite:{niveau:conf,home_n_eff:n1,away_n_eff:n2,home_n_brut:n1,away_n_brut:n2,
      rank_1:J[p1].rank,rank_2:J[p2].rank}};
}

function moteurLigue(sport,div){return ((DATA.moteur[sport]||{})[div])||null;}
function pronosticJS(sport,div,h,a,extra){
  const L=moteurLigue(sport,div); if(!L) return null;
  extra=extra||{};
  let p=null;
  if(sport==="basket") p=pronosticBasket(L,h,a);
  else if(sport==="hockey") p=pronosticHockey(L,h,a);
  else if(sport==="tennis") p=pronosticTennis(L,h,a,extra.surface||"Hard",parseInt(extra.best_of||3,10));
  if(!p) return null;
  p.ligue=div; p.sport=sport;
  for(const fx of (DATA.matchs||[])){
    if(fx.sport===sport&&fx.div===div&&fx.home===h&&fx.away===a&&fx.cote_1&&fx.cote_2){
      /* marché déjà dévigé côté précalcul */
    }
  }
  return p;
}

function conseilsJS(seuil,sport){
  const jours={};
  for(const m of DATA.matchs){
    if(sport&&m.sport!==sport) continue;
    if(!m.disponible) continue;
    let cands=[["1",m.p1],["2",m.p2]];
    if(m.sport==="basket"){ cands.push(["over",m.over_ref],["under",m.under_ref]); }
    else if(m.sport==="hockey"){ const o=m.over||{},u=m.under||{};
      cands.push(["over 5.5",o["5.5"]],["under 5.5",u["5.5"]],["les deux marquent",m.btts]); }
    else if(m.sport==="tennis"){ const s=m.sets||{};
      cands.push(["sets 2-0",s["2-0"]||s["3-0"]],["over 22.5 jeux",(m.over||{})["22.5"]]); }
    cands=cands.filter(c=>c[1]!=null);
    if(!cands.length) continue;
    let best=cands[0]; for(const c of cands) if(c[1]>best[1]) best=c;
    if(best[1]<seuil) continue;
    const item={sport:m.sport,div:m.div,ligue:m.ligue,date:m.date,heure:m.heure,jour:m.jour,
      jour_delta:m.jour_delta,home:m.home,away:m.away,option:best[0],p:+best[1].toFixed(4),
      cote_juste:best[1]>0?+(1/best[1]).toFixed(2):null,confiance:m.confiance};
    (jours[m.jour_delta]=jours[m.jour_delta]||[]).push(item);
  }
  const liste=Object.keys(jours).map(Number).sort((a,b)=>a-b).map(d=>{
    const sel=jours[d].sort((a,b)=>b.p-a.p);
    return {jour:sel[0].jour,jour_delta:d,date:sel[0].date,nb:sel.length,selections:sel};
  });
  return {seuil,jours:liste,note:"Probabilités du moteur statistique. Rentabilité face aux cotes non démontrée."};
}

async function api(p){
  const [chemin,qs]=String(p).split("?");
  const q=new URLSearchParams(qs||"");
  const g=k=>q.get(k)||"";
  switch(chemin){
    case "/api/ligues": return DATA.ligues;
    case "/api/matchs": return DATA.matchs;
    case "/api/bilan": return DATA.bilan;
    case "/api/conseils": return conseilsJS(parseFloat(q.get("seuil")||"0.70"), q.get("sport")||null);
    case "/api/classement": return (DATA.classements[g("sport")+"|"+g("div")])||null;
    case "/api/extremes": return (DATA.extremes[g("sport")||"basket"])||{plus_prolifiques:[],plus_fermes:[]};
    case "/api/pronostic":{
      const r=pronosticJS(g("sport"),g("div"),decodeURIComponent(g("home")),decodeURIComponent(g("away")),
        {surface:g("surface")||"Hard",best_of:g("best_of")||"3"});
      if(!r) throw new Error(p); return r;
    }
    case "/api/refresh":
    case "/api/maj":
      return {impossible:true,
        message:"Version web / autonome : les données sont embarquées dans ce fichier. "+
                "Un navigateur ne peut pas ré-entraîner le modèle. La mise à jour est faite par GitHub "+
                "(toutes les 3 h). Pour forcer : onglet Actions du dépôt → Run workflow, puis rechargez."};
    default: throw new Error("route inconnue : "+chemin);
  }
}
"""


def precalculer():
    print("→ pré-calcul…")
    data = {
        "ligues": S.api_ligues(),
        "matchs": S.api_matchs(),
        "bilan": S.api_bilan(),
        "classements": {},
        "extremes": {},
        "moteur": {},
        "meta": S.DB.get("meta") or {},
    }
    for lig in data["ligues"]:
        sport, div = lig["sport"], lig["div"]
        try:
            data["classements"][f"{sport}|{div}"] = S.api_classement(sport, div)
        except Exception:
            data["classements"][f"{sport}|{div}"] = None
        L = S.ligue(sport, div)
        if not L:
            continue
        mot = {"nom": L.get("nom"), "pays": L.get("pays"), "forces": L.get("forces"),
               "joueurs": L.get("joueurs"),
               "mu_home": L.get("mu_home"), "mu_away": L.get("mu_away"),
               "sigma_margin": L.get("sigma_margin"), "sigma_total": L.get("sigma_total"),
               "gamma": L.get("gamma"), "s_away": L.get("s_away"), "rho": L.get("rho")}
        data["moteur"].setdefault(sport, {})[div] = mot
    for sp in ("basket", "hockey", "tennis"):
        try:
            data["extremes"][sp] = S.api_extremes(sp)
        except Exception:
            data["extremes"][sp] = {"plus_prolifiques": [], "plus_fermes": []}
    print(f"   {len(data['ligues'])} ligues | {len(data['matchs'])} matchs")
    return data


def generer(data):
    html = (RACINE / "static" / "index.html").read_text(encoding="utf-8")
    ancienne = 'async function api(p){const r=await fetch(p);if(!r.ok)throw new Error(p);return r.json();}'
    if ancienne not in html:
        raise SystemExit("api() d'origine introuvable")
    html = html.replace(ancienne, "/* api() fournie par le moteur autonome */", 1)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    bandeau = (
        "\n/* IMPACT GAMES — version autonome. Données et moteur embarqués. */\n"
        "const DATA = " + payload + ";\n" + MOTEUR_JS + "\n"
    )
    html = html.replace("<script>", "<script>" + bandeau, 1)
    html = html.replace("<title>Impact Games — basket · hockey · tennis</title>",
                        "<title>Impact Games — version autonome</title>", 1)
    SORTIE.write_text(html, encoding="utf-8")
    print(f"   {SORTIE.name} : {SORTIE.stat().st_size/1024:,.0f} Ko")
    return SORTIE


if __name__ == "__main__":
    d = precalculer()
    generer(d)
    print("→ ouvrez impactgames-autonome.html dans un navigateur.")
