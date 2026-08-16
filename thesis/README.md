# Diplomska naloga

Ta imenik vsebuje delovni osnutek diplomske naloge v klasičnem formatu `bachelor-thesis-book`. Izvorna predloga v nadrejenem imeniku ni bila spremenjena; njene podporne datoteke so kopirane v `podporno/`, da je diplomsko delo samostojno in vključeno v isti Git repozitorij kot programska oprema ter meritve.

## Pomembne datoteke

- `diploma.tex`: glavna datoteka in uradni podatki o nalogi;
- `studis_topic.md`: predlog naslova in opisa teme za mentorja oziroma StudIS;
- `chapter_plan.md`: razpored poglavij, strani, dokazov in 20-urni načrt pisanja;
- `poglavja/`: ločene datoteke za posamezna poglavja;
- `literatura.bib`: preverjeni bibliografski viri;
- `output/pdf/`: končni PDF-ji, namenjeni pregledu.

## Delovni način

Vidna polja z napisom **Navodilo za pisanje** so pomoč pri pripravi prvega osnutka. Ko so vsa nadomeščena z avtorjevim besedilom, v `diploma.tex` spremenite:

```tex
\thesisdrafttrue
```

v:

```tex
\thesisdraftfalse
```

Pred oddajo je treba odstraniti ali dopolniti tudi zahvalo, povzetek in angleški abstract ter opis teme uskladiti z besedilom v StudISu.

## Prevajanje

V okolju z nameščenimi LaTeX, Biber in Pygments:

```powershell
latexmk -pdf -shell-escape -interaction=nonstopmode diploma.tex
```

Trenutni pregledani delovni izvod je shranjen kot
`output/pdf/diplomska_naloga_osnutek.pdf`. Za oddajo ga preimenujte šele po
odstranitvi vseh navodil in končnem preverjanju skladnosti PDF/A. Rezultat
preglejte tudi z možnostjo `draft`, kot priporoča uradna predloga.
