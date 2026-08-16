# Predlog teme za StudIS

## Slovenski naslov

**Razvoj in vrednotenje sistema za zaznavanje nevarnih zvočnih dogodkov na mikrokrmilniku STM32N6 z uporabo nevronskega pospeševalnika**

## Angleški naslov

**Development and Evaluation of a Hazardous Sound Event Detection System on an STM32N6 Microcontroller with a Neural Accelerator**

## Predlog opisa v slovenščini

Cilj diplomskega dela je razviti in ovrednotiti vgrajeni sistem za sprotno zaznavanje nevarnih zvočnih dogodkov na razvojni plošči STM32N6570-DK. Sistem je zasnovan kot prototip vidnega opozarjanja za gluhe in naglušne osebe, pri čemer se zvok obdeluje lokalno brez dostopa do računalniškega oblaka in brez trajnega shranjevanja surovih zvočnih posnetkov. Kandidat bo prilagodil kvantizirani model na osnovi arhitekture YAMNet za izvajanje na mikrokrmilniku STM32N6 z nevronskim pospeševalnikom Neural-ART ter povezal zajem zvoka z vgrajenega mikrofona, predobdelavo z logaritemskim melovim spektrogramom, sklepanje in prikaz rezultatov na zaslonu. Sistem bo prepoznaval izbran nabor nevarnih dogodkov, človeški govor in druge zvoke kot varovalna razreda. Izvedbo bo ovrednotil z nadzorovanim preskusom na fizični napravi ter analiziral pravilnost zaznavanja, lažne alarme, čas izvajanja in porabo pomnilnika. Rezultati bodo podprti s ponovljivim protokolom, shranjenimi meritvami in razpravo o omejitvah sistema.

## Proposed description in English

The aim of the thesis is to develop and evaluate an embedded system for real-time hazardous sound event detection on the STM32N6570-DK development board. The system is designed as a visual-alert prototype for deaf and hard of hearing users, with local audio processing, no cloud access, and no persistent storage of raw audio recordings. The candidate will adapt a quantized model based on the YAMNet architecture for execution on an STM32N6 microcontroller with the Neural-ART accelerator and integrate audio acquisition from the onboard microphone, log-mel spectrogram preprocessing, inference, and presentation of results on the display. The system will recognize a selected set of hazardous events, human speech, and other sounds as guard classes. The implementation will be evaluated through a controlled test on the physical device, including detection performance, false alerts, execution time, and memory usage. The results will be supported by a reproducible protocol, preserved measurements, and a discussion of system limitations.

## Predlagane ključne besede

- vgrajeni sistemi
- zaznavanje zvočnih dogodkov
- STM32N6
- nevronski pospeševalnik
- robna umetna inteligenca
- zasebnost

> Opomba: končni opis v datoteki `diploma.tex` mora biti dobesedno enak opisu, ki ga mentor vnese v StudIS. Ta dokument je predlog, ki ga lahko mentor potrdi ali jezikovno prilagodi.
