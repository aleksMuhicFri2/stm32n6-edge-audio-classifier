# Načrt diplomske naloge

Cilj je približno **48--54 strani skupaj**, vključno z naslovnimi stranmi, kazali, literaturo in kratko prilogo. Glavno besedilo naj obsega približno 36--40 strani. Število strani je orientacijsko; pomembnejša sta jasna argumentacija in sledljivost rezultatov.

| Del | Cilj strani | Vsebina |
| --- | ---: | --- |
| Uvodne strani | 8--10 | naslovnica, opis teme, zahvala, kazalo, povzetek in abstract |
| 1 Uvod | 3 | problem, motivacija, cilji, raziskovalna vprašanja in prispevki |
| 2 Teoretične osnove in sorodna dela | 7 | digitalni zvok, STFT, melov spektrogram, YAMNet, kvantizacija, robna UI in podobni sistemi |
| 3 Zasnova sistema | 5--6 | zahteve, arhitektura, strojna in programska oprema, razredi in pravila odločanja |
| 4 Implementacija | 8--9 | mikrofon, večnamenski digitalni filter, neposredni dostop do pomnilnika, predobdelava, model, Neural-ART, pomnilnik, zagon, filtriranje in zaslon |
| 5 Metodologija vrednotenja | 4--5 | pilotski preskusi, zamrznjeni končni protokol, 60 preskusov, metrike in omejitve meritev |
| 6 Rezultati | 6--7 | pravilnost, lažni alarmi, čas izvajanja, pomnilnik in analiza razredov |
| 7 Razprava in sklep | 3--4 | odgovori na raziskovalna vprašanja, omejitve, uporabnost in nadaljnje delo |
| Literatura | 2--3 | samo dejansko uporabljeni in preverjeni viri |
| Priloga | 1--2 | identiteta izdaje, poti do dokazov in navodila za ponovitev analiz |

## Predlagana raziskovalna vprašanja

1. Ali je mogoče kvantizirani model za zaznavanje zvočnih dogodkov izvajati v realnem času na mikrokrmilniku STM32N6 z uporabo pospeševalnika Neural-ART?
2. Kakšno stopnjo potrjenih pravilnih zaznav in lažnih nevarnostnih alarmov doseže končni sistem pri nadzorovanem predvajanju zvokov na fizični napravi?
3. Kako se posamezni zvočni razredi razlikujejo po zanesljivosti ter kateri dejavniki omejujejo delovanje sistema?

Raziskovalna vprašanja so primernejša od agresivnih hipotez, ker naloga predstavlja empirično inženirsko študijo in ne primerjave z Raspberry Pi sistemom, ki ni bil izveden v primerljivi obliki.

## Razpored obstoječih dokazov

| Tema | Glavni dokaz v repozitoriju |
| --- | --- |
| Zamrznjena končna evalvacija | `experiments/results/hazard6_final_evaluation_v4_independent/` |
| Rezultati po razredih | `experiments/results/hazard6_final_evaluation_v4_independent/class_summary.csv` |
| Matrika zamenjav | `experiments/results/hazard6_final_evaluation_v4_independent/dominant_output_confusion_matrix.png` |
| Časi predobdelave in sklepanja | `experiments/results/hazard6_final_evaluation_v4_independent/firmware_timing_summary.csv` |
| Pomnilniški odtis | `experiments/results/deployment_footprint/` |
| Podatki o modelu in Neural-ART | `experiments/results/deployment_footprint/deployment_metrics.csv` |
| Protokol 60 preskusov | `experiments/final_evaluation_v4_independent/PROTOCOL.md` |
| Fotografije prototipa | `Doc/thesis_photos/` |
| Razvojni dnevnik in tehnične odločitve | `THESIS_SETUP.md` in zgodovina Git |

## Pisanje v največ 20 urah

| Čas | Naloga |
| ---: | --- |
| 1 h | potrditev naslova/opisa z mentorjem in izbira 12--18 ključnih virov |
| 4 h | teoretične osnove in sorodna dela |
| 3 h | zasnova sistema in strojna oprema |
| 4 h | implementacija, napisana ob odprti kodi in `THESIS_SETUP.md` |
| 3 h | metodologija končnega preskusa |
| 2 h | opis rezultatov ob že pripravljenih grafih in tabelah |
| 1 h | uvod, ko je jedro že napisano |
| 1 h | razprava, sklep in omejitve |
| 1 h | povzetek, jezikovni pregled, reference in končno prevajanje PDF/A |

Pri pisanju naj avtor najprej pripravi grobe odstavke s svojimi besedami. Pomoč se nato uporabi za razlago nejasnih tehničnih delov, preverjanje logike, oblikovanje tabel in jezikovni pregled. Poseben dnevnik uporabe generativne UI ni predviden; v nalogi pa mora biti kratko in resnično pojasnjeno, kako je bila uporabljena, skladno z navodili FRI.
