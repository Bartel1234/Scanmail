# ScanMail 0.3.0 – fra papir til indbakke

Lokal, mobilvenlig app til HP Color LaserJet Pro MFP M176n på **172.16.60.252**.
Kører på Unraid/DeathStar. Scan sider fra glasset, gennemgå dem, download én PDF,
og send via Gmail eller en anden SMTP-udbyder med TLS.

## Opdater en eksisterende installation

Gem først de PDF'er du vil beholde: midlertidige scans og login-sessioner forsvinder
ved containerskift. Mailindstillinger, favoritter, webadgangskode og HP-plugin bevares.

```bash
cd /mnt/user/appdata/scanmail-source/Scanmail
git pull --ff-only
bash update-unraid.sh
```

Opdateringen bygger på dit eksisterende driver-image. Den holder HPLIP-pakkerne på
samme version og tilføjer lokal OCR på dansk og engelsk. HP-licensen skal ikke
accepteres igen, da pluginet genbruges og ikke distribueres i dette repository.

Scriptet kontrollerer brugerpost, privat D-Bus, pluginversion, OCR/PDF samt faktisk
HTTP-opstart, før den gamle app stoppes. Testcontaineren har intet netværk og får
ikke dine kontodata. Den nye app får samme appdata og runtime.env. Hvis den ikke
starter korrekt, gendanner scriptet automatisk den tidligere container.

Den tidligere container bevares som `scanmail-backup-…`, med autostart slået fra.
Et image-arkiv gemmes i `/mnt/user/appdata/scanmail-images/`. Tag almindelig backup
 af appdata på Unraid. Gamle backup-containere/images kan fjernes manuelt, når den
nye version er fysisk testet. Scriptet rydder dem ikke automatisk.

Åbn derefter **http://172.16.61.213:8788** (eller din Unraid-IP). Genindlæs siden,
log ind og test scanning, preview og PDF-download før mail.

## Nyt i denne version

1. **Efter afsendelse:** en tydelig kvittering og knappen **Scan nyt dokument**.
   Scan og afsendelse af det gamle dokument låses for at undgå dubletter.
2. **Sideredigering:** rotér 90° med uret, slet en side og flyt sider op/ned.
   Rækkefølge og rotation følger med i preview, PDF og OCR.
3. **Stor forhåndsvisning:** tryk på siden, vælg Zoom ind, og luk med Luk/Escape.
4. **Favoritter:** modtagere vises som knapper. **Husk seneste modtager på denne
   enhed** er et frivilligt tilvalg og kan slås fra for at slette den lokale adresse.
5. **PDF-kvalitet:** Høj kvalitet eller Lille fil. Lille fil bruger op til 150 dpi og
   mere JPEG-komprimering; sidens fysiske størrelse bevares. Før klargøring vises et
   groft størrelsesoverslag; bagefter vises PDF'ens præcise størrelse. PDF over 17 MiB
   kan downloades, men send-knappen deaktiveres.
6. **Opdatering med rollback:** ét script, som tester før skift, bevarer driveren og
   starter den gamle container igen ved opstartsfejl. `repair-unraid.sh` henviser nu
   til dette script.
7. **OCR:** frivillig lokal tekstgenkendelse på dansk og engelsk. PDF'en får et
   usynligt tekstlag, som kan søges og kopieres. Resultatet kan indeholde fejl;
   kontrollér vigtig tekst. Der udføres ingen cloud-OCR.

PDF-klargøring kører i baggrunden med status pr. side. OCR kan tage op til 90 sekunder
pr. side. OCR-resultater genbruges ved skift af PDF-kvalitet. Rotation genkendes på ny.
Kun én PDF/OCR-opgave behandles ad gangen for at begrænse ressourceforbrug. En fejl
kan genprøves med **Prøv PDF-klargøring igen**, eller OCR kan slås fra.

## Første installation

```bash
mkdir -p /mnt/user/appdata/scanmail-source
cd /mnt/user/appdata/scanmail-source
git clone https://github.com/Bartel1234/Scanmail.git
cd Scanmail
SCANMAIL_PLUGIN_SOURCE=openprinting bash install-unraid.sh
```

Scriptet bygger et lokalt Debian-image og åbner HP's interaktive plugin-guide.
Den nødvendige pluginversion og dens signatur hentes fra OpenPrinting, fordi HP's
server svarede 403 under installationen. Du læser og accepterer selv HP-licensen.
Stop ved signaturfejl eller manglende signeringsnøgle. Accepter aldrig at installere
uden signaturkontrol. `SCANMAIL_PLUGIN_SOURCE=hp` vælger HP's normale downloadguide.

Netværksprinteren kræver hverken privilegeret container, USB-passthrough eller en
CUPS-printerkø. UID/GID 1000 har en rigtig brugerpost; HPLIP får en privat D-Bus på
en Unix-socket i containerens /tmp. Ingen værtsbus monteres, og appen kører som
bruger 1000 med skrivebeskyttet rodfilsystem.

Se [INSTALLATION.md](INSTALLATION.md) for trinvis kontrol.

## Gmail og andre SMTP-udbydere

| Felt | Gmail |
|---|---|
| Server | smtp.gmail.com |
| Port | 587 |
| Kryptering | STARTTLS |
| Mailkonto | Hele Gmail-adressen |
| Adgangskode | Google-app-adgangskode |
| Afsender | Samme adresse, eller tom |

Gmail kræver normalt totrinsbekræftelse og en konto, der tillader app-adgangskoder.
Opret den på https://myaccount.google.com/apppasswords og indtast den lokalt i appen.
Del aldrig adgangskoden i chat eller GitHub. Google OAuth understøttes ikke.
Andre udbydere kan vælges under Indstillinger; STARTTLS og implicit TLS understøttes.
TLS-certifikater kontrolleres. Der faldes aldrig tilbage til ukrypteret login.

Mailserverens accept er ikke en garanti for modtagelse. Ved uklar levering låses
dokumentet; kontrollér indbakke, spam og udbyderens log før en ny forsendelse.
SMTP-mails fremgår ikke nødvendigvis af Sendt post. Appen genafsender ikke automatisk.

## Data og adgang

- Appen er til et betroet LAN. Åbn ingen routerporte. Brug din VPN til adgang udefra.
- HTTP er standard. Lokal HTTPS kan etableres med en reverse proxy og et certifikat,
  som enhederne stoler på. Bevar Host-headeren, sæt `COOKIE_SECURE=1` i runtime.env,
  og genskab containeren med opdateringsscriptet. Brug derefter HTTPS-adressen.
- Webadgangskoden er saltet PBKDF2 i appdata/runtime.env. SMTP-hemmeligheden er i
  settings.json med filrettighed 600. Den er **ikke krypteret mod administratorer**
  og kan læses af Unraid-administratorer og i appdata-backups. Del ikke mappen via SMB.
- Scans, OCR-tekst og PDF'er ligger i privat midlertidigt RAM-lager i containeren.
  De ryddes efter omkring en times inaktivitet (oprydning hvert minut), efter endt
  igangværende opgave, og ved containerskift. Logud sletter færdige dokumenter.
- Der er én fælles adgangskode; dokumenter er adskilt pr. browsersession. Kun én
  fysisk scanning kan køre ad gangen. Højst 20 sider/dokument og 10 dokumenter.
- Cookies er HttpOnly/SameSite=Strict. Ændringer kræver CSRF-token. Et revisionsnummer
  beskytter sideredigering fra gamle browserfaner. Logs indeholder ikke dokumenttekst,
  mailbeskeder eller SMTP-svar med mulige kontooplysninger.
- Seneste modtager gemmes kun efter dit tilvalg i browseren. Slå feltet fra for at
  slette den; undlad tilvalget på en delt enhed.

## Drift og manuel tilbagerulning

```bash
docker logs --tail 60 scanmail
docker restart scanmail
```

Ved funktionsfejl efter en ellers vellykket opdatering kan du bruge den gemte gamle
container. Erstat `scanmail-backup-…` med navnet, som opdateringsscriptet viste:

```bash
docker stop scanmail
docker rename scanmail scanmail-new-paused
docker update --restart=no scanmail-new-paused
docker rename scanmail-backup-… scanmail
docker update --restart=unless-stopped scanmail
docker start scanmail
```

Scriptet bruger som standard appdata i `/mnt/user/appdata/scanmail`, arkiver i
`/mnt/user/appdata/scanmail-images` og port 8788. Særlige installationer kan sætte
`SCANMAIL_DATA_DIR`, `SCANMAIL_ARCHIVE_DIR` og `SCANMAIL_PORT` ved opdatering.

## Teststatus

Se [VALIDERING.md](VALIDERING.md). De automatiske test kræver Python, Pillow,
ReportLab og pypdf. En OCR-test bruger lokalt installeret Tesseract. Frontend-flow
kan testes uden browser med Node:

```bash
python3 -m unittest discover -s tests -v
node tests/frontend.test.js
node --check app/static/app.js
bash -n update-unraid.sh
bash -n install-unraid.sh
```

Docker-tjenesten er utilgængelig i udviklingsmiljøet. Den nye Docker-build og det
fysiske 0.3.0-flow skal derfor kontrolleres på Unraid. 0.2.0 med rettet bruger/D-Bus
blev af brugeren bekræftet fungerende til scanning og mail.

Kilder: [HP-plugin](https://developers.hp.com/hp-linux-imaging-and-printing/binary_plugin.html),
[OpenPrinting-arkiv](https://www.openprinting.org/download/printdriver/auxfiles/HP/plugins/),
[Google-app-adgangskoder](https://support.google.com/accounts/answer/185833).
