import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from atualizar import MODALIDADES, atualizar, gravar, validar

def amostra(modalidade="megasena", numero=3081):
    qtd, _ = MODALIDADES[modalidade]
    dados = {
        "numero": numero,
        "dataApuracao": datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"),
        "listaDezenas": [str(n).zfill(2) for n in range(1, (qtd or 0) + 1)],
        "listaRateioPremio": [{"faixa": 1, "numeroDeGanhadores": 0, "valorPremio": 0.0}],
    }
    if modalidade == "federal":
        dados["listaDezenas"] = ["012345", "023456", "034567", "045678", "056789"]
    if modalidade == "loteca":
        dados["listaResultadoEquipeEsportiva"] = [{} for _ in range(14)]
    if modalidade == "duplasena":
        dados["listaDezenasSegundoSorteio"] = ["10", "11", "12", "13", "14", "15"]
    if modalidade == "maismilionaria":
        dados["trevosSorteados"] = ["1", "3"]
    return dados

class TestCaixa(unittest.TestCase):
    def test_todas_modalidades(self):
        for modalidade in MODALIDADES:
            with self.subTest(modalidade=modalidade):
                validar(modalidade, amostra(modalidade))

    def test_premiacao_invalida(self):
        dado = amostra()
        dado["listaRateioPremio"] = []
        with self.assertRaises(ValueError):
            validar("megasena", dado)

    def test_concurso_divergente(self):
        with self.assertRaises(ValueError):
            validar("megasena", amostra(), 123)

    def test_preserva_se_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gravar(pasta / "megasena" / "ultimo.json", amostra(numero=3001))
            def falha(_):
                raise RuntimeError("indisponivel")
            sucessos, _ = atualizar(["megasena"], pasta=pasta, buscar_fn=falha)
            self.assertEqual(sucessos, 0)
            self.assertEqual(json.loads((pasta / "megasena" / "ultimo.json").read_text())["numero"], 3001)

    def test_nao_retrocede(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            gravar(pasta / "megasena" / "ultimo.json", amostra(numero=3003))
            sucessos, _ = atualizar(["megasena"], pasta=pasta,
                                    buscar_fn=lambda _: amostra(numero=3002))
            self.assertEqual(sucessos, 0)

    def test_ultimo_e_historico(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            sucessos, _ = atualizar(["megasena"], pasta=pasta,
                                    buscar_fn=lambda _: amostra(numero=3003))
            self.assertEqual(sucessos, 1)
            self.assertTrue((pasta / "megasena" / "3003.json").exists())
            self.assertTrue((pasta / "ultimo.json").exists())

if __name__ == "__main__":
    unittest.main()
