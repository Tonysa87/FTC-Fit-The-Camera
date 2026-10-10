# FTC – Fit The Camera

Estensione per Blender 5.2+ che calibra una camera su una singola immagine
(foto, render, disegno): focale, sensore, posizione e rotazione, con scala reale.
Specifica completa: `FTC – Specifica addon Blender 5.2+.md`.

## Struttura

```
fit_the_camera/          # l'estensione (questa cartella diventa lo zip)
  blender_manifest.toml
  __init__.py            # registrazione dei moduli
  solver/                # numpy puro, senza bpy
    common.py            # convenzioni, CameraSolution, geometria condivisa
    vp.py  plane.py  horizon.py  convert.py
  exif.py                # parser EXIF in Python puro (JPEG, TIFF, PNG, WebP)
  props.py               # PropertyGroup salvato su ogni Camera (camera.ftc)
  calibrate.py           # ponte impostazioni -> solver -> camera Blender
  ops_load.py            # Carica immagine, copia raddrizzata (orientamento EXIF)
  ops_modal.py           # operatore modale, undo interno, Applica/Reset/Aggancio
  ops_move_view.py       # Move Along View
  draw.py                # overlay gpu (guide, maniglie, griglia, orizzonte)
  ui.py                  # pannello nella sidebar, tab "FTC"
  translations.py        # traduzione italiana dell'interfaccia
tests/                   # pytest: solver ed EXIF, fuori da Blender
tests_blender/           # test dentro Blender (headless e con GUI simulata)
scripts/                 # build, Blender locale, runner dei test
```

## Convenzioni

- Coordinate immagine in pixel, origine in basso a sinistra, y verso l'alto.
  Le maniglie sono salvate normalizzate 0–1 nello stesso sistema.
- Sistema camera = quello di Blender: x a destra, y in alto, sguardo lungo −Z.
- Mondo destrorso con Z in alto. `rotation` del solver è camera→mondo e va
  direttamente in `matrix_world`.
- Yaw in gradi, orario da +Y (come una bussola con il nord su +Y).
- Il sensore si applica al lato lungo dell'immagine (`sensor_fit` HORIZONTAL o
  VERTICAL secondo l'orientamento). Senza sensore noto si usa 36 mm, che dà la
  focale equivalente 35 mm.

## Ambiente di sviluppo (Ubuntu / WSL)

Serve [pixi](https://pixi.sh). Python e numpy sono gli stessi di Blender 5.2 (3.13, 2.3).

```bash
pixi install
pixi run test            # solver ed EXIF (pytest)
pixi run lint            # ruff
pixi run validate        # valida il manifest con Blender
pixi run blender-tests   # build + installazione in un profilo isolato + test headless
pixi run check           # tutto quanto sopra
pixi run build           # crea dist/fit_the_camera-<versione>.zip
pixi run gui-tests       # facoltativo: GUI simulata, apre una finestra Blender via WSLg
```

Al primo uso gli script scaricano Blender 5.2 per Linux in `.tools/`
(verificato con sha256). I test usano un profilo utente temporaneo: le
preferenze reali di Blender non vengono toccate.

## Installazione su Windows

1. `pixi run build` crea lo zip in `dist/`.
2. In Blender: *Edit › Preferences › Get Extensions › ⌄ › Install from Disk…* e
   scegli lo zip (raggiungibile da Windows in
   `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\`).
3. Per aggiornare, reinstalla lo zip nuovo nello stesso modo.

Per l'interfaccia in italiano: *Preferences › Interface › Translation*, lingua
Italiano, con le voci *Interface* e *Tooltips* attive.
