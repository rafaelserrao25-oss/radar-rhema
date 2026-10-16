"""Radar Rhema: coleta as licitações abertas no PNCP e aplica o funil do config.json.

Uso: python coletar.py
Saída: docs/dados.json (lido pelo site em docs/index.html).
"""
import csv, gzip, json, math, re, sys, time, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
API = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
BRT = timezone(timedelta(hours=-3))
PAUSA = 0.6  # segundos entre páginas, para o PNCP não bloquear


def norm(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def padrao(palavras):
    return re.compile(r"\b(" + "|".join(re.escape(norm(p)) for p in palavras) + r")\b")


def km(a, b):
    r = math.pi / 180
    h = (math.sin((b[0] - a[0]) * r / 2) ** 2
         + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def baixar(modalidade, pagina, data_final):
    url = (f"{API}?dataFinal={data_final}&codigoModalidadeContratacao={modalidade}"
           f"&pagina={pagina}&tamanhoPagina=50")
    for tentativa in range(8):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RadarRhema"})
            with urllib.request.urlopen(req, timeout=90) as r:
                time.sleep(PAUSA)
                if r.status == 204:
                    return {"data": [], "totalPaginas": 0}
                return json.loads(r.read())
        except Exception as e:
            erro = e
            # 429 = PNCP pedindo para ir mais devagar
            espera = 20 * (tentativa + 1) if "429" in str(e) else 3 + tentativa * 4
            time.sleep(espera)
    print(f"  falhou modalidade {modalidade} página {pagina}: {erro}", file=sys.stderr)
    return None


def coletar(modalidades):
    data_final = (datetime.now(BRT) + timedelta(days=400)).strftime("%Y%m%d")
    itens, falhas = [], 0
    for m in modalidades:
        primeira = baixar(m, 1, data_final)
        if not primeira:
            falhas += 1
            continue
        paginas = primeira.get("totalPaginas") or 0
        print(f"modalidade {m}: {primeira.get('totalRegistros', 0)} registros, {paginas} páginas")
        itens += primeira["data"]
        with ThreadPoolExecutor(2) as ex:
            for res in ex.map(lambda p: baixar(m, p, data_final), range(2, paginas + 1)):
                if res is None:
                    falhas += 1
                else:
                    itens += res["data"]
    return itens, falhas


def main():
    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))

    coords, por_nome = {}, {}
    uf_cod = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA",
              "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
              "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
              "51": "MT", "52": "GO", "53": "DF"}
    arq_mun = RAIZ / "municipios.csv"
    if not arq_mun.exists():
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv", arq_mun)
    with open(arq_mun, encoding="utf-8") as f:
        for l in csv.DictReader(f):
            p = (float(l["latitude"]), float(l["longitude"]))
            coords[l["codigo_ibge"]] = p
            por_nome[(norm(l["nome"]), uf_cod[l["codigo_uf"]])] = (l["codigo_ibge"], p)

    def achar(nome, uf):
        if (norm(nome), uf) not in por_nome:
            sys.exit(f"Município não encontrado em municipios.csv: {nome}/{uf}")
        return por_nome[(norm(nome), uf)]

    bases = [(b["nome"], achar(b["nome"], b["uf"])[1], b["raio_km"]) for b in cfg["bases"]]
    convales = {achar(n, uf)[0] for n, uf in cfg["convales"]["municipios"]}
    ufs_obras = set(cfg["ufs_inteiras_para_obras"])
    trilhas = {k: padrao(t["palavras"]) for k, t in cfg["trilhas"].items()}
    exclusao = padrao(cfg["exclusoes"])
    # exclusões que não valem quando o objeto é serviço com mão de obra (ex.: "limpeza com fornecimento de material")
    rel = cfg.get("relevar_exclusoes")
    r = (padrao(rel["se"]), {norm(p) for p in rel["relevar"]}) if rel else None
    alertas = [(padrao(a["se"]), a["texto"]) for a in cfg["alertas"]]
    vmin, vmax = cfg.get("valor_minimo") or 0, cfg.get("valor_maximo") or 0
    corte = cfg.get("publicado_a_partir_de") or ""

    cache = RAIZ / "bruto.json.gz"
    if "--sem-baixar" in sys.argv and cache.exists():
        # só reaplica o funil sobre a última coleta (para testar filtros sem esperar o PNCP)
        with gzip.open(cache, "rt", encoding="utf-8") as f:
            guardado = json.load(f)
        brutos, falhas = guardado["itens"], guardado["falhas"]
    else:
        brutos, falhas = coletar(cfg["modalidades"].keys())
        with gzip.open(cache, "wt", encoding="utf-8") as f:
            json.dump({"itens": brutos, "falhas": falhas}, f, ensure_ascii=False)

    vistos, saida = set(), []
    for c in brutos:
        chave = c.get("numeroControlePNCP")
        if chave in vistos:
            continue
        vistos.add(chave)
        if corte and (c.get("dataPublicacaoPncp") or "")[:10] < corte:
            continue
        # trilhas olham só o objeto; o campo complementar traz muito texto genérico
        texto = norm(c.get("objetoCompra") or "")
        if any(not (r and r[0].search(texto) and m.group(0) in r[1]) for m in exclusao.finditer(texto)):
            continue
        uo = c.get("unidadeOrgao") or {}
        ibge, uf = str(uo.get("codigoIbge") or ""), uo.get("ufSigla") or ""
        cnpj = (c.get("orgaoEntidade") or {}).get("cnpj") or ""
        valor = c.get("valorTotalEstimado") or 0
        if vmin and valor and valor < vmin or vmax and valor > vmax:
            continue

        pos = coords.get(ibge)
        dist = {n: round(km(p, pos)) for n, p, _ in bases} if pos else {}
        e_convales = ibge in convales or cnpj == cfg["convales"]["cnpj"]
        na_regiao = (uf in ufs_obras or e_convales
                     or any(dist.get(n, 1e9) <= r for n, _, r in bases))

        sem_mao = re.sub(r"mao[- ]de[- ]obra", " ", texto)
        achou = []
        for k, rx in trilhas.items():
            alvo = sem_mao if k == "obras" else texto
            if not rx.search(alvo):
                continue
            if cfg["trilhas"][k]["abrangencia"] == "regiao" and not na_regiao:
                continue
            achou.append(k)
        if not achou:
            continue

        motivo = []
        if e_convales:
            motivo.append("CONVALES")
        if uf in ufs_obras:
            motivo.append(uf)
        motivo += [f"{d} km de {n}" for n, _, r in bases if (d := dist.get(n)) is not None and d <= r]

        cnpj_o, ano, seq = cnpj, c.get("anoCompra"), c.get("sequencialCompra")
        saida.append({
            "id": chave,
            "trilhas": achou,
            "orgao": (c.get("orgaoEntidade") or {}).get("razaoSocial"),
            "unidade": uo.get("nomeUnidade"),
            "municipio": uo.get("municipioNome"),
            "uf": uf,
            "esfera": {"M": "Municipal", "E": "Estadual", "F": "Federal", "D": "Distrital"}.get(
                (c.get("orgaoEntidade") or {}).get("esferaId"), ""),
            "objeto": (c.get("objetoCompra") or "").strip(),
            "modalidade": c.get("modalidadeNome"),
            "numero": f'{c.get("numeroCompra")}/{ano}',
            "srp": bool(c.get("srp")),
            "valor": valor,
            "abertura_propostas": c.get("dataAberturaProposta"),
            "encerramento": c.get("dataEncerramentoProposta"),
            "publicacao": c.get("dataPublicacaoPncp"),
            "plataforma": c.get("linkSistemaOrigem") or "",
            "pncp": f"https://pncp.gov.br/app/editais/{cnpj_o}/{ano}/{seq}",
            "distancias": dist,
            "regiao": motivo,
            "convales": e_convales,
            "alertas": [t for rx, t in alertas if rx.search(texto)],
            "lat": pos[0] if pos else None,
            "lng": pos[1] if pos else None,
        })

    destino = RAIZ / "docs" / "dados.json"
    anteriores = set()
    if destino.exists():
        try:
            antigo = json.loads(destino.read_text(encoding="utf-8"))
            anteriores = {i["id"] for i in antigo["itens"]}
            primeira_vez = {i["id"]: i.get("visto_em") for i in antigo["itens"]}
        except Exception:
            primeira_vez = {}
    else:
        primeira_vez = {}
    agora = datetime.now(BRT).isoformat(timespec="minutes")
    for i in saida:
        i["novo"] = bool(anteriores) and i["id"] not in anteriores
        i["visto_em"] = primeira_vez.get(i["id"]) or agora

    saida.sort(key=lambda i: i["encerramento"] or "9999")
    destino.write_text(json.dumps({
        "atualizado_em": agora,
        "total_pncp": len(vistos),
        "publicado_a_partir_de": corte,
        "falhas": falhas,
        "trilhas": {k: t["nome"] for k, t in cfg["trilhas"].items()},
        "bases": [{"nome": n, "lat": p[0], "lng": p[1], "raio_km": r} for n, p, r in bases],
        "itens": saida,
    }, ensure_ascii=False), encoding="utf-8")
    por = {k: sum(k in i["trilhas"] for i in saida) for k in trilhas}
    print(f"PNCP: {len(vistos)} abertas | no funil: {len(saida)} {por} | falhas: {falhas}")


if __name__ == "__main__":
    main()
