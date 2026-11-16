"""Coleta os dados públicos usados pelo app Açude Vivo e grava dados.json.

Fontes (todas públicas, sem cadastro):
  - ANA / SAR ............ volumes diários de todos os reservatórios do Nordeste
  - ANA / SNISB .......... localização e capacidade das barragens
  - ANA / Atlas Águas .... captações de água: qual município usa qual açude
  - ANA / Atlas Águas .... canais da Transposição do São Francisco (PISF)
  - ANA + FUNCEME ........ Monitor de Secas (área em seca por estado)
  - IBGE ................. malha municipal e população (Censo 2022)
  - Open-Meteo ........... chuva dos últimos 30 dias e previsão de 15 dias

Opcional (você fornece): dados_externos/decretos.csv e dados_externos/carro_pipa.csv
com uma coluna "cod_ibge" (veja o LEIAME.md).

Uso:  python atualizar_dados.py          (1ª execução leva alguns minutos)
      python atualizar_dados.py --rapido (pula chuva e camadas fixas já baixadas)
"""
import csv
import gzip
import html
import json
import re
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import date, datetime, timedelta
from pathlib import Path

PASTA = Path(__file__).resolve().parent
CACHE = PASTA / "cache"
EXTERNOS = PASTA / "dados_externos"
SAIDA = PASTA / "dados.json"
SAR = "https://www.ana.gov.br/sar0/"
ARC = "https://www.snirh.gov.br/arcgis/rest/services/"
UFS = {"21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB",
       "26": "PE", "27": "AL", "28": "SE", "29": "BA"}
UF_COD = {v: k for k, v in UFS.items()}
UF_AREA_KM2 = {"MA": 329651, "PI": 251756, "CE": 148894, "RN": 52810, "PB": 56467,
               "PE": 98068, "AL": 27830, "SE": 21938, "BA": 564760}
# Reservatórios do Sistema Interligado Nacional no Nordeste (o SAR informa % do volume útil)
SIN = [
    (19121, "Sobradinho", "BA", "Sobradinho", -9.43, -40.83, 34116),
    (19122, "Luiz Gonzaga (Itaparica)", "PE", "Petrolândia", -9.15, -38.30, 10782),
    (19126, "Xingó", "AL", "Piranhas", -9.62, -37.79, 3800),
    (19117, "Pedra do Cavalo", "BA", "Cachoeira", -12.59, -38.98, 4630),
    (19127, "Boa Esperança", "PI", "Guadalupe", -6.75, -43.57, 5085),
]
HOJE = date.today()
RAPIDO = "--rapido" in sys.argv


def log(msg):
    print(msg, flush=True)


def _baixar(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "AcudeVivo/2.0",
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        corpo = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or corpo[:2] == b"\x1f\x8b":
            corpo = gzip.decompress(corpo)
        return corpo.decode("utf-8", errors="replace")


def _com_prazo(url, timeout):
    """baixa com prazo TOTAL (o timeout do urllib vale só por leitura;
    um servidor que manda dados a conta-gotas nunca estoura)"""
    caixa = {}

    def alvo():
        try:
            caixa["ok"] = _baixar(url, timeout)
        except Exception as e:
            caixa["erro"] = e
    th = threading.Thread(target=alvo, daemon=True)
    th.start()
    th.join(timeout * 1.5)
    if th.is_alive():
        raise TimeoutError(f"sem resposta completa em {timeout * 1.5:.0f}s")
    if "erro" in caixa:
        raise caixa["erro"]
    return caixa["ok"]


def get(url, tentativas=3, timeout=120):
    for i in range(tentativas):
        try:
            return _com_prazo(url, timeout)
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(3 * (i + 1))


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def arcgis(servico, where, campos="*", geometria=False):
    q = urllib.parse.urlencode({"where": where, "outFields": campos,
                                "returnGeometry": str(geometria).lower(), "f": "json"})
    d = get_json(f"{ARC}{servico}/query?{q}")
    if "error" in d:
        raise RuntimeError(d["error"].get("message"))
    return d.get("features", [])


def num(txt):
    txt = (txt or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


PALAVRAS_IGNORADAS = {"ACUDE", "BARRAGEM", "RESERVATORIO", "PUBLICO", "UHE", "AHE", "LAGOA",
                      "DE", "DA", "DO", "DOS", "DAS", "E", "D", "ENG", "ENGENHEIRO", "DR",
                      "DOUTOR", "PRESIDENTE", "GOVERNADOR", "DEPUTADO", "SENADOR", "PE", "PADRE"}


def tokens(nome):
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return frozenset(t for t in s.split() if t not in PALAVRAS_IGNORADAS and len(t) > 1)


def variantes(nome):
    """'MIRORÓS (MANOEL NOVAIS)' -> {MIRORÓS, MANOEL NOVAIS, nome inteiro}"""
    partes = re.split(r"[/()]", nome or "")
    out = {tokens(nome)} | {tokens(p) for p in partes}
    return [v for v in out if v]


def semelhanca(a, b):
    best = 0.0
    for x in variantes(a):
        for y in variantes(b):
            j = len(x & y) / len(x | y)
            best = max(best, j)
    return best


# ---------------------------------------------------------------- SAR
def lista_sar():
    copia = CACHE / "lista_sar.html"
    try:
        t = get(SAR + "Medicao", tentativas=3, timeout=60)
        copia.write_text(t, encoding="utf-8")
    except Exception as e:
        if not copia.exists():
            raise
        log(f"  SAR fora do ar ({e}); usando a lista salva da última execução")
        t = copia.read_text(encoding="utf-8")
    res = []
    for cod, nome in re.findall(r'<option value="(\d+)">([^<]*)', t):
        nome = html.unescape(nome).strip()
        m = re.match(r"(.*?)\s*\((\w\w)\)$", nome)
        if not m or m.group(2) not in UF_COD:
            continue
        res.append({"codigo": int(cod), "nome": m.group(1).strip().rstrip("*").strip(),
                    "uf": m.group(2), "sistema": "ne"})
    for cod, nome, uf, mun, lat, lng, cap in SIN:
        res.append({"codigo": cod, "nome": nome, "uf": uf, "sistema": "sin", "municipio": mun,
                    "lat": lat, "lng": lng, "cap": cap, "fonte_local": "fixa"})
    return res


def baixar_medicoes(r, inicio):
    pagina = "Medicao" if r["sistema"] == "ne" else "MedicaoSin"
    url = (f"{SAR}{pagina}?dropDownListEstados=&dropDownListReservatorios={r['codigo']}"
           f"&dataInicial={inicio:%d/%m/%Y}&dataFinal={HOJE:%d/%m/%Y}&button=Buscar")
    t = get(url, tentativas=2, timeout=60)
    tabela = t[t.find("<table"):]
    out = {}
    cap = None
    for tr in re.findall(r"<tr.*?</tr>", tabela, re.S):
        c = [html.unescape(re.sub(r"<.*?>", "", x)).strip()
             for x in re.findall(r"<td.*?</td>", tr, re.S)]
        if not c:
            continue
        try:
            dia = datetime.strptime(c[-1], "%d/%m/%Y").date().isoformat()
        except ValueError:
            continue
        if r["sistema"] == "ne":
            pct, vol, cota = num(c[5]), num(c[4]), num(c[3])
            cap = num(c[2]) or cap
        else:
            pct, vol, cota = num(c[8]), None, num(c[2])
        if pct is not None:
            out[dia] = [pct, vol, cota]
    return out, cap


SAR_FALHAS = {"seguidas": 0, "desligado": False}
SAR_LIMITE_FALHAS = 12  # depois disso, considera o SAR fora do ar e usa o histórico salvo


def atualizar_serie(r):
    arq = CACHE / "sar" / f"{r['codigo']}.json"
    antigo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"serie": {}}
    serie = antigo["serie"]
    if SAR_FALHAS["desligado"]:
        return r["codigo"], antigo, "SAR fora do ar; usado histórico salvo"
    if serie:
        inicio = date.fromisoformat(max(serie)) - timedelta(days=15)
    else:
        inicio = HOJE - timedelta(days=400)
    try:
        novo, cap = baixar_medicoes(r, inicio)
        SAR_FALHAS["seguidas"] = 0
    except Exception as e:
        SAR_FALHAS["seguidas"] += 1
        if SAR_FALHAS["seguidas"] >= SAR_LIMITE_FALHAS and not SAR_FALHAS["desligado"]:
            SAR_FALHAS["desligado"] = True
            log("  SAR/ANA não está respondendo; usando o histórico salvo dos açudes restantes")
        return r["codigo"], antigo, f"falha: {e}"
    serie.update(novo)
    limite = (HOJE - timedelta(days=430)).isoformat()
    serie = {k: v for k, v in sorted(serie.items()) if k >= limite}
    dados = {"serie": serie, "cap": cap or antigo.get("cap")}
    arq.write_text(json.dumps(dados), encoding="utf-8")
    return r["codigo"], dados, None


# ---------------------------------------------------------------- indicadores
def tendencia(serie, dias=60):
    """inclinação (p.p./dia) por mínimos quadrados nos últimos `dias`"""
    if not serie:
        return None
    fim = date.fromisoformat(max(serie))
    pts = [((date.fromisoformat(d) - fim).days, v[0]) for d, v in serie.items()
           if (fim - date.fromisoformat(d)).days <= dias]
    if len(pts) < 5:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    den = sum((p[0] - mx) ** 2 for p in pts)
    if den == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / den


def valor_em(serie, alvo, tolerancia=12):
    melhor = None
    for d, v in serie.items():
        dist = abs((date.fromisoformat(d) - alvo).days)
        if dist <= tolerancia and (melhor is None or dist < melhor[0]):
            melhor = (dist, v[0])
    return melhor[1] if melhor else None


def meses_ultimos(n=12):
    y, m, out = HOJE.year, HOJE.month, []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def indicadores(serie):
    if not serie:
        return None
    ultima_data = max(serie)
    pct, vol, cota = serie[ultima_data]
    incl = tendencia(serie)
    ref = date.fromisoformat(ultima_data)
    mensal, ultimo = [], None
    por_mes = {}
    for d, v in sorted(serie.items()):
        por_mes[d[:7]] = v[0]
    for mes in meses_ultimos():
        if mes in por_mes:
            ultimo = por_mes[mes]
        mensal.append(ultimo)
    primeiro = next((v for v in mensal if v is not None), None)
    mensal = [primeiro if v is None else v for v in mensal]
    prev = {}
    for n in (30, 60, 90):
        prev[str(n)] = None if incl is None else round(min(100, max(0, pct + incl * n)), 2)
    autonomia = None
    if incl is not None and incl < -0.003:
        autonomia = 0 if pct <= 5 else int((pct - 5) / -incl)
    return {
        "pct": pct, "vol": vol, "cota": cota, "data": ultima_data,
        "tendencia_pp_dia": None if incl is None else round(incl, 4),
        "previsao": prev,
        "autonomia_dias": autonomia,
        "ano_anterior": valor_em(serie, ref - timedelta(days=365)),
        "ha_30_dias": valor_em(serie, ref - timedelta(days=30), 6),
        "mensal": mensal,
        "diario": [[d, v[0]] for d, v in sorted(serie.items())[-120:]],
        "atrasado": (HOJE - ref).days > 45,
    }


def nome_bonito(nome):
    """'JATOBÁ II (DO CAIS)' -> 'Jatobá II (do Cais)'"""
    s = nome.title()
    s = re.sub(r"\b(Ii|Iii|Iv|Vi|Vii|Viii|Ix|Xi|Xii)\b", lambda m: m.group(1).upper(), s)
    s = re.sub(r"(?<=\w )(Da|De|Do|Das|Dos|E)\b", lambda m: m.group(1).lower(), s)
    s = re.sub(r"\bD'(\w)", lambda m: "d'" + m.group(1).upper(), s)
    return s


def status(p):
    if p is None:
        return "nd"
    return "crit" if p <= 20 else "alert" if p <= 40 else "ok"


# ---------------------------------------------------------------- localização (SNISB)
def localizar(reservatorios):
    log("Buscando localização das barragens (SNISB)…")
    por_uf = {}
    for uf in UF_COD:
        try:
            fs = arcgis("IG/SNISB/MapServer/0",
                        f"ING_SG_UFMUNICIPIO='{uf}' AND BAR_NU_CAP_TOTAL_RESERV>=0.3",
                        "BAR_NM_NOME,BAR_NM_SECUNDARIO,BAR_NU_LATITUDE,BAR_NU_LONGITUDE,"
                        "BAR_NU_CAP_TOTAL_RESERV,ING_NM_MUNICIPIO")
            por_uf[uf] = [f["attributes"] for f in fs]
        except Exception as e:
            log(f"  SNISB {uf}: {e}")
            por_uf[uf] = []
    achados = 0
    for r in reservatorios:
        if r.get("lat") is not None:
            continue
        melhor, nota = None, 0
        for b in por_uf.get(r["uf"], []):
            s = max(semelhanca(r["nome"], b["BAR_NM_NOME"] or ""),
                    semelhanca(r["nome"], b["BAR_NM_SECUNDARIO"] or ""))
            if r.get("cap") and b["BAR_NU_CAP_TOTAL_RESERV"]:
                razao = r["cap"] / b["BAR_NU_CAP_TOTAL_RESERV"]
                s += 0.15 if 0.6 <= razao <= 1.6 else (-0.4 if razao > 4 or razao < 0.25 else 0)
            if s > nota:
                melhor, nota = b, s
        if melhor and nota >= 0.66 and melhor["BAR_NU_LATITUDE"]:
            r.update(lat=round(melhor["BAR_NU_LATITUDE"], 5), lng=round(melhor["BAR_NU_LONGITUDE"], 5),
                     municipio=(melhor["ING_NM_MUNICIPIO"] or "").title(), fonte_local="SNISB")
            achados += 1
    log(f"  {achados} reservatórios localizados pelo SNISB")


# ---------------------------------------------------------------- captações (Atlas Águas)
def captacoes():
    log("Buscando captações de abastecimento (Atlas Águas)…")
    out = []
    for cod in UFS:
        try:
            fs = arcgis("AtlasAguas2020/captacoes/MapServer/1", f"cd_ibge LIKE '{cod}%'",
                        "cd_ibge,nm_municip,nm_massa_d,sistema,populacao_", geometria=True)
        except Exception as e:
            log(f"  captações {UFS[cod]}: {e}")
            continue
        for f in fs:
            a = f["attributes"]
            pts = (f.get("geometry") or {}).get("points") or []
            out.append({"massa": (a.get("nm_massa_d") or "").strip(),
                        "sistema": a.get("sistema"),
                        "pop": a.get("populacao_"),
                        "municipios": re.findall(r"\d{7}", a.get("cd_ibge") or ""),
                        "ponto": pts[0] if pts else None})
    log(f"  {len(out)} captações superficiais")
    return out


def ligar_captacoes(capts, reservatorios):
    """associa cada captação a um reservatório monitorado pelo nome do corpo d'água"""
    por_uf = {}
    for r in reservatorios:
        por_uf.setdefault(r["uf"], []).append(r)
    ligacoes = {}  # cod_ibge -> set(codigo SAR)
    for c in capts:
        if not c["massa"] or not c["municipios"]:
            continue
        uf = UFS.get(c["municipios"][0][:2])
        candidatos = por_uf.get(uf, []) + [r for r in reservatorios if r["sistema"] == "sin"]
        melhor, nota = None, 0
        for r in candidatos:
            s = semelhanca(c["massa"], r["nome"])
            if s > nota:
                melhor, nota = r, s
        if melhor and nota >= 0.66:
            for m in c["municipios"]:
                ligacoes.setdefault(m, set()).add(melhor["codigo"])
            if melhor.get("lat") is None and c["ponto"]:
                melhor.update(lng=round(c["ponto"][0], 5), lat=round(c["ponto"][1], 5),
                              fonte_local="Atlas Águas (captação)")
    return ligacoes


# ---------------------------------------------------------------- IBGE
def ibge_municipios():
    log("Buscando municípios e população (IBGE)…")
    mun = {}
    for m in get_json("https://servicodados.ibge.gov.br/api/v1/localidades/regioes/2/municipios"):
        uf = m["microrregiao"]["mesorregiao"]["UF"]["sigla"] if m.get("microrregiao") else \
            m["regiao-imediata"]["regiao-intermediaria"]["UF"]["sigla"]
        mun[str(m["id"])] = {"nome": m["nome"], "uf": uf, "pop": None}
    for cod in UFS:
        try:
            d = get_json("https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/"
                         f"variaveis/93?localidades=N6%5BN3%5B{cod}%5D%5D")
            for s in d[0]["resultados"][0]["series"]:
                i = s["localidade"]["id"]
                if i in mun:
                    mun[i]["pop"] = int(s["serie"]["2022"])
        except Exception as e:
            log(f"  população {UFS[cod]}: {e}")
    arq = PASTA / "municipios.geojson"
    if not arq.exists() or not RAPIDO:
        g = get("https://servicodados.ibge.gov.br/api/v3/malhas/regioes/2?formato="
                "application/vnd.geo+json&intrarregiao=municipio&qualidade=minima", timeout=240)
        arq.write_text(g, encoding="utf-8")
    g = json.loads(arq.read_text(encoding="utf-8"))
    for f in g["features"]:
        cod = str(f["properties"].get("codarea"))
        if cod in mun:
            mun[cod]["centro"] = centroide(f["geometry"])
    log(f"  {len(mun)} municípios")
    return mun


def centroide(geom):
    aneis = geom["coordinates"] if geom["type"] == "Polygon" else \
        max(geom["coordinates"], key=lambda p: len(p[0]))
    pts = aneis[0]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [round(sum(ys) / len(ys), 4), round(sum(xs) / len(xs), 4)]


# ---------------------------------------------------------------- transposição
def transposicao():
    arq = PASTA / "transposicao.geojson"
    if arq.exists() and RAPIDO and (CACHE / "pisf_mun.json").exists():
        b = json.loads((CACHE / "pisf_mun.json").read_text())
        if isinstance(b, dict):
            return b
    log("Buscando canais da Transposição do São Francisco (Atlas Águas)…")
    feats = []
    try:
        for f in arcgis("AtlasAguas2020/PISF_SNIRH3/MapServer/0", "1=1",
                        "adt_nm_adu,adt_status,adt_ramal", geometria=True):
            paths = (f.get("geometry") or {}).get("paths")
            if paths:
                feats.append({"type": "Feature", "properties": f["attributes"],
                              "geometry": {"type": "MultiLineString",
                                           "coordinates": [[[round(x, 4), round(y, 4)] for x, y in p] for p in paths]}})
        arq.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    except Exception as e:
        log(f"  canais PISF: {e}")
    beneficiados = {}  # cod_ibge -> ano em que passa a ser beneficiado (2020, 2025, 2035…)
    try:
        for f in arcgis("AtlasAguas2020/PISF_SNIRH3/MapServer/5", "1=1", "cod_ibge,ben_pisf"):
            a = f["attributes"]
            ano = re.search(r"Beneficiados em (\d{4})", a.get("ben_pisf") or "")
            if a.get("cod_ibge") and ano:
                beneficiados[str(int(float(a["cod_ibge"])))] = int(ano.group(1))
        (CACHE / "pisf_mun.json").write_text(json.dumps(beneficiados))
    except Exception as e:
        log(f"  municípios PISF: {e}")
    log(f"  {len(feats)} trechos de canal, {len(beneficiados)} municípios beneficiados")
    return beneficiados


# ---------------------------------------------------------------- monitor de secas
def monitor_secas():
    log("Buscando Monitor de Secas (ANA/FUNCEME)…")
    out = {}
    for cod, uf in UFS.items():
        try:
            d = get_json(f"https://apimsbr.ana.gov.br/rpc/v1/dados-tabulares-monitor?tipo_area=1&area={cod}")
            lista = d["data"]["list"]
            ult = max(lista, key=lambda x: (x["mapa"]["ano"], x["mapa"]["mes"]))
            areas = {a["categoria"]: a["area"] for a in ult["areas"]}
            out[uf] = {"mapa": ult["mapa"]["nome"], "imagem":
                       "https://ana-monitor-secas-files.s3.sa-east-1.amazonaws.com/" + ult["mapa"]["path"],
                       "km2": areas,
                       "pct": {k: round(100 * v / UF_AREA_KM2[uf], 1) for k, v in areas.items()}}
        except Exception as e:
            log(f"  monitor de secas {uf}: {e}")
    return out


# ---------------------------------------------------------------- chuva
def chuva_pontos(itens, rotulo):
    """Chuva diária dos últimos 30 dias e previsão de 16 dias (Open-Meteo) para cada ponto.
    Grava em item["_chuva"] = {"dias": [...], "mm": [...], "prob": [...]}."""
    pts = [x for x in itens if x.get("_lat") is not None]
    log(f"Buscando chuva observada e prevista para {len(pts)} {rotulo} (Open-Meteo)…")
    lote_n = 100
    for i in range(0, len(pts), lote_n):
        lote = pts[i:i + lote_n]
        q = urllib.parse.urlencode({
            "latitude": ",".join(str(x["_lat"]) for x in lote),
            "longitude": ",".join(str(x["_lng"]) for x in lote),
            "daily": "precipitation_sum,precipitation_probability_max",
            "past_days": 30, "forecast_days": 16, "timezone": "America/Fortaleza"})
        for tentativa in range(3):
            try:
                d = get_json("https://api.open-meteo.com/v1/forecast?" + q, tentativas=1)
                if isinstance(d, dict) and d.get("error"):
                    raise RuntimeError(d.get("reason"))
                d = d if isinstance(d, list) else [d]
                for x, r in zip(lote, d):
                    x["_chuva"] = {"dias": r["daily"]["time"],
                                   "mm": [round(v or 0, 1) for v in r["daily"]["precipitation_sum"]],
                                   "prob": r["daily"].get("precipitation_probability_max")}
                break
            except Exception as e:
                if tentativa == 2:
                    log(f"  chuva lote {i}: {e}")
                else:
                    time.sleep(30)  # limite de uso por minuto
        time.sleep(11)  # respeita o limite gratuito (600 chamadas/min por local)


def resumo_chuva(c):
    if not c:
        return None
    hoje = HOJE.isoformat()
    obs = [(t, v) for t, v in zip(c["dias"], c["mm"]) if t < hoje]
    prev = [(t, v, p) for t, v, p in zip(c["dias"], c["mm"], c["prob"] or [None] * len(c["mm"])) if t >= hoje]
    return {
        "obs_30d": round(sum(v for _, v in obs), 1),
        "obs_7d": round(sum(v for _, v in obs[-7:]), 1),
        "prev_7d": round(sum(v for _, v, _ in prev[:7]), 1),
        "prev_15d": round(sum(v for _, v, _ in prev[:15]), 1),
        "prev_dias": [[t, v, p] for t, v, p in prev[:15]],
        "dias_com_chuva_prev": sum(1 for _, v, _ in prev[:15] if v >= 1),
    }


def serie_chuva_estado(ac):
    """média diária da chuva entre os municípios do estado"""
    if not ac or not ac["n"]:
        return None
    hoje = HOJE.isoformat()
    media = [round(s / ac["n"], 1) for s in ac["soma"]]
    obs = [v for t, v in zip(ac["dias"], media) if t < hoje]
    prev = [v for t, v in zip(ac["dias"], media) if t >= hoje]
    return {"dias": ac["dias"], "mm": media, "obs_30d": round(sum(obs), 1),
            "prev_7d": round(sum(prev[:7]), 1), "prev_15d": round(sum(prev[:15]), 1)}


def chuva(reservatorios):
    for r in reservatorios:
        r["_lat"], r["_lng"] = r.get("lat"), r.get("lng")
    chuva_pontos(reservatorios, "açudes")
    for r in reservatorios:
        s = resumo_chuva(r.pop("_chuva", None))
        if s:
            r["chuva_30d"], r["chuva_prev_15d"] = s["obs_30d"], s["prev_15d"]


# ---------------------------------------------------------------- CSV externos
def ler_csv_externo(nome):
    arq = EXTERNOS / nome
    if not arq.exists():
        return {}
    out = {}
    texto = arq.read_text(encoding="utf-8-sig", errors="replace")
    sep = ";" if texto.count(";") > texto.count(",") else ","
    for linha in csv.DictReader(texto.splitlines(), delimiter=sep):
        linha = {k.strip().lower(): (v or "").strip() for k, v in linha.items() if k}
        cod = re.sub(r"\D", "", linha.get("cod_ibge", ""))
        if len(cod) == 6:  # código sem dígito verificador
            cod = next((k for k in MUNICIPIOS_CACHE if k.startswith(cod)), cod)
        if len(cod) == 7:
            out[cod] = {k: v for k, v in linha.items() if k != "cod_ibge"}
    log(f"  {nome}: {len(out)} municípios")
    return out


MUNICIPIOS_CACHE = {}


# ---------------------------------------------------------------- principal
def main():
    t0 = time.time()
    (CACHE / "sar").mkdir(parents=True, exist_ok=True)
    EXTERNOS.mkdir(exist_ok=True)

    log("Listando reservatórios do SAR/ANA…")
    res = lista_sar()
    log(f"  {len(res)} reservatórios no Nordeste")

    log("Baixando medições (a 1ª vez demora alguns minutos; depois só o que for novo)…")
    # teste rápido: se a ANA não responde, nem tenta açude por açude
    try:
        get(SAR + "Medicao", tentativas=1, timeout=25)
    except Exception:
        SAR_FALHAS["desligado"] = True
        log("  SAR/ANA fora do ar agora; usando o histórico salvo de todos os açudes")
    resultados = {}
    ex = ThreadPoolExecutor(max_workers=8)
    futuros = {ex.submit(atualizar_serie, r): r for r in res}
    prazo = time.time() + 20 * 60  # no máximo 20 minutos nesta etapa
    feitos = 0
    try:
        for fut in as_completed(futuros, timeout=max(1, prazo - time.time())):
            cod, dados, erro = fut.result()
            resultados[cod] = (dados, erro)
            feitos += 1
            if feitos % 50 == 0:
                log(f"  {feitos}/{len(res)}")
    except FuturesTimeout:
        SAR_FALHAS["desligado"] = True
        log(f"  prazo esgotado com {feitos}/{len(res)} açudes; o restante usa o histórico salvo")
    ex.shutdown(wait=False, cancel_futures=True)
    for r in res:
        if r["codigo"] not in resultados:
            arq = CACHE / "sar" / f"{r['codigo']}.json"
            antigo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {"serie": {}}
            resultados[r["codigo"]] = (antigo, "sem resposta do SAR; usado histórico salvo")
    for r in res:
        dados, erro = resultados[r["codigo"]]
        r["cap"] = r.get("cap") or dados.get("cap")
        r["ind"] = indicadores(dados["serie"])
        if erro:
            r["erro"] = erro

    localizar(res)
    capts = captacoes()
    ligacoes = ligar_captacoes(capts, res)
    mun = ibge_municipios()
    MUNICIPIOS_CACHE.update(mun)
    pisf = transposicao()
    secas = monitor_secas()
    chuva_estado = {}
    if not RAPIDO:
        chuva(res)
        for m in mun.values():
            m["_lat"], m["_lng"] = (m.get("centro") or [None, None])
        chuva_pontos(list(mun.values()), "municípios")
        for m in mun.values():
            bruto = m.pop("_chuva", None)
            m["chuva"] = resumo_chuva(bruto)
            if bruto:
                ac = chuva_estado.setdefault(m["uf"], {"dias": bruto["dias"], "soma": [0.0] * len(bruto["mm"]), "n": 0})
                if len(bruto["mm"]) == len(ac["soma"]):
                    ac["soma"] = [a + b for a, b in zip(ac["soma"], bruto["mm"])]
                    ac["n"] += 1
    log("Lendo planilhas externas (opcional)…")
    decretos = ler_csv_externo("decretos.csv")
    pipa = ler_csv_externo("carro_pipa.csv")

    por_cod = {r["codigo"]: r for r in res}
    servidos = {}
    for cod_ibge, cods in ligacoes.items():
        for c in cods:
            servidos.setdefault(c, []).append(cod_ibge)

    # municípios
    municipios = []
    for cod, m in mun.items():
        fontes = sorted(ligacoes.get(cod, []))
        pcts = [(por_cod[c]["ind"]["pct"], c) for c in fontes if por_cod[c].get("ind")]
        pior = min(pcts) if pcts else None
        municipios.append({
            "cod": cod, "nome": m["nome"], "uf": m["uf"], "pop": m["pop"],
            "centro": m.get("centro"),
            "mananciais": fontes,
            "pct": pior[0] if pior else None,
            "manancial_critico": pior[1] if pior else None,
            "status": status(pior[0]) if pior else ("nd" if fontes else "sm"),
            "pisf": pisf.get(cod),
            "decreto": decretos.get(cod),
            "carro_pipa": pipa.get(cod),
            "chuva": m.get("chuva"),
        })

    # reservatórios (saída)
    reservatorios = []
    for r in res:
        i = r.get("ind")
        reservatorios.append({
            "codigo": r["codigo"], "nome": nome_bonito(r["nome"]) if r["sistema"] == "ne" else r["nome"],
            "uf": r["uf"], "municipio": r.get("municipio"), "sistema": r["sistema"],
            "lat": r.get("lat"), "lng": r.get("lng"), "fonte_local": r.get("fonte_local"),
            "cap": r.get("cap"), "status": status(i["pct"] if i else None), "ind": i,
            "chuva_30d": r.get("chuva_30d"), "chuva_prev_15d": r.get("chuva_prev_15d"),
            "municipios": sorted(servidos.get(r["codigo"], [])),
        })

    # estados
    estados = {}
    for uf in UF_COD:
        rs = [r for r in reservatorios if r["uf"] == uf and r["ind"] and r["sistema"] == "ne"
              and r["cap"] and r["ind"]["vol"] is not None]
        cap = sum(r["cap"] for r in rs)
        vol = sum(r["ind"]["vol"] for r in rs)
        ms = [m for m in municipios if m["uf"] == uf]
        cont = {s: sum(1 for m in ms if m["status"] == s) for s in ("crit", "alert", "ok", "nd", "sm")}
        estados[uf] = {
            "equivalente_pct": round(100 * vol / cap, 2) if cap else None,
            "cap_hm3": round(cap, 1), "vol_hm3": round(vol, 1),
            "reservatorios": {s: sum(1 for r in reservatorios if r["uf"] == uf and r["status"] == s)
                              for s in ("crit", "alert", "ok", "nd")},
            "municipios": cont,
            "pop_critica": sum(m["pop"] or 0 for m in ms if m["status"] == "crit"),
            "pop_alerta": sum(m["pop"] or 0 for m in ms if m["status"] == "alert"),
            "decretos": sum(1 for m in ms if m["decreto"]),
            "carro_pipa": sum(1 for m in ms if m["carro_pipa"]),
            "seca": secas.get(uf),
            "chuva": serie_chuva_estado(chuva_estado.get(uf)),
        }

    # alertas
    alertas = []
    for r in reservatorios:
        i = r["ind"]
        if not i or i["atrasado"]:
            continue
        for lim in (10, 20):
            if i["ha_30_dias"] is not None and i["ha_30_dias"] > lim >= i["pct"]:
                alertas.append({"tipo": f"abaixo_{lim}", "codigo": r["codigo"], "nivel": "crit" if lim == 10 else "alert",
                                "texto": f"{r['nome']} ({r['uf']}) caiu abaixo de {lim}% nos últimos 30 dias: {i['pct']:.1f}%"})
                break
        if i["autonomia_dias"] is not None and i["autonomia_dias"] <= 120 and r["municipios"]:
            alertas.append({"tipo": "autonomia", "codigo": r["codigo"], "nivel": "crit",
                            "texto": (f"{r['nome']} ({r['uf']}) já está em {i['pct']:.1f}% e segue caindo"
                                      if i["autonomia_dias"] == 0 else
                                      f"{r['nome']} ({r['uf']}) chega a 5% em cerca de {i['autonomia_dias']} dias no ritmo atual")
                                     + f"; abastece {len(r['municipios'])} município(s)"})

    saida = {
        "gerado_em": datetime.now().isoformat(timespec="minutes"),
        "meses": meses_ultimos(),
        "fontes": {
            "volumes": "ANA — Sistema de Acompanhamento de Reservatórios (SAR)",
            "localizacao": "ANA — SNISB; Atlas Águas (captações) quando não encontrado",
            "abastecimento": "ANA — Atlas Águas 2021, captações superficiais",
            "populacao": "IBGE — Censo Demográfico 2022",
            "malha": "IBGE — Malha municipal",
            "transposicao": "ANA — Atlas Águas, canais do PISF",
            "secas": "Monitor de Secas — ANA/FUNCEME e parceiros",
            "chuva": "Open-Meteo (modelos ECMWF, GFS e outros centros de meteorologia)",
            "decretos": "Planilha fornecida pelo usuário (S2iD)" if decretos else None,
            "carro_pipa": "Planilha fornecida pelo usuário" if pipa else None,
        },
        "reservatorios": reservatorios,
        "municipios": municipios,
        "estados": estados,
        "alertas": alertas,
    }
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    com_dado = sum(1 for r in reservatorios if r["ind"])
    no_mapa = sum(1 for r in reservatorios if r["lat"] is not None)
    ligados = sum(1 for m in municipios if m["mananciais"])
    log("")
    log(f"Pronto em {time.time() - t0:.0f}s → {SAIDA.name}")
    log(f"  reservatórios: {len(reservatorios)} | com medição: {com_dado} | no mapa: {no_mapa}")
    log(f"  municípios: {len(municipios)} | ligados a açude monitorado: {ligados}")
    log(f"  alertas: {len(alertas)}")


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)  # não espera conexões penduradas com o SAR
