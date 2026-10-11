# FTC – Fit The Camera

[English](README.md) · **Italiano**

![Un oggetto CG renderizzato in una foto calibrata con FTC](docs/images/ftc_hero.jpg)

Estensione per Blender 5.2+ che calibra una camera su una singola immagine
(foto, render, disegno): focale, sensore, posizione e rotazione, con scala reale;
poi prepara la scena per renderizzare oggetti 3D sopra la foto. Storia delle
versioni: [`docs/CHANGELOG.md`](docs/CHANGELOG.md). Sviluppo:
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Guida rapida

1. **Installa** – scarica `fit_the_camera-<versione>.zip` dalle
   [Release](https://github.com/Tonysa87/FTC-Fit-The-Camera/releases), poi in
   Blender *Edit › Preferences › Get Extensions › ⌄ › Install from Disk…*
2. **Carica la foto** – sidebar del viewport (**N**) › tab **FTC** › **Load
   Image**. La foto va sulla camera della scena (su una nuova camera col nome
   della foto, se quella ha già una foto) e la vista guarda da lì; focale e
   sensore arrivano dall'EXIF (controllali in *Camera Data*).
3. **Disegna le guide** – lascia *Vanishing Points* con 2 gruppi e premi
   **Calibrate**. Trascina le due guide **rosse** (X) su due spigoli che nella
   realtà vanno nella stessa direzione – fughe delle piastrelle, un battiscopa,
   il fondo di una porta – e le due **verdi** (Y) su due spigoli ad angolo retto
   con quelli, sempre sul pavimento. Metti la maniglia bianca dell'origine sul
   pavimento, dove vuoi il centro della scena. Tieni **Shift** per muovere fine
   con una lente ×4.
4. **Imposta la scala** – trascina le due maniglie di *Reference Distance*
   sugli estremi di qualcosa di cui conosci la lunghezza (una porta, una
   piastrella) e scrivila in *Reference Length*.
5. **Applica** – premi **Invio**: la camera è a posto. *Results* mostra focale,
   altezza della camera e quanto ci si può fidare delle guide.
6. **Renderizza sopra la foto** – modella il tuo oggetto, aggiungi un piano sul
   pavimento vero e dagli il ruolo *Shadow Catcher* (*Render › Object Roles*),
   premi **Prepare Render** e renderizza (F12): l'oggetto è nella foto con la
   sua ombra.

![Calibrazione nella vista camera: guide dei punti di fuga sulla porta e sul pavimento, misura di riferimento di 0,8 m e pannello FTC](docs/images/ftc_calibration.jpg)

<table>
  <tr>
    <td width="33%"><img src="docs/images/ftc_elevator.jpg" alt="Un oggetto CG davanti alla porta di un ascensore, con l'ombra sul pavimento vero" width="100%"></td>
    <td width="33%"><img src="docs/images/ftc_fountain_view.jpg" alt="La camera calibrata nel viewport: orizzonte, griglia e origine su una piazza" width="100%"></td>
    <td width="33%"><img src="docs/images/ftc_gallery.jpg" alt="Un oggetto CG in una foto di una galleria, in scala reale" width="100%"></td>
  </tr>
  <tr>
    <td>Il risultato: un oggetto CG con l'ombra sul pavimento vero (shadow catcher)</td>
    <td>La camera calibrata nel viewport: orizzonte, griglia e origine</td>
    <td>Un oggetto CG in una galleria, in scala reale</td>
  </tr>
</table>

Il resto della pagina spiega ogni opzione.

## Installazione

1. Scarica `fit_the_camera-<versione>.zip` dalle
   [Release](https://github.com/Tonysa87/FTC-Fit-The-Camera/releases).
2. Blender 5.2 o successivo: *Edit › Preferences › Get Extensions › ⌄ ›
   Install from Disk…* e scegli lo zip.
3. Interfaccia in italiano: *Preferences › Interface › Translation*, lingua
   Italiano.

## Il pannello, passo per passo

Sidebar del viewport (N) › tab **FTC**.

1. **Load Image** – nel pannello laterale della finestra file si sceglie la
   **Camera**: una nuova (col nome della foto con *Name After Photo*, attivo di
   default) o una della scena, di cui si sostituisce la foto. Propone la camera
   inquadrata finché non ha una foto, altrimenti una nuova. Poi imposta lo
   sfondo, adatta la risoluzione, legge l'EXIF e inquadra la camera. Con più
   camere calibrate, il nome della camera nel pannello è un menu per passare
   dall'una all'altra. Foto salvate ruotate
   (orientamento EXIF): **Make Upright Copy**.
2. **Camera Data** – marca, modello, focale reale, equivalente 35 mm, sensore,
   GPS, direzione; ogni campo è *da EXIF*, *mancante* (rosso) o *manuale*.
   Il sensore va inserito come nelle schede tecniche (lato lungo del sensore
   intero), anche per foto ritagliate. Immagini non 4:3 / 3:2 sono trattate come
   ritaglio centrato di un sensore 4:3 (come fanno i telefoni).
3. **Calibration** – modalità e parametri, poi **Calibrate** (operatore modale nel
   viewport camera). Scorciatoie nell'header: trascina = sposta maniglia,
   Shift = fine, con una lente ×4 sulla maniglia, Ctrl = snap, 1/2/3 = asse, F = inverti verso, H = raddrizza,
   Ctrl+Z / Ctrl+Shift+Z = undo/redo interni, Invio = applica, Esc/RMB = esci.
   Con *Live Update* (default) la camera segue le guide mentre trascini; Invio o
   **Apply** la scrivono e chiudono la sessione. Fuori dalla sessione, le
   modifiche fatte nel pannello spostano la camera solo con **Apply**. Nella vista
   camera la foto si muove con la camera: il risultato si vede dagli oggetti
   della scena o dalla posizione della camera.
   Accanto a ogni asse un pulsante ne inverte il verso.
   **Focale**: *Nota + guide* (default: parte dalla focale di Camera Data e le guide
   la correggono per quanto la misurano; se è sconosciuta la risolvono), *Solo
   guide*, *Solo nota*. **Scala**: *Misura di riferimento* (default per le
   foto nuove) o *Cubo di scala*.
4. **Align to Scene** – porta il piano calibrato (XY, XZ, YZ) sul 3D cursor, sulla
   faccia attiva (Edit Mode) o sull'oggetto attivo; Ruota 90° / Inverti.
5. **Results** – focale, FOV, altezza, angoli, **incertezza** (focale ± %,
   orientamento ± °) e **aderenza guide** (scarto massimo); avvisi in giallo/rosso.
6. **Render** – **Prepare Render** prepara la scena per renderizzare la CG sopra la
   foto (vedi sotto); **Object Roles** elenca gli oggetti della scena: per ognuno
   si attiva *Shadow Catcher* o *Holdout*, oppure si assegnano ai selezionati con
   *Set Role of Selected*. Cambiano solo le impostazioni degli oggetti, non viene
   creato nulla.
7. **Tools › FTC Orientation** – rende l'orientamento "FTC" quello del viewport: gli
     assi calibrati della foto nella scena (creato da *Apply* e da *Align to
     Scene*). Gizmo di Blender, G/R/S con X/Y/Z e snapping seguono la foto anche
     dopo averla allineata a una faccia o al cursore. Ricliccato torna a Global.

### Modalità

| Modalità | Input | Note |
| --- | --- | --- |
| Punti di fuga 1 | 2 guide per l'asse 1 + una linea lungo l'asse 2 | richiede la focale |
| Punti di fuga 2 | 2 guide per asse | opzioni: focale, *Linea terzo asse* |
| Punti di fuga 3 | 2 guide per asse | punto principale al centro (default), manuale o *Risolvi* (ortocentro, instabile) |
| Rettangolo noto | 4 angoli, lunghezza reale dei due lati | su XY, XZ o YZ; focale come sopra |
| Orizzonte | linea d'orizzonte, altezza camera, yaw | richiede la focale |

### Cubo di scala

Un cubo wireframe di lato noto (10 cm … 10 m o misura personalizzata) appoggiato sul
piano di riferimento, con gli spigoli nei colori degli assi. La maniglia alla base
scorre sul piano (mettila ai piedi di un oggetto di altezza nota); quella in cima
scorre lungo lo spigolo verticale: portala all'altezza dell'oggetto e la scala
della scena si adegua. Cubo e *Misura di riferimento* si escludono: sullo schermo
c'è solo quello scelto nel menu *Scala*. Nel rettangolo noto e nell'orizzonte la
scala è già nota e il cubo è solo un controllo visivo, spento di default (si accende
in *Display* › *Scale Cube*, con la sua dimensione).
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
