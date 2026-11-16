# Açude Vivo

Mapa da segurança hídrica do Nordeste: volume dos açudes (ANA/SAR), municípios abastecidos por cada açude, população afetada, monitor de secas, chuva, transposição e imagens de satélite.

## Como abrir

No PowerShell, dentro desta pasta:

```
python servidor.py
```

O navegador abre em http://localhost:8765. Enquanto a janela estiver aberta, os dados são atualizados sozinhos a cada 12 horas.

Para só atualizar os dados, sem abrir o app:

```
python atualizar_dados.py
```

A primeira execução baixa um ano de medições de todos os açudes e leva alguns minutos. As seguintes baixam só o que é novo.

## Atualização diária automática

A tarefa "Acude Vivo - atualizar dados" do Agendador de Tarefas do Windows roda `..\atualizar_e_enviar.ps1` todo dia às 7h (ou assim que o PC ligar, se estiver desligado nesse horário). Ela baixa os dados, redesenha os gráficos e envia ao GitHub, que republica o site. O registro fica em `..\logs\`.

Se a ANA estiver fora do ar, o script usa o último histórico salvo dos açudes e atualiza o resto (chuva, IBGE, Monitor de Secas).

## Arquivos

| Arquivo | O que é |
|---|---|
| `index.html` | O app (mapa) |
| `assistente.js` | Aba "Perguntar": responde perguntas buscando nos dados |
| `gerar_graficos.py` | Gera os gráficos SVG do README em `../docs/graficos` |
| `relatorio.html` | Relatório pronto para imprimir ou salvar em PDF |
| `sobre.html` | Metodologia, fontes e limitações |
| `atualizar_dados.py` | Baixa os dados públicos e gera `dados.json` |
| `servidor.py` | Abre o app e atualiza os dados automaticamente |
| `dados.json`, `municipios.geojson`, `transposicao.geojson` | Dados gerados (não editar) |
| `cache/` | Histórico salvo dos açudes (pode apagar; será baixado de novo) |
| `dados_externos/` | Suas planilhas de decretos e carro-pipa |

## Decretos de emergência e Carro-Pipa

Esses dados não têm download automático. Para incluir:

1. Copie `dados_externos/decretos.modelo.csv` para `dados_externos/decretos.csv` (ou `carro_pipa.modelo.csv` para `carro_pipa.csv`).
2. Preencha uma linha por município. A coluna `cod_ibge` é obrigatória; as outras aparecem no mapa como estiverem.
3. Rode `python atualizar_dados.py`.

No mapa, ative a camada "Decretos / carro-pipa" para destacar esses municípios.

## Requisitos

Python 3.9 ou mais novo. Não precisa instalar nenhum pacote.
