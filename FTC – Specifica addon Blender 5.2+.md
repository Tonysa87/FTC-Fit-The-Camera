# FTC – Specifica addon Blender 5.2+

Oct 9, 2026 · @Antonio Sartini

## Scopo

Addon generalista per Blender che calibra una camera su una singola immagine (foto, render, disegno) e la applica alla camera di scena: focale, sensore, posizione e rotazione, con scala reale.

- Sostituisce il flusso esterno tipo fSpy: tutto avviene nel viewport di camera.
- Interfaccia ispirata a [Perspective Plotter](https://perspective-plotter.readthedocs.io/en/latest/): guide interattive, aggiornamento live, modalità a 1/2/3 punti di fuga, misura di riferimento, punto principale.
- Nessuna assunzione su settore, tipo di scena o dispositivo di ripresa.

## Vincoli tecnici

- **Versione:** solo Blender 5.2 o successivi. Formato Extension con `blender_manifest.toml`, `blender_version_min = "5.2.0"`; niente `bl_info` né codice di compatibilità.
- **Licenza:** GPL-3.0-or-later.
- **Dipendenze:** solo moduli inclusi in Blender (`mathutils`, `numpy`, `gpu`, `gpu_extras`, `blf`). Lettura EXIF con parser Python puro, senza wheel esterne.
- **Disegno:** shader built-in del modulo `gpu`, compatibili con Vulkan, Metal e OpenGL.
- **Permessi manifest:** `files`. Nessun accesso di rete.

## Modalità di calibrazione

Tre modalità, tutte con la stessa uscita: camera con Z verso l'alto e scala in unità di scena.

| Modalità | Input dell'utente | Cosa risolve | Scala da |
| --- | --- | --- | --- |
| Punti di fuga | Coppie di linee per 1, 2 o 3 punti di fuga; asse di ciascun punto | Rotazione; focale con 2 o 3 punti | Misura di riferimento lungo un asse, o distanza camera–origine |
| Rettangolo noto | 4 vertici di un rettangolo piano; larghezza e altezza reali | Posa completa; focale se non fornita | Dimensioni del rettangolo |
| Orizzonte | Linea d'orizzonte (2 punti); altezza camera; direzione (yaw) | Beccheggio e rollio; yaw da EXIF o manuale | Altezza camera |

- **Punto principale:** al centro per default, manuale come opzione.
- **Origine:** punto griglia trascinabile (punti di fuga), centro del rettangolo (rettangolo noto), verticale sotto la camera (orizzonte). L'origine si può agganciare a posizione e rotazione del 3D cursor; l'aggancio resta memorizzato, così ritoccando le guide la camera rimane allineata alla scena esistente.
- **Raddrizza orizzonte:** forza rollio zero in qualsiasi modalità.

## Dati camera ed EXIF

L'addon non inventa mai un dato mancante: lo segnala e lo fa inserire a mano.

- **Campi mostrati:** marca e modello, obiettivo, focale reale, focale equivalente 35 mm, larghezza sensore, dimensioni immagine, GPS, direzione.
- **Stato per campo:** da EXIF, mancante (evidenziato), inserito a mano.
- **Avviso** quando focale o sensore mancano, con marca e modello in evidenza se presenti.
- **Inserimento manuale:** focale reale + larghezza sensore, oppure focale equivalente 35 mm.
- Le modalità che richiedono la focale (punti di fuga a 1 punto, orizzonte) restano disabilitate finché non è disponibile.

## Interfaccia

Pannello nella sidebar (tab "Camera Match") più operatore modale nel viewport di camera, con aggiornamento in tempo reale.

### Pannello

1. **Carica immagine:** crea o usa la camera attiva, imposta lo sfondo, adatta risoluzione e aspetto, legge l'EXIF.
2. **Dati camera:** riquadro descritto sopra.
3. **Modalità** e relativi parametri (numero di punti di fuga e assi, dimensioni del rettangolo, altezza camera, punto principale, misura di riferimento).
4. **Calibra:** avvia l'operatore modale.
5. **Aggiornamento live**, **Congela guide**, **Raddrizza orizzonte**, **Reset**.
6. **Opacità:** cursori per l'opacità dell'immagine di sfondo della camera e della griglia di verifica (espongono proprietà già esistenti in Blender).
7. **Risultati:** focale, campo visivo, altezza camera, beccheggio, rollio, yaw; avviso se la configurazione non è risolvibile.

### Viewport

- Guide colorate per asse con i colori degli assi del tema di Blender (X rosso, Y verde, Z blu), senza opzioni di personalizzazione; maniglie trascinabili.
- Overlay: griglia sul piano Z=0, linea d'orizzonte.
- Rettangolo noto: 4 maniglie collegate, primo vertice marcato.
- Maniglia d'orizzonte, in tutte le modalità: trascinata in verticale corregge a mano il beccheggio; la correzione si azzera quando si modificano le guide. In modalità orizzonte la linea ha anche 2 maniglie per definirla.
- Testo di stato nell'header con modalità attiva e scorciatoie.

### Move Along View

Strumento per spostare oggetti selezionati o, in Edit Mode, vertici selezionati lungo il raggio che parte dalla camera attiva: il punto resta fermo nell'immagine e cambia solo la distanza dalla camera.

- Operatore modale: trascinamento del mouse per avvicinare o allontanare, Shift per il movimento fine, inserimento numerico della distanza, Invio per confermare, Esc per annullare.
- Opzione per scalare l'oggetto in proporzione alla distanza, così la sua dimensione apparente nell'immagine resta invariata.
- Funziona con qualsiasi camera attiva, anche fuori dall'operatore di calibrazione.

### Scorciatoie

| Tasto | Azione |
| --- | --- |
| Trascina con tasto sinistro | Sposta maniglia |
| Shift (tenuto) | Movimento fine |
| Ctrl (tenuto) | Snap a maniglia o origine |
| 1 / 2 / 3 | Asse attivo X / Y / Z |
| F | Inverte l'asse della guida selezionata |
| H | Raddrizza orizzonte |
| Ctrl+Z / Ctrl+Shift+Z | Undo e redo interni |
| Invio | Applica e chiudi |
| Esc / tasto destro | Esci mantenendo le guide |

Pan e zoom del viewport restano attivi durante l'operatore.

## Solver

Modulo Python puro, senza `bpy`: riceve punti in pixel e parametri, restituisce intrinseci e matrice camera→mondo. Coordinate rispetto al punto principale p.

### Punti di fuga

- Punto di fuga: intersezione ai minimi quadrati delle linee della stessa coppia (omogenee, SVD).
- Focale da 2 punti di fuga:

```latex
f^2 = -\,(\mathbf{v}_1 - \mathbf{p}) \cdot (\mathbf{v}_2 - \mathbf{p})
```

- Valore negativo = configurazione impossibile, segnalata.
- 3 punti di fuga: p = ortocentro del triangolo dei punti di fuga.
- 1 punto di fuga: focale fornita; secondo asse dalla direzione dell'orizzonte.
- Rotazione: direzioni (vᵢ − p, −f) normalizzate, terzo asse per prodotto vettoriale, ortonormalizzazione SVD, terna destrorsa.
- Scala: misura di riferimento lungo un asse (raggio del punto misurato intersecato con la retta dell'asse).

### Rettangolo noto

- Omografia piano→immagine dai 4 vertici, DLT normalizzata.
- Focale nota: posa da K⁻¹H, r₃ = r₁ × r₂, SVD.
- Focale ignota: due vincoli di Zhang (ortogonalità e uguale norma) con p al centro; media delle stime positive. Rettangolo quasi frontale → stima instabile, segnalata.

### Orizzonte

- Rollio: inclinazione della linea d'orizzonte.
- Beccheggio, con d distanza con segno tra p e l'orizzonte:

```latex
\theta = \arctan\left(\frac{d}{f}\right)
```

- Posizione: (0, 0, h). Yaw da EXIF o manuale.

### Uscita verso Blender

- Conversione al sistema camera di Blender (sguardo lungo −Z, Y in alto).
- `lens` = fₚₓ · `sensor_width` / larghezza immagine; `sensor_fit` secondo orientamento.
- Punto principale manuale → `shift_x`, `shift_y`.

### Riferimenti

- [fSpy, codice sorgente](https://github.com/stuffmatic/fSpy) (GPL-3).
- Caprile, Torre (1990), *Using vanishing points for camera calibration*, IJCV.
- Guillou et al. (2000), *Using vanishing points for camera calibration and coarse 3D reconstruction from a single image*, The Visual Computer.
- Zhang (2000), *A flexible new technique for camera calibration*, IEEE TPAMI.
- Hartley, Zisserman (2004), *Multiple View Geometry in Computer Vision*.

## Architettura e persistenza

```
camera_match/
  blender_manifest.toml
  __init__.py
  solver/
    vp.py          # punti di fuga
    plane.py       # rettangolo noto
    horizon.py     # orizzonte
    convert.py     # solver → camera Blender
  exif.py          # parser EXIF minimo
  props.py         # PropertyGroup per camera
  ops_load.py      # carica immagine
  ops_modal.py     # operatore modale, maniglie, undo interno
  ops_move_view.py # Move Along View
  draw.py          # overlay gpu
  ui.py            # pannello
tests/
  test_vp.py  test_plane.py  test_horizon.py
```

- Stato in un `PropertyGroup` sulla camera: modalità, maniglie in coordinate normalizzate 0–1, parametri, dati EXIF.
- Ogni camera ha le sue guide; tutto si salva nel `.blend`.
- La camera viene scritta solo in modalità live o con "Applica". L'aggiornamento live è attivo solo dentro l'operatore: uscendo si ferma, così le chiavi d'animazione della camera non vengono sovrascritte.

## Fasi di sviluppo e test

1. **F0 – Solver.** Test sintetici: camera nota in Blender, punti proiettati, il solver ritrova focale entro l'1% e angoli entro 0,2°.
2. **F1 – Carica immagine ed EXIF.** Riquadro dati camera, campi mancanti, inserimento manuale.
3. **F2 – Punti di fuga.** Operatore modale, 1/2/3 punti, misura di riferimento, punto principale.
4. **F3 – Rettangolo noto.**
5. **F4 – Orizzonte.**
6. **F5 – Rifinitura.** Undo interno, congela guide, maniglia d'orizzonte, opacità, Move Along View, più camere, messaggi d'errore.

Ogni fase da F2 in poi si verifica confrontando il risultato con fSpy sulle stesse immagini.
