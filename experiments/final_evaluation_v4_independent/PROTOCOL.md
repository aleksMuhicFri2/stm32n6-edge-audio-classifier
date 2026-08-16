# Neodvisni končni fizični preizkus šestih razredov

Oznaka preizkusa: `STM32N6-HAZARD6-FINAL-003`  
Oznaka poskusa: `FE4-A01`  
Kontrolna vsota manifesta: `0355fca0f9a3d26be1e41b4fd9896f7fb7c9f567557a7dde23826dbb36c1342b`

Končni preizkus vsebuje 60 zvočnih dražljajev: po deset primerov pasjega
laježa, razbitja stekla, strela oziroma streljanja, drugih zvokov, sirene in
govora. Nevihta ni samostojen sistemski razred; njena modelska verjetnost se
v vgrajeni programski opremi prišteje razredu drugo.

Pred zamrznitvijo je bil opravljen slepi slušni pregled. Sprejeti so bili samo
posnetki z običajnim in jasno prepoznavnim dogodkom, popolno mejo dogodka,
normalno slišnostjo ter brez označenega zvočnega artefakta. Preverjene so bile
tudi izvorne identitete med zbirkami, zato isti izvorni posnetek ne sme biti
hkrati v učnih podatkih in končnem preizkusu. Izbira ne uporablja napovedi
modela ali razvojne plošče.

Za razred drugo je izbran po en primer desetih vrst zvoka: alarm, aplavz,
zvonec, ploskanje, računalniška tipkovnica, pok, posoda, ognjemet, trkanje in
veter. S tem razred ni predstavljen samo z eno vrsto ozadja.

Vsi dražljaji ohranijo raven največje 100-milisekundne efektivne vrednosti
približno -42 decibelov glede na polno skalo. Glasnost sistema Windows mora
ostati 100 odstotkov, zvočnik pa 30 centimetrov od vgrajenega mikrofona.
Položaj, glasnost in prostor se med preizkusom ne spreminjajo.

Primarni rezultat posameznega poskusa je uspeh, če sistem med zajemom vsaj
enkrat potrdi pričakovani razred. Dodatno se poročajo prevladujoči potrjeni
izhod, matrika zamenjav, lažni nevarnostni alarmi pri govoru in razredu drugo
ter časi predobdelave, sklepanja in poobdelave. Napačna napoved modela ni
razlog za ponovitev. Ponovitev je dovoljena samo po dokumentirani tehnični
napaki ali materialni zunanji motnji.
