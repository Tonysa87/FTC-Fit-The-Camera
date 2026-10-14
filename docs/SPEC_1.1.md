# FTC 1.1 – Specifica

Oct 14, 2026 · @Antonio Sartini

## Scopo

La 1.0 copre bene le foto con linee parallele chiare: interni, facciate,
pavimenti. La 1.1 porta FTC **all'aperto e nel mondo reale**:

1. **Sole** – una luce solare orientata come quella della foto, dall'EXIF
   (data, ora, GPS, bussola) o da un'ombra visibile nell'immagine.
2. **Punti noti** – nuova modalità di calibrazione da corrispondenze punto
   immagine ↔ punto 3D della scena, per le foto senza linee parallele (campi
   aperti, paesaggi, rovine).

Più tre aggiunte piccole: più di due linee per punto di fuga, import dei
progetti fSpy, report di calibrazione.

In una riga, per le note di versione: *"FTC now works outdoors: calibrate from
known points and get the real sun."*

## Principi (invariati dalla 1.0)

- **Generalista**: nessuna assunzione su settore, tipo di scena o dispositivo.
  Niente funzioni legate a un flusso di lavoro preciso.
- **Solo Blender 5.2+**, GPL-3.0-or-later, solo moduli inclusi in Blender
  (`numpy`, `mathutils`, `gpu`, `blf`), **nessun accesso di rete**.
- **Il solver resta senza `bpy`** (`solver/`), testabile con pytest.
- **Solo gizmo e strumenti nativi** per spostare oggetti: niente operatori di
  trasformazione propri (scelta confermata dopo la 1.0).
- **Mai inventare un dato mancante**: lo si segnala e lo si fa inserire a mano.
- **Enum salvati per indice** nei `.blend`: le nuove voci vanno in fondo, mai
  riordinare le esistenti.
- **Tag del manifest**: restano `Camera`, `Render` (i moderatori tolgono i tag
  generici).

## 1. Sole

Nuova sezione **Sun** nel pannello, dopo *Render*. Funziona con qualsiasi
modalità di calibrazione, a calibrazione applicata.

### Due sorgenti, stessa uscita

| Sorgente | Input | Serve |
| --- | --- | --- |
| **Da EXIF** | data e ora di scatto, latitudine e longitudine, direzione della camera rispetto al nord | foto da telefono o camera con GPS |
| **Dall'ombra** | nella foto: piede e cima di un oggetto verticale, punta della sua ombra a terra | qualsiasi foto con un'ombra netta, anche senza EXIF |

Uscita: direzione del sole nel sistema della scena (azimut ed elevazione
rispetto al piano di riferimento e al nord della scena), applicata a una luce
Sun.

### Da EXIF

- **Data e ora**: da leggere in `exif.py`, che oggi non le legge.
  - `GPSDateStamp` + `GPSTimeStamp` (UTC) quando presenti: sono la fonte
    migliore.
  - Altrimenti `DateTimeOriginal` + `OffsetTimeOriginal`.
  - Senza offset: ora locale con fuso **inserito a mano**, con avviso. Niente
    fuso dedotto dalla longitudine: sbaglia con l'ora legale.
- **Posizione**: latitudine e longitudine, già lette.
- **Nord della scena**: la camera calibrata ha una direzione di vista nella
  scena; `GPSImgDirection` dice dove guardava rispetto al nord. Il nord della
  scena è la direzione di vista orizzontale ruotata di −bearing.
  - `GPSImgDirectionRef = M` (magnetico): campo **declinazione** a mano,
    default 0, con avviso. Nessun modello geomagnetico incluso.
  - La bussola dei telefoni sbaglia spesso di 5–15°: campo **correzione del
    nord** a mano e confronto con l'ombra quando c'è (vedi sotto).
  - Senza direzione nell'EXIF: nord a mano (angolo, oppure "il nord è lungo
    l'asse +Y della scena").
- **Posizione del sole**: algoritmo NOAA, approssimazione dello SPA,
  accurato a circa 0,01°. Solver puro in `solver/sun.py`, senza dipendenze.
  Non usare l'estensione *Sun Position* di Blender: non è una dipendenza
  ammessa.
- **Sole sotto l'orizzonte** (foto notturna o ora sbagliata): errore chiaro,
  nessuna luce cambiata.

### Dall'ombra

Tre maniglie nell'operatore modale, colore giallo:

1. **piede** dell'oggetto verticale, sul piano di riferimento;
2. **cima** dell'oggetto, sulla verticale del piede (stessa regola della
   maniglia alta del cubo di scala);
3. **punta dell'ombra** della cima, sul piano di riferimento.

Piede e punta si ricavano con raggio ∩ piano, la cima con il punto della
normale più vicino al raggio. Queste funzioni esistono già in
`solver/scale.py` e `solver/vp.py`. Direzione del sole = cima − punta,
normalizzata. Dà azimut ed elevazione **senza EXIF e senza nord**.

### Le due sorgenti insieme

Con EXIF e ombra disponibili, l'ombra misura il nord vero: l'azimut del sole
calcolato meno l'azimut dell'ombra misurato. Il pannello mostra la
**differenza con la bussola** (es. "la bussola sbaglia di 8°") e permette
*Use Shadow North*. È il controllo più utile per le foto da telefono.

### Luce

- Ruota la luce Sun **attiva o selezionata**.
- **Decisione aperta**: se non c'è una Sun, FTC ne crea una ("FTC Sun") o
  chiede di crearla? La regola della 1.0 è "FTC non crea oggetti per i
  ruoli". La proposta è un pulsante esplicito *New Sun*, mai una creazione
  automatica.
- Intensità, colore e angolo (morbidezza) restano all'utente: FTC imposta
  solo la direzione.
- Opzionale: se il World usa un nodo *Sky Texture*, sincronizzarne
  elevazione e rotazione del sole.
- Il nord della scena si disegna come freccia sul piano di riferimento nella
  sezione *Display*.

### Orientare l'HDRI sul sole

Con un HDRI equirettangolare nel World, FTC lo ruota **solo attorno a Z**
finché il sole dell'HDRI coincide in azimut con il sole calcolato. Così luce
ambiente, riflessi e luce diretta arrivano dalla stessa parte della foto.

**Scelta del sole nell'HDRI**
- Pulsante *Orient HDRI* nella sezione *Sun*, attivo quando il sole è già
  calcolato (da EXIF o da ombra) e il World ha un nodo *Environment Texture*
  in proiezione equirettangolare.
- Si apre un **visore**: una miniatura dell'HDRI (~1024 px di lato lungo)
  disegnata in sovrimpressione nel viewport con `gpu`, come la lente. È più
  semplice che aprire una finestra Image Editor e resta nello stesso operatore
  modale.
- **Proposta automatica**: FTC marca il punto più luminoso (baricentro dei
  pixel oltre il 99,9° percentile di luminanza, sulla miniatura). Di solito è
  il sole.
- L'utente **clicca** per correggerlo (nuvole luminose, riflessi, sole
  coperto), poi *Invio* applica ed *Esc* annulla.
- Sulla miniatura compaiono anche la riga dell'orizzonte e, dopo
  l'applicazione, un mirino dove *dovrebbe* stare il sole calcolato: un
  controllo visivo immediato.

**Calcolo**
- Il clic dà le coordinate (u, v) dell'immagine, con origine in basso a
  sinistra come i pixel di Blender. Da lì si ricavano azimut ed elevazione del
  sole nell'HDRI con la convenzione equirettangolare di Cycles: u = 0,5 guarda
  +X, u cresce in senso orario visto dall'alto, v = 0,5 è l'orizzonte. **Da
  confermare con un test di render** (probe `hdri`) prima di fidarsi.
- Rotazione Z = azimut del sole nell'HDRI − azimut del sole calcolato. Il
  segno va verificato nello stesso probe: il nodo Mapping ruota le coordinate,
  non l'immagine.
- **Elevazione: non si tocca**, si confronta. Se l'elevazione del sole
  nell'HDRI e quella calcolata differiscono oltre ~10°, appare un avviso:
  "l'HDRI è stato ripreso con il sole più alto o più basso, le ombre non
  avranno la stessa lunghezza".

**Nodi del World**
- Se tra *Texture Coordinate* e *Environment Texture* c'è già un *Mapping*,
  FTC cambia solo la sua rotazione Z. X, Y e posizione restano come sono.
- Se manca, FTC inserisce *Texture Coordinate (Generated) → Mapping* con un
  tag `ftc_hdri`, così lo ritrova e non ne aggiunge un secondo.
- World con più Environment Texture: si sceglie quale dalla lista, oppure
  avviso.
- Lettura dei pixel solo sulla miniatura: un HDRI 16k pieno pesa ~2 GB in
  float. Si lavora su una copia ridotta, poi eliminata.

**Insieme alla luce Sun**: è il caso tipico. La Sun dà ombre nette, l'HDRI dà
luce ambiente e riflessi. Il pannello lo dice in una riga: se l'HDRI contiene
già un sole molto forte, conviene abbassare la Sun o l'HDRI per non
raddoppiare la luce diretta.

### Test

- HDRI: un HDRI sintetico con un "sole" in una posizione nota, poi
  clic → rotazione → la direzione del picco nel mondo coincide con il sole
  calcolato entro 0,5°. Il probe `hdri` fa un render Cycles di una sfera
  speculare per confermare convenzioni e segno.
- `solver/sun.py` contro tabelle NOAA per alcune date e località, incluse
  latitudini alte e l'emisfero sud: errore < 0,05°.
- Ombra sintetica: camera nota, palo e ombra proiettati, direzione ritrovata
  entro 0,2°.
- EXIF: nuovi campi in `tests/exif_builder.py` (UTC GPS, offset, senza
  offset).

## 2. Modalità "Punti noti" (PnP)

Nuova voce in fondo all'enum delle modalità: **Known Points**.

### Input

Una lista di coppie, ognuna fatta da una **maniglia nell'immagine** e un
**punto 3D**. Il punto 3D può essere:
- l'origine di un oggetto (empty, palo, picchetto);
- un vertice di una mesh, preso dalla selezione in Edit Mode;
- coordinate scritte a mano.

UI: `UIList` nel pannello con nome, punto 3D, scarto in px e una spunta
on/off per escludere un punto senza cancellarlo. Pulsanti *Add from
Selected*, *Add 3D Cursor* e *Remove*. Nell'operatore modale ogni coppia è
una maniglia con il suo numero; trascinandola il risultato si aggiorna dal
vivo come nelle altre modalità.

### Solver (`solver/pnp.py`)

| Caso | Minimo | Metodo |
| --- | --- | --- |
| Focale nota, punti qualsiasi | 4 | EPnP o DLT su punti normalizzati, poi LM sulla posa (6 parametri) |
| Focale ignota, punti non complanari | 6 | DLT 3×4 → K, R, t (RQ), poi LM su posa + focale (7 parametri) |
| Focale ignota, punti complanari | 4 | Omografia + vincoli di Zhang, come `plane.py` |

- Focale "Known + Guides" come nella 1.0: prior gaussiano nel LM
  (`refine.focal_prior_residual`), stessa logica per decidere quando i punti
  scavalcano l'EXIF.
- Punto principale al centro, con l'opzione manuale come nelle altre
  modalità.
- **Coordinate grandi** (UTM, coordinate di progetto): il solver lavora in
  float64 attorno al baricentro dei punti. Avviso se la scena ha coordinate
  oltre ~10 km dall'origine, dove la precisione float32 di Blender inizia a
  tremare.
- Configurazioni degeneri, da segnalare: punti quasi allineati, tutti
  complanari con focale ignota e vista frontale, meno punti del minimo.

### Uscita

- La camera va **direttamente nelle coordinate della scena**: niente
  origine, niente scala, niente *Align to Scene* (non servono).
- Lo **scarto per punto** in px appare nella lista e accanto alla maniglia,
  in rosso oltre una soglia. È il modo per trovare il punto sbagliato.
- Incertezza con lo stesso metodo della 1.0 (`calibrate.uncertainty`: ogni
  maniglia spostata dell'1‰).
- L'orientamento "FTC" in questa modalità coincide con Global.

### Test

- Sintetici: camera nota, punti proiettati con rumore di 1–2 px; posa entro
  0,2°, focale entro l'1%, per ognuno dei tre casi.
- Un outlier di 50 px deve risultare il punto con lo scarto maggiore.
- Coordinate tipo UTM (x ~ 700000, y ~ 4900000): stesso risultato delle
  coordinate locali.

## 3. Aggiunte piccole

### Più di due linee per punto di fuga

- Pulsante **+** per gruppo, fino a 6 linee. Le nuove maniglie si chiamano
  `vp1_3a`/`vp1_3b` e così via: la `CollectionProperty` per nome resta
  compatibile con i file 1.0, che hanno 2 linee.
- `common.vanishing_point` è già ai minimi quadrati su N linee. Vanno
  adattati `refine.residuals`, `max_misfit`, i default e il disegno.
- La prima linea del gruppo continua a definire il verso dell'asse.
- Test: con 4 linee rumorose l'errore deve scendere rispetto a 2.

### Import dei progetti fSpy

- *File › Import › fSpy Project (.fspy)*, oppure un pulsante in *Load
  Image*.
- Il file è binario: intestazione, stato in JSON, immagine. **Formato da
  verificare sul sorgente di fSpy** (GPL-3) prima di scrivere il parser.
- Si mappano: immagine, modalità 1/2 punti di fuga, linee di controllo, assi,
  punto principale, distanza di riferimento, focale nota. Il resto produce un
  avviso.
- Risultato: nuova camera con foto e guide di FTC, da controllare e
  applicare. Non si copia la camera calcolata da fSpy: si ricalcola.
- Test: due o tre progetti `.fspy` reali in `tests/data/`, con il risultato
  di FTC confrontato con la soluzione salvata da fSpy.

### Report di calibrazione

- *Export Report* in *Results*: file Markdown o JSON con focale, sensore,
  campo visivo, posizione e rotazione della camera, altezza, incertezza, fit
  delle guide e fonte di ogni dato (EXIF o manuale). Se calcolato, anche il
  sole: data, ora e azimut.
- **Permesso del manifest**: oggi `files` dice "Read the reference image and
  its EXIF metadata". Va aggiornato (es. "Read the reference image and its
  EXIF metadata, save calibration reports"), perché i moderatori controllano
  che il testo corrisponda a quello che fa l'estensione.

### Changelog in inglese

`docs/CHANGELOG.md` è in italiano ed è linkato dalle note di versione su
Extensions. Dalla 1.1 il changelog va in inglese, con l'italiano nella guida.

## Fuori dalla 1.1

- **Correzione della distorsione dell'obiettivo**: i telefoni consegnano JPEG
  già corretti, e per il resto c'è il compositor. Costo alto, guadagno basso.
- **Georeferenziazione e CRS** (EPSG, riproiezioni): troppo specialistica.
  La modalità Punti noti con coordinate di progetto copre il caso.
- **Modelli geomagnetici o fusi orari inclusi**: dati che invecchiano.
  Declinazione e fuso si inseriscono a mano.
- **Rete**: nessuna, come nella 1.0.

## Decisioni aperte

1. Sole: pulsante *New Sun* esplicito, o solo una luce scelta dall'utente?
2. Punti noti: bastano oggetti, vertici e coordinate a mano, o servono anche
   punti da un CSV di rilievo? Il CSV può aspettare la 1.2.
3. Import fSpy nella 1.1 o rimandato, se i tempi si allungano.

## Fasi

1. **1.0.x** – correzioni dalle segnalazioni degli utenti (Reddit, issue,
   Extensions), separate dalla 1.1. Con la prima esce il manifest senza il tag
   `3D View`.
2. **S1 – EXIF data e ora**, `solver/sun.py` e test.
3. **S2 – Sole**: sezione *Sun*, sorgente EXIF, luce, freccia del nord.
4. **S3 – Sole dall'ombra** e confronto con la bussola.
5. **P1 – `solver/pnp.py`** con test sintetici dei tre casi.
6. **P2 – Modalità Punti noti**: lista, maniglie, scarti, incertezza.
7. **A1 – Linee extra per punto di fuga.**
8. **A2 – Import fSpy**, **A3 – Report**, changelog in inglese.
9. **Rilascio 1.1.0**:
   - `pixi run check`, test GUI di Antonio su Windows, release GitHub e
     *Upload new version* su Extensions;
   - post di aggiornamento su r/blender con un video breve: punti noti su un
     campo aperto e ombra del CG allineata a quella vera.

Ogni fase si chiude con `pixi run check` verde e un commit su `main`. Le fasi
S e P sono indipendenti: se una delle due si blocca, l'altra può uscire da
sola.

## Riferimenti

- NOAA, *Solar Position Calculator* e relative equazioni (Meeus,
  *Astronomical Algorithms*, 1998).
- Reda, Andreas (2004), *Solar Position Algorithm for Solar Radiation
  Applications*, NREL.
- Lepetit, Moreno-Noguer, Fua (2009), *EPnP: An Accurate O(n) Solution to the
  PnP Problem*, IJCV.
- Hartley, Zisserman (2004), *Multiple View Geometry in Computer Vision*,
  cap. 7 (DLT) e 6 (fattorizzazione RQ).
- Zhang (2000), *A flexible new technique for camera calibration*, IEEE
  TPAMI.
- [fSpy, codice sorgente](https://github.com/stuffmatic/fSpy) (GPL-3), per il
  formato `.fspy`.
- EXIF 2.32 / CIPA DC-008: `DateTimeOriginal`, `OffsetTimeOriginal`,
  `GPSDateStamp`, `GPSTimeStamp`, `GPSImgDirection(Ref)`.
