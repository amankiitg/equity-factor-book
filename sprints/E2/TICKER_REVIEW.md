# Ticker identity review, close-out C6

Every reused symbol from the C1 identity check, reopened. The question
for each one is whether the symbol is a current index constituent, or
has an added row for the same ticker dated after its removal. Where
either holds, the name on that side is compared with the yfinance
holder of the symbol: a match means the symbol was renamed rather than
taken over, so the ticker returns with its history truncated; no match
means it stays out of the panel.

Generated from data/processed/ticker_identity_readded.parquet, so this
table and the decision the build acted on cannot disagree.

## Kept, truncated to the current company

| Ticker | Removed name | Added name | Current name | Score | Decision | Truncation date |
| --- | --- | --- | --- | --- | --- | --- |
| FOX | 21st Century Fox | Fox Corporation (Class B) | Fox Corporation | 1.00 | keep_truncated | 2019-03-13 |
| FOXA | 21st Century Fox | Fox Corporation (Class A) | Fox Corporation | 1.00 | keep_truncated | 2019-03-12 |
| PCG | Pacific Gas & Electric Company | PG&E | PG&E Corporation | 1.00 | keep_truncated | 2022-10-03 |

## Reviewed and left out of the panel

| Ticker | Removed name | Added name | Current name | Score | Decision |
| --- | --- | --- | --- | --- | --- |
| ADCT | ADC Telecommunications | no add row | ADC Therapeutics SA | 0.00 | stays_dropped |
| AN | Amoco | no add row | AutoNation, Inc. | 0.00 | stays_dropped |
| APC | Anadarko Petroleum | no add row | ARKO Petroleum Corp. | 0.00 | stays_dropped |
| ATI | Allegheny Technologies | no add row | ATI Inc. | 0.00 | stays_dropped |
| AV | Avaya | no add row | Corgi Aerospace & Commercial Aviation ETF | 0.00 | stays_dropped |
| BEAM | Suntory Global Spirits | no add row | Beam Therapeutics Inc. | 0.00 | stays_dropped |
| CAM | Cameron International | no add row | AB California Intermediate Municipal ETF | 0.00 | stays_dropped |
| CCE | Coca-Cola Enterprises | no add row | Coca-Cola European Partners plc | 0.00 | stays_dropped |
| CLF | Cliffs Natural Resources | no add row | Cleveland-Cliffs Inc. | 0.00 | stays_dropped |
| CNX | Consol Energy | no add row | CNX Resources Corporation | 0.00 | stays_dropped |
| CPWR | Compuware | no add row | Ocean Thermal Energy Corporation | 0.00 | stays_dropped |
| CSC | Computer Sciences Corporation | no add row | CSC Collective Holdings Ltd | 0.00 | stays_dropped |
| CSRA | CSRA | no add row | Cohen & Steers Real Assets Active ETF | 0.00 | stays_dropped |
| DD | DuPont | DuPont | DuPont de Nemours, Inc. | 0.33 | stays_dropped |
| DV | DeVry | no add row | DoubleVerify Holdings, Inc. | 0.00 | stays_dropped |
| DYN | Dynegy | no add row | Dyne Therapeutics, Inc. | 0.00 | stays_dropped |
| EMC | EMC Corporation | no add row | Global X Emerging Markets Great Consumer ETF | 0.00 | stays_dropped |
| EP | El Paso Corporation | no add row | Empire Petroleum Corporation | 0.00 | stays_dropped |
| GENZ | Genzyme | no add row | VanEck Digital Native Economy ETF | 0.00 | stays_dropped |
| GRN | General Re | no add row | iPath Series B Carbon ETN | 0.00 | stays_dropped |
| INFO | IHS Markit | no add row | Harbor PanAgora Dynamic Large Cap Core ETF | 0.00 | stays_dropped |
| KG | King Pharmaceuticals | no add row | Kestrel Group Ltd | 0.00 | stays_dropped |
| LIFE | Life Technologies | no add row | Ethos Technologies Inc. | 0.00 | stays_dropped |
| MHS | Medco Health Solutions | no add row | Morningstar US Healthcare | 0.00 | stays_dropped |
| MI | Marshall & Ilsley | no add row | NFT Limited | 0.00 | stays_dropped |
| MMI | Motorola Mobility | no add row | Marcus & Millichap, Inc. | 0.00 | stays_dropped |
| NFX | Newfield Exploration | no add row | Corgi NFLX 2x Daily ETF | 0.00 | stays_dropped |
| NSM | National Semiconductor | no add row | Nationstar Mortgage Holdings Inc. | 0.00 | stays_dropped |
| NYX | NYSE Euronext | no add row | NYIAX, Inc. Common Stock | 0.00 | stays_dropped |
| OI | Owens-Illinois | Owens-Illinois | O-I Glass, Inc. | 0.00 | stays_dropped |
| PCL | Plum Creek Timber | no add row | PGIM Corporate Bond 10+ Year ETF | 0.00 | stays_dropped |
| PCS | MetroPCS | no add row | PGIM Corporate Bond 0-5 Year ETF | 0.00 | stays_dropped |
| POM | Pepco Holdings | no add row | Pomdoctor Limited | 0.00 | stays_dropped |

36 reused symbols reviewed, 3 kept, 33 left out.
