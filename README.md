# Açude Vivo

Mapa da segurança hídrica do Nordeste brasileiro, feito só com dados públicos.

**Acesse:** https://sergiorsantana.github.io/Acude-vivo/

## O que mostra

- **548 açudes** monitorados pela ANA (SAR), com volume, cota, histórico de 12 meses e comparação com o ano anterior
- **1.794 municípios** coloridos pela situação do açude que os abastece (crítico ≤ 20%, alerta 20–40%, normal > 40%)
- **População afetada** em municípios com manancial crítico (Censo 2022)
- **Previsão de 30, 60 e 90 dias** e **autonomia** (dias até o açude chegar a 5% no ritmo atual)
- **Reservatório equivalente** por estado e **Monitor de Secas** (área em seca por categoria)
- **Chuva** dos últimos 30 dias e previsão de 15 dias para cada açude
- **Transposição do São Francisco**: canais e municípios beneficiados
- **Imagens de satélite** antes e depois de cada açude (Esri Wayback)
- **Alertas** automáticos, **relatório** pronto para PDF e **exportação em CSV**

## Fontes

ANA (SAR, SNISB, Atlas Águas), Monitor de Secas (ANA/FUNCEME), IBGE (Censo 2022 e malha municipal), Open-Meteo e Esri World Imagery. Metodologia e limitações em [`sobre.html`](monitor-reservatorios/sobre.html).

## Rodar no seu computador

Precisa de Python 3.9 ou mais novo, sem pacotes extras.

```
cd monitor-reservatorios
python servidor.py
```

Abre em http://localhost:8765 e atualiza os dados a cada 12 horas. Para só atualizar os dados: `python atualizar_dados.py`.

Mais detalhes em [`monitor-reservatorios/LEIAME.md`](monitor-reservatorios/LEIAME.md).
