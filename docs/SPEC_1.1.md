# FTC 1.1 – Specifica

Oct 14, 2026 · @Antonio Sartini

## Scopo

La 1.0 copre bene le foto con linee parallele chiare: interni, facciate,
pavimenti. La 1.1 porta nella scena **la luce vera della foto**:

- **Sole** – una luce solare orientata come quella della foto, dall'EXIF
  (data, ora, GPS, bussola) o da un'ombra visibile nell'immagine.
- **HDRI sul sole** – l'HDRI del World si ruota attorno a Z per avere il suo
  sole nella stessa direzione.

Più due aggiunte piccole: più di due linee per punto di fuga e report di
calibrazione.

In una riga, per le note di versione: *"FTC now gets the real sun: the
light and the HDRI match the photo."*

Una modalità di calibrazione da punti rilevati (PnP) è descritta in
*Possibili sviluppi*, come non prioritaria.

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

Nuova sezione **Fit Sun** nel pannello, dopo *Render* (nomi *Fit Sun* / *Fit HDRI*
scelti da Antonio il 2026-10-14: richiamano *Fit The Camera*, non si traducono). Funziona con qualsiasi
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
  - Senza direzione nell'EXIF: **è il caso normale sui telefoni Android**
    (nessuna delle foto in `samples/`, Motorola e OnePlus, ha
    `GPSImgDirection`; tutte hanno GPS e ora UTC). Va trattato come strada
    principale, non come ripiego. L'elevazione resta esatta (la calibrazione
    conosce la verticale); manca solo il nord, un angolo attorno a Z:
    - **da mappa**: "l'asse +X (o +Y) della scena punta a N°", letto su una
      mappa da una facciata o una strada;
    - **da un punto lontano**: una maniglia su un riferimento riconoscibile
      (punta di un'isola, campanile, cima) e il suo azimut letto sulla
      mappa; il nord = azimut del raggio orizzontale della maniglia − azimut
      inserito. Serve nei paesaggi senza facciate (`samples/IMG_20250630_152535968_HDR.jpg`:
      lago con isola all'orizzonte, calibrazione *Horizon*, sole a ~239°/56°,
      GPS vero). L'errore di parallasse è trascurabile se il punto è lontano;
    - **slider dell'azimut** a occhio: elevazione fissa, si ruota il sole
      finché le ombre del CG coincidono con quelle della foto;
    - **dall'ombra** (sotto), il più preciso.
- Senza GPS: latitudine e longitudine a mano (basta la città: 100 km
  ≈ 1° sul sole). Senza data e ora: solo l'ombra.
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
normale più vicino al raggio.

**Punta dell'ombra anche su un muro.** In `samples/IMG_20260804_185218650.jpg`
(cabina elettrica, sole a ~279°/16°) l'ombra del cartello cade sulla facciata,
non a terra. Con l'origine nello spigolo muro–marciapiede il pavimento (XY) e
il muro (XZ o YZ) passano entrambi per l'origine: la punta si interseca con il
piano scelto per lei (pavimento di default, muro a scelta). È anche la foto di
prova della S3: GPS da cella (`GPSProcessingMethod` = CELLID, errore di km,
< 0,05° sul sole), ora UTC dal GPS, nessuna bussola.

Altra foto di prova S3: `samples/IMG_20230108_110414.jpg` (ponte levatoio,
sole ~162°/22°): ombre nette dei montanti della ringhiera sul piano del
ponte, il caso da manuale (piede, cima, punta tutti sul pavimento).
Grandangolo verso l'alto, 3 punti di fuga; EXIF senza equivalente 35 mm.
L'ora GPS è di 22 s più vecchia dell'orologio: i telefoni scrivono l'ora
dell'ultimo fix, quindi con orologio e GPS concordi l'istante viene
dall'orologio e dal GPS solo il fuso. Queste funzioni esistono già in
`solver/scale.py` e `solver/vp.py`. Direzione del sole = cima − punta,
normalizzata. Dà azimut ed elevazione **senza EXIF e senza nord**.

### Le due sorgenti insieme

Con EXIF e ombra disponibili, l'ombra misura il nord vero: l'azimut del sole
calcolato meno l'azimut dell'ombra misurato. Il pannello mostra la
**differenza con la bussola** (es. "la bussola sbaglia di 8°") e permette
*Use Shadow North*. È il controllo più utile per le foto da telefono.

### Luce

- Ruota la luce Sun **attiva o selezionata**.
- Se non c'è una Sun: pulsante esplicito *New Sun* che crea "FTC Sun", mai
  una creazione automatica (deciso da Antonio, 2026-10-14).
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
- Pulsante *Fit HDRI* nella sezione *Sun*, attivo quando il sole è già
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

## 2. Aggiunte piccole

### Più di due linee per punto di fuga

- Pulsante **+** per gruppo, fino a 6 linee. Le nuove maniglie si chiamano
  `vp1_3a`/`vp1_3b` e così via: la `CollectionProperty` per nome resta
  compatibile con i file 1.0, che hanno 2 linee.
- `common.vanishing_point` è già ai minimi quadrati su N linee. Vanno
  adattati `refine.residuals`, `max_misfit`, i default e il disegno.
- La prima linea del gruppo continua a definire il verso dell'asse.
- Test: con 4 linee rumorose l'errore deve scendere rispetto a 2.

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

## Possibili sviluppi (non prioritari)

### Modalità "Punti noti" (PnP)

**Stato: possibile, non prioritaria.** Serve solo quando in campo, oltre
alla foto, si rilevano (stazione totale, GNSS) punti ben visibili
nell'immagine: spigoli di edifici, pali, angoli di finestre. Nel
fotoinserimento tipico si ha solo la foto, quindi resta fuori dalla 1.1. Da
riprendere se gli utenti la chiedono.

**Flusso d'uso**, per quando servirà:
1. In campo: foto, più 6–10 punti visibili nella foto misurati con la
   stazione totale, sparsi nell'immagine e non tutti sulla stessa facciata.
2. In Blender: i punti entrano come empty con il loro nome. Le coordinate
   grandi (UTM, di progetto) si traslano vicino a 0,0,0 sottraendo un
   **offset di scena**, salvato una volta sola.
3. *Load Image*, modalità *Known Points*: per ogni punto una maniglia sullo
   spigolo nella foto, con il nome del punto. Ne servono almeno 6, o 4 con la
   focale nota.
4. FTC mette la camera nel punto di presa, già in scala, con l'errore in px
   per ogni punto.
5. Il progetto entra nella scena **con lo stesso offset** e si trova al posto
   giusto. Render sopra la foto come nella 1.0.
6. Facoltativo: FTC aggiunge di nuovo l'offset e restituisce la posizione
   della camera in coordinate di progetto, per mettere il punto di presa nel
   CAD con la precisione del rilievo.

Import CSV di rilievo (nome, X, Y, Z, separatore, ordine delle colonne,
offset): solo insieme a questa modalità.

Nuova voce in fondo all'enum delle modalità: **Known Points**.

#### Input

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

#### Solver (`solver/pnp.py`)

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

#### Uscita

- La camera va **direttamente nelle coordinate della scena**: niente
  origine, niente scala, niente *Align to Scene* (non servono).
- Lo **scarto per punto** in px appare nella lista e accanto alla maniglia,
  in rosso oltre una soglia. È il modo per trovare il punto sbagliato.
- Incertezza con lo stesso metodo della 1.0 (`calibrate.uncertainty`: ogni
  maniglia spostata dell'1‰).
- L'orientamento "FTC" in questa modalità coincide con Global.

#### Test

- Sintetici: camera nota, punti proiettati con rumore di 1–2 px; posa entro
  0,2°, focale entro l'1%, per ognuno dei tre casi.
- Un outlier di 50 px deve risultare il punto con lo scarto maggiore.
- Coordinate tipo UTM (x ~ 700000, y ~ 4900000): stesso risultato delle
  coordinate locali.

## Fuori dalla 1.1

- **Correzione della distorsione dell'obiettivo**: i telefoni consegnano JPEG
  già corretti, e per il resto c'è il compositor. Costo alto, guadagno basso.
- **Georeferenziazione e CRS** (EPSG, riproiezioni): troppo specialistica.
  La scena di Blender resta locale attorno a 0,0,0.
- **Modelli geomagnetici o fusi orari inclusi**: dati che invecchiano.
  Declinazione e fuso si inseriscono a mano.
- **Rete**: nessuna, come nella 1.0.
- **Import dei progetti fSpy** (`.fspy`): tolto su decisione di Antonio
  (2026-10-14). Non riproporlo.

## Decisioni prese (2026-10-14)

1. Sole: pulsante *New Sun* esplicito; altrimenti la Sun attiva o
   selezionata.
2. Fit HDRI: solo Environment Texture equirettangolare; con altre
   proiezioni il pulsante è disattivato e lo spiega.

## Stato

- S1, S2: fatte (1.1.0-alpha.2, audit incluso).
- S3: fatta. *Sole da* (Data e luogo / Ombra), *Misura un'ombra*, nord
  *Ombra* in coda all'enum, punta anche su parete XZ/YZ per l'origine.
  Riferimento per il vincolo: Kee, O'Brien, Farid (2013), *Exposing Photo
  Manipulation with Inconsistent Shadows*, ACM TOG 32(4).
- S4: fatta (*Fit HDRI*). Convenzione equirettangolare e segno del Mapping
  verificati da render Cycles (test `fit_hdri_renders_the_sun_where_computed`,
  al posto della sfera speculare). In più rispetto alla spec: l'HDRI adattato
  segue il sole quando cambiano nord, correzione o ora. Immagini generate o
  modificate non salvate: lette direttamente (la copia di Blender le
  rigenera vuote).

- A1: fatta (fino a 6 linee, pulsanti − n +; la nuova linea punta
  all'incontro delle prime due).
- A2: fatta. Report Markdown/JSON (`report.py`), permesso del manifest
  "Read the photo and its EXIF metadata, save calibration reports" (il
  validatore accetta al massimo 64 caratteri, senza punto finale);
  `docs/CHANGELOG.md` in inglese, storia italiana in `docs/CHANGELOG.it.md`.

- **Semplificazione dopo il primo test GUI** (decisione di Antonio,
  2026-10-14): niente misure su mappe. *Map* e *Landmark* tolti (le voci
  dell'enum restano, lette come *Side*); nuovo nord **Side**: l'asse della
  scena da cui arriva il sole (+X −X +Y −Y, scelti come assi della scena) più
  *Turn* a occhio, default −Y senza bussola. Il nord dall'ombra si sceglie
  direttamente (*North = Shadow*); con la bussola resta *Check with a Shadow*.

## Fasi

1. **1.0.x** – correzioni dalle segnalazioni degli utenti (Reddit, issue,
   Extensions), separate dalla 1.1. Con la prima esce il manifest senza il tag
   `3D View`.
2. **S1 – EXIF data e ora**, `solver/sun.py` e test.
3. **S2 – Sole**: sezione *Sun*, sorgente EXIF, luce, freccia del nord.
4. **S3 – Sole dall'ombra** e confronto con la bussola.
5. **S4 – Fit HDRI**: probe `hdri` per le convenzioni, visore, rotazione Z.
6. **A1 – Linee extra per punto di fuga.**
7. **A2 – Report**, changelog in inglese.
8. **Rilascio 1.1.0**:
   - `pixi run check`, test GUI di Antonio su Windows, release GitHub e
     *Upload new version* su Extensions;
   - post di aggiornamento su r/blender con un video breve: ombra del CG allineata
     a quella vera della foto, HDRI che ruota sul sole.

Ogni fase si chiude con `pixi run check` verde e un commit su `main`. Le aggiunte
A sono indipendenti dal sole: se una si allunga, la 1.1 esce senza.

## Riferimenti

- NOAA, *Solar Position Calculator* e relative equazioni (Meeus,
  *Astronomical Algorithms*, 1998).
- Reda, Andreas (2004), *Solar Position Algorithm for Solar Radiation
  Applications*, NREL.
- Kee, O'Brien, Farid (2013), *Exposing Photo Manipulation with Inconsistent
  Shadows*, ACM TOG 32(4): retta ombra–oggetto per la sorgente di luce.
- Cao, Foroosh (2007), *Camera calibration and light source orientation from
  solar shadows*, CVIU 105(1).
- Lepetit, Moreno-Noguer, Fua (2009), *EPnP: An Accurate O(n) Solution to the
  PnP Problem*, IJCV.
- Hartley, Zisserman (2004), *Multiple View Geometry in Computer Vision*,
  cap. 7 (DLT) e 6 (fattorizzazione RQ).
- Zhang (2000), *A flexible new technique for camera calibration*, IEEE
  TPAMI.
- EXIF 2.32 / CIPA DC-008: `DateTimeOriginal`, `OffsetTimeOriginal`,
  `GPSDateStamp`, `GPSTimeStamp`, `GPSImgDirection(Ref)`.
