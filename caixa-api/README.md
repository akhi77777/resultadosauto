# Espelho de resultados da CAIXA

Este código está isolado em `caixa-api/` e **não altera o site existente**, inclusive o `index.html` do repositório.

## Como ativar
1. Integre a pull request à branch principal.
2. Em Settings > Actions > General > Workflow permissions, permita escrita ao workflow, se necessário.
3. Em Actions > Espelho da API CAIXA > Run workflow, execute a coleta (retroativos=5).
4. Confira os logs. O agendamento subsequente é aproximado.

## URLs dos resultados (depois da primeira coleta)
- Mega-Sena: https://raw.githubusercontent.com/akhi77777/resultadosauto/main/caixa-api/docs/api/megasena/ultimo.json
- Lotofácil: https://raw.githubusercontent.com/akhi77777/resultadosauto/main/caixa-api/docs/api/lotofacil/ultimo.json
- Federal: https://raw.githubusercontent.com/akhi77777/resultadosauto/main/caixa-api/docs/api/federal/ultimo.json
- Todas: https://raw.githubusercontent.com/akhi77777/resultadosauto/main/caixa-api/docs/api/ultimo.json

Concurso individual arquivado: `caixa-api/docs/api/megasena/NUMERO.json`.

## Modalidades
megasena, lotofacil, quina, lotomania, duplasena, timemania, diadesorte, supersete, maismilionaria, federal e loteca.

## Execução local
```bash
python -m unittest discover -s caixa-api/tests -v
python caixa-api/src/atualizar.py --retroativos 5
```

Usa Python 3.12 sem bibliotecas externas. Preserva JSONs originais, concursos e premiações. Se a CAIXA falhar ou devolver concurso anterior, mantém o resultado válido já arquivado. É um **cache dos serviços oficiais**, não uma fonte independente. A coleta pode falhar por bloqueio de rede, manutenção ou mudança de formato. Os resultados deste espelho não substituem a conferência oficial de prêmios.
