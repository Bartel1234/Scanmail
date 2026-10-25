# ScanMail 0.2.0 – kort installationsguide

1. Pak mappen ud på DeathStar, fx `/mnt/user/appdata/scanmail-source/scanmail-v0.2.0`.
2. Åbn Unraid-terminalen:

   ```bash
   cd /mnt/user/appdata/scanmail-source/scanmail-v0.2.0
   bash install-unraid.sh
   ```

3. HP-pluginets tekstguide åbner. Læs licensen og accepter selv, hvis du er enig.
   Stop ved download- eller signaturfejl; godkend aldrig at springe kontrollen over.
   Guiden skal hente et plugin til præcis den installerede HPLIP-version.
4. Vælg webadgangskode. Åbn `http://DIN-UNRAID-IP:8788` på dit betroede LAN.
5. **Test scanner først:** Log ind → Indstillinger → Test scanner. Kontrollér at
   output viser den rigtige M176n på `172.16.60.252` og understøtter Color/Gray og
   150/300 dpi. En test, der åbner enheden, beviser endnu ikke at scanning virker.
6. Læg papir på glasset. Scan én side. Kontrollér preview og download PDF.
   Tilføj en anden side og kontrollér rækkefølge i PDF. Afprøv begge modes og DPI.
7. Først derefter: Opsæt Gmail lokalt med `smtp.gmail.com`, port `587`, STARTTLS,
   hele mailadressen og en Google-app-adgangskode. Del aldrig adgangskoden i chat.
8. Send én PDF til dig selv. Kontrollér indbakke/spam og vedhæftningen. Ved uklar
   levering låses dokumentet; kontrollér modtagelse før du starter et nyt dokument.
9. Genstart containeren og kontrollér login, gemte indstillinger og scanner igen.
   Scans skal være væk efter genstart. Kontrollér også Unraid-autostart efter reboot.

Åbn ingen routerporte. Til lokal HTTPS kan du anvende en eksisterende lokal
reverse proxy med et certifikat dine enheder stoler på. Bevar Host-header,
videresend til port 8788 og tilføj `COOKIE_SECURE=1` i runtime.env; genskab
containeren for at indlæse ændringen. Brug herefter altid HTTPS-adressen.

Docker og HP-plugin-installationen er endnu ikke kørt i udviklingsmiljøet.
Ved fejl: gem fejltekst og trin, men fjern adgangskoder og dokumentindhold.
Se README for backup, opdatering og gendannelse. Kør ikke installationen over en
aktiv container; scriptet stopper, hvis `scanmail` allerede findes.
