# FTC – Sviluppo

Guida utente: [`README.it.md`](../README.it.md) / [`README.md`](../README.md).
Specifica originale: `FTC – Specifica addon Blender 5.2+.md` (il nome definitivo è
FTC; la specifica parla ancora di "Camera Match"). Pubblicazione su Blender
Extensions: [`PUBLISHING.md`](PUBLISHING.md).

## Struttura

```
fit_the_camera/          # l'estensione (questa cartella diventa lo zip)
  blender_manifest.toml
  __init__.py            # registrazione dei moduli
  solver/                # numpy puro, senza bpy (testabile con pytest)
    common.py            # convenzioni, CameraSolution, piani, reframe
    vp.py                # punti di fuga 1/2/3, segni degli assi, aderenza
    refine.py            # minimi quadrati (Levenberg-Marquardt), focale nota come vincolo
    scale.py             # cubo di scala
    plane.py             # rettangolo noto (omografia, vincoli di Zhang)
    horizon.py           # orizzonte
    convert.py           # soluzione -> camera Blender, focale da mm / 35 mm
  exif.py                # parser EXIF in Python puro (JPEG, TIFF, PNG, WebP)
  props.py               # PropertyGroup salvato su ogni Camera (camera.ftc)
  calibrate.py           # impostazioni -> solver -> camera; incertezza; avvisi
  ops_load.py            # Carica immagine, copia raddrizzata
  ops_modal.py           # operatore modale, undo interno, Applica/Reset
  ops_align.py           # allineamento alla scena
  ops_move_view.py       # Move Along View
  ops_render.py          # Prepara render, ruoli Shadow Catcher / Holdout
  draw.py                # overlay gpu (guide, maniglie, griglia, orizzonte, cubo)
  ui.py                  # pannello
  translations.py        # traduzione italiana
tests/                   # pytest: solver, EXIF, dati da foto reali, fuzz
tests/data/              # linee misurate al sub-pixel su foto reali (senza foto)
tests_blender/           # test dentro Blender (headless; GUI simulata facoltativa)
scripts/                 # build, Blender locale, runner dei test
scripts/probes/          # sonde diagnostiche: bash scripts/probe.sh <nome>
samples/                 # foto di prova (ignorata da git: contengono GPS)
README.md / README.it.md # guida utente (inglese / italiano)
LICENSE                  # GPL-3.0-or-later
docs/CHANGELOG.md
docs/DEVELOPMENT.md      # questo file
docs/PUBLISHING.md       # pubblicazione su extensions.blender.org
docs/TEST_GUI.md         # checklist del test a mano in Blender (da fare: 1.0.0)
```

## Convenzioni

- Coordinate immagine in pixel, origine in basso a sinistra, y verso l'alto.
  Le maniglie sono salvate normalizzate 0–1 nello stesso sistema.
- Sistema camera = Blender: x a destra, y in alto, sguardo lungo −Z.
- Mondo destrorso con Z in alto. `rotation` del solver è camera→mondo e va
  direttamente in `matrix_world`.
- Segno degli assi: lungo la prima guida del gruppo (prima → seconda maniglia),
  calcolato con la velocità d'immagine, stabile anche con punti di fuga all'infinito.
- Yaw in gradi, orario da +Y (bussola con il nord su +Y).
- Piano di riferimento: XY (pavimento), XZ (parete rivolta a −Y), YZ (parete
  rivolta a +X), y locale verso l'alto sulle pareti.
- Sensore = lato lungo del sensore intero; la parte coperta dall'immagine si
  ricava dal formato nativo (`exif.native_frame`).

## Ambiente di sviluppo (Ubuntu / WSL)

Serve [pixi](https://pixi.sh). Python e numpy sono gli stessi di Blender 5.2 (3.13, 2.3).

```bash
pixi install
pixi run test            # solver, EXIF, foto reali, fuzz (pytest)
pixi run lint            # ruff
pixi run validate        # valida il manifest con Blender
pixi run blender-tests   # build + installazione in profilo isolato + test headless
pixi run check           # tutto quanto sopra
pixi run build           # crea dist/fit_the_camera-<versione>.zip
pixi run gui-tests       # facoltativo: GUI simulata via WSLg (a volte si blocca all'avvio)
```

Al primo uso gli script scaricano Blender 5.2 per Linux in `.tools/` (sha256
verificato). I test usano un profilo utente temporaneo: le preferenze reali di
Blender non vengono toccate.

## Installazione su Windows (build locale)

1. `pixi run build` crea lo zip in `dist/`.
2. Blender: *Edit › Preferences › Get Extensions › ⌄ › Install from Disk…* e scegli
   `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-<versione>.zip`.
3. Per aggiornare, reinstalla lo zip nuovo e riavvia Blender.

Interfaccia in italiano: *Preferences › Interface › Translation*, lingua Italiano.
