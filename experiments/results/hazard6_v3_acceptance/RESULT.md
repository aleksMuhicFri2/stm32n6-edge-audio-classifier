# Rezultat nadzorovanega sprejemnega preskusa V3

Preskus `STM32N6-HAZARD6-ACCEPTANCE-001` je bil izveden kot enkraten poskus `AT-A01` na
zamrznjeni programski in modelski različici. Vseh 21 načrtovanih poskusov je
bilo zajetih brez ponavljanja neuspešnih napovedi.

## Glavni rezultati

- skupaj uspešnih: 18/21 (85,7 odstotka);
- nominalna raven: 8/9 (88,9 odstotka);
- šest ciljnih zvokov pri nominalni ravni: 5/6;
- ciljni zvoki pri -6 decibelih: 6/6;
- ciljni zvoki pri -12 decibelih: 4/6;
- varni zvoki brez nevarnostnega alarma: 3/3;
- povprečni čas predobdelave: 0,71 milisekunde;
- povprečni čas sklepanja: 4,63 milisekunde.

Pasji lajež, strel in sirena so uspeli pri vseh treh ravneh. Razbitje stekla in
govor sta uspela pri 0 in -6 decibelih, pri -12 decibelih pa je bil vhod že pod
pragom aktivnosti. Nevihta je uspela pri -6 in -12 decibelih, ne pa pri
nominalni ravni. Ker je bila vsaka kombinacija posnetka in ravni predvajana le
enkrat, iz tega ne sklepamo, da utišanje na splošno izboljša zaznavo nevihte.
Razlika je lahko posledica akustične variabilnosti in drugačne poravnave
dogodka z 960-milisekundskimi obdelovalnimi bloki.

## Neuspešni poskusi

- `AT-004`: Razbitje stekla, -12 decibelov; noben blok ni presegel vhodnega praga aktivnosti, zato modelskega izhoda odločitveni filter ni smel potrditi.
- `AT-012`: Nevihta, 0 decibelov; nevihta je bila med aktivnimi bloki večkrat najvišje ocenjena, vendar ni izpolnila zahteve dveh zaporednih dokaznih blokov z nevihto na prvem mestu ob potrditvi.
- `AT-021`: Govor, -12 decibelov; noben blok ni presegel vhodnega praga aktivnosti, zato modelskega izhoda odločitveni filter ni smel potrditi.

## Celovitost časovnih meritev

Od 271 odločilnih zapisov jih je
269 vsebovalo tudi popoln časovni zapis
(99,3 odstotka). Povprečja časa so
izračunana samo iz popolnih zapisov; manjkajoče vrednosti niso obravnavane kot
ničle.

## Omejitev razlage

Vsi izvorni zvoki so bili predhodno poslušani in odobreni, nekateri pa so bili
uporabljeni tudi med razvojem, kalibracijo ali funkcijskim preizkusom. Rezultat
zato dokazuje ponovljivo delovanje končne naprave na jasnih kanoničnih primerih
in robustnost istega vira na treh ravneh. Ne predstavlja neodvisne ocene
posploševanja na nove posnetke ali resnično okolje.
