# ScanMail 0.3.0 – kort guide til Unraid

## Du har allerede en fungerende ScanMail

Download først de scannede dokumenter, du vil beholde. Opdateringen genstarter
containeren, så midlertidige scans og login-sessioner forsvinder.

```bash
cd /mnt/user/appdata/scanmail-source/Scanmail
git pull --ff-only
bash update-unraid.sh
```

Scriptet genbruger dit HP-plugin og bevarer appdata, favoritter og adgangskoder.
Det installerer OCR, tester den nye app før skift, gemmer en backup af den gamle
container og ruller tilbage, hvis den nye ikke starter. Det rydder ikke selv gamle
backup-containere. Første kørsel kan tage flere minutter.

Åbn http://172.16.61.213:8788 (eller din Unraid-IP), genindlæs og log ind igen.

## Kontrol efter opdatering

1. Scan én side og tryk på preview. Kontrollér Zoom ind og Luk.
2. Tilføj en anden side. Rotér, flyt rækkefølgen og slet en side. Kontrollér PDF.
3. Vælg Lille fil, og sammenlign den viste størrelse med Høj kvalitet.
4. Slå OCR til. Vent på klargøring. Download PDF og kontrollér, at tekst kan søges
   og kopieres. Dansk OCR bør testes med æ, ø og å samt dine egne dokumenter.
5. Kontrollér en favoritknap. Prøv frivilligt Husk seneste modtager; slå det fra
   igen for at slette den lokale adresse på en delt enhed.
6. Send én mail til dig selv. Kontrollér indbakke og PDF. Tryk Scan nyt dokument,
   og kontrollér at scannevalgene åbnes igen.
7. Test Color/Gray, 150/300 dpi og genstart. Ingen fysisk test køres automatisk
   af opdateringsscriptet, og det sender aldrig en prøvemail på egen hånd.

## Første installation

```bash
mkdir -p /mnt/user/appdata/scanmail-source
cd /mnt/user/appdata/scanmail-source
git clone https://github.com/Bartel1234/Scanmail.git
cd Scanmail
SCANMAIL_PLUGIN_SOURCE=openprinting bash install-unraid.sh
```

Læs og accepter selv HP-pluginets licens. Stop ved download-/signaturfejl eller
hvis signeringsnøglen ikke kan hentes. Vælg aldrig installation uden kontrol.
Vælg derefter webadgangskode og åbn `http://DIN-UNRAID-IP:8788`.

Første fysiske kontrol: Indstillinger → Test scanner, derefter en ægte scanning
og PDF-download. Printeren er 172.16.60.252. Først derefter opsættes Gmail lokalt
med smtp.gmail.com, port 587, STARTTLS og en Google-app-adgangskode. Del ikke koden.

Se README for lokal HTTPS, backup og manuel tilbagerulning. Ingen routerporte
skal åbnes, og Unraids D-Bus skal ikke monteres ind i containeren.
