# Povzetek končnega fizičnega preizkusa

Preizkus `STM32N6-HAZARD6-FINAL-003`, poskus `FE4-A01`, je bil izveden z zvočnikom pri 100-odstotni sistemski glasnosti na razdalji 30 cm od mikrofona razvojne plošče. Zamrznjeni nabor je vseboval 60 slušno pregledanih posnetkov iz virov, ločenih od učne množice, po 10 za vsak sistemski razred.

Sistem je pravilni razred vsaj enkrat potrdil v 57 od 60 poskusov, kar pomeni 95,0 %. Wilsonov 95-odstotni interval zaupanja znaša 86,3–98,3 %.

## Rezultat po razredih

| Razred | Uspešni poskusi | Delež |
|---|---:|---:|
| Pasji lajež | 10/10 | 100,0 % |
| Razbitje stekla | 10/10 | 100,0 % |
| Strel | 10/10 | 100,0 % |
| Drugo | 9/10 | 90,0 % |
| Sirena | 9/10 | 90,0 % |
| Govor | 9/10 | 90,0 % |

Štirje nevarnostni razredi skupaj so bili potrjeni v 39/40 poskusih.

## Neuspešni poskusi

| Poskus | Pričakovani razred | Kategorija vira | Prevladujoči izhod | Najvišja verjetnost pričakovanega razreda |
|---|---|---|---|---:|
| FE4-010 | Govor | Govor | Drugo | 35,7 % |
| FE4-032 | Drugo | Pok | Razbitje stekla | 36,0 % |
| FE4-058 | Sirena | Sirena | Drugo | 59,5 % |

Primarna uspešnost šteje poskus kot uspešen, če je sistem med predvajanjem vsaj enkrat pravilno potrdil pričakovani razred. Strožji pogled na prevladujoči potrjeni izhod se ujema v 54/60 poskusih oziroma 90,0 %. Zato se matrika prevladujočih izhodov razlikuje od deleža uspešnih poskusov.

## Lažni nevarnostni alarmi

V časovnem območju predvajanja je nevarnostni izhod nastopil v 6/10 poskusih razreda Drugo. Pri govoru ga ni bilo v nobenem od 10 poskusov. Štirje od 20 varovalnih poskusov so vsebovali več kot en lažni nevarnostni okvir. En dodaten nevarnostni izhod v celotnem zajemu je nastopil pred začetkom predvajanja in je zato obravnavan ločeno kot preneseno stanje prejšnjega poskusa.
Uspešnost 9/10 za razred Drugo in šest poskusov z lažnim alarmom se ne izključujeta: v petih poskusih je sistem najprej ali pozneje pravilno potrdil Drugo, v delu istega predvajanja pa je kratkotrajno potrdil tudi nevarnostni razred.

| Kategorija razreda Drugo | Lažni nevarnostni okvirji | Izhodi |
|---|---:|---|
| Alarm | 2 | Razbitje stekla: 2 |
| Aplavz | 4 | Strel: 4 |
| Zvonec | 0 | brez |
| Ploskanje | 1 | Razbitje stekla: 1 |
| Računalniška tipkovnica | 1 | Razbitje stekla: 1 |
| Pok | 17 | Razbitje stekla: 17 |
| Posoda in kuhinjski pripomočki | 0 | brez |
| Ognjemet | 0 | brez |
| Trkanje | 2 | Razbitje stekla: 2 |
| Veter | 0 | brez |

## Časovne meritve, ki jih poroča strojna programska oprema

Predobdelava je trajala 1,43 ms, izvajanje omrežja na nevronskem pospeševalniku 9,38 ms, poročana obremenitev procesorskega jedra pa je bila 10,81 %. Te vrednosti izvirajo iz telemetrije strojne programske opreme in niso neodvisne osciloskopske meritve.

Mediana časa od začetka predvajanja do prve pravilne potrditve je bila pasji lajež 1,07 s, razbitje stekla 1,00 s, strel 1,14 s, drugo 2,50 s, sirena 1,66 s, govor 1,50 s. Ta čas poleg računanja vključuje tudi položaj dogodka v posnetku, zbiranje vhodnega zvočnega okna in odločitveni filter, zato ga ne smemo enačiti z 9,38 ms časa izvajanja omrežja.

## Omejitev interpretacije

Rezultat predstavlja preskus celotnega sistema v določeni postavitvi zvočnik–vgrajeni mikrofon. Zaradi 10 poskusov na razred ne dokazuje splošne pravilnosti na vseh resničnih zvokih. Posebej očitna omejitev ostaja zavračanje kratkih običajnih zvokov v razred Drugo.
