# Validering – ScanMail 0.3.1

## Bestået i udviklingsmiljøet

37 Python-test, Node-test af frontend-flow, Python-/JavaScript-/Bash-syntaks.

- Login, sessionsudløb, logud, loginbegrænsning, Origin og CSRF.
- Dokumentisolering, inkl. nyt preview, redigering og PDF-klargøring.
- Simuleret scanning, hardwarelås, timeout, manglende driver og pluginfejl.
- Rotation, rækkefølge, sletning, ugyldige positioner, gamle revisioner og låste jobs.
- Ægte multipage-PDF'er med kontrolleret sidestørrelse, rotation og billedrækkefølge.
- Lille fil giver under halvdelen af filstørrelsen på testbilledet, med samme fysiske
  sidestørrelse. Forholdet er dokumentafhængigt og er ikke et løfte for alle scans.
- Rigtig Tesseract genkendte engelsk tekst, der kunne udtrækkes fra PDF med pypdf.
  Det usynlige tekstlag, OCR-cache ved kvalitetsskift og OCR-timeout testes også.
- SMTP TLS-rækkefølge og certifikatkontrol, loginfejl, dobbeltforsendelse og uklar
  levering, mailheaderkontrol og QUIT-fejl efter accepteret DATA.
- Brugerpost og privat D-Bus-start med mocks; ingen login/opstart hvis busstart fejler.
- Hele opdateringsscriptet køres mod en Docker-simulator: build-/preflight-/smoke-fejl
  berører ikke den gamle app; run-/healthfejl gendanner den gamle container og restart-policy.
- JavaScript køres i en simuleret DOM: favoritter, frivillig browserlagring, preview,
  zoom, redigering, dobbeltklik på Send, næste dokument og uklar levering.

Testenes HTTP-transport er i hukommelsen. Scanner og SMTP simuleres. Den rigtige
OCR-test bruger engelsk tekst; dansk sprogpakke installeres og kontrolleres af
opdateringen, men genkendelseskvaliteten på danske scans skal vurderes på Unraid.

## Begrænsninger

Docker-socket-adgang afvises i udviklingsmiljøet. Chromium findes, men kunne ikke
starte under miljøets begrænsninger. Der er derfor ikke udført Docker-build,
0.3.1 hardwaretest, faktisk browser-/mobil-layouttest eller Gmail-test her.

På brugerens netværk blev 0.2.0-valg af scanner, modes/DPI, scanning og mail bekræftet
fungerende efter rettelse af Unix-bruger og privat D-Bus. De rettelser er bevaret.
Ny kode, OCR-pakker og opdateringsscriptet skal stadig valideres på Unraid.

Opdateringen foretager selv en rigtig lokal D-Bus-kontrol, en OCR/PDF-prøve og
HTTP-opstart i en container uden netværk, før den gamle app stoppes. Efter skiftet
kontrolleres healthz igen. Ingen scanner eller mailserver kontaktes automatisk.


## Beskæring i 0.3.1

Fem ekstra Python-test kontrollerer billedets pixels og PDF-sidestørrelse,
nulstilling uden ødelæggelse af originalen, rotation/reordering, ugyldige og gamle
koordinater, CSRF og dokumentisolering. En rigtig OCR-test genkender først hele
siden og derefter et udsnit; PDF-tekst og indlejret billede indeholder efter
beskæring kun udsnittet. Gamle OCR-cacher kasseres ved beskæring/nulstilling.

Frontend-testen simulerer træk i begge retninger, nulstilling, procentfelter og
ugyldige udsnit. I alt består 37 Python-test og frontend-testen. Rigtig touch-
og musebetjening samt det endelige layout skal stadig kontrolleres på Unraid.
