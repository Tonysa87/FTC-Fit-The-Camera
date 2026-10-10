# FTC – Fit The Camera

[English](README.md) · **Italiano**

Estensione per Blender 5.2+ che calibra una camera su una singola immagine
(foto, render, disegno): focale, sensore, posizione e rotazione, con scala reale;
poi prepara la scena per renderizzare oggetti 3D sopra la foto. Storia delle
versioni: [`docs/CHANGELOG.md`](docs/CHANGELOG.md). Sviluppo:
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Installazione

1. Scarica `fit_the_camera-<versione>.zip` dalle
   [Release](https://github.com/Tonysa87/FTC-Fit-The-Camera/releases).
2. Blender 5.2 o successivo: *Edit › Preferences › Get Extensions › ⌄ ›
   Install from Disk…* e scegli lo zip.
3. Interfaccia in italiano: *Preferences › Interface › Translation*, lingua
   Italiano.

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
   Con *Live Update* (default) la camera segue le guide mentre trascini; Invio o
   **Apply** la scrivono e chiudono la sessione. Fuori dalla sessione, le
   modifiche fatte nel pannello spostano la camera solo con **Apply**. Nella vista
   camera la foto si muove con la camera: il risultato si vede dagli oggetti
   della scena o dalla posizione della camera.
   Accanto a ogni asse un pulsante ne inverte il verso.
   **Focale**: *Nota + guide* (default: parte dalla focale di Camera Data e le guide
   la correggono per quanto la misurano; se è sconosciuta la risolvono), *Solo
   guide*, *Solo nota*. **Scala**: *Cubo di scala* (default) o *Misura di
   riferimento*.
4. **Align to Scene** – porta il piano calibrato (XY, XZ, YZ) sul 3D cursor, sulla
   faccia attiva (Edit Mode) o sull'oggetto attivo; Ruota 90° / Inverti.
5. **Results** – focale, FOV, altezza, angoli, **incertezza** (focale ± %,
   orientamento ± °) e **aderenza guide** (scarto massimo); avvisi in giallo/rosso.
6. **Render** – **Prepare Render** prepara la scena per renderizzare la CG sopra la
   foto (vedi sotto); **Object Roles** elenca gli oggetti della scena: per ognuno
   si attiva *Shadow Catcher* o *Holdout*, oppure si assegnano ai selezionati con
   *Set Role of Selected*. Cambiano solo le impostazioni degli oggetti, non viene
   creato nulla.
7. **Tools › Move Along View** – sposta oggetti/vertici lungo il raggio dalla camera
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
della scena si adegua. Cubo e *Misura di riferimento* si escludono: sullo schermo
c'è solo quello scelto nel menu *Scala*. Nel rettangolo noto e nell'orizzonte la
scala è già nota e il cubo è solo un controllo visivo (si nasconde in *Opacity*).
Spostando la base o l'origine il cubo non si ribalta: si estende nel verso in cui
guarda la camera (su una parete: verso l'alto).

### Misura di riferimento

Due maniglie agli estremi di una lunghezza nota (larghezza di una porta, una
piastrella, un tavolo), sul piano scelto in *Measured On* (passa per l'origine;
XY = pavimento di default, indipendente dal piano usato per allineare la scena).
Lungo un asse di quel piano entrambi gli estremi stanno sul piano, in qualunque
punto (non serve che siano sull'asse che passa per l'origine). Lungo la normale
è un'altezza: la prima maniglia al piede sul piano, la seconda in cima.

### Render sopra la foto

**Prepare Render** (dialogo: *Sopra la foto* / *Trasparente*, *Usa Cycles*):

- **Color management**: display *sRGB*, view transform **Standard**, look *None*,
  esposizione 0, gamma 1, niente curve né bilanciamento del bianco. La foto è
  sRGB: solo con Standard esce identica (misurato: scarto < 1/255). AgX, Filmic,
  ACES e Khronos PBR Neutral la ritoccano come fossero luce della scena (scarto
  medio ~9 livelli su 255, fino a ~130 sulle tinte sature). La luminosità della
  CG si regola con le luci, non con l'esposizione.
- **Film trasparente**: il mondo illumina ma non si vede; la risoluzione torna
  quella della foto (la percentuale resta).
- **Compositor** (Blender 5: gruppo nodi `FTC Compositing` assegnato alla scena):
  `Image` (la foto) › `Scale` (*Render Size*, *Fit*, estensione *Extend*) ›
  `Mix` *Multiply* con il pass **Shadow Catcher** › `Alpha Over` (sfondo) con
  l'immagine del render (primo piano) › `Group Output` + `Viewer`. Con il pass
  attivo le ombre e la luce che la CG rimbalza sugli shadow catcher passano dal
  pass (anche colorate) invece che dall'alpha. Un compositor fatto a mano viene
  conservato nel file (fake user) e sostituito; quello di FTC viene rigenerato.
- **Trasparente**: niente compositor, pass Shadow Catcher spento (le ombre restano
  nell'alpha), formato PNG RGBA se quello impostato non ha l'alpha: per comporre
  in un altro programma.
- Solo il view layer attivo viene composto sulla foto. Con una configurazione
  colore personalizzata (OCIO) senza display sRGB / vista Standard, la vista va
  impostata a mano (lo dice un avviso).
- **Cycles** consigliato: EEVEE non ha shadow catcher (gli holdout funzionano).

**Ruoli** (*Object Roles*): due interruttori per oggetto, che si escludono a
vicenda; cambiano solo le proprietà native dell'oggetto (nessun oggetto viene
creato). Gli oggetti senza ruolo sono la CG, renderizzata normalmente.

| Ruolo | Cosa fa | Uso |
| --- | --- | --- |
| Shadow Catcher | mostra la foto, riceve ombre e luce della CG, nasconde ciò che sta dietro (solo Cycles) | pavimento, tavolo, muri reali (modellati da te) |
| Holdout | mostra la foto e nasconde la CG dietro, senza ombre | oggetti reali davanti alla CG |

Un clic su una riga seleziona l'oggetto. *Set Role of Selected* assegna *Shadow
Catcher*, *Holdout* o *No Role* a tutti gli oggetti selezionati.

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

## Licenza

GPL-3.0-or-later, vedi [LICENSE](LICENSE).
