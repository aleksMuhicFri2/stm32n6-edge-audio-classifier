# Nadzorovani sprejemni preskus V3

Oznaka preskusa: `STM32N6-HAZARD6-ACCEPTANCE-001`  
Oznaka poskusa: `AT-A01`

## Namen

Preskus preverja celotno pot od zvočnika in vgrajenega mikrofona do prikaza ter
serijskega zapisa odločitve na zamrznjeni različici YAMNet-1024 V3. Vsak od
šestih ročno odobrenih modelskih zvokov se uporabi pri 0, -6 in -12 decibelih.
Trije odobreni varni zvoki se uporabijo pri nominalni ravni, skupaj torej v
21 poskusih. S tem merimo funkcijsko pravilnost, občutljivost zaznave
na raven vhodnega zvoka in lažne nevarnostne alarme pri varnih zvokih.

To ni nov neodvisen preskus posploševanja. Posnetki so bili predhodno poslušani,
nekateri pa uporabljeni med razvojem, kalibracijo ali funkcijskim preizkusom.
Rezultati so zato dokaz sprejemljivosti končne naprave na jasnih kanoničnih
primerih in ne ocena pravilnosti na nevidenih posnetkih.

## Semantični nadzor

- Vsak izvorni posnetek je uporabnik že poslušal in odobril.
- Posnetek razbitja stekla je označen kot čisto in celovito razbitje.
- Posnetki, ki vsebujejo le rokovanje s steklom, trk ali cingljanje, so izključeni.
- Posnetek strela je jasen posamezen strel, v dražljaju ponovljen štirikrat.
- Posnetek nevihte nima prej zavrnjenega visokofrekvenčnega ozadja.
- Dež, veter in trkanje po vratih so varni negativni primeri.

## Zamrznjeni pogoji

- glasnost sistema Windows: 70 odstotkov;
- razdalja med zvočnikom in vgrajenim mikrofonom: 30 centimetrov;
- položaj plošče in zvočnika se med preskusom ne spreminja;
- prostor naj bo čim bolj tih;
- model: `YAMNet-1024 Hazard-5 + Speech V3 int8`;
- programska različica na plošči: `9c7c7b7`;
- vrstni red je določen s semenom 811;
- posnetki in manifest so zaščiteni z 256-bitnimi kriptografskimi kontrolnimi vsotami.

## Merilo uspeha

Pri šestih modelskih razredih je poskus uspešen, če se pričakovani razred med
predvajanjem potrdi vsaj v enem časovnem bloku. Pri dežju, vetru in trkanju je
poskus uspešen, če se ne potrdi noben nevarnostni razred. Odločitev `neznano`,
`čakanje` ali `govor` je pri varnem negativnem primeru dovoljena.

Primarni rezultat je delež uspešnih nominalnih poskusov pri 0 decibelih,
vključno z odsotnostjo nevarnostnega alarma pri treh varnih zvokih. Rezultata
šestih modelskih razredov pri -6 in -12 decibelih sta sekundarni meritvi
robustnosti. Varnih zvokov dodatno ne utišamo, saj bi s tem ustvarili trivialne
negativne primere. Ker je za vsako kombinacijo izvora in ravni le en poskus,
rezultate prikazujemo opisno in brez trditve o populacijski pravilnosti.

## Izvedba

1. Ploščo pustimo v načinu zagona uporabniške aplikacije in pritisnemo gumb NRST.
2. Nastavimo glasnost na 70 odstotkov in razdaljo na 30 centimetrov.
3. Zaženemo avtomatizirano predvajanje in zajem po zamrznjenem seznamu.
4. Med preskusom ne spreminjamo nastavitev in ne ponavljamo neuspešne napovedi.
5. Če pride do zunanje motnje, jo zapišemo; zajetih podatkov ne brišemo.
6. Po zadnjem poskusu zaženemo `ml/analyze_v3_acceptance_test.py`.
