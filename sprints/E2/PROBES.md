# Sprint E2: PROBES

## Task 0: point-in-time member coverage by calendar year

Ran 2026-09-10. A point-in-time member counts as covered in a year when
at least half of the business days on which it was a member have a
non-null adjusted close. The denominator is the ticker's own membership
window.

| year | n_members | n_covered | coverage |
| --- | --- | --- | --- |
| 2010 | 514 | 354 | 0.6887 |
| 2011 | 519 | 363 | 0.6994 |
| 2012 | 520 | 375 | 0.7212 |
| 2013 | 519 | 387 | 0.7457 |
| 2014 | 515 | 393 | 0.7631 |
| 2015 | 528 | 409 | 0.7746 |
| 2016 | 533 | 431 | 0.8086 |
| 2017 | 533 | 446 | 0.8368 |
| 2018 | 527 | 453 | 0.8596 |
| 2019 | 528 | 464 | 0.8788 |
| 2020 | 523 | 469 | 0.8968 |
| 2021 | 525 | 478 | 0.9105 |
| 2022 | 524 | 486 | 0.9275 |
| 2023 | 520 | 496 | 0.9538 |
| 2024 | 522 | 505 | 0.9674 |
| 2025 | 523 | 512 | 0.9790 |
| 2026 | 515 | 511 | 0.9922 |

MODEL_START = 2010. The first year with at least 300 covered
point-in-time members is 2010 (354 covered), so every E2 regression
starts at 2010-01-04 and the full E1 window is usable.

Notes.

1. Coverage improves monotonically from 68.9% in 2010 to 99.2% in 2026.
   The gradient is the survivorship effect: names deleted before 2010 or
   in the early years often have no recoverable history, while recent
   members are almost fully covered.
2. The gap is one-sided. Missing deletions are disproportionately
   failures, so the lower tail of residual returns is thin and specific
   risk on the loser side is biased downward. That is context for E3 and
   E5, not something E2 fixes.
3. F2.0a stores this table and MODEL_START rather than a single coverage
   threshold, following the E1 finding that F1.1 failed on calibration,
   not on data quality.

## C1 ticker identity check (criterion F2.6b, 2026-09-10)

Every ticker on the Wikipedia changes table's removed list compared
with the current holder of that symbol on yfinance, matched by name
token overlap. Cached in data/raw/yf_names.parquet, so each symbol is
asked once. This is the printed table, taken from
`python -m efb.identity`.

```
=== C1 ticker identity: removed members vs the current holder ===
ticker                       removed_name                                 current_name  match_score first_valid_date last_valid_date removal_date
    AA                              Alcoa                            Alcoa Corporation       1.0000       2010-01-04      2026-09-03   2016-11-01
   AAL            American Airlines Group                 American Airlines Group Inc.       1.0000       2010-01-04      2026-09-03   2024-09-23
   AAP                 Advance Auto Parts                     Advance Auto Parts, Inc.       1.0000       2010-01-04      2026-09-03   2023-08-25
   ABK                    Ambac Financial                                          NaN       0.0000              NaT             NaT   2008-06-10
  ABMD                            Abiomed                                          NaN       0.0000              NaT             NaT   2022-12-22
   ABS                         Albertsons                                          NaN       0.0000              NaT             NaT   2006-06-02
  ACAS                   American Capital                                          NaN       0.0000              NaT             NaT   2009-03-03
   ACE                              Chubb                                          NaN       0.0000              NaT             NaT   2016-01-19
  ADCT             ADC Telecommunications                          ADC Therapeutics SA       0.2500       2020-05-18      2026-09-03   2007-07-02
   ADS              Alliance Data Systems                                          NaN       0.0000              NaT             NaT   2020-06-22
   ADT                                ADT                                     ADT Inc.       1.0000       2018-01-19      2026-09-03   2016-05-03
   AET                              Aetna                                   Aetna Inc.       1.0000       2010-01-04      2018-11-29   2018-12-03
   AGN                           Allergan                                          NaN       0.0000              NaT             NaT   2015-03-23
   AIV  Apartment Investment & Management  Apartment Investment and Management Company       0.7500       2010-01-04      2026-09-03   2020-12-21
   AKS                           AK Steel                                          NaN       0.0000              NaT             NaT   2011-12-16
   ALK                   Alaska Air Group                       Alaska Air Group, Inc.       1.0000       2010-01-04      2026-09-03   2023-12-18
  ALTR                             Altera                                          NaN       0.0000              NaT             NaT   2015-12-29
  ALXN            Alexion Pharmaceuticals                                          NaN       0.0000              NaT             NaT   2021-07-21
   AMD             Advanced Micro Devices                 Advanced Micro Devices, Inc.       1.0000       2010-01-04      2026-09-03   2013-09-20
   AMG          Affiliated Managers Group              Affiliated Managers Group, Inc.       1.0000       2010-01-04      2026-09-03   2019-12-23
  AMTM                            Amentum                       Amentum Holdings, Inc.       0.5000       2024-09-24      2026-09-03   2024-12-23
    AN                              Amoco                             AutoNation, Inc.       0.0000       2010-01-04      2026-09-03   1998-12-11
  ANDV                           Andeavor                                     Andeavor       1.0000       2010-01-04      2018-10-01   2018-10-01
   ANF                Abercrombie & Fitch                      Abercrombie & Fitch Co.       1.0000       2010-01-04      2026-09-03   2013-12-23
   ANR            Alpha Natural Resources                                          NaN       0.0000              NaT             NaT   2012-10-02
  ANSS                              Ansys                                          NaN       0.0000              NaT             NaT   2025-07-18
   APC                 Anadarko Petroleum                         ARKO Petroleum Corp.       0.3333       2026-02-12      2026-09-03   2019-08-09
  APOL             Apollo Education Group                                          NaN       0.0000              NaT             NaT   2013-07-01
   ARG                             Airgas                                          NaN       0.0000              NaT             NaT   2016-05-23
  ARNC                            Arconic                                          NaN       0.0000              NaT             NaT   2020-04-01
   ATI             Allegheny Technologies                                     ATI Inc.       0.0000       2010-01-04      2026-09-03   2015-07-02
  ATVI                Activision Blizzard                                          NaN       0.0000              NaT             NaT   2023-10-18
    AV                              Avaya    Corgi Aerospace & Commercial Aviation ETF       0.0000       2026-05-06      2026-09-03   2007-10-26
   AVP                      Avon Products                                          NaN       0.0000              NaT             NaT   2015-03-23
   AYE                   Allegheny Energy                                          NaN       0.0000              NaT             NaT   1976-07-01
   AYI                      Acuity Brands                                  Acuity Inc.       0.5000       2010-01-04      2026-09-03   2018-06-18
  BBBY                  Bed Bath & Beyond                      Bed Bath & Beyond, Inc.       1.0000       2026-07-17      2026-09-03   2017-07-26
  BBWI            Bath & Body Works, Inc.                      Bath & Body Works, Inc.       1.0000       2010-01-04      2026-09-03   2024-10-01
    BC                          Brunswick                        Brunswick Corporation       1.0000       2010-01-04      2026-09-03   2008-06-23
   BCR                            CR Bard                                          NaN       0.0000              NaT             NaT   2018-01-03
  BEAM             Suntory Global Spirits                       Beam Therapeutics Inc.       0.0000       2020-02-06      2026-09-03   2014-05-01
   BHF              Brighthouse Financial                  Brighthouse Financial, Inc.       1.0000       2017-07-17      2026-09-03   2019-04-02
   BHI                       Baker Hughes                                          NaN       0.0000              NaT             NaT   2017-07-07
   BIG                           Big Lots                                          NaN       0.0000              NaT             NaT   2013-02-15
   BIO               Bio-Rad Laboratories                   Bio-Rad Laboratories, Inc.       1.0000       2010-01-04      2026-09-03   2024-09-23
   BJS                        BJ Services                                          NaN       0.0000              NaT             NaT   2010-04-29
   BMC                       BMC Software                                          NaN       0.0000              NaT             NaT   2013-09-10
   BMS                      Bemis Company                          Bemis Company, Inc.       1.0000       2010-01-04      2019-06-10   2014-12-05
  BRCM               Broadcom Corporation                                          NaN       0.0000              NaT             NaT   2016-02-01
    BS                    Bethlehem Steel                                          NaN       0.0000              NaT             NaT   2000-12-05
   BTU                     Peabody Energy                   Peabody Energy Corporation       1.0000       2017-04-03      2026-09-03   2014-09-20
   BWA                         BorgWarner                              BorgWarner Inc.       1.0000       2010-01-04      2026-09-03   2025-03-24
  BXLT                            Baxalta                                          NaN       0.0000              NaT             NaT   2016-06-03
    CA                    CA Technologies                                          NaN       0.0000              NaT             NaT   2018-11-06
   CAG                     Conagra Brands                         Conagra Brands, Inc.       1.0000       2010-01-04      2026-09-03   2026-06-30
   CAM              Cameron International     AB California Intermediate Municipal ETF       0.0000       2025-10-06      2026-09-03   2016-04-04
   CBE                  Cooper Industries                                          NaN       0.0000              NaT             NaT   2009-09-28
   CCE              Coca-Cola Enterprises              Coca-Cola European Partners plc       0.4000              NaT             NaT   2016-05-31
   CCK                     Crown Holdings                         Crown Holdings, Inc.       1.0000       2010-01-04      2026-09-03   2000-12-05
  CDAY                           Ceridian                                          NaN       0.0000              NaT             NaT   2024-02-01
    CE                           Celanese                         Celanese Corporation       1.0000       2010-01-04      2026-09-03   2025-03-24
   CEG         Constellation Energy Group             Constellation Energy Corporation       0.6667       2022-01-19      2026-09-03   2012-03-13
  CELG                            Celgene                                          NaN       0.0000              NaT             NaT   2019-11-21
  CEPH                           Cephalon                                          NaN       0.0000              NaT             NaT   2011-10-14
  CERN                             Cerner                                          NaN       0.0000              NaT             NaT   2022-06-08
   CFC         Countrywide Financial Corp                                          NaN       0.0000              NaT             NaT   2008-07-01
   CFN                         Carefusion                                          NaN       0.0000              NaT             NaT   2015-03-18
   CHK                  Chesapeake Energy                                          NaN       0.0000              NaT             NaT   2018-03-19
  CIEN                              Ciena                            Ciena Corporation       1.0000       2010-01-04      2026-09-03   2009-12-18
   CLF           Cliffs Natural Resources                        Cleveland-Cliffs Inc.       0.2500       2010-01-04      2026-09-03   2014-04-02
   CMA                           Comerica                                          NaN       0.0000              NaT             NaT   2024-06-24
 CMCSK                     Comcast K Corp                                          NaN       0.0000              NaT             NaT   2015-12-15
   CNX                      Consol Energy                    CNX Resources Corporation       0.0000       2010-01-04      2026-09-03   2016-03-04
   COL                   Rockwell Collins                                          NaN       0.0000       2012-08-02      2020-11-30   2018-12-03
  COTY                               Coty                                    Coty Inc.       1.0000       2013-06-13      2026-09-03   2020-09-21
   COV                           Covidien                                          NaN       0.0000              NaT             NaT   2009-06-05
   CPB                         Campbell's                       The Campbell's Company       0.5000       2010-01-04      2026-09-03   2026-06-22
  CPGX            Columbia Pipeline Group                Columbia Pipeline Group, Inc.       1.0000              NaT             NaT   2016-07-05
  CPRI                     Capri Holdings                       Capri Holdings Limited       1.0000       2011-12-15      2026-09-03   2020-05-12
  CPWR                          Compuware             Ocean Thermal Energy Corporation       0.0000       2010-01-04      2026-09-03   2011-12-31
   CSC      Computer Sciences Corporation                  CSC Collective Holdings Ltd       0.0000              NaT             NaT   2015-12-01
  CSRA                               CSRA        Cohen & Steers Real Assets Active ETF       0.0000       2026-08-12      2026-09-03   2018-04-04
  CTLT                           Catalent                                          NaN       0.0000              NaT             NaT   2024-12-23
  CTRA                     Coterra Energy                                          NaN       0.0000              NaT             NaT   2026-05-07
   CTX                       Centex Corp.                                          NaN       0.0000              NaT             NaT   2009-08-19
  CTXS                     Citrix Systems                                          NaN       0.0000              NaT             NaT   2022-10-03
   CVC                Cablevision Systems                                          NaN       0.0000              NaT             NaT   2016-06-22
   CVG                          Convergys                        Convergys Corporation       1.0000       2010-01-04      2026-09-03   2009-12-18
   CVH               Coventry Health Care                                          NaN       0.0000              NaT             NaT   2013-05-08
   CXO                   Concho Resources                                          NaN       0.0000              NaT             NaT   2021-01-21
   CZR              Caesars Entertainment                  Caesars Entertainment, Inc.       1.0000       2014-09-22      2026-09-03   2025-09-22
   DAY                           Dayforce                                          NaN       0.0000              NaT             NaT   2026-02-09
    DD                             DuPont                      DuPont de Nemours, Inc.       0.3333       2010-01-04      2026-09-03   2017-09-01
  DELL                               Dell                       Dell Technologies Inc.       0.5000       2016-08-17      2026-09-03   2013-10-29
    DF                         Dean Foods                                          NaN       0.0000              NaT             NaT   2013-05-23
   DFS                 Discover Financial                                          NaN       0.0000              NaT             NaT   2025-05-19
 DISCA                    Discovery, Inc.                                          NaN       0.0000              NaT             NaT   2022-04-11
 DISCK                    Discovery, Inc.                                          NaN       0.0000              NaT             NaT   2022-04-11
  DISH                       Dish Network                                          NaN       0.0000              NaT             NaT   2023-06-20
    DJ                          Dow Jones                                          NaN       0.0000              NaT             NaT   2007-12-13
   DNB                   Dun & Bradstreet                                          NaN       0.0000              NaT             NaT   2017-04-05
   DNR                  Denbury Resources                                          NaN       0.0000              NaT             NaT   2015-03-23
    DO          Diamond Offshore Drilling                                          NaN       0.0000              NaT             NaT   2016-09-30
   DOW               Dow Chemical Company                                     Dow Inc.       0.5000       2019-03-20      2026-09-03   2017-09-01
   DPS            Dr Pepper Snapple Group                                          NaN       0.0000              NaT             NaT   2018-07-02
   DRE                        Duke Realty                                          NaN       0.0000              NaT             NaT   2022-10-03
   DTV                            DirecTV                                          NaN       0.0000              NaT             NaT   2015-07-29
    DV                              DeVry                  DoubleVerify Holdings, Inc.       0.0000       2021-04-21      2026-09-03   2012-10-01
  DWDP                             DuPont                                          NaN       0.0000              NaT             NaT   2019-06-03
   DXC                     DXC Technology                       DXC Technology Company       1.0000       2010-01-04      2026-09-03   2023-10-03
   DYN                             Dynegy                      Dyne Therapeutics, Inc.       0.0000       2020-09-17      2026-09-03   2009-12-18
    EA                    Electronic Arts                          Electronic Arts Inc       1.0000       2026-07-17      2026-08-10   2026-08-05
    EK                      Eastman Kodak                                          NaN       0.0000              NaT             NaT   2010-12-17
   EMC                    EMC Corporation Global X Emerging Markets Great Consumer ETF       0.0000       2023-05-15      2026-09-03   2016-09-08
   EMN               Eastman Chemical Co.                     Eastman Chemical Company       1.0000       2010-01-04      2026-09-03   2025-11-04
  ENDP                 Endo International                                          NaN       0.0000              NaT             NaT   2017-03-02
  ENPH                     Enphase Energy                         Enphase Energy, Inc.       1.0000       2012-03-30      2026-09-03   2025-09-22
    EP                El Paso Corporation                 Empire Petroleum Corporation       0.0000       2010-01-04      2026-09-03   2012-05-17
  EPAM                       EPAM Systems                           EPAM Systems, Inc.       1.0000       2012-02-08      2026-09-03   2026-06-02
   EQT                    EQT Corporation                              EQT Corporation       1.0000       2010-01-04      2026-09-03   2018-11-13
  ESRX                    Express Scripts              Express Scripts Holding Company       0.6667       2010-01-04      2018-12-21   2018-12-24
   ESV                              Ensco                                          NaN       0.0000              NaT             NaT   2016-03-30
  ETFC                            E-Trade                                          NaN       0.0000              NaT             NaT   2020-10-07
  ETSY                               Etsy                                   Etsy, Inc.       1.0000       2015-04-16      2026-09-03   2024-09-23
  EVHC                Envision Healthcare              Envision Healthcare Corporation       1.0000       2013-08-14      2018-10-10   2018-10-11
  FBHS     Fortune Brands Home & Security                                          NaN       0.0000              NaT             NaT   2022-12-19
   FDC                         First Data                                          NaN       0.0000              NaT             NaT   2007-09-26
   FDO                      Family Dollar                                          NaN       0.0000              NaT             NaT   2015-07-08
   FHN                      First Horizon                    First Horizon Corporation       1.0000       2010-01-04      2026-09-03   2013-06-21
   FII                Federated Investors                                          NaN       0.0000              NaT             NaT   2013-01-02
    FL                        Foot Locker                                          NaN       0.0000              NaT             NaT   2019-08-09
  FLIR                       FLIR Systems                                          NaN       0.0000              NaT             NaT   2021-05-14
   FLR                  Fluor Corporation                            Fluor Corporation       1.0000       2010-01-04      2026-09-03   2019-06-03
   FLS                          Flowserve                        Flowserve Corporation       1.0000       2010-01-04      2026-09-03   2021-03-22
   FLT              FLEETCOR Technologies                                          NaN       0.0000              NaT             NaT   2024-03-25
   FMC                    FMC Corporation                              FMC Corporation       1.0000       2010-01-04      2026-09-03   2025-03-24
   FNM                         Fannie Mae                                          NaN       0.0000              NaT             NaT   2008-09-12
  FOSL                       Fossil Group                           Fossil Group, Inc.       1.0000       2010-01-04      2026-09-03   2016-01-05
   FOX                   21st Century Fox                              Fox Corporation       0.3333       2019-03-13      2026-09-03   2019-03-19
  FOXA                   21st Century Fox                              Fox Corporation       0.3333       2019-03-12      2026-09-03   2019-03-19
   FRC                First Republic Bank                                          NaN       0.0000              NaT             NaT   2023-05-04
   FRE                        Freddie Mac                                          NaN       0.0000              NaT             NaT   2008-09-12
   FRX                Forest Laboratories                                          NaN       0.0000              NaT             NaT   2014-07-01
  FSLR                        First Solar                            First Solar, Inc.       1.0000       2010-01-04      2026-09-03   2017-03-20
   FTI                         TechnipFMC                               TechnipFMC plc       1.0000       2010-01-04      2026-09-03   2021-02-12
   FTR            Frontier Communications                                          NaN       0.0000              NaT             NaT   2017-03-20
   GAS                          Nicor Gas                                          NaN       0.0000              NaT             NaT   2011-12-12
  GENZ                            Genzyme            VanEck Digital Native Economy ETF       0.0000       2010-01-04      2026-09-03   2011-04-01
   GGP                                GGP                                     GGP Inc.       1.0000              NaT             NaT   2018-08-28
   GHC                    Graham Holdings                      Graham Holdings Company       1.0000       2010-01-04      2026-09-03   2014-09-20
   GLK               Great Lakes Chemical                                          NaN       0.0000              NaT             NaT   2005-07-01
  GMCR              Keurig Green Mountain                                          NaN       0.0000              NaT             NaT   2016-03-07
   GME                           GameStop                               GameStop Corp.       1.0000       2010-01-04      2026-09-03   2016-04-25
   GNW                 Genworth Financial                     Genworth Financial, Inc.       1.0000       2010-01-04      2026-09-03   2015-11-18
   GPS                                Gap                                          NaN       0.0000              NaT             NaT   2022-02-03
    GR               Goodrich Corporation                                          NaN       0.0000              NaT             NaT   2012-07-31
   GRA                           WR Grace                                          NaN       0.0000              NaT             NaT   2000-12-05
   GRN                         General Re                    iPath Series B Carbon ETN       0.0000       2019-09-18      2026-09-03   1998-12-11
    GT The Goodyear Tire & Rubber Company           The Goodyear Tire & Rubber Company       1.0000       2010-01-04      2026-09-03   2019-02-27
   HAR               Harman International                                          NaN       0.0000              NaT             NaT   2017-03-16
   HBI                        Hanesbrands                                          NaN       0.0000              NaT             NaT   2021-12-20
  HCBK                Hudson City Bancorp                                          NaN       0.0000              NaT             NaT   2015-11-02
   HES                   Hess Corporation                                          NaN       0.0000              NaT             NaT   2025-07-23
   HFC                      HollyFrontier                                          NaN       0.0000              NaT             NaT   2021-06-04
   HNG                Houston Natural Gas                                          NaN       0.0000              NaT             NaT   1976-07-01
   HNZ                              Heinz                                          NaN       0.0000              NaT             NaT   2013-06-06
   HOG                    Harley-Davidson                        Harley-Davidson, Inc.       1.0000       2010-01-04      2026-09-03   2020-06-22
  HOLX                            Hologic                                          NaN       0.0000              NaT             NaT   2026-04-09
   HOT                           Starwood                                          NaN       0.0000       2015-01-02      2017-03-20   2016-09-22
    HP                  Helmerich & Payne                      Helmerich & Payne, Inc.       1.0000       2010-01-04      2026-09-03   2020-05-22
   HPH           Harnischfeger Industries                                          NaN       0.0000              NaT             NaT   1999-06-09
   HRB                          H&R Block                              H&R Block, Inc.       1.0000       2010-01-04      2026-09-03   2020-09-21
   HSP                            Hospira                                          NaN       0.0000              NaT             NaT   2015-09-02
   IGT      International Game Technology                                          NaN       0.0000              NaT             NaT   2014-06-20
  ILMN                     Illumina, Inc.                               Illumina, Inc.       1.0000       2010-01-04      2026-09-03   2024-06-24
  INFO                         IHS Markit   Harbor PanAgora Dynamic Large Cap Core ETF       0.0000       2024-10-10      2026-09-03   2022-03-02
   IPG                  Interpublic Group                                          NaN       0.0000              NaT             NaT   2025-11-28
  IPGP                      IPG Photonics                    IPG Photonics Corporation       1.0000       2010-01-04      2026-09-03   2022-06-21
   ITT                                ITT                                     ITT Inc.       1.0000       2010-01-04      2026-09-03   2011-10-31
   JBL                      Jabil Circuit                                   Jabil Inc.       0.5000       2010-01-04      2026-09-03   2014-11-05
   JCP                           JCPenney                                          NaN       0.0000              NaT             NaT   2013-12-02
  JDSU                       JDS Uniphase                                          NaN       0.0000              NaT             NaT   2013-12-23
   JEF          Jefferies Financial Group               Jefferies Financial Group Inc.       1.0000       2010-01-04      2026-09-03   2019-09-26
  JNPR                   Juniper Networks                                          NaN       0.0000              NaT             NaT   2025-07-09
   JNS                Janus Capital Group                                          NaN       0.0000              NaT             NaT   2011-11-18
   JNY                Jones Apparel Group                                          NaN       0.0000              NaT             NaT   2009-03-03
   JOY                         Joy Global                                          NaN       0.0000              NaT             NaT   2015-10-07
   JWN                          Nordstrom                                          NaN       0.0000              NaT             NaT   2020-06-22
     K                          Kellanova                                          NaN       0.0000              NaT             NaT   2025-12-11
   KBH                            KB Home                                      KB Home       1.0000       2010-01-04      2026-09-03   2009-12-18
   KFT                        Kraft Foods                                          NaN       0.0000              NaT             NaT   2012-10-02
    KG               King Pharmaceuticals                            Kestrel Group Ltd       0.0000       2010-01-04      2026-09-03   2010-12-17
   KMX                             CarMax                                 CarMax, Inc.       1.0000       2010-01-04      2026-09-03   2025-10-31
  KRFT                        Kraft Foods                                          NaN       0.0000              NaT             NaT   2015-07-06
   KSE                            KeySpan                                          NaN       0.0000              NaT             NaT   2007-08-24
   KSS                             Kohl's                           Kohl's Corporation       1.0000       2010-01-04      2026-09-03   2020-09-21
   KSU               Kansas City Southern                                          NaN       0.0000              NaT             NaT   2021-12-14
   LDW                            Laidlaw                                          NaN       0.0000              NaT             NaT   1999-12-08
   LEG                    Leggett & Platt                          Leggett & Platt Inc       1.0000       2010-01-04      2026-08-27   2021-12-20
   LEH                    Lehman Brothers                                          NaN       0.0000              NaT             NaT   2008-09-16
  LIFE                  Life Technologies                      Ethos Technologies Inc.       0.3333       2026-01-29      2026-09-03   2014-01-24
   LKQ                    LKQ Corporation                              LKQ Corporation       1.0000       2010-01-04      2026-09-03   2025-12-22
   LLL                    L3 Technologies                                          NaN       0.0000              NaT             NaT   2019-07-01
  LLTC                  Linear Technology                                          NaN       0.0000              NaT             NaT   2017-03-13
    LM                         Legg Mason                                          NaN       0.0000              NaT             NaT   2016-12-02
   LNC       Lincoln National Corporation                 Lincoln National Corporation       1.0000       2010-01-04      2026-09-03   2023-09-18
    LO          Lorillard Tobacco Company                                          NaN       0.0000              NaT             NaT   2015-06-11
   LSI                    LSI Corporation                                          NaN       0.0000              NaT             NaT   2014-05-08
  LUMN                 Lumen Technologies                     Lumen Technologies, Inc.       1.0000       2010-01-04      2026-09-03   2023-03-20
  LVLT             Level 3 Communications                                          NaN       0.0000              NaT             NaT   2017-10-13
    LW                        Lamb Weston                   Lamb Weston Holdings, Inc.       0.6667       2016-11-10      2026-09-03   2026-03-23
   LXK                            Lexmark                                          NaN       0.0000              NaT             NaT   2012-10-01
     M                             Macy's                                 Macy's, Inc.       1.0000       2010-01-04      2026-09-03   2020-04-06
   MAC                           Macerich                         The Macerich Company       0.5000       2010-01-04      2026-09-03   2019-12-23
   MAT                             Mattel                                 Mattel, Inc.       1.0000       2010-01-04      2026-09-03   2019-06-07
   MBC                        MasterBrand                            MasterBrand, Inc.       1.0000       2022-12-09      2026-09-03   2022-12-19
   MBI                               MBIA                                    MBIA Inc.       1.0000       2010-01-04      2026-09-03   2009-12-18
   MCK                           McKesson                         McKesson Corporation       1.0000       2010-01-04      2026-09-03   1994-09-30
   MDP                      Meredith Corp                                          NaN       0.0000              NaT             NaT   2011-01-03
   MEE                      Massey Energy                                          NaN       0.0000              NaT             NaT   2011-06-01
   MFE                             McAfee                                          NaN       0.0000              NaT             NaT   2011-02-28
   MHK                  Mohawk Industries                      Mohawk Industries, Inc.       1.0000       2010-01-04      2026-09-03   2025-12-22
   MHS             Medco Health Solutions                    Morningstar US Healthcare       0.0000       2020-02-12      2026-07-17   2012-04-03
    MI                  Marshall & Ilsley                                  NFT Limited       0.0000       2015-11-25      2026-09-03   2011-07-05
   MIL                          Millipore                                          NaN       0.0000              NaT             NaT   2010-07-14
   MJN                       Mead Johnson                                          NaN       0.0000              NaT             NaT   2017-06-19
  MKTX                        MarketAxess                    MarketAxess Holdings Inc.       0.5000       2010-01-04      2026-09-03   2025-09-22
   MMI                  Motorola Mobility                     Marcus & Millichap, Inc.       0.0000       2013-10-31      2026-09-03   2012-05-21
   MNK                       Mallinckrodt                                          NaN       0.0000              NaT             NaT   2017-07-26
   MOH                  Molina Healthcare                      Molina Healthcare, Inc.       1.0000       2010-01-04      2026-09-03   2026-03-23
  MOLX                              Molex                                          NaN       0.0000              NaT             NaT   2013-12-10
   MON                           Monsanto                                          NaN       0.0000              NaT             NaT   2018-06-07
   MRO                       Marathon Oil                                          NaN       0.0000              NaT             NaT   2024-11-26
  MTCH                        Match Group                            Match Group, Inc.       1.0000       2010-01-04      2026-09-03   2026-03-23
   MUR                         Murphy Oil                       Murphy Oil Corporation       1.0000       2010-01-04      2026-09-03   2017-07-26
   MWW                  Monster Worldwide                                          NaN       0.0000              NaT             NaT   2011-12-16
  MXIM          Maxim Integrated Products                                          NaN       0.0000              NaT             NaT   2007-09-27
  NAVI                            Navient                          Navient Corporation       1.0000       2014-04-17      2026-09-03   2018-06-05
   NBL                       Noble Energy                                          NaN       0.0000              NaT             NaT   2020-10-12
   NBR                  Nabors Industries                       Nabors Industries Ltd.       1.0000       2010-01-04      2026-09-03   2015-03-23
   NCR                    NCR Corporation                                          NaN       0.0000              NaT             NaT   2007-10-01
    NE                  Noble Corporation                        Noble Corporation plc       1.0000       2021-06-09      2026-09-03   2015-07-20
   NFX               Newfield Exploration                      Corgi NFLX 2x Daily ETF       0.0000       2026-07-07      2026-09-03   2019-02-15
  NKTR                Nektar Therapeutics                          Nektar Therapeutics       1.0000       2010-01-04      2026-09-03   2019-10-03
  NLSN                   Nielsen Holdings                                          NaN       0.0000              NaT             NaT   2022-10-12
   NOV                                Nov                                     NOV Inc.       1.0000       2010-01-04      2026-09-03   2021-09-20
  NOVL                             Novell                                          NaN       0.0000              NaT             NaT   2011-04-27
   NSM             National Semiconductor            Nationstar Mortgage Holdings Inc.       0.0000       2012-03-08      2018-07-31   2011-09-23
  NVLS                   Novellus Systems                                          NaN       0.0000              NaT             NaT   2012-06-05
   NWL                      Newell Brands                           Newell Brands Inc.       1.0000       2010-01-04      2026-09-03   2023-09-18
   NYT         The New York Times Company                   The New York Times Company       1.0000       2010-01-04      2026-09-03   2010-12-17
   NYX                      NYSE Euronext                     NYIAX, Inc. Common Stock       0.0000              NaT             NaT   2013-11-13
   ODP                       Office Depot                                          NaN       0.0000              NaT             NaT   2010-12-17
   OGN                      Organon & Co.                                Organon & Co.       1.0000       2021-05-14      2026-09-03   2023-10-18
    OI                     Owens-Illinois                              O-I Glass, Inc.       0.0000       2010-01-04      2026-09-03   2000-12-05
   OMX                          OfficeMax                                          NaN       0.0000              NaT             NaT   2008-06-23
  PAYC                             Paycom                        Paycom Software, Inc.       0.5000       2014-04-15      2026-09-03   2026-03-23
  PBCT          People's United Financial                                          NaN       0.0000              NaT             NaT   2022-04-04
   PBI                       Pitney Bowes                            Pitney Bowes Inc.       1.0000       2010-01-04      2026-09-03   2017-03-01
   PCG     Pacific Gas & Electric Company                             PG&E Corporation       0.0000       2010-01-04      2026-09-03   2019-01-18
   PCL                  Plum Creek Timber             PGIM Corporate Bond 10+ Year ETF       0.0000       2025-08-05      2026-09-03   2016-02-22
   PCP    Precision Castparts Corporation                                          NaN       0.0000              NaT             NaT   2016-02-01
   PCS                           MetroPCS             PGIM Corporate Bond 0-5 Year ETF       0.0000       2025-08-01      2026-09-03   2013-04-30
  PDCO                Patterson Companies                                          NaN       0.0000              NaT             NaT   2018-03-19
  PENN                 Penn Entertainment                     PENN Entertainment, Inc.       1.0000       2010-01-04      2026-09-03   2022-09-19
  PETM                           PetSmart                                          NaN       0.0000              NaT             NaT   2015-03-12
   PGN                    Progress Energy                                          NaN       0.0000              NaT             NaT   2012-07-02
   PLL                   Pall Corporation                                          NaN       0.0000              NaT             NaT   2015-08-28
   POM                     Pepco Holdings                            Pomdoctor Limited       0.0000       2025-10-08      2026-09-03   2016-03-30
  POOL                   Pool Corporation                                          NaN       0.0000       2010-01-04      2026-09-03   2026-06-22
  PRGO                            Perrigo                                          NaN       0.0000       2010-01-04      2026-09-03   2021-09-20
   PTV                             Pactiv                                          NaN       0.0000              NaT             NaT   2010-11-17
   PVH                                PVH                                          NaN       0.0000       2010-01-04      2026-09-03   2022-09-19
   PXD          Pioneer Natural Resources                                          NaN       0.0000              NaT             NaT   2024-05-08
     Q               Qwest Communications                                          NaN       0.0000       2025-10-27      2026-09-03   2011-03-31
   QEP                      QEP Resources                                          NaN       0.0000              NaT             NaT   2015-07-01
  QRVO                              Qorvo                                          NaN       0.0000       2015-01-02      2026-09-03   2024-12-23
  QTRN            Quintiles Transnational                                          NaN       0.0000              NaT             NaT   2003-09-25
     R                       Ryder System                                          NaN       0.0000       2010-01-04      2026-09-03   2017-06-19
   RAD                           Rite Aid                                          NaN       0.0000              NaT             NaT   2000-07-27
   RAI                  Reynolds American                                          NaN       0.0000              NaT             NaT   2017-07-26
   RDC                    Rowan Companies                                          NaN       0.0000              NaT             NaT   2014-08-18
    RE                   Everest Re Group                                          NaN       0.0000              NaT             NaT   2023-07-10
   RHI                        Robert Half                                          NaN       0.0000       2010-01-04      2026-09-03   2024-06-24
   RHT                            Red Hat                                          NaN       0.0000              NaT             NaT   2019-07-15
   RIG                         Transocean                                          NaN       0.0000       2010-01-04      2026-09-03   2017-07-26
   RRC                    Range Resources                                          NaN       0.0000       2010-01-04      2026-09-03   2018-06-18
   RRD                       RR Donnelley                                          NaN       0.0000              NaT             NaT   2012-12-11
   RSH                         RadioShack                                          NaN       0.0000              NaT             NaT   2011-06-30
   RTN                   Raytheon Company                                          NaN       0.0000              NaT             NaT   2020-04-06
    RX                         IMS Health                                          NaN       0.0000              NaT             NaT   2010-02-26
     S                      Sprint Nextel                                          NaN       0.0000       2021-06-30      2026-09-03   2013-07-08
   SAI                               SAIC                                          NaN       0.0000              NaT             NaT   2013-09-20
   SBL                Symbol Technologies                                          NaN       0.0000              NaT             NaT   2007-01-10
  SBNY                     Signature Bank                                          NaN       0.0000       2024-08-15      2026-09-03   2023-03-15
   SCG                              SCANA                                          NaN       0.0000       2015-07-16      2018-12-31   2019-01-02
    SE                     Spectra Energy                                          NaN       0.0000       2017-10-20      2026-09-03   2017-02-28
  SEDG                          SolarEdge                                          NaN       0.0000       2015-03-26      2026-09-03   2023-12-18
   SEE                         Sealed Air                                          NaN       0.0000              NaT             NaT   2023-12-18
   SGP                    Schering-Plough                                          NaN       0.0000       2026-02-06      2026-09-03   2009-11-03
  SHLD                     Sears Holdings                                          NaN       0.0000       2023-09-14      2026-09-03   2012-09-05
  SIAL                      Sigma-Aldrich                                          NaN       0.0000              NaT             NaT   2015-11-19
   SIG                    Signet Jewelers                                          NaN       0.0000       2010-01-04      2026-09-03   2018-03-19
   SII                Smith International                                          NaN       0.0000       2010-02-22      2026-09-03   2010-08-26
  SIVB                SVB Financial Group                                          NaN       0.0000              NaT             NaT   2023-03-15
   SLE               Sara Lee Corporation                                          NaN       0.0000       2019-02-26      2026-09-03   2012-06-29
   SLG                    SL Green Realty                                          NaN       0.0000       2010-01-04      2026-09-03   2021-03-22
   SLM                    SLM Corporation                                          NaN       0.0000       2010-01-04      2026-09-03   2014-05-01
   SLR                          Solectron                                          NaN       0.0000              NaT             NaT   2007-10-02
   SMS             Shared Medical Systems                                          NaN       0.0000              NaT             NaT   2000-06-07
  SNDK                            SanDisk                                          NaN       0.0000       2025-02-13      2026-09-03   2016-05-13
   SNI       Scripps Networks Interactive                                          NaN       0.0000              NaT             NaT   2018-03-07
  SOLS        Solstice Advanced Materials                                          NaN       0.0000       2025-10-20      2026-09-03   2025-12-22
  SPLS                            Staples                                          NaN       0.0000       2026-01-16      2026-09-03   2017-09-18
  SRCL                         Stericycle                                          NaN       0.0000              NaT             NaT   2018-12-03
   STI                     SunTrust Banks                                          NaN       0.0000       2022-05-02      2026-09-03   2019-12-09
   STJ                    St Jude Medical                                          NaN       0.0000              NaT             NaT   2017-01-05
   STR                            Questar                                          NaN       0.0000              NaT             NaT   2010-06-30
   SUN                         SunAmerica                                          NaN       0.0000       2012-09-20      2026-09-03   1998-12-11
   SVU                          Supervalu                                          NaN       0.0000       2010-01-04      2018-10-22   2012-04-23
   SWN                Southwestern Energy                                          NaN       0.0000              NaT             NaT   2017-04-04
   SWY                            Safeway                                          NaN       0.0000              NaT             NaT   2015-01-27
     T                   AT&T Corporation                                          NaN       0.0000       2010-01-04      2026-09-03   2005-11-18
   TDC                           Teradata                                          NaN       0.0000       2010-01-04      2026-09-03   2017-06-19
    TE                        TECO Energy                                          NaN       0.0000       2020-01-10      2026-09-03   2016-07-01
   TEG              Integrys Energy Group                                          NaN       0.0000              NaT             NaT   2015-07-01
   TEL                    TE Connectivity                                          NaN       0.0000       2010-01-04      2026-09-03   2009-06-25
   TER                           Teradyne                                          NaN       0.0000       2010-01-04      2026-09-03   2013-12-23
   TFX                           Teleflex                                          NaN       0.0000       2010-01-04      2026-09-03   2025-03-24
  TGNA                              Tegna                                          NaN       0.0000              NaT             NaT   2017-06-02
   THC                   Tenet Healthcare                                          NaN       0.0000       2010-01-04      2026-09-03   2016-04-18
   TIE                    Titanium Metals                                          NaN       0.0000              NaT             NaT   2012-12-21
   TIF                       Tiffany & Co                                          NaN       0.0000              NaT             NaT   2021-01-07
  TLAB                            Tellabs                                          NaN       0.0000              NaT             NaT   2011-12-20
   TMC                       Times Mirror                                          NaN       0.0000       2021-09-10      2026-09-03   2000-06-12
   TRB                      Tribune Media                                          NaN       0.0000              NaT             NaT   2007-12-20
  TRIP                        TripAdvisor                                          NaN       0.0000       2011-12-07      2026-09-03   2019-12-23
   TSG                  Sabre Corporation                                          NaN       0.0000              NaT             NaT   2007-03-30
   TSS                               TSYS                                          NaN       0.0000              NaT             NaT   2019-09-23
   TWC                  Time Warner Cable                                          NaN       0.0000              NaT             NaT   2016-05-18
  TWTR                            Twitter                                          NaN       0.0000              NaT             NaT   2022-11-01
   TWX                        Time Warner                                          NaN       0.0000       2010-01-04      2018-06-15   2018-06-20
   TYC                 Tyco International                                          NaN       0.0000              NaT             NaT   2016-09-06
    UA             Under Armour (Class C)                                          NaN       0.0000       2016-03-23      2026-09-03   2022-06-21
   UAA             Under Armour (Class A)                                          NaN       0.0000       2010-01-04      2026-09-03   2022-06-21
   UNM                               Unum                                          NaN       0.0000       2010-01-04      2026-09-03   2021-09-20
  URBN                   Urban Outfitters                                          NaN       0.0000       2010-01-04      2026-09-03   2017-03-20
   USL                             USLife                                          NaN       0.0000       2010-01-04      2026-09-03   1997-06-17
   VAR             Varian Medical Systems                                          NaN       0.0000              NaT             NaT   2021-04-20
   VFC                     VF Corporation                                          NaN       0.0000       2010-01-04      2026-09-03   2024-04-03
  VIAB                             Viacom                                          NaN       0.0000              NaT             NaT   2019-12-05
   VNO               Vornado Realty Trust                                          NaN       0.0000       2010-01-04      2026-09-03   2023-01-05
   VNT                            Vontier                                          NaN       0.0000       2020-09-24      2026-09-03   2021-03-22
    WB                      Wachovia Bank                                          NaN       0.0000       2014-04-17      2026-09-03   2008-12-31
   WBA           Walgreens Boots Alliance                                          NaN       0.0000              NaT             NaT   2025-08-28
   WCG                           WellCare                                          NaN       0.0000              NaT             NaT   2020-01-28
   WFM                 Whole Foods Market                                          NaN       0.0000              NaT             NaT   2017-08-29
   WFR          MEMC Electronic Materials                                          NaN       0.0000              NaT             NaT   2011-12-16
   WHR              Whirlpool Corporation                                          NaN       0.0000       2010-01-04      2026-09-03   2024-03-18
   WIN          Windstream Communications                                          NaN       0.0000              NaT             NaT   2015-04-07
  WLTW               Willis Towers Watson                                          NaN       0.0000              NaT             NaT   2022-01-10
   WPX                         WPX Energy                                          NaN       0.0000              NaT             NaT   2014-03-21
    WU                      Western Union                                          NaN       0.0000       2010-01-04      2026-09-03   2021-12-20
   WYN                  Wyndham Worldwide                                          NaN       0.0000              NaT             NaT   2018-05-31
     X                United States Steel                                          NaN       0.0000              NaT             NaT   2014-07-02
   XEC                     Cimarex Energy                                          NaN       0.0000              NaT             NaT   2020-03-02
    XL                           XL Group                                          NaN       0.0000              NaT             NaT   2018-09-14
  XLNX                             Xilinx                                          NaN       0.0000              NaT             NaT   2022-02-15
  XRAY                    Dentsply Sirona                                          NaN       0.0000       2010-01-04      2026-09-03   2024-04-03
   XRX                              Xerox                                          NaN       0.0000       2010-01-04      2026-09-03   2021-03-22
   XTO                         XTO Energy                                          NaN       0.0000              NaT             NaT   2010-06-28
  YHOO                             Yahoo!                                          NaN       0.0000              NaT             NaT   2017-06-19
  ZION               Zions Bancorporation                                          NaN       0.0000       2010-01-04      2026-09-03   2024-03-18

rows compared: 373
name matches the current holder: 93
could not verify, no name today: 244
symbol reused: 36
  of which with a visible price break: 4
  of which no price break visible: 32
  ADCT (ADC Telecommunications -> ADC Therapeutics SA), AN (Amoco -> AutoNation, Inc.), APC (Anadarko Petroleum -> ARKO Petroleum Corp.), ATI (Allegheny Technologies -> ATI Inc.), AV (Avaya -> Corgi Aerospace & Commercial Aviation ETF), BEAM (Suntory Global Spirits -> Beam Therapeutics Inc.), CAM (Cameron International -> AB California Intermediate Municipal ETF), CCE (Coca-Cola Enterprises -> Coca-Cola European Partners plc), CLF (Cliffs Natural Resources -> Cleveland-Cliffs Inc.), CNX (Consol Energy -> CNX Resources Corporation), CPWR (Compuware -> Ocean Thermal Energy Corporation), CSC (Computer Sciences Corporation -> CSC Collective Holdings Ltd), CSRA (CSRA -> Cohen & Steers Real Assets Active ETF), DD (DuPont -> DuPont de Nemours, Inc.), DV (DeVry -> DoubleVerify Holdings, Inc.), DYN (Dynegy -> Dyne Therapeutics, Inc.), EMC (EMC Corporation -> Global X Emerging Markets Great Consumer ETF), EP (El Paso Corporation -> Empire Petroleum Corporation), FOX (21st Century Fox -> Fox Corporation), FOXA (21st Century Fox -> Fox Corporation), GENZ (Genzyme -> VanEck Digital Native Economy ETF), GRN (General Re -> iPath Series B Carbon ETN), INFO (IHS Markit -> Harbor PanAgora Dynamic Large Cap Core ETF), KG (King Pharmaceuticals -> Kestrel Group Ltd), LIFE (Life Technologies -> Ethos Technologies Inc.), MHS (Medco Health Solutions -> Morningstar US Healthcare), MI (Marshall & Ilsley -> NFT Limited), MMI (Motorola Mobility -> Marcus & Millichap, Inc.), NFX (Newfield Exploration -> Corgi NFLX 2x Daily ETF), NSM (National Semiconductor -> Nationstar Mortgage Holdings Inc.), NYX (NYSE Euronext -> NYIAX, Inc. Common Stock), OI (Owens-Illinois -> O-I Glass, Inc.), PCG (Pacific Gas & Electric Company -> PG&E Corporation), PCL (Plum Creek Timber -> PGIM Corporate Bond 10+ Year ETF), PCS (MetroPCS -> PGIM Corporate Bond 0-5 Year ETF), POM (Pepco Holdings -> Pomdoctor Limited)
dropped by the build: ['ADCT', 'AN', 'APC', 'ATI', 'AV', 'BEAM', 'CAM', 'CCE', 'CLF', 'CNX', 'CPWR', 'CSC', 'CSRA', 'DD', 'DV', 'DYN', 'EMC', 'EP', 'FOX', 'FOXA', 'GENZ', 'GRN', 'INFO', 'KG', 'LIFE', 'MHS', 'MI', 'MMI', 'NFX', 'NSM', 'NYX', 'OI', 'PCG', 'PCL', 'PCS', 'POM']
truncated to the current company: {}
gaps above 60 business days: []
the four known cases caught: ['CPWR', 'EP', 'MI', 'POM']
missing from the check: []
additional tickers caught: ['ADCT', 'AN', 'APC', 'ATI', 'AV', 'BEAM', 'CAM', 'CCE', 'CLF', 'CNX', 'CSC', 'CSRA', 'DD', 'DV', 'DYN', 'EMC', 'FOX', 'FOXA', 'GENZ', 'GRN', 'INFO', 'KG', 'LIFE', 'MHS', 'MMI', 'NFX', 'NSM', 'NYX', 'OI', 'PCG', 'PCL', 'PCS']
```

Reading of the summary below the table:

- 373 removed tickers compared; 93 still match the holder name today.
- 244 cannot be verified: the symbol has no listing today, and a
  missing name is not evidence of reuse, so those rows are kept and
  recorded rather than dropped.
- 36 symbols were reused. Four show the splice in the prices (the
  F2.6 level break): CPWR, EP, MI and POM. The other 32 have a name
  mismatch and clean prices, and the vendor has hidden the splice by
  keeping only one company's history, so the member's own prices are
  absent entirely. Both groups are excluded.
- No ticker needed truncation: none of the reused symbols has two live
  price segments separated by more than 60 business days, and none has
  a gap at all, so the spec's fallback (drop the ticker) applies.
- The 32 additional names are listed above with the removed security
  and the current holder. Nine of them are plausibly real renames of
  the same issuer (ATI, CCE, CLF, CNX, DD, FOX, FOXA, OI, PCG) and are
  excluded anyway, because a rename and a hidden reuse are
  indistinguishable from names and prices alone. Keeping a fabricated
  history is worse than dropping a legitimate one. Both sets are
  recorded in docs/hygiene_ledger.md and the security-master fix is in
  docs/open_items.md.

## C3 F2.3 diagnostic (2026-09-10)

Trailing volatility beating EWMA and GARCH on a majority of names
contradicts the daily-vol literature, so the fail was treated as a
hypothesis rather than a result. Output of `efb.vol.diagnose` on the
flagged-row-excluded returns, window 2024-09-03 to 2026-09-03.

```
=== C3 F2.3 diagnostic ===
out-of-sample window: 2024-09-03 to 2026-09-03
(a) target and horizons
  QLIKE(sigma2, r) = ln(sigma2) + r^2 / sigma2, so the target is the
  NEXT-DAY squared return, one step ahead, for every estimator below.
      method  horizon  names  mean_qlike
    ewma_094        1    483      -6.701
    ewma_097        1    483      -6.744
       garch        1     45      -6.716
 realized_21        1    615      -6.479
 realized_63        1    611      -6.574
trailing_252        1    608      -6.620
  trailing_21 and trailing_63 are trailing variances: one step ahead.
  All methods are one-step, so F2.3 is horizon aligned already.
(b) arch fit
  returns are scaled by 100 before arch_model and the variance is
  divided by 1e4 on the way out, for numerical stability.
  attempted: 60, fitted: 47, failed: 13
  did not converge: ['ABK', 'ABMD', 'ABS', 'ACAS', 'ACE', 'ADS', 'AGN', 'AKS', 'ALTR', 'ALXN', 'AMTM', 'ANR', 'ANSS']
(c) win rate by calendar year
  EWMA(0.94) vs trailing 252d, fraction of name-days with lower QLIKE
    2024: 0.513
    2025: 0.546
    2026: 0.472
  pooled: 0.516   excluding 2020: 0.516
```

Aligned evaluation, same window, flagged rows excluded, forecast and
target matched on both sides:

```
 horizon      method  n_names  win_share  mean_qlike  baseline_qlike
       1    ewma_094      483     0.3540     -6.7009         -6.7487
       1    ewma_097      483     0.5197     -6.7436         -6.7487
       1       garch       45     0.4667     -6.7166         -6.7103
       1 trailing_63      608     0.3668     -6.5820         -6.6199
      21    ewma_094      483     0.1988     -3.5884         -3.6759
      21    ewma_097      483     0.3437     -3.6488         -3.6759
      21       garch       45     0.5556     -3.6459         -3.6430
      21 trailing_63      608     0.3076     -3.5125         -3.5471

garch fitted: 47
```

## C4 momentum seed book sanity check (2026-09-10)

The long/short seed book is built from a momentum signal, so its TS-v1
MOM loading has to be positive with a t statistic beyond two. If it were
not, the idio share reported for the book would be suspect. Output of
efb.portfolios.mom_sanity on the flagged-row-excluded returns.

```
=== C4 momentum long/short seed book, portfolio return regressed on FF5 + MOM ===
Newey-West standard errors at lag 5, weights 1 - j/6. 4067 days, gross 1.0,
dollar neutral, 192 names in the last month.

        loading   nw_se  ols_se   t_stat  n_obs  r_squared
alpha   -0.0000  0.0000  0.0000  -1.1188   4067     0.5606
mkt_rf  -0.0274  0.0072  0.0043  -3.8305   4067     0.5606
smb     -0.0566  0.0174  0.0079  -3.2502   4067     0.5606
hml     -0.0140  0.0162  0.0076  -0.8614   4067     0.5606
rmw     -0.0459  0.0154  0.0099  -2.9835   4067     0.5606
cma     -0.0224  0.0245  0.0127  -0.9126   4067     0.5606
mom      0.2947  0.0102  0.0048  28.9983   4067     0.5606

MOM loading 0.2947 with t 29.00: positive, and the t statistic is far beyond
two, so the required sanity check passes.

the factor share of this book is not one number. Three measurements:
  regression betas, all six factors in the covariance: 0.8951
  regression betas, MOM removed from the covariance:   0.1381
  name-level TS betas, last-month weights (snapshot):  0.0939
  share of daily variance explained by the regression: 0.5606

so the book is mostly a momentum factor position, not a collection of
independent name bets: the 0.0939 in the snapshot comes from static
name-level betas and one month of weights, and it is an artifact of
treating the residual covariance as diagonal.
```
