# Opgave til Codex — færdiggør ScanMail til Unraid

Vi bygger en lokal, mobilvenlig webapp til min HP Color LaserJet Pro MFP M176n.
Printeren er tilsluttet via Ethernet og har IP **172.16.60.252**. Appen skal køre
i Docker på min Unraid-server DeathStar. Brug Gmail til afsendelse, men understøt
andre SMTP-udbydere via indstillinger. Appen skal være lokal uden offentlig
eksponering, cloudproxy eller portåbning på routeren.

## Arbejd videre med koden i denne mappe

Dette er en påbegyndt prototype, ikke en færdig eller hardwaretestet udgivelse.
Filerne er syntakskontrolleret med `py_compile`, `node --check` og `bash -n`.
Der er ingen funktionstest endnu. Docker er ikke tilgængelig i det miljø,
hvor filerne blev oprettet. Scanner og Gmail er ikke kontaktet.

Koden har en Python HTTP-server med Pillow og ReportLab, en responsiv webside,
Dockerfile og et første installationsscript til Unraid. Undersøg løsningen
kritisk og ret fejl, før du kalder den klar til brug. Hold installationen enkel.

## Det færdige brugerflow

1. Log ind på lokal webside fra mobil eller computer.
2. Læg dokument på scannerglas, vælg farve/gråtoner og 150/300 dpi, tryk Scan.
3. Vis reel forhåndsvisning. Tilføj sider manuelt til én PDF.
4. Download PDF eller indtast modtager, emne og besked, og send PDF via SMTP.
5. Gem favoritmodtagere og SMTP-indstillinger lokalt.
6. Vis forståelige fejl for manglende HP-plugin, printer utilgængelig, timeout
   og afvist mail-login. Undgå automatisk genafsendelse og dobbeltforsendelser.

## Vigtige tekniske forhold

- HP oplyser eksplicit, at M176n kræver HPLIP's proprietære plugin til scanning.
  Hent et plugin, der matcher installeret HPLIP. Licensgodkendelse skal vises
  til brugeren; den må ikke accepteres automatisk. Spring ikke signaturkontrol over.
- Prototypens SANE-enhed er
  `hpaio:/net/HP_Color_LaserJet_Pro_MFP_M176n?ip=172.16.60.252`.
  Bekræft navn, tilgængelige modes og DPI gennem en reel test på brugerens netværk.
- Gennemgå især `install-unraid.sh`: hp-plugin i konsol uden GUI, pluginets
  placering, uid/gid, containerens entrypoint ved commit, image-persistens,
  read-only runtime, tmpfs og Unraid WebUI-link. Det er ikke bygget/testet.
- Undersøg om manuelt `docker commit` bør erstattes af en mere vedligeholdbar
  driverinstallation, uden automatisk licensaccept eller indlejrede hemmeligheder.
- Brug ikke privilegeret container eller USB-passthrough til netværksprinteren.
- Gmail: smtp.gmail.com, 587, STARTTLS og app-adgangskode, hvis kontoen tillader det.
  Ingen OAuth i prototypen. Bed ikke brugeren sende adgangskoden i chat.
- HTTP på et betroet LAN er udgangspunktet; dokumentér mulighed for lokal HTTPS.
- Beskyt adgang, sessioner, CSRF, dokumentisolering, filstier og mailheaders.
  Undgå dokumentindhold og kontodata i logs. Slet scans efter højst en times
  inaktivitet. Beskriv ærligt, at SMTP-hemmeligheden er beskyttet af filrettigheder,
  men ikke krypteret mod serveradministratorer.

## Næste arbejde

1. Gennemgå og ret backend, frontend og installation. Kontrollér også ressource-
   forbrug, oprydning, genindlæsning af siden og parallelle brugere.
2. Tilføj meningsfulde test af login/CSRF/dokumentisolering, scannerfejl,
   multipage-PDF, SMTP-TLS og fejl/uklar levering. Mock scanner og mailserver.
3. Byg og kontroller Docker-image, hvis miljøet har Docker. Angiv præcist,
   hvad der er testet, og hvad der kræver brugerens printer.
4. Lever en versionsnummereret pakke med en kort dansk installationsguide.
5. Første fysiske kontrol skal være scannerforbindelse og en PDF-download.
   Derefter opsætter brugeren Gmail lokalt og foretager en mailtest til sig selv.

Tag almindelige implementeringsvalg selv og fortsæt arbejdet. Spørg kun, når en
afklaring reelt blokerer. Opret ikke et offentligt repository, og publicér ikke
en tjeneste, medmindre jeg beder om det. Brug et eksisterende valgt repository,
hvis jeg har åbnet projektet dér; opfind ikke et GitHub-link.

Kilder: Se links nederst i README.md. De dokumenterer HP-plugin og Gmail.
