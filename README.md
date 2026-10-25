# ScanMail 0.2.0 — Unraid

Lokal webside til HP Color LaserJet Pro MFP M176n på **172.16.60.252**.
Scan fra mobilen, se siderne, saml dem i en PDF og send med Gmail eller en anden
SMTP-udbyder. Der kræves ingen åbne porte på din router og ingen offentlig hjemmeside.
Browseren og Unraid skal kunne nå hinanden. Unraid skal kunne nå printeren over LAN.
Installation og mailafsendelse kræver udgående internetadgang.

**Status: testet med simuleret scanner og SMTP; afventer installationstest på Unraid.**
11 automatiske test består. Python-, JavaScript- og Bash-syntaks er kontrolleret.
Testene afvikler HTTP-handlerne via en hukommelsestransport og laver rigtige PDF-filer;
de åbner ingen netværksporte og sender ingen mail. Docker-klienten findes i udviklingsmiljøet,
men adgang til Docker-tjenesten er afvist. Derfor er image-build, HP-plugin, read-only
containerdrift og Unraid-WebUI-link **ikke afprøvet**. Printer, driverens modes/DPI og
Gmail skal valideres på dit netværk. Se [INSTALLATION.md](INSTALLATION.md).

## Installation på Unraid

1. Pak ZIP-filen ud på et Unraid-share, eksempelvis:
   `/mnt/user/appdata/scanmail-source/scanmail-v0.2.0/`.
2. Åbn Unraids webterminal, og kør:

   ```bash
   cd /mnt/user/appdata/scanmail-source/scanmail-v0.2.0
   bash install-unraid.sh
   ```

3. Installationen bygger et lokalt image med Debian, SANE og HPLIP. HP's
   tekstguide åbner derefter. Vælg download af pluginet, læs licensen, og besvar
   selv dens spørgsmål. M176n kræver pluginet til scanning. Der accepteres ingen
   licens automatisk. Hvis signaturkontrol/download fejler, stop og send fejlteksten;
   spring ikke signaturkontrollen over. Første installation kan tage flere minutter.
4. Vælg en adgangskode til ScanMail, når installationsscriptet spørger.
5. Åbn `http://DIN-UNRAID-IP:8788` fra din telefon eller computer på lokalnettet.
   Brug Unraid-serverens IP, ikke printerens IP.
6. Log ind. Åbn **Indstillinger → Test scanner**. Denne test åbner driveren;
   en rigtig scanning er næste kontrol. Læg et papir på scannerglasset og tryk
   **Scan første side**. Kontrollér forhåndsvisningen og download PDF'en.
7. Opsæt Gmail som nedenfor og send en enkelt prøvescanning til dig selv.

Scriptet bruger Docker direkte, så Docker Compose ikke er nødvendigt. Ingen
færdig Docker Hub/GHCR-udgivelse er forudsat. Pluginet installeres i en separat
midlertidig container og bevares i dit lokale image. Scriptet gemmer også imaget på
`/mnt/user/appdata/scanmail-images/scanmail-0.2.0-hp.tar.gz`, så det overlever
gendannelse af Unraids docker.img. Arkivet er kun til din lokale installation. Kontodata og adgangskode
kopieres ikke ind i dette image. Hvis guiden afbrydes, oprettes appen ikke.

## Gmail

I din Google-konto skal totrinsbekræftelse være slået til, og du skal kunne oprette
en **app-adgangskode**: https://myaccount.google.com/apppasswords

Indtast følgende under Indstillinger:

| Felt | Værdi |
|---|---|
| SMTP-server | `smtp.gmail.com` |
| Port | `587` |
| Kryptering | `STARTTLS` |
| Mailkonto | Hele din Gmail-adresse |
| App-adgangskode | Den særlige adgangskode fra Google |
| Afsender | Samme Gmail-adresse, eller lad feltet stå tomt |

Brug ikke din normale Google-adgangskode. Koden indtastes kun i din lokale
installation; del den ikke i chatten. Nogle administrerede konti og konti med
Advanced Protection tillader ikke app-adgangskoder. Denne version har ikke
Google OAuth-login. En anden udbyder kan vælges via **Anden SMTP-udbyder**;
udbyderen skal tillade SMTP-login med brugernavn/adgangskode og TLS.

Der er ingen grund til at skifte mailudbyder, hvis app-adgangskoder virker på din
Gmail-konto. Afsendte dokumenter går gennem den valgte mailudbyder.

## Sådan bruges den

- **Scan første side** starter printerens fladbedscanner fra websiden.
- **Tilføj side** scanner det næste papir til samme dokument, højst 20 sider.
- Farve/gråtoner og 150/300 dpi vælges før første side; indstillingerne holdes ens.
- **Download PDF** virker også uden mailkonto.
- **Send dokument** sender til én mailadresse. Gem op til 25 favoritmodtagere.
- Efter accepteret afsendelse låses send-knappen for at undgå dobbeltklik.
- Mailserverens accept er ikke en leveringskvittering. Se også spamfilteret.
- Ved en uklar SMTP-forbindelsesfejl genprøver appen ikke automatisk. Afsendelse og tilføjelse af sider låses for dette dokument. Kontrollér
  modtagerens indbakke og mailudbyderens log, før du eventuelt starter et nyt dokument.
  SMTP-mails fremgår ikke nødvendigvis af Sendt post.
- **Nyt dokument** sletter siderne fra den igangværende session.
- Hver browsersession har sit eget dokument. Kun én fysisk scanning kan køre ad gangen.

Scannerens glas håndterer én side ad gangen. M176n har ikke automatisk papirføder.
Versionen laver billedbaserede PDF'er uden OCR. Et dokument kan højst være 17 MiB
før vedhæftningens mailkodning; brug 150 dpi eller færre sider ved store dokumenter.

## Data og adgang

- Appen er tiltænkt et betroet lokalnet. Standardadressen bruger HTTP. Undgå
  gæstenet/offentligt net; brug din eksisterende VPN til adgang udefra. Hvis du
  senere sætter HTTPS foran appen, sæt `COOKIE_SECURE=1` og bevar Host-headeren.
- Webadgangskoden gemmes som en saltet PBKDF2-hash i
  `/mnt/user/appdata/scanmail/runtime.env`.
- SMTP-adgangskoden ligger i `/mnt/user/appdata/scanmail/settings.json`, som kun
  containerens bruger kan læse (filrettigheder 600). Den er **ikke krypteret på
  disken**; Unraid-administratorer og backups af appdata kan læse den. Filen og
  appdata-mappen skal ikke deles som et åbent SMB-share.
- Sider ligger i containerens midlertidige RAM-filsystem. Dokumenter slettes
  efter 1 times inaktivitet, dog først når en scanning/afsendelse er afsluttet.
  De forsvinder også ved containerens genstart. Modtagerens og Gmails kopier
  slettes naturligvis ikke af appen.
- Sessionscookies er HttpOnly og SameSite=Strict. Ændringer kræver CSRF-token.
  Loginforsøg begrænses. Der er én fælles familieadgangskode i denne version.

## Drift, fejl og tilbagerulning

```bash
docker logs --tail 80 scanmail
docker restart scanmail
```

Ved scannerfejl: brug **Test scanner**, og kopier fejlteksten. Kontrollér at
Unraid kan nå 172.16.60.252, at printeren er tændt, og at en anden app ikke
bruger scanneren. HP-pluginet skal være installeret i det image, der kører.
Der kræves ikke en CUPS-printerkø for at starte scanningen her.

Scriptet afbryder, hvis `scanmail` allerede findes. Ved en senere opdatering
skal den eksisterende container først stoppes og omdøbes, eksempelvis
`docker stop scanmail` og `docker rename scanmail scanmail-previous`, så den kan
gendannes. Gem tidligere image og appdata-backup før en versionsopdatering.
Byg først en ny version, når en opdateret pakke er tilgængelig.

Fjern denne testinstallation uden at slette indstillinger:

```bash
docker stop scanmail
docker rm scanmail
```

Printeren ændres ikke af appen. Slet kun appdata og de lokale images, hvis du
også vil fjerne kontoopsætningen og installationen helt.

## Verifikation og kilder

Kør offline-testene med Python 3.11+ og Pillow/ReportLab installeret:

```bash
python3 -m unittest discover -s tests -v
node --check app/static/app.js
bash -n install-unraid.sh
```

Se [VALIDERING.md](VALIDERING.md) for testomfang og resterende fysiske kontroller.

### HP-plugin og vedligeholdelse

Pluginet kræver interaktiv licensaccept og versionsmatch med HPLIP. Vi beholder
et scriptstyret `docker commit` efter den interaktive installation: dette undgår
at acceptere licensen under et automatisk build eller distribuere pluginet.
Et separat plugin-volume er fravalgt, fordi pluginets biblioteker, links og
HPLIP-state ellers let kommer ud af takt med base-imaget. Ved opdatering bygges
basen på ny, og plugin-guiden køres igen. Download- eller signaturfejl skal stoppe
installationen; vælg aldrig at fortsætte uden signaturkontrol. Ingen SMTP-konto
eller webadgangskode er tilført, når image-snapshot og arkiv oprettes.

Efter gendannelse af Unraids docker.img kan arkivet indlæses med:

```bash
gzip -dc /mnt/user/appdata/scanmail-images/scanmail-0.2.0-hp.tar.gz | docker image load
```

Genskab derefter containeren med `docker run`-kommandoen i installationsscriptet
(uden build/plugin-trinene). Appdata og runtime.env skal være bevaret. Udpak ikke
pluginet manuelt fra en anden HPLIP-version. Et importeret image genskaber ikke
containeren eller Unraids autostart-indstillinger automatisk.

- HP om M176n-specifikationer: https://support.hp.com/dk-da/product/product-specs/hp-color-laserjet-pro-mfp-m176n/model/5303439
- HP om plugin og kravet for M176n-scanning: https://developers.hp.com/hp-linux-imaging-and-printing/binary_plugin.html
- Google om app-adgangskoder: https://support.google.com/accounts/answer/185833
- Google om printer/app via SMTP: https://support.google.com/a/answer/176600
