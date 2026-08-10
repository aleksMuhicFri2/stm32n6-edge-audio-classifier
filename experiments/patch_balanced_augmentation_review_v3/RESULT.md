# Rezultat tretjega pregleda in modela

Datum: 10. avgust 2026

Slepi pregled je zajel 12 novih primerov razbitja stekla. Vseh 12 je bilo
veljavnih in popolnih: 11 značilnih ter eden netipičen, vendar še vedno
pravilen. Noben primer ni bil odrezan, pretih ali preglasen. Pet pregledanih
primerov je uporabilo varovalni izbor najmočnejšega energijskega okvirja,
vključno s prej neuspešnim izvorom 92644. Skupaj z bitno nespremenjenimi in že
potrjenimi streli je bilo veljavnih 24 od 24 dogodkov.

Kvantizirani model za namestitev je na nespremenjenih 278 razvojnih posnetkih
pravilno razvrstil 246 posnetkov (88,49 odstotka). V primerjavi z izhodiščnim
modelom z izboljšano oznako razbitja stekla se je priklic stekla izboljšal s
83,33 na 85,00 odstotka, priklic strelov pa z 90,74 na 92,59 odstotka. Priklic
pasjega laježa se je zmanjšal z 78,33 na 75,00 odstotka. Priklic sirene,
človeškega govora in nevihte je ostal nespremenjen.

Model je uspešno preveden za pospeševalnik Neural-ART. Uteži zasedejo 3.279.505
bajtov, delovni pomnilnik 245.760 bajtov, 29 od 34 izvajalnih odsekov pa se
izvede strojno. Model je vgrajen v izvorno kodo strojne programske opreme.
Predobdelava sedaj zapisuje spektrogram v časovno glavnem vrstnem redu, ki ga
zahteva neposredni vhod večjega modela. Čista gradnja in podpisovanje sta uspela
brez napak. Dne 10. avgusta 2026 so bile uteži in podpisani program naloženi na
ploščo STM32N6570-DK ter po zapisu uspešno preverjeni. Fizični preizkus novega
programa se je začel z uspešnim zagonom in pravilnim prikazom uporabniškega
vmesnika. Preizkus odziva vseh šestih razredov še ni bil opravljen.
