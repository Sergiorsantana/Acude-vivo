/* Assistente "Pergunte aos dados" do Açude Vivo.
 *
 * Funciona como um RAG com ferramentas, mas sem modelo generativo:
 *   1. entende a pergunta (intenção + município/açude/estado + números)
 *   2. busca os registros em dados.json com a ferramenta certa
 *   3. monta a resposta só com o que encontrou, citando fonte e data
 * Se não encontrar, diz que não sabe. Nada é inventado. Custo zero, roda no navegador.
 *
 * Depende das variáveis globais de index.html: D, RES, MUN, RES_BY, MUN_BY, UF_NAMES,
 * resPct, munPct, munStatus, statusOf, LABEL, fmt, fmtInt, fmtDate, esc, norm, flyRes, flyMun.
 */
"use strict";
(function(){
const UF_POR_NOME={};
const SIGLAS=["AL","BA","CE","MA","PB","PE","PI","RN","SE"];
let indice=null;            // nomes normalizados -> registros
const historico=[];         // [{q, html}]

const EXEMPLOS=[
  "Como está Campina Grande?",
  "Quais municípios estão críticos na Paraíba?",
  "Quantas pessoas estão em risco em Pernambuco?",
  "Vai chover em Patos nos próximos dias?",
  "Quando o açude Jucazinho chega a 5%?",
  "Açudes abaixo de 10% no Ceará",
  "Quais os maiores açudes da Bahia?",
  "Resumo do Nordeste",
];

function prep(){
  if(indice)return;
  for(const [s,n] of Object.entries(UF_NAMES))UF_POR_NOME[norm(n)]=s;
  indice=[];
  for(const m of MUN)indice.push({tipo:"mun",n:norm(m.nome),o:m});
  for(const r of RES){
    indice.push({tipo:"res",n:norm(r.nome),o:r});
    // variantes: "Epitácio Pessoa (Boqueirão)" -> "boqueirao"; "Curema/Mãe d'Água" -> partes
    for(const p of r.nome.split(/[()\/]/).map(s=>norm(s).trim()).filter(s=>s.length>3))
      if(p!==norm(r.nome))indice.push({tipo:"res",n:p,o:r});
  }
  indice.sort((a,b)=>b.n.length-a.n.length);
}

// ------------------------------------------------------------ entendimento
function achaUF(qOrig,q){
  for(const [n,s] of Object.entries(UF_POR_NOME))if(new RegExp(`\\b${n}\\b`).test(q))return s;
  // sigla só em maiúsculas (evita confundir "se" e "pe" com palavras)
  const m=qOrig.match(/\b(AL|BA|CE|MA|PB|PE|PI|RN|SE)\b/);
  return m?m[1]:null;
}
function achaEntidades(q,uf){
  const achados=[];
  const qq=" "+q.replace(/[^a-z0-9 ]/g," ").replace(/\s+/g," ")+" ";
  for(const it of indice){
    if(it.n.length<3)continue;
    if(!qq.includes(" "+it.n+" "))continue;
    if(achados.some(a=>a.n.includes(it.n)&&a.n!==it.n))continue; // já achou um nome maior que contém este
    if(UF_POR_NOME[it.n])continue; // nome de estado
    achados.push(it);
  }
  // prefere o mesmo estado, se o usuário citou um
  if(uf)achados.sort((a,b)=>(b.o.uf===uf)-(a.o.uf===uf));
  return achados;
}
function intencao(q){
  const tem=(...p)=>p.some(x=>q.includes(x));
  if(tem("chuva","chover","choveu","previsao do tempo","precipita"))return "chuva";
  if(tem("monitor de secas","area em seca","areas em seca","seca no estado","estiagem","categoria de seca"))return "seca";
  if(tem("quando","quanto tempo","autonomia","secar","vai secar","acabar","dias ate","chega a 5","esvaziar"))return "autonomia";
  if(tem("quantas pessoas","populacao","habitantes","pessoas em risco","gente"))return "populacao";
  if(tem("abaixo de","menos de","inferior a"))return "abaixo";
  if(tem("maiores","maior acude","maior reservatorio","maiores reservatorios"))return "maiores";
  if(tem("alerta"))return "alertas";
  if(tem("transposicao","sao francisco","pisf"))return "transposicao";
  if(tem("critico","criticos","critica","piores","pior","mais baixo","mais baixos","mais vazios","risco"))return "criticos";
  if(tem("resumo","situacao geral","panorama","como esta o nordeste","nordeste"))return "resumo";
  if(tem("como esta","situacao","volume","nivel","quanto tem","abastece","abastecido"))return "situacao";
  return null;
}

// ------------------------------------------------------------ ferramentas (busca nos dados)
const dataRef=()=>fmtDate(D.gerado_em);
const fonte=(...f)=>`<div class="ask-src">Fonte: ${f.filter(Boolean).join(" · ")} · dados de ${dataRef()}</div>`;
const PREP={AL:"em",BA:"na",CE:"no",MA:"no",PB:"na",PE:"em",PI:"no",RN:"no",SE:"em"};
const linkMun=m=>`<a href="#" data-ask-mun="${m.cod}">${esc(m.nome)}/${m.uf}</a>`;
const linkRes=r=>`<a href="#" data-ask-res="${r.codigo}">${esc(r.nome)}</a>`;
const pctTxt=p=>p==null?"sem medição":fmt(p)+"%";
const pill=st=>`<span class="pill" style="background:${({crit:"#ef4444",alert:"#f59e0b",ok:"#22c55e",nd:"#7b8a8c",sm:"#3b4a4d"})[st]}">${LABEL[st]}</span>`;
const autTxt=i=>!i||i.autonomia_dias==null?null:i.autonomia_dias===0?"já está abaixo de 5% e segue caindo":`chega a 5% em cerca de ${fmtInt(i.autonomia_dias)} dias se o ritmo atual continuar`;

function situacaoMun(m){
  const st=munStatus(m), p=munPct(m);
  let h=`<p><b>${linkMun(m)}</b> ${pill(st)} · ${fmtInt(m.pop)} habitantes (Censo 2022).</p>`;
  if(m.mananciais.length){
    h+=`<p>É abastecido por ${m.mananciais.length} açude(s) monitorado(s) pela ANA:</p><ul>`+
      m.mananciais.map(c=>RES_BY[c]).filter(Boolean).map(r=>`<li>${linkRes(r)}: <b>${pctTxt(resPct(r))}</b>${r.ind?` (medição de ${fmtDate(r.ind.data)})`:""}</li>`).join("")+"</ul>";
    const pior=RES_BY[m.manancial_critico]; const a=autTxt(pior?.ind);
    if(a)h+=`<p>O mais baixo, ${linkRes(pior)}, ${a}.</p>`;
  }else h+=`<p>Não há captação deste município em açude monitorado pelo SAR/ANA. O abastecimento pode vir de poços, rios ou açudes menores, e por isso não há dado de volume para avaliar.</p>`;
  if(m.chuva)h+=`<p>Chuva: ${fmt(m.chuva.obs_30d)} mm nos últimos 30 dias; previsão de ${fmt(m.chuva.prev_15d)} mm nos próximos 15 dias.</p>`;
  if(m.pisf)h+=`<p>${m.pisf<=new Date().getFullYear()?"É beneficiado pela Transposição do São Francisco.":"Está previsto para receber água da Transposição em "+m.pisf+"."}</p>`;
  return h+fonte("ANA/SAR","Atlas Águas","IBGE",m.chuva?"Open-Meteo":"");
}
function situacaoRes(r){
  const i=r.ind, p=resPct(r);
  if(!i)return `<p>${linkRes(r)} (${r.uf}) está cadastrado no SAR/ANA, mas não tem medições no último ano. Não tenho como dizer o volume atual.</p>`+fonte("ANA/SAR");
  let h=`<p><b>${linkRes(r)}</b> (${esc(r.municipio||"")}/${r.uf}) ${pill(statusOf(p))}</p>
  <p>Está com <b>${fmt(i.pct,1)}%</b>${i.vol!=null?` (${fmt(i.vol)} hm³ de ${fmt(r.cap)} hm³)`:""} na medição de ${fmtDate(i.data)}.`;
  if(i.ha_30_dias!=null)h+=` Em 30 dias variou ${(i.pct-i.ha_30_dias>=0?"+":"")+fmt(i.pct-i.ha_30_dias)} pontos.`;
  if(i.ano_anterior!=null)h+=` Há um ano estava em ${fmt(i.ano_anterior)}%.`;
  h+="</p>";
  const a=autTxt(i); if(a)h+=`<p>No ritmo dos últimos 60 dias, ${a}.</p>`;
  else if(i.tendencia_pp_dia!=null)h+=`<p>O volume está estável ou subindo nos últimos 60 dias.</p>`;
  if(r.municipios.length){const ms=r.municipios.map(c=>MUN_BY[c]).filter(Boolean);
    h+=`<p>Abastece ${ms.length} município(s), com ${fmtInt(ms.reduce((s,m)=>s+(m.pop||0),0))} habitantes: ${ms.slice(0,8).map(linkMun).join(", ")}${ms.length>8?"…":""}.</p>`}
  if(r.sistema==="sin")h+=`<p class="ask-src">Reservatório do setor elétrico: o percentual é do volume útil.</p>`;
  return h+fonte("ANA/SAR","Atlas Águas","IBGE");
}
function chuvaMun(m){
  const c=m.chuva;
  if(!c)return `<p>Não tenho dados de chuva para ${linkMun(m)} nesta atualização.</p>`;
  const dias=c.prev_dias.filter(d=>d[1]>=1);
  let h=`<p><b>${linkMun(m)}</b>: previsão de <b>${fmt(c.prev_7d)} mm</b> nos próximos 7 dias e <b>${fmt(c.prev_15d)} mm</b> em 15 dias. Nos últimos 30 dias choveu ${fmt(c.obs_30d)} mm.</p>`;
  h+=dias.length?`<p>Dias com chuva prevista (≥ 1 mm): ${dias.slice(0,8).map(d=>`${fmtDate(d[0]).slice(0,5)} (${fmt(d[1])} mm${d[2]!=null?", "+d[2]+"%":""})`).join(", ")}.</p>`
    :`<p>Nenhum dia com chuva de 1 mm ou mais está previsto nos próximos 15 dias.</p>`;
  return h+fonte("Open-Meteo (modelos ECMWF, GFS e outros)")+`<div class="ask-src">Previsão de modelo numérico: pode mudar de um dia para o outro.</div>`;
}
function chuvaUF(uf){
  const ms=MUN.filter(m=>m.uf===uf&&m.chuva);
  if(!ms.length)return `<p>Sem dados de chuva para ${UF_NAMES[uf]}.</p>`;
  const top=[...ms].sort((a,b)=>b.chuva.prev_15d-a.chuva.prev_15d).slice(0,6);
  const e=D.estados[uf].chuva;
  return `<p>${PREP[uf][0].toUpperCase()+PREP[uf].slice(1)} <b>${UF_NAMES[uf]}</b>, a média prevista é de <b>${fmt(e?.prev_15d)} mm</b> nos próximos 15 dias (${fmt(e?.prev_7d)} mm em 7 dias). Nos últimos 30 dias a média foi ${fmt(e?.obs_30d)} mm.</p>
   <p>Onde mais deve chover:</p><ul>${top.map(m=>`<li>${linkMun(m)}: ${fmt(m.chuva.prev_15d)} mm</li>`).join("")}</ul>`+fonte("Open-Meteo");
}
function filtroUF(arr,uf){return uf?arr.filter(o=>o.uf===uf):arr}
const onde=uf=>uf?`${PREP[uf]} ${UF_NAMES[uf]}`:"no Nordeste";
function autonomiaLista(uf){
  const rs=filtroUF(RES,uf).filter(r=>r.ind&&r.ind.autonomia_dias!=null&&!r.ind.atrasado&&r.municipios.length)
    .sort((a,b)=>a.ind.autonomia_dias-b.ind.autonomia_dias).slice(0,12);
  if(!rs.length)return `<p>Nenhum açude que abastece cidades ${onde(uf)} está em queda que leve a 5% no ritmo atual.</p>`+fonte("ANA/SAR","Atlas Águas");
  return `<p>Açudes que abastecem cidades ${onde(uf)} e estão mais perto de 5%, no ritmo dos últimos 60 dias:</p><ul>${rs.map(r=>`<li>${linkRes(r)} (${r.uf}): ${fmt(r.ind.pct)}%, ${r.ind.autonomia_dias===0?"já abaixo de 5%":"~"+fmtInt(r.ind.autonomia_dias)+" dias"} · ${r.municipios.length} município(s)</li>`).join("")}</ul>`+fonte("ANA/SAR","Atlas Águas");
}
function criticos(uf){
  const ms=filtroUF(MUN,uf).filter(m=>munStatus(m)==="crit").sort((a,b)=>(b.pop||0)-(a.pop||0));
  if(!ms.length)return `<p>Nenhum município ${onde(uf)} depende de açude monitorado em situação crítica (≤ 20%).</p>`+fonte("ANA/SAR","Atlas Águas");
  return `<p><b>${ms.length} municípios</b> ${onde(uf)} dependem de açude com até 20% (${fmtInt(ms.reduce((s,m)=>s+(m.pop||0),0))} habitantes). Os mais populosos:</p>
   <ul>${ms.slice(0,12).map(m=>`<li>${linkMun(m)}: ${fmtInt(m.pop)} hab. · ${linkRes(RES_BY[m.manancial_critico])} com ${fmt(munPct(m))}%</li>`).join("")}</ul>${ms.length>12?`<p>…e mais ${ms.length-12}. A lista completa está no botão "Municípios (CSV)".</p>`:""}`+fonte("ANA/SAR","Atlas Águas","IBGE");
}
function populacao(uf){
  const ms=filtroUF(MUN,uf);
  const c=ms.filter(m=>munStatus(m)==="crit"), a=ms.filter(m=>munStatus(m)==="alert");
  const sp=x=>fmtInt(x.reduce((s,m)=>s+(m.pop||0),0));
  return `<p>${uf?PREP[uf][0].toUpperCase()+PREP[uf].slice(1)+" "+UF_NAMES[uf]:"No Nordeste"}, <b>${sp(c)} pessoas</b> vivem em ${c.length} municípios cujo açude de abastecimento está crítico (≤ 20%), e mais ${sp(a)} em ${a.length} municípios em alerta (20–40%).</p>
   <p>Isso conta só municípios abastecidos por açudes monitorados pela ANA; quem depende de poços ou açudes pequenos não entra na conta.</p>`+fonte("ANA/SAR","Atlas Águas","IBGE Censo 2022");
}
function abaixo(uf,lim){
  const rs=filtroUF(RES,uf).filter(r=>{const p=resPct(r);return p!=null&&p<lim}).sort((a,b)=>resPct(a)-resPct(b));
  if(!rs.length)return `<p>Nenhum açude ${onde(uf)} está abaixo de ${lim}%.</p>`+fonte("ANA/SAR");
  return `<p><b>${rs.length} açudes</b> ${onde(uf)} estão abaixo de ${lim}%:</p><ul>${rs.slice(0,15).map(r=>`<li>${linkRes(r)} (${r.uf}): ${fmt(resPct(r))}%${r.municipios.length?` · abastece ${r.municipios.length} município(s)`:""}</li>`).join("")}</ul>${rs.length>15?`<p>…e mais ${rs.length-15}.</p>`:""}`+fonte("ANA/SAR");
}
function maiores(uf){
  const rs=filtroUF(RES,uf).filter(r=>r.cap).sort((a,b)=>b.cap-a.cap).slice(0,10);
  return `<p>Maiores açudes ${onde(uf)} por capacidade:</p><ul>${rs.map(r=>`<li>${linkRes(r)} (${r.uf}): ${fmt(r.cap,0)} hm³ · hoje ${pctTxt(resPct(r))}</li>`).join("")}</ul>`+fonte("ANA/SAR");
}
function alertas(uf){
  const al=D.alertas.filter(a=>!uf||RES_BY[a.codigo]?.uf===uf);
  if(!al.length)return `<p>Nenhum alerta ${onde(uf)} nesta atualização.</p>`+fonte("ANA/SAR");
  return `<p>${al.length} alerta(s) ${onde(uf)}:</p><ul>${al.slice(0,12).map(a=>`<li>${esc(a.texto)} ${RES_BY[a.codigo]?"· "+linkRes(RES_BY[a.codigo]):""}</li>`).join("")}</ul>`+fonte("ANA/SAR");
}
function transposicao(uf){
  const ano=new Date().getFullYear();
  const ms=filtroUF(MUN,uf).filter(m=>m.pisf), ja=ms.filter(m=>m.pisf<=ano), fut=ms.filter(m=>m.pisf>ano);
  return `<p>${uf?PREP[uf][0].toUpperCase()+PREP[uf].slice(1)+" "+UF_NAMES[uf]:"No Nordeste"}, <b>${ja.length} municípios</b> já são beneficiados pela Transposição do São Francisco (${fmtInt(ja.reduce((s,m)=>s+(m.pop||0),0))} hab.) e ${fut.length} estão previstos para os próximos anos.</p>
   ${ja.length?`<p>Alguns dos maiores: ${ja.sort((a,b)=>(b.pop||0)-(a.pop||0)).slice(0,8).map(linkMun).join(", ")}.</p>`:""}`+fonte("ANA Atlas Águas (PISF)");
}
function seca(uf){
  const lista=uf?[[uf,D.estados[uf]]]:Object.entries(D.estados);
  const linhas=lista.filter(([,e])=>e.seca).map(([u,e])=>{const s=e.seca,t=Object.values(s.pct).reduce((a,b)=>a+b,0);
    return `<li>${UF_NAMES[u]}: ${fmt(t)}% da área em seca (${["S0","S1","S2","S3","S4"].filter(k=>s.pct[k]).map(k=>k+" "+fmt(s.pct[k])+"%").join(", ")})</li>`});
  if(!linhas.length)return `<p>Sem dados do Monitor de Secas.</p>`;
  return `<p>Monitor de Secas, ${esc(lista.find(([,e])=>e.seca)[1].seca.mapa)}:</p><ul>${linhas.join("")}</ul><p class="ask-src">S0 = anormalmente seco, S1 moderada, S2 grave, S3 extrema, S4 excepcional.</p>`+fonte("Monitor de Secas (ANA/FUNCEME)");
}
function resumo(uf){
  const ms=filtroUF(MUN,uf), rs=filtroUF(RES,uf);
  const c=ms.filter(m=>munStatus(m)==="crit");
  let cap=0,vol=0;rs.forEach(r=>{const p=resPct(r);if(r.sistema==="ne"&&r.cap&&p!=null){cap+=r.cap;vol+=r.cap*p/100}});
  const b10=rs.filter(r=>{const p=resPct(r);return p!=null&&p<10}).length;
  const ch=uf?D.estados[uf].chuva:null;
  if(!cap)return `<p><b>${UF_NAMES[uf]}</b> não tem açudes com medição recente no SAR/ANA (só reservatórios do setor elétrico ou açudes sem dados), então não há volume para resumir.</p>
   ${ch?`<p>Chuva prevista para os próximos 15 dias: média de ${fmt(ch.prev_15d)} mm.</p>`:""}`+fonte("ANA/SAR",ch?"Open-Meteo":"");
  return `<p><b>${uf?UF_NAMES[uf]:"Nordeste"}</b>: os açudes monitorados estão com <b>${fmt(100*vol/cap)}%</b> do volume total. ${b10} açudes estão abaixo de 10%.</p>
   <p>${c.length} municípios (${fmtInt(c.reduce((s,m)=>s+(m.pop||0),0))} habitantes) dependem de açude em situação crítica.</p>
   ${ch?`<p>Chuva prevista para os próximos 15 dias: média de ${fmt(ch.prev_15d)} mm.</p>`:""}`+fonte("ANA/SAR","Atlas Águas","IBGE",ch?"Open-Meteo":"");
}

// ------------------------------------------------------------ orquestração
function responder(qOrig){
  prep();
  const q=norm(qOrig).replace(/[?!.,;]/g," ");
  const uf=achaUF(qOrig,q);
  const ents=achaEntidades(q,uf);
  let it=intencao(q);
  const querAcude=/\b(acude|barragem|reservatorio|represa)\b/.test(q);
  let ent=ents.find(e=>querAcude?e.tipo==="res":e.tipo==="mun")||ents[0];
  const num=+(q.match(/(\d{1,2})\s*%?/)||[])[1]||null;
  // nome de açude solto numa pergunta sem assunto de água ("capital da França") não conta
  if(ent&&ent.tipo==="res"&&!querAcude&&!it&&!/\b(agua|volume|nivel|cheio|vazio)\b/.test(q))ent=null;

  if(ent){
    const o=ent.o;
    if(it==="chuva")return ent.tipo==="mun"?chuvaMun(o):(()=>{const m=MUN.find(x=>x.cod===o.municipios[0])||MUN.find(x=>norm(x.nome)===norm(o.municipio||"")&&x.uf===o.uf);
      return m?`<p>Chuva na região do açude ${linkRes(o)}, município de referência ${linkMun(m)}:</p>`+chuvaMun(m):`<p>Não tenho o município de referência do açude ${linkRes(o)}.</p>`})();
    if(it==="autonomia"&&ent.tipo==="mun"){const r=RES_BY[o.manancial_critico];return r?situacaoRes(r):situacaoMun(o)}
    const outro=ents.find(e=>e.tipo!==ent.tipo&&e.n===ent.n);
    return (ent.tipo==="mun"?situacaoMun(o):situacaoRes(o))+(outro?`<p class="ask-src">Também existe ${outro.tipo==="res"?"o açude "+linkRes(outro.o):"o município "+linkMun(outro.o)} com esse nome.</p>`:"");
  }
  switch(it){
    case "chuva": return uf?chuvaUF(uf):`<p>Diga o município ou o estado. Exemplo: "Vai chover em Patos?" ou "Previsão de chuva no Ceará".</p>`;
    case "criticos": return criticos(uf);
    case "populacao": return populacao(uf);
    case "abaixo": return abaixo(uf,num||10);
    case "maiores": return maiores(uf);
    case "alertas": return alertas(uf);
    case "transposicao": return transposicao(uf);
    case "seca": return seca(uf);
    case "autonomia": return autonomiaLista(uf);
    case "resumo": case "situacao": return resumo(uf);
  }
  if(uf&&q.split(" ").filter(Boolean).length<=3)return resumo(uf); // só o nome do estado
  return `<p>Não encontrei isso nos dados. Eu respondo só com o que está nas bases da ANA, do IBGE e da previsão de chuva, então prefiro não chutar.</p>
   <p>Tente citar um município, um açude ou um estado, por exemplo: ${EXEMPLOS.slice(0,3).map(e=>`<a href="#" data-ask-q="${esc(e)}">${esc(e)}</a>`).join(" · ")}</p>`;
}

// ------------------------------------------------------------ interface
window.renderAsk=function(body){
  if(body.dataset.tab==="ask")return;     // não redesenha ao mover o mapa
  body.dataset.tab="ask";
  body.innerHTML=`<div class="ask">
    <p class="ask-intro">Pergunte em português. As respostas vêm só dos dados do app (ANA, IBGE, Monitor de Secas e previsão de chuva), sempre com a fonte. Se a informação não estiver nos dados, o assistente avisa em vez de inventar.</p>
    <div class="ask-chips">${EXEMPLOS.map(e=>`<button class="chip" data-ask-q="${esc(e)}">${esc(e)}</button>`).join("")}</div>
    <div id="askLog" aria-live="polite"></div>
    <form id="askForm" class="ask-form"><input id="askIn" type="search" placeholder="Ex.: Como está o açude Castanhão?" aria-label="Sua pergunta" autocomplete="off"><button class="btn primary" type="submit">Perguntar</button></form>
  </div>`;
  const log=body.querySelector("#askLog");
  for(const h of historico)log.insertAdjacentHTML("beforeend",h);
  body.querySelector("#askForm").onsubmit=e=>{e.preventDefault();const i=body.querySelector("#askIn");perguntar(i.value);i.value=""};
};
function perguntar(q){
  q=(q||"").trim(); if(!q)return;
  let resp; try{resp=responder(q)}catch(err){console.error(err);resp="<p>Não consegui responder essa. Tente reformular citando um município, açude ou estado.</p>"}
  const h=`<div class="ask-q">${esc(q)}</div><div class="ask-a">${resp}</div>`;
  historico.push(h);
  const log=document.getElementById("askLog");
  if(log){log.insertAdjacentHTML("beforeend",h);log.lastElementChild.scrollIntoView({behavior:"smooth",block:"nearest"})}
}
document.addEventListener("click",e=>{
  const a=e.target.closest("[data-ask-q],[data-ask-mun],[data-ask-res]"); if(!a)return;
  e.preventDefault();
  if(a.dataset.askQ)perguntar(a.dataset.askQ);
  else if(a.dataset.askMun){const m=MUN_BY[a.dataset.askMun];if(m)flyMun(m)}
  else if(a.dataset.askRes){const r=RES_BY[a.dataset.askRes];if(r)flyRes(r)}
});
window.perguntarAcudeVivo=perguntar;
window.responderAcudeVivo=responder;
})();
