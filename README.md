# FTC – Fit The Camera

Estensione per Blender 5.2+ che calibra una camera su una singola immagine
(foto, render, disegno): focale, sensore, posizione e rotazione, con scala reale.
Specifica originale: `FTC – Specifica addon Blender 5.2+.md` (il nome definitivo è
FTC; la specifica parla ancora di "Camera Match"). Storia delle versioni:
[`docs/CHANGELOG.md`](docs/CHANGELOG.md).

## Uso

Sidebar del viewport (N) › tab **FTC**.

1. **Load Image** – usa la camera attiva (o la crea), imposta lo sfondo, adatta la
   risoluzione, legge l'EXIF e inquadra la camera. Foto salvate ruotate
   (orientamento EXIF): **Make Upright Copy**.
2. **Camera Data** – marca, modello, focale reale, equivalente 35 mm, sensore,
   GPS, direzione; ogni campo è *da EXIF*, *mancante* (rosso) o *manuale*.
   Il sensore va inserito come nelle schede tecniche (lato lungo del sensore
   intero), anche per foto ritagliate. Immagini non 4:3 / 3:2 sono trattate come
   ritaglio centrato di un sensore 4:3 (come fanno i telefoni).
3. **Calibration** – modalità e parametri, poi **Calibrate** (operatore modale nel
   viewport camera). Scorciatoie nell'header: trascina = sposta maniglia,
   Shift = fine, Ctrl = snap, 1/2/3 = asse, F = inverti verso, H = raddrizza,
   Ctrl+Z / Ctrl+Shift+Z = undo/redo interni, Invio = applica, Esc/RMB = esci.
   Accanto a ogni asse un pulsante ne inverte il verso.
   **Focale**: *Nota + guide* (default: parte dalla focale di Camera Data e le guide
   la correggono per quanto la misurano; se è sconosciuta la risolvono), *Solo
   guide*, *Solo nota*. **Scala**: *Cubo di scala* (default) o *Misura di
   riferimento*.
4. **Align to Scene** – porta il piano calibrato (XY, XZ, YZ) sul 3D cursor, sulla
   faccia attiva (Edit Mode) o sull'oggetto attivo; Ruota 90° / Inverti.
5. **Results** – focale, FOV, altezza, angoli, **incertezza** (focale ± %,
   orientamento ± °) e **aderenza guide** (scarto massimo); avvisi in giallo/rosso.
6. **Tools › Move Along View** – sposta oggetti/vertici lungo il raggio dalla camera
   (anche da *Object/Mesh › Transform*).

### Modalità

| Modalità | Input | Note |
| --- | --- | --- |
| Punti di fuga 1 | 2 guide per l'asse 1 + una linea lungo l'asse 2 | richiede la focale |
| Punti di fuga 2 | 2 guide per asse | opzioni: focale, *Linea terzo asse* |
| Punti di fuga 3 | 2 guide per asse | punto principale al centro (default), manuale o *Risolvi* (ortocentro, instabile) |
| Rettangolo noto | 4 angoli, larghezza/altezza reali | su XY, XZ o YZ; focale come sopra |
| Orizzonte | linea d'orizzonte, altezza camera, yaw | richiede la focale |

### Cubo di scala

Un cubo wireframe di lato noto (10 cm … 10 m o misura personalizzata) appoggiato sul
piano di riferimento, con gli spigoli nei colori degli assi. La maniglia alla base
scorre sul piano (mettila ai piedi di un oggetto di altezza nota); quella in cima
scorre lungo lo spigolo verticale: portala all'altezza dell'oggetto e la scala
della scena si adegua. Con la *Misura di riferimento*, nel rettangolo noto e
nell'orizzonte la scala è già nota e il cubo è solo un controllo visivo (si può
nascondere in *Opacity*).

### Consigli (verificati su foto reali, vedi `tests/data`)

- Il verso **+** di un asse va lungo la **prima** guida del gruppo, dalla prima alla
  seconda maniglia (freccia sulla guida). F o il pulsante accanto all'asse lo
  invertono. Il terzo asse segue dai primi due (riferimento destrorso): invertirlo
  inverte anche l'asse 2 (o l'1 se il 2 è Z); la sua freccia indica il verso reale.
- Due punti di fuga **solo sul pavimento** non misurano la verticale: le estrusioni
  in Z possono deviare di gradi. Aggiungi la **Linea terzo asse** (uno stipite) o
  usa 3 punti di fuga; con la focale nota (*Nota + guide*) l'incertezza scende
  sotto 1°.
- Un punto di fuga lontanissimo (parete quasi frontale) rende la focale
  indeterminabile: usa la focale nota o linee in un'altra direzione.
- Le linee "che sembrano parallele" non sempre lo sono (binari luci, facciate di
  edifici diversi, fughe di piastrelle). Con 3 gruppi o la focale nota l'**aderenza
  guide** lo rivela.
- La focale EXIF può essere sbagliata (foto zoomate o ritagliate). Con *Nota +
  guide*, se le guide non riescono ad accordarsi con essa (scarto > 1°) e con la
  propria vanno molto meglio, prevalgono loro e un avviso riporta di quanto
  l'hanno cambiata (riga *Rispetto alla nota* nei risultati). Due punti di fuga
  di cui uno lontano, o un rettangolo, non bastano a scoprirlo: servono 3 gruppi.
- **Raddrizza orizzonte** forza il rollio a 0: se la foto è inclinata la camera
  non segue più le guide (l'avviso indica quanti gradi ha tolto).

## Struttura

```
fit_the_camera/          # l'estensione (questa cartella diventa lo zip)
  blender_manifest.toml
  __init__.py            # registrazione dei moduli
  solver/                # numpy puro, senza bpy (testabile con pytest)
    common.py            # convenzioni, CameraSolution, piani, reframe
    vp.py                # punti di fuga 1/2/3, segni degli assi, aderenza
    refine.py            # minimi quadrati (Levenberg-Marquardt) su tutte le guide
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
  draw.py                # overlay gpu (guide, maniglie, griglia, orizzonte)
  ui.py                  # pannello
  translations.py        # traduzione italiana
tests/                   # pytest: solver, EXIF, dati da foto reali, fuzz
tests/data/              # linee misurate al sub-pixel su foto reali (senza foto)
tests_blender/           # test dentro Blender (headless; GUI simulata facoltativa)
scripts/                 # build, Blender locale, runner dei test
samples/                 # foto di prova (ignorata da git: contengono GPS)
docs/CHANGELOG.md
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

## Installazione su Windows

1. `pixi run build` crea lo zip in `dist/`.
2. Blender: *Edit › Preferences › Get Extensions › ⌄ › Install from Disk…* e scegli
   `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-<versione>.zip`.
3. Per aggiornare, reinstalla lo zip nuovo e riavvia Blender.

Interfaccia in italiano: *Preferences › Interface › Translation*, lingua Italiano.
