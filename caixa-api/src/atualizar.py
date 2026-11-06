#!/usr/bin/env python3
"""Espelho público de resultados da CAIXA para JSONs estáticos.

Fonte primária: https://servicebus2.caixa.gov.br/portaldeloterias/api/
Não é uma API oficial ou uma fonte independente da CAIXA.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = "https://servicebus2.caixa.gov.br/portaldeloterias/api"
SAIDA = Path(__file__).resolve().parents[1] / "docs" / "api"
BR = ZoneInfo("America/Sao_Paulo")
LOG = logging.getLogger("loterias")

# Quantidade de números e limite superior. Federal e Loteca têm validação específica.
MODALIDADES = {
    "megasena": (6, 60), "lotofacil": (15, 25), "quina": (5, 80),
    "lotomania": (20, 99), "duplasena": (6, 50), "timemania": (7, 80),
    "diadesorte": (7, 31), "supersete": (7, 9),
    "maismilionaria": (6, 50), "federal": (None, None),
    "loteca": (None, None),
}


def buscar(url: str, tentativas: int = 3) -> dict:
    erro = None
    for i in range(tentativas):
        try:
            req = Request(url, headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "ResultadosPublicosCAIXA/1.0",
                "Cache-Control": "no-cache",
            })
            with urlopen(req, timeout=22) as resp:
                conteudo = resp.read(2_000_001)
                if resp.status != 200 or len(conteudo) > 2_000_000:
                    raise ValueError("Resposta HTTP/tamanho inválidos")
            dados = json.loads(conteudo.decode("utf-8-sig"))
            if not isinstance(dados, dict):
                raise ValueError("JSON sem objeto")
            return dados
        except (HTTPError, URLError, TimeoutError, UnicodeError, ValueError) as exc:
            erro = exc
            if i < tentativas - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Falha ao consultar {url}: {erro}")


def numeros_validos(lista, quantidade, minimo, maximo, repetidos=False):
    if not isinstance(lista, list) or len(lista) != quantidade:
        return False
    if not all(isinstance(x, (str, int)) and not isinstance(x, bool)
               and re.fullmatch(r"\d{1,3}", str(x)) for x in lista):
        return False
    vals = [int(x) for x in lista]
    return all(minimo <= n <= maximo for n in vals) and (
        repetidos or len(set(vals)) == quantidade
    )


def validar(modalidade: str, dados: dict, esperado: int | None = None):
    if modalidade not in MODALIDADES or not isinstance(dados, dict):
        raise ValueError("Modalidade ou JSON inválido")
    n = dados.get("numero")
    if type(n) is not int or n < 1 or (esperado is not None and n != esperado):
        raise ValueError("Número do concurso inválido ou inesperado")
    try:
        data = datetime.strptime(dados["dataApuracao"], "%d/%m/%Y").date()
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Data de apuração inválida") from exc
    if data.year < 1960 or data > datetime.now(BR).date() + timedelta(days=1):
        raise ValueError("Data fora do intervalo permitido")
    faixas = dados.get("listaRateioPremio")
    if not isinstance(faixas, list) or not faixas:
        raise ValueError("Premiação ausente")
    for faixa in faixas:
        if not isinstance(faixa, dict):
            raise ValueError("Faixa de premiação inválida")
        ganhadores = faixa.get("numeroDeGanhadores")
        valor = faixa.get("valorPremio")
        if (type(ganhadores) is not int or ganhadores < 0
                or isinstance(valor, bool) or not isinstance(valor, (int, float))
                or valor < 0):
            raise ValueError("Faixa de premiação incompleta")
    if modalidade == "loteca":
        jogos = dados.get("listaResultadoEquipeEsportiva")
        if not isinstance(jogos, list) or len(jogos) != 14:
            raise ValueError("Loteca sem os 14 jogos")
        return
    if modalidade == "federal":
        bilhetes = dados.get("listaDezenas")
        if (not isinstance(bilhetes, list) or len(bilhetes) != 5
                or not all(isinstance(x, str) and re.fullmatch(r"\d{5,6}", x)
                           for x in bilhetes)):
            raise ValueError("Federal sem cinco bilhetes")
        return
    qtd, maximo = MODALIDADES[modalidade]
    minimo = 0 if modalidade in ("lotomania", "supersete") else 1
    if not numeros_validos(dados.get("listaDezenas"), qtd, minimo, maximo,
                          repetidos=modalidade == "supersete"):
        raise ValueError("Dezenas incompletas ou inválidas")
    if modalidade == "duplasena" and not numeros_validos(
            dados.get("listaDezenasSegundoSorteio"), 6, 1, 50):
        raise ValueError("Dupla Sena sem segundo sorteio")
    if modalidade == "maismilionaria" and not numeros_validos(
            dados.get("trevosSorteados"), 2, 1, 6):
        raise ValueError("+Milionária sem trevos")


def ler(caminho: Path) -> dict | None:
    try:
        with caminho.open(encoding="utf-8") as arq:
            dado = json.load(arq)
        return dado if isinstance(dado, dict) else None
    except (OSError, ValueError):
        return None


def gravar(caminho: Path, dados: dict) -> bool:
    novo = json.dumps(dados, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if caminho.exists() and caminho.read_text(encoding="utf-8") == novo:
        return False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".json.tmp")
    temporario.write_text(novo, encoding="utf-8")
    os.replace(temporario, caminho)
    return True


def buscar_supersete_numerado(url: str, anterior: dict | None, buscar_fn):
    """Contorna falha do endpoint /supersete consultando concursos numerados.

    O ponto de partida 918 é APENAS um número de concurso conhecido em 04/11/2026,
    não um resultado fabricado. Todos os dados continuam vindo da CAIXA.
    """
    if anterior and isinstance(anterior.get("numero"), int):
        inicio = anterior["numero"] + 1
        ultimo = None
    else:
        inicio = 918
        ultimo = None

    # Uma consulta numerada bem-sucedida confirma a fonte CAIXA; um 500
    # no concurso futuro pode significar que ele ainda não foi apurado.
    for n in range(inicio, inicio + 3):
        try:
            dados = buscar_fn(f"{url}/{n}")
            validar("supersete", dados, n)
            ultimo = dados
            LOG.info("Super Sete: concurso %d confirmado pelo endpoint numerado", n)
        except (RuntimeError, ValueError) as exc:
            LOG.warning("Super Sete: concurso numerado %d indisponível: %s", n, exc)
            break

    if ultimo is not None:
        return ultimo
    raise RuntimeError("O endpoint geral e o numerado do Super Sete falharam")


SUPERSETE_ESPELHO = "https://loteriascaixa-api.herokuapp.com/api/supersete/latest"


def buscar_supersete_espelho(buscar_fn):
    """Converte o espelho secundário para campos compatíveis com os da CAIXA.

    Dados não são identificados como obtidos diretamente do servidor oficial.
    Campos não presentes no espelho não são inventados.
    """
    fonte = buscar_fn(SUPERSETE_ESPELHO)
    if fonte.get("loteria") != "supersete":
        raise ValueError("O espelho respondeu outra modalidade")
    concursos = fonte.get("concurso")
    if type(concursos) is not int or concursos < 1:
        raise ValueError("Concurso inválido no espelho")
    if not numeros_validos(fonte.get("dezenas"), 7, 0, 9, repetidos=True):
        raise ValueError("Colunas do Super Sete inválidas no espelho")
    premios = fonte.get("premiacoes")
    if not isinstance(premios, list) or len(premios) != 5:
        raise ValueError("Rateio incompleto no espelho")
    faixas = []
    for p in premios:
        if not isinstance(p, dict):
            raise ValueError("Faixa de premiação malformada")
        faixas.append({
            "descricaoFaixa": p.get("descricao"),
            "faixa": p.get("faixa"),
            "numeroDeGanhadores": p.get("ganhadores"),
            "valorPremio": p.get("valorPremio"),
        })
    esperado = [1, 2, 3, 4, 5]
    if [p["faixa"] for p in faixas] != esperado:
        raise ValueError("Faixas inválidas no espelho")
    dado = {
        "numero": concursos,
        "dataApuracao": fonte.get("data"),
        "listaDezenas": fonte["dezenas"],
        "dezenasSorteadasOrdemSorteio": fonte.get("dezenasOrdemSorteio", fonte["dezenas"]),
        "listaRateioPremio": faixas,
        "acumulado": fonte.get("acumulou"),
        "numeroConcursoProximo": fonte.get("proximoConcurso"),
        "dataProximoConcurso": fonte.get("dataProximoConcurso"),
        "localSorteio": fonte.get("local"),
        "valorArrecadado": fonte.get("valorArrecadado"),
        "valorAcumuladoConcurso_0_5": fonte.get("valorAcumuladoConcurso_0_5"),
        "valorAcumuladoConcursoEspecial": fonte.get("valorAcumuladoConcursoEspecial"),
        "valorAcumuladoProximoConcurso": fonte.get("valorAcumuladoProximoConcurso"),
        "valorEstimadoProximoConcurso": fonte.get("valorEstimadoProximoConcurso"),
        "observacao": fonte.get("observacao"),
        "tipoJogo": "SUPER_SETE",
        "fonteDados": "espelho-secundario",
        "origemDados": SUPERSETE_ESPELHO,
        "obtidoDiretamenteDaCaixa": False,
    }
    validar("supersete", dado)
    return dado


def atualizar(modalidades, pasta=SAIDA, retroativos=0, buscar_fn=buscar):
    sucessos = 0
    alteracoes = 0
    for modalidade in modalidades:
        anterior = ler(pasta / modalidade / "ultimo.json")
        try:
            url = f"{BASE}/{modalidade}"
            try:
                dados = buscar_fn(url)
            except RuntimeError as exc:
                if modalidade != "supersete":
                    raise
                LOG.warning("Super Sete: endpoint geral indisponível (%s); tentando concursos numerados", exc)
                try:
                    dados = buscar_supersete_numerado(url, anterior, buscar_fn)
                except RuntimeError as err_numerado:
                    LOG.warning("Super Sete: consulta numerada também falhou (%s); usando espelho secundário identificado", err_numerado)
                    dados = buscar_supersete_espelho(buscar_fn)
            validar(modalidade, dados)
            numero = dados["numero"]
            if anterior and isinstance(anterior.get("numero"), int) and (
                    numero < anterior["numero"]):
                raise ValueError("A CAIXA retornou um concurso anterior ao salvo")

            # Pequenos intervalos não consultados são recuperados, no máximo 10.
            anteriores = []
            if anterior and isinstance(anterior.get("numero"), int):
                anteriores = range(max(anterior["numero"] + 1, numero - 10), numero)
            elif retroativos:
                anteriores = range(max(1, numero - retroativos), numero)
            for n in anteriores:
                caminho = pasta / modalidade / f"{n}.json"
                if caminho.exists():
                    continue
                try:
                    antigo = buscar_fn(f"{url}/{n}")
                    validar(modalidade, antigo, n)
                    alteracoes += int(gravar(caminho, antigo))
                except (ValueError, RuntimeError) as exc:
                    LOG.warning("%s/%d não recuperado: %s", modalidade, n, exc)

            alteracoes += int(gravar(pasta / modalidade / f"{numero}.json", dados))
            alteracoes += int(gravar(pasta / modalidade / "ultimo.json", dados))
            LOG.info("%s: concurso %d OK", modalidade, numero)
            sucessos += 1
        except (RuntimeError, ValueError, OSError) as exc:
            LOG.error("%s: %s. Dados anteriores preservados.", modalidade, exc)

    agregado = {}
    for modalidade in MODALIDADES:
        dados = ler(pasta / modalidade / "ultimo.json")
        if dados:
            agregado[modalidade] = dados
    if agregado:
        indice = pasta / "ultimo.json"
        anterior = ler(indice)
        if not anterior or anterior.get("modalidades") != agregado:
            alteracoes += int(gravar(indice, {
                "fonte": "Loterias CAIXA",
                "atualizadoEm": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "modalidades": agregado,
            }))
    return sucessos, alteracoes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modalidade", action="append", choices=list(MODALIDADES))
    parser.add_argument("--retroativos", type=int, default=0)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args()
    if not 0 <= args.retroativos <= 20:
        parser.error("--retroativos deve ser de 0 a 20")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sucessos, alteracoes = atualizar(
        list(dict.fromkeys(args.modalidade or MODALIDADES)), args.saida,
        args.retroativos)
    LOG.info("%d modalidades consultadas; %d arquivos alterados", sucessos, alteracoes)
    return 0 if sucessos else 1


if __name__ == "__main__":
    sys.exit(main())
