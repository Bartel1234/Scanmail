# Validering af ScanMail 0.2.0

## Bestået i udviklingsmiljøet

- 19 offline-test med Python 3.12, Pillow 12.3 og ReportLab.
- Login, begrænsning af loginforsøg, sessionudløb, logout, Origin og CSRF.
- Adskillelse af dokumenter ved læsning, download, sletning og afsendelse.
- Simuleret scanimage, ægte JPEG-forhåndsvisning og to-siders PDF med kontrolleret sidestørrelse.
- Gendannelse af joboplysninger ved genindlæsning; scannerlås, timeout og manglende driver/plugin.
- Indstillinger med filrettighed 600; hemmeligheden udelades fra API-svar.
- SMTP STARTTLS/implicit TLS med certifikatkontrol; ingen login efter fejlet TLS.
- Afvist mail-login, uklar levering, gentagen afsendelse, mailheaders og QUIT-fejl efter accept.
- Oprydning af inaktive dokumenter og bevarelse af igangværende scanning.
- Python-, JavaScript- og Bash-syntaks.

HTTP-handlerne køres med rå HTTP-forespørgsler gennem en hukommelsestransport.
Ingen faktisk TCP-server, browser, scanner eller SMTP-server indgår i disse test.

## Ikke afprøvet

Docker-adgang er afvist af udviklingsmiljøet (operation not permitted på
/var/run/docker.sock). Image-build og runtime, Debian-pakkernes konkrete versioner,
HP's plugin-download/signatur/licensguide, Unraid WebUI/autostart og gendannelse
fra image-arkiv skal afprøves på Unraid. Der er ikke omgået nogen adgangsbegrænsning.

Printer-IP, SANE-enhedsnavn, modes og DPI er konfigureret ud fra prototypen og er
ikke hardwarebekræftet. Følg INSTALLATION.md: først scannerforbindelse og fysisk
PDF-download, derefter Gmail-mailtest. Responsivt layout er bevaret, men ikke
visuelt browsertestet her. Versionen er en testkandidat, ikke en hardwarevalideret udgivelse.

## Ændringer siden 0.1.0

Uklar SMTP-levering låser dokumentet. Bekræftet DATA-accept bevares ved fejl i QUIT.
Frontend gendanner modes/DPI og rydder preview ved logout. Scannerfejl viser ikke
rå driverfejl; mailfejl viser ikke serverens potentielt følsomme svar. Dokument-
adgang opdaterer aktivitetstid. Samtidige HTTP-arbejdere, socketventetid, pixelantal,
scannerens outputfil og samlet dokumentlager er begrænset. Installer gemmer nu et
lokalt image-arkiv uden brugerens SMTP-konto og kræver plugin-state før snapshot.


## Opfølgning fra brugerens Unraid 25. oktober 2026

- Base-image blev bygget og websiden blev startet efter rettelse af entrypoint.
- Driveren åbner M176n og viser Gray/Color og 150/300 dpi som understøttet.
- Scanning fejlede med 139, når UID 1000 manglede i /etc/passwd.
- Med brugerpost ændredes fejlen til 134 og en manglende D-Bus-forbindelse.
- Med brugerpost og privat bus gennemførtes fysisk Gray/150-dpi scan med exitkode 0.
- Fem nye offline-test kontrollerer brugerpost, privat bus, fejlet opstart og at
  reparationsscriptet ikke stopper appen ved fejlet build. I alt 19 består.
- Det permanente image, read-only bus-kontrol og reparationsscript afventer
  brugerens kørsel. Browser-preview/PDF, Color/300 dpi og Gmail er ikke bekræftet.
