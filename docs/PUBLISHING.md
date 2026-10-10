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

## Da preparare per la bozza

| Elemento | Requisito | Stato |
| --- | --- | --- |
| Zip | `pixi run build` (manifest validato) | pronto: `dist/fit_the_camera-<ver>.zip` |
| Icona | PNG, al massimo 256 × 256 (obbligatoria) | **da fare** |
| Immagine in evidenza (*featured image*) | JPEG, PNG o WebP (obbligatoria; mostrata in home) | **da fare** |
| Anteprime | almeno 1: JPEG, PNG, WebP o video MP4, con didascalia | **da fare** |
| Descrizione | deve elencare tutto ciò che fa l'estensione | bozza sotto |
| Support URL | issue tracker del repository | `https://github.com/Tonysa87/FTC---Fit-The-Camera/issues` |
| Website | nel manifest | GitHub |

Immagini: niente logo di Blender, niente GIF pesanti nella descrizione. Le
immagini incluse nello zip devono essere CC0 (FTC non ne include). Suggerimento
per le anteprime: overlay delle guide su una foto vera, pannello FTC, render con
oggetto e ombra sopra la foto, prima/dopo.

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

## Da decidere prima di caricare

- **Maintainer**: lo schema chiede `"Nome <email>"`; ora è solo il nome (la
  validazione passa). Se si aggiunge un'email sarà pubblica sulla pagina.
- **Test GUI** della 1.0.0 (`docs/TEST_GUI.md`): i moderatori provano le
  funzioni di base; meglio caricare dopo il test.

## Bozza della descrizione (inglese, Markdown)

```markdown
Match a camera to a single image – a photo, a render or a drawing – then render
3D objects over it with their shadows.

**Calibration**
- Vanishing points (1, 2 or 3), a known rectangle or the horizon line
- Focal length, sensor and GPS read from EXIF; the guides refine a known focal
  length or solve it
- Real-world scale from a scale cube of known size or a reference distance
- Uncertainty of the result and guide fit, with warnings for lines that are not
  really parallel, a wrong EXIF focal length or a far vanishing point
- Align the calibrated floor or wall to the 3D cursor, a face or an object
- Move Along View: move objects along the camera rays, keeping them in place in
  the image

**Render over the photo**
- Prepare Render: Standard view transform (the photo comes out unchanged),
  transparent film, Cycles, and a compositor that puts the render over the photo
  with the Shadow Catcher pass – or a transparent output for other programs
- Object roles: shadow catcher and holdout for the objects standing in for real
  surfaces and objects of the photo

Sidebar › FTC tab. Interface in English and Italian.
Documentation: https://github.com/Tonysa87/FTC---Fit-The-Camera
```

## Fonti

- [About – come pubblicare](https://extensions.blender.org/about/)
- [Terms of Service](https://extensions.blender.org/terms-of-service/)
- [Moderation guidelines](https://developer.blender.org/docs/features/extensions/moderation/guidelines/)
- [Add-on guidelines](https://developer.blender.org/docs/handbook/extensions/addon_guidelines/)
- [Manifest schema 1.0.0](https://developer.blender.org/docs/features/extensions/schema/1.0.0/)
- [Manuale – How to create extensions](https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html)
- [Codice del sito: requisiti di icona, immagine in evidenza e anteprime](https://projects.blender.org/infrastructure/extensions-website/src/branch/main/extensions/forms.py)
