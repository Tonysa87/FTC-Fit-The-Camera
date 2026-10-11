# Pubblicare FTC su Blender Extensions

Riassunto delle regole di [extensions.blender.org](https://extensions.blender.org)
(letto il 2026-10-10). Fonti in fondo.

## Procedura

1. **Account**: serve un Blender ID (pulsante *Sign in* in alto sul sito).
2. **Termini**: solo software libero GPL; per gli add-on serve
   GPL-3.0-or-later (FTC lo è: `LICENSE`, manifest).
3. **Prova** lo zip con *Install from Disk…* su un Blender pulito (stessa
   versione minima del manifest: 5.2).
4. **Carica** lo zip in [extensions.blender.org/submit](https://extensions.blender.org/submit/):
   il sito legge il manifest e crea una bozza (*draft*).
5. **Completa la bozza** (sotto) e premi *Submit for review*.
6. **Revisione**: l'estensione entra nella
   [coda di approvazione](https://extensions.blender.org/approval-queue/); i
   moderatori la provano in Blender e scrivono nei commenti della pagina. Si
   risponde lì e si carica una versione corretta se richiesto. Dopo
   l'approvazione l'estensione è pubblica e installabile da *Get Extensions*.
7. **Aggiornamenti**: alzare `version` nel manifest, `pixi run build`, poi
   *Upload new version* dalla pagina dell'estensione (con le note di versione).
   Blender non aggiorna da solo: l'utente vede l'aggiornamento in *Get
   Extensions*.

## Materiale (2026-10-11: 1.0.0 inviata, in attesa di revisione)

Il materiale sta in `extensions_listing/`, cartella locale esclusa da git (vedi
il suo README): immagini in `extensions_listing/upload/`, testi e didascalie in
`extensions_listing/description.md`.

| Elemento | Requisito | Stato |
| --- | --- | --- |
| Zip | `pixi run build` (manifest validato) | pronto: `dist/fit_the_camera-1.0.0.zip`, uguale a quello della release GitHub |
| Icona | PNG, al massimo 256 × 256 (obbligatoria) | `upload/icon.png` |
| Immagine in evidenza | JPEG, PNG o WebP (obbligatoria; in home in un riquadro 16:9) | `upload/00_featured.jpg` (1920 × 1080) |
| Anteprime | almeno 1: JPEG, PNG, WebP o MP4, didascalia ≤ 255 caratteri; ridotte senza ritaglio | `upload/01…05_*.jpg` |
| Descrizione | deve elencare tutto ciò che fa l'estensione | `description.md` |
| Support URL | issue tracker del repository | `https://github.com/Tonysa87/FTC-Fit-The-Camera/issues` |
| Website | nel manifest | GitHub |

Immagini: niente logo di Blender, niente GIF pesanti nella descrizione. Le
immagini incluse nello zip devono essere CC0 (FTC non ne include).

## Compilare la bozza sul sito (passo per passo)

1. <https://extensions.blender.org> › *Sign in* con il Blender ID (crealo se
   non c'è).
2. <https://extensions.blender.org/submit/>: carica
   `dist/fit_the_camera-1.0.0.zip` e accetta i termini (licenza GPL). Il sito
   legge nome, versione, tagline, licenza, tag e permessi dal manifest e apre la
   bozza; se il manifest non va, lo dice qui.
3. Nella bozza (pagina *Edit* dell'estensione):
   - **Description**: incolla la sezione *Description* di `description.md`
     (Markdown).
   - **Support URL**: l'indirizzo delle issue (in `description.md`).
   - **Icon**: `upload/icon.png`.
   - **Featured image**: `upload/00_featured.jpg`.
   - **Previews**: aggiungi `01…05_*.jpg` nell'ordine, ognuna con la sua
     didascalia (tabella in `description.md`).
   - Salva (*Save draft*) e controlla l'anteprima della pagina.
4. *Submit for review*. L'estensione va nella coda di approvazione: i commenti
   dei moderatori arrivano per email e sulla pagina dell'estensione.
5. Se chiedono modifiche: correggi, alza `version` (es. 1.0.1) in
   `fit_the_camera/blender_manifest.toml` e `pixi.toml`, `pixi run check`,
   `pixi run build`, poi *Upload new version* sulla pagina dell'estensione e
   rispondi nei commenti. Pubblica la stessa versione anche come release GitHub.
6. Dopo l'approvazione l'estensione compare in *Get Extensions* dentro Blender
   (cercando "FTC" o "Fit The Camera") e sul sito.

## Regole già verificate su FTC

- Manifest: tutti i campi pieni; tagline ≤ 64 caratteri senza punto finale;
  `permissions.files` (una frase breve senza punto) perché legge l'immagine e
  l'EXIF; niente `network`. Niente sezione `[build]` con i valori di default
  (i moderatori la segnalano).
- Codice: import relativi, nessuna modifica a `sys.path`, nessun riferimento a
  `bl_ext`, nessuna scrittura nella cartella dell'add-on (`open` solo in lettura
  per l'EXIF), nessuna rete, nessun auto-updater, nessuna dipendenza esterna
  (numpy è incluso in Blender), `ruff check` pulito.
- Nome senza la parola "Blender"; nessuna pubblicità o link di donazione
  nell'interfaccia (sono ammessi solo nella descrizione sul sito).

## Scelte fatte

- **Maintainer**: solo il nome, senza email (lo schema suggerisce
  `"Nome <email>"`, ma la validazione passa; un'email sarebbe pubblica).
- **Test GUI** della 1.0.0 (`docs/TEST_GUI.md`) fatto dall'autore il 2026-10-11.

## Fonti

- [About – come pubblicare](https://extensions.blender.org/about/)
- [Terms of Service](https://extensions.blender.org/terms-of-service/)
- [Moderation guidelines](https://developer.blender.org/docs/features/extensions/moderation/guidelines/)
- [Add-on guidelines](https://developer.blender.org/docs/handbook/extensions/addon_guidelines/)
- [Manifest schema 1.0.0](https://developer.blender.org/docs/features/extensions/schema/1.0.0/)
- [Manuale – How to create extensions](https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html)
- [Codice del sito: requisiti di icona, immagine in evidenza e anteprime](https://projects.blender.org/infrastructure/extensions-website/src/branch/main/extensions/forms.py)
