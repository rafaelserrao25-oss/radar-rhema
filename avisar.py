"""
Radar Rhema - aviso no WhatsApp das licitações novas.

Roda depois do coletar.py. Lê docs/dados.json, separa as licitações que
entraram nesta coleta (campo "novo") e manda um resumo pelo CallMeBot.

Destinos no segredo WHATSAPP_DESTINOS do GitHub, no formato
    5584999999999:APIKEY;5561988888888:OUTRAKEY
(cada pessoa ativa o próprio número no CallMeBot e recebe a própria APIKEY).

Teste sem enviar:  python avisar.py --teste
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SITE = "https://rafaelserrao25-oss.github.io/radar-rhema/"


def reais(v):
    if not v:
        return "valor sigiloso"
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(iso):
    if not iso:
        return "sem data"
    d, h = iso[:10], iso[11:16]
    return f"{d[8:10]}/{d[5:7]} {h}"


def montar(dados, cfg):
    novos = [i for i in dados["itens"] if i.get("novo")]
    if not novos:
        return None
    nomes = dados["trilhas"]
    na_regiao = [i for i in novos if i.get("regiao")]
    so_brasil = [i for i in novos if not i.get("regiao")]
    if not cfg.get("brasil_todo", False):
        lista = na_regiao
    else:
        lista = novos
        so_brasil = []
    if not lista and not so_brasil:
        return None

    lista.sort(key=lambda i: (not i.get("convales"), i.get("encerramento") or "9999"))
    maximo = cfg.get("max_itens", 12)
    linhas = [f"*Radar Rhema* - {len(lista)} licitação(ões) nova(s) nas suas regiões"]
    for i in lista[:maximo]:
        trilha = ", ".join(nomes.get(t, t) for t in i["trilhas"])
        selo = "CONVALES | " if i.get("convales") else ""
        objeto = i["objeto"][:140] + ("..." if len(i["objeto"]) > 140 else "")
        linhas += [
            "",
            f"*{selo}{i['municipio']}/{i['uf']}* ({trilha})",
            objeto,
            f"{reais(i.get('valor'))} | propostas até {data_br(i.get('encerramento'))}",
            i["pncp"],
        ]
    if len(lista) > maximo:
        linhas += ["", f"E mais {len(lista) - maximo} no site."]
    if so_brasil:
        por = {}
        for i in so_brasil:
            for t in i["trilhas"]:
                por[nomes.get(t, t)] = por.get(nomes.get(t, t), 0) + 1
        resumo = ", ".join(f"{n} de {t.lower()}" for t, n in por.items())
        linhas += ["", f"Fora das regiões (Brasil todo): {resumo}."]
    linhas += ["", SITE]
    return "\n".join(linhas)


def enviar(texto, destinos):
    for n, (fone, chave) in enumerate(destinos):
        if n:
            time.sleep(5)
        url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
            {"phone": fone, "text": texto, "apikey": chave})
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                corpo = r.read().decode("utf-8", "replace")
            ok = r.status == 200 and "error" not in corpo.lower()
        except Exception as e:
            ok, corpo = False, str(e)
        final = fone[-4:]
        print(f"Aviso para ...{final}: {'enviado' if ok else 'FALHOU'}")
        if not ok:
            print(corpo[:300].replace(chave, "***"))


def main():
    cfg = json.loads((RAIZ / "config.json").read_text(encoding="utf-8")).get("aviso_whatsapp", {})
    dados = json.loads((RAIZ / "docs" / "dados.json").read_text(encoding="utf-8"))
    texto = montar(dados, cfg)
    if "--teste" in sys.argv:
        print(texto or "(nada novo: nenhum aviso seria enviado)")
        return
    if not cfg.get("ligado", True):
        print("Aviso desligado no config.json.")
        return
    if not texto:
        print("Nada novo nas regiões: sem aviso.")
        return
    bruto = os.environ.get("WHATSAPP_DESTINOS", "").strip()
    destinos = [tuple(p.strip().split(":", 1)) for p in bruto.split(";") if ":" in p]
    if not destinos:
        print("Segredo WHATSAPP_DESTINOS vazio: aviso não enviado.")
        return
    enviar(texto, destinos)


if __name__ == "__main__":
    main()
