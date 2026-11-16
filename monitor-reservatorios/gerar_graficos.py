"""Gera os gráficos SVG do README a partir de dados.json.

Uso:  python gerar_graficos.py   (grava em ../docs/graficos/)

Os SVGs seguem o tema claro/escuro de quem visita o GitHub.
"""
import json
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

PASTA = Path(__file__).resolve().parent
SAIDA = PASTA.parent / "docs" / "graficos"
D = json.loads((PASTA / "dados.json").read_text(encoding="utf-8"))
UF_NOME = {"AL": "Alagoas", "BA": "Bahia", "CE": "Ceará", "MA": "Maranhão", "PB": "Paraíba",
           "PE": "Pernambuco", "PI": "Piauí", "RN": "Rio Grande do Norte", "SE": "Sergipe"}
MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
FONTE = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"

ESTILO = f"""<style>
  .bg{{fill:#ffffff}} .card{{fill:#f6f8fa;stroke:#d0d7de}} .fg{{fill:#1f2328}} .mu{{fill:#59636e}}
  .grid{{stroke:#d8dee4}} .axis{{stroke:#8c959f}} .acc{{fill:#0e7490}} .accs{{stroke:#0e7490}} .area{{fill:#0e7490;fill-opacity:.12}}
  .crit{{fill:#dc2626}} .alert{{fill:#d97706}} .ok{{fill:#16a34a}} .nd{{fill:#8c959f}}
  .s0{{fill:#f5e050}} .s1{{fill:#fcc55a}} .s2{{fill:#f59e0b}} .s3{{fill:#dc2626}} .s4{{fill:#7f1d1d}} .track{{fill:#eaeef2}}
  text{{font-family:{FONTE}}} .num{{font-family:{MONO};font-variant-numeric:tabular-nums}}
  @media (prefers-color-scheme: dark){{
    .bg{{fill:#0d1117}} .card{{fill:#161b22;stroke:#30363d}} .fg{{fill:#e6edf3}} .mu{{fill:#8d96a0}}
    .grid{{stroke:#21262d}} .axis{{stroke:#484f58}} .acc{{fill:#4fc3d9}} .accs{{stroke:#4fc3d9}} .area{{fill:#4fc3d9;fill-opacity:.15}}
    .crit{{fill:#f85149}} .alert{{fill:#f0a020}} .ok{{fill:#3fb950}} .nd{{fill:#6e7681}} .track{{fill:#21262d}}
  }}
</style>"""


def fmt(n, d=0):
    s = f"{n:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def svg(w, h, corpo, titulo):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{escape(titulo)}"><title>{escape(titulo)}</title>{ESTILO}'
            f'<rect class="bg" width="{w}" height="{h}" rx="12"/>{corpo}</svg>')


def t(x, y, txt, cls="fg", size=14, weight=400, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" {extra}>{escape(str(txt))}</text>')


def data_ref():
    g = datetime.fromisoformat(D["gerado_em"])
    return g.strftime("%d/%m/%Y")


def cabecalho(titulo, sub, w):
    return (t(28, 40, titulo, size=20, weight=700) + t(28, 62, sub, "mu", 13) +
            t(w - 28, 40, f"dados de {data_ref()}", "mu num", 12, anchor="end"))


# ------------------------------------------------------------------ 1. painel
def painel():
    ms, rs = D["municipios"], D["reservatorios"]
    crit = [m for m in ms if m["status"] == "crit"]
    pop = sum(m["pop"] or 0 for m in crit)
    abaixo10 = sum(1 for r in rs if r["ind"] and r["ind"]["pct"] < 10)
    cap = vol = 0
    for r in rs:
        if r["sistema"] == "ne" and r["ind"] and r["cap"] and r["ind"]["vol"] is not None:
            cap += r["cap"]
            vol += r["ind"]["vol"]
    eq = 100 * vol / cap if cap else 0
    w, h = 900, 200
    itens = [
        (fmt(pop), "pessoas em municípios", "com açude em nível crítico", "crit"),
        (fmt(len(crit)), "municípios dependem", "de açude com até 20%", "fg"),
        (fmt(abaixo10), "açudes abaixo de 10%", "do volume total", "fg"),
        (fmt(eq, 1) + "%", "volume total armazenado", "nos açudes do Nordeste", "acc"),
    ]
    corpo = t(28, 36, "Situação hídrica do Nordeste agora", size=18, weight=700)
    corpo += t(w - 28, 36, f"ANA · IBGE · {data_ref()}", "mu num", 12, anchor="end")
    cw, gap, x0 = (w - 56 - 3 * 14) / 4, 14, 28
    for i, (n, l1, l2, cls) in enumerate(itens):
        x = x0 + i * (cw + gap)
        corpo += f'<rect class="card" x="{x}" y="56" width="{cw}" height="120" rx="10" stroke-width="1"/>'
        corpo += t(x + 16, 104, n, cls + " num", 30, 700)
        corpo += t(x + 16, 136, l1, "fg", 13, 600) + t(x + 16, 155, l2, "mu", 12.5)
    return svg(w, h, corpo, "Painel da situação hídrica do Nordeste")


# ------------------------------------------------------------------ 2. evolução
def evolucao():
    meses = D["meses"]
    rs = [r for r in D["reservatorios"] if r["sistema"] == "ne" and r["ind"] and r["cap"]
          and all(v is not None for v in r["ind"]["mensal"])]
    cap = sum(r["cap"] for r in rs)
    serie = [sum(r["cap"] * r["ind"]["mensal"][i] / 100 for r in rs) / cap * 100 for i in range(len(meses))]
    w, h = 900, 330
    L, R, T, B = 64, 40, 92, 52
    pw, ph = w - L - R, h - T - B
    lo = max(0, int(min(serie) // 10) * 10 - 10)
    hi = min(100, int(max(serie) // 10) * 10 + 20)
    X = lambda i: L + i * pw / (len(serie) - 1)
    Y = lambda v: T + ph - (v - lo) / (hi - lo) * ph
    corpo = cabecalho("Volume armazenado nos açudes do Nordeste",
                      f"Reservatório equivalente: {len(rs)} açudes do SAR/ANA, últimos 12 meses", w)
    for v in range(lo, hi + 1, 10):
        corpo += f'<line class="grid" x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
        corpo += t(L - 10, Y(v) + 4, f"{v}%", "mu num", 11.5, anchor="end")
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(serie))
    corpo += f'<polygon class="area" points="{X(0):.1f},{T + ph} {pts} {X(len(serie) - 1):.1f},{T + ph}"/>'
    corpo += f'<polyline class="accs" fill="none" stroke-width="3" stroke-linejoin="round" points="{pts}"/>'
    for i, m in enumerate(meses):
        ano, mes = m.split("-")
        corpo += t(X(i), h - B + 22, f"{MES[int(mes) - 1]}/{ano[2:]}", "mu", 11.5, anchor="middle")
    imax = max(range(len(serie)), key=lambda i: serie[i])
    for i, rot in ((imax, "pico"), (len(serie) - 1, "agora")):
        corpo += f'<circle class="acc" cx="{X(i):.1f}" cy="{Y(serie[i]):.1f}" r="5"/>'
        anc = "end" if i == len(serie) - 1 else "middle"
        corpo += t(X(i) + (0 if anc == "middle" else -2), Y(serie[i]) - 14,
                   f"{rot}: {fmt(serie[i], 1)}%", "fg num", 13, 700, anchor=anc)
    return svg(w, h, corpo, "Evolução do volume armazenado no Nordeste")


# ------------------------------------------------------------------ 3. população
def populacao():
    est = sorted(((uf, e) for uf, e in D["estados"].items() if e["pop_critica"] or e["pop_alerta"]),
                 key=lambda x: -(x[1]["pop_critica"]))
    w = 900
    row = 40
    h = 110 + row * len(est) + 30
    L, R = 190, 300
    mx = max(e["pop_critica"] + e["pop_alerta"] for _, e in est) or 1
    corpo_col = t(w - 168, 86, "crítico", "mu", 11.5, anchor="end") + t(w - 28, 86, "em alerta", "mu", 11.5, anchor="end")
    corpo = cabecalho("Quem depende de açude em nível baixo",
                      "População (Censo 2022) de municípios cujo açude de abastecimento está crítico ou em alerta", w)
    y = 100
    for uf, e in est:
        c, a = e["pop_critica"], e["pop_alerta"]
        wc = (w - L - R) * c / mx
        wa = (w - L - R) * a / mx
        corpo += t(L - 14, y + 18, UF_NOME[uf], "fg", 13.5, 600, anchor="end")
        corpo += f'<rect class="track" x="{L}" y="{y + 4}" width="{w - L - R}" height="20" rx="4"/>'
        corpo += f'<rect class="crit" x="{L}" y="{y + 4}" width="{wc:.1f}" height="20" rx="4"/>'
        corpo += f'<rect class="alert" x="{L + wc:.1f}" y="{y + 4}" width="{wa:.1f}" height="20"/>'
        corpo += t(w - 168, y + 19, fmt(c), "crit num", 13.5, 700, anchor="end")
        corpo += t(w - 28, y + 19, fmt(a), "alert num", 13, 600, anchor="end")
        y += row
    corpo += corpo_col
    corpo += (f'<rect class="crit" x="{L}" y="{y + 10}" width="12" height="12" rx="2"/>' +
              t(L + 18, y + 21, "crítico (até 20%)", "mu", 12) +
              f'<rect class="alert" x="{L + 150}" y="{y + 10}" width="12" height="12" rx="2"/>' +
              t(L + 168, y + 21, "alerta (20% a 40%)", "mu", 12))
    return svg(w, h, corpo, "População em municípios com açude crítico por estado")


# ------------------------------------------------------------------ 4. açudes por situação
def acudes():
    est = [(uf, e["reservatorios"]) for uf, e in D["estados"].items() if sum(e["reservatorios"].values())]
    est.sort(key=lambda x: -x[1]["crit"] / max(1, sum(x[1].values())))
    w = 900
    row = 40
    h = 110 + row * len(est) + 30
    L, R = 190, 80
    corpo = cabecalho("Situação dos açudes por estado",
                      "Percentual de açudes monitorados pela ANA em cada faixa de volume", w)
    y = 100
    for uf, r in est:
        tot = sum(r.values())
        x = L
        corpo += t(L - 14, y + 18, UF_NOME[uf], "fg", 13.5, 600, anchor="end")
        for k in ("crit", "alert", "ok", "nd"):
            ww = (w - L - R) * r[k] / tot
            if ww > 0:
                corpo += f'<rect class="{k}" x="{x:.1f}" y="{y + 4}" width="{ww:.1f}" height="20"/>'
                if ww > 34:
                    corpo += t(x + ww / 2, y + 19, r[k], "num", 12, 700, anchor="middle", extra='fill="#fff"')
            x += ww
        corpo += t(w - 28, y + 19, f"{tot}", "mu num", 12.5, anchor="end")
        y += row
    leg = [("crit", "crítico ≤ 20%"), ("alert", "alerta 20–40%"), ("ok", "normal > 40%"), ("nd", "sem medição recente")]
    x = L
    for k, l in leg:
        corpo += f'<rect class="{k}" x="{x}" y="{y + 10}" width="12" height="12" rx="2"/>' + t(x + 18, y + 21, l, "mu", 12)
        x += 150
    corpo += t(w - 28, 86, "açudes", "mu", 11.5, anchor="end")
    return svg(w, h, corpo, "Açudes por situação em cada estado")


# ------------------------------------------------------------------ 5. seca
def seca():
    est = [(uf, e["seca"]) for uf, e in D["estados"].items() if e.get("seca")]
    est.sort(key=lambda x: -sum(x[1]["pct"].values()))
    w = 900
    row = 40
    h = 110 + row * len(est) + 30
    L, R = 190, 80
    ref = est[0][1]["mapa"] if est else ""
    corpo = cabecalho("Área em seca por estado", f"Monitor de Secas (ANA/FUNCEME) · {ref}", w)
    y = 100
    for uf, s in est:
        corpo += t(L - 14, y + 18, UF_NOME[uf], "fg", 13.5, 600, anchor="end")
        corpo += f'<rect class="track" x="{L}" y="{y + 4}" width="{w - L - R}" height="20" rx="4"/>'
        x = L
        for k in ("S0", "S1", "S2", "S3", "S4"):
            ww = (w - L - R) * s["pct"].get(k, 0) / 100
            if ww > 0:
                corpo += f'<rect class="{k.lower()}" x="{x:.1f}" y="{y + 4}" width="{ww:.1f}" height="20"/>'
            x += ww
        corpo += t(w - 28, y + 19, f"{fmt(sum(s['pct'].values()), 1)}%", "fg num", 13, 700, anchor="end")
        y += row
    leg = [("s0", "S0 anormalmente seco"), ("s1", "S1 moderada"), ("s2", "S2 grave"), ("s3", "S3 extrema"), ("s4", "S4 excepcional")]
    x = L
    for k, l in leg:
        corpo += f'<rect class="{k}" x="{x}" y="{y + 10}" width="12" height="12" rx="2"/>' + t(x + 18, y + 21, l, "mu", 11.5)
        x += 128 if k != "s0" else 165
    return svg(w, h, corpo, "Área em seca por estado")


# ------------------------------------------------------------------ 6. chuva
def chuva():
    est = [(uf, e["chuva"]) for uf, e in D["estados"].items() if e.get("chuva")]
    if not est:
        return None
    # série diária média do Nordeste (ponderada pelo nº de municípios ≈ média simples dos estados)
    dias = est[0][1]["dias"]
    n = len(dias)
    media = [sum(c["mm"][i] for _, c in est) / len(est) for i in range(n)]
    hoje = datetime.fromisoformat(D["gerado_em"]).date().isoformat()
    i_hoje = next((i for i, t in enumerate(dias) if t >= hoje), n)
    w = 900
    L, R, T = 64, 40, 92
    ph = 170
    pw = w - L - R
    mx = max(5, max(media) * 1.15)
    bw = pw / n
    corpo = cabecalho("Chuva no Nordeste: últimos 30 dias e previsão",
                      "Média diária dos municípios (mm) · Open-Meteo, modelos ECMWF, GFS e outros", w)
    for v in (0, mx / 2, mx):
        y = T + ph - v / mx * ph
        corpo += f'<line class="grid" x1="{L}" x2="{w - R}" y1="{y:.1f}" y2="{y:.1f}"/>'
        corpo += t(L - 10, y + 4, fmt(v, 1), "mu num", 11.5, anchor="end")
    xh = L + i_hoje * bw
    corpo += f'<rect x="{xh:.1f}" y="{T - 6}" width="{w - R - xh:.1f}" height="{ph + 6}" class="track" opacity=".6"/>'
    for i, v in enumerate(media):
        bh = v / mx * ph
        cls = "acc" if i >= i_hoje else "mu"
        corpo += f'<rect class="{cls}" x="{L + i * bw + 1:.1f}" y="{T + ph - bh:.1f}" width="{bw - 2:.1f}" height="{bh:.1f}" rx="1.5"/>'
    corpo += f'<line class="axis" x1="{xh:.1f}" x2="{xh:.1f}" y1="{T - 6}" y2="{T + ph}" stroke-dasharray="4 3"/>'
    corpo += t(xh + 8, T + 8, "previsão →", "acc", 12, 700) + t(xh - 8, T + 8, "← observado", "mu", 12, 600, anchor="end")
    for i in (0, i_hoje, n - 1):
        if i < n:
            d = dias[i]
            corpo += t(L + i * bw + bw / 2, T + ph + 20, f"{d[8:10]}/{d[5:7]}", "mu num", 11.5, anchor="middle")
    # tabela por estado
    y = T + ph + 56
    corpo += t(L, y, "Previsão para os próximos 15 dias por estado (média dos municípios)", "fg", 13.5, 700)
    y += 14
    est.sort(key=lambda x: -x[1]["prev_15d"])
    col = (w - L - R) / 3
    for k, (uf, c) in enumerate(est):
        cx = L + (k % 3) * col
        cy = y + 28 * (k // 3) + 22
        corpo += t(cx, cy, UF_NOME[uf], "fg", 13) + t(cx + col - 24, cy, f"{fmt(c['prev_15d'], 0)} mm", "acc num", 13, 700, anchor="end")
    h = y + 28 * ((len(est) + 2) // 3) + 28
    return svg(w, int(h), corpo, "Chuva observada e prevista no Nordeste")


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    for nome, f in (("painel", painel), ("evolucao", evolucao), ("populacao", populacao),
                    ("acudes", acudes), ("seca", seca), ("chuva", chuva)):
        conteudo = f()
        if not conteudo:
            print(f"  {nome}: sem dados, mantido o anterior")
            continue
        (SAIDA / f"{nome}.svg").write_text(conteudo, encoding="utf-8")
        print(f"  docs/graficos/{nome}.svg")


if __name__ == "__main__":
    main()
