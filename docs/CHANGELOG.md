# Changelog

## 1.0.0 – 2026-10-10
- Nuova sezione **Render** nel pannello:
  - **Prepare Render**: view transform Standard (la foto esce identica), look
    None, display sRGB, esposizione/gamma neutre, film trasparente, risoluzione
    della foto, Cycles; compositor `FTC Compositing` (foto scalata › moltiplicata
    per il pass Shadow Catcher › Alpha Over col render) oppure uscita trasparente
    con le ombre nell'alpha.
  - **Object Roles**: lista degli oggetti della scena con il ruolo (Oggetto CG,
    Shadow Catcher, Holdout, Nascosto) e menu per i selezionati.
  - **Shadow Catcher Plane**: piano shadow catcher sul piano di riferimento.
- **Misura di riferimento corretta**: gli estremi stanno sul piano di riferimento
  in qualunque punto. Prima venivano riportati sull'asse che passa per l'origine:
  una misura presa altrove (es. la larghezza della porta sulla soglia, con
  l'origine più indietro) dava una scala sbagliata (−5% sulla foto
  dell'ascensore). Lungo la normale al piano la misura è un'altezza sopra il
  primo estremo. I file salvati con una misura lontana dall'asse dell'origine
  cambiano scala alla riapertura (ora è quella giusta).
- La misura di riferimento ha il suo piano (*Measured On*, default XY): cambiare
  il piano in *Align to Scene* non cambia più la scala.
- Incertezza: una misura o un cubo vicini all'orizzonte non danno più un falso
  "calibrazione instabile".
- Il cubo di scala non si ribalta più trascinando la base o l'origine: in un
  piano si estende nel verso in cui guarda la camera, su una parete verso l'alto.
- Sessione di calibrazione (audit):
  - chiudere la finestra della sessione non la lascia più "appesa" (Calibrate
    ripartiva solo ricaricando il file);
  - cambiare la camera di vista, o caricare un'immagine in un'altra camera, chiude
    la sessione invece di lasciarla invisibile a bloccare i clic;
  - *Ruota 90°*, *Inverti* e l'allineamento su faccia hanno effetto subito anche
    durante la sessione;
  - rinominare la camera non chiude la sessione; il testo nell'header viene
    sempre tolto (anche dopo Ctrl+Spazio o cambio workspace);
  - l'undo di Blender (menu Edit, Undo History) durante la sessione ricalcola la
    soluzione; Ctrl+Z fuori dall'area della sessione è l'undo di Blender;
  - Invio con guide non risolvibili lo dice invece di chiudere in silenzio;
    *Reset Guides* rispetta il limite dell'undo.
- Camera locale non-camera (empty, luce) gestita; avviso se la camera ha keyframe
  di posizione/rotazione (sovrascrivono la calibrazione) o se il render ha
  proporzioni diverse dall'immagine (Apply e Calibrate le correggono).
- Allineamento su faccia: corretto un riferimento a una faccia BMesh già
  liberata; una faccia senza area viene rifiutata.
- Caricamento: un file non immagine non lascia un'immagine vuota; la copia
  raddrizzata di un JPEG viene impacchettata come JPEG (un PNG era molte volte più
  grande); EXIF: orientamento fuori 1–8, focali e sensori assurdi ignorati, un
  sotto-IFD rotto non fa perdere marca/modello/orientamento.
- Traduzioni: "Flip Axis Direction" (prima mostrava "Scambia assi" di Blender),
  Risultati, Imbardata, Sposta lungo la vista, nuovi avvisi.
- Il pulsante del piano diventa **New Shadow Catcher Plane**, su una riga a sé,
  e il piano è una griglia: prima sembrava vuoto (bordi fuori inquadratura) e
  veniva scambiato per "rendi shadow catcher la selezione" (che è *Set Role of
  Selected*).
- Render (audit): niente crash con config colore OCIO personalizzate, uscita
  video, Cycles disattivato; il compositor usa il view layer attivo; il bordo
  ritagliato viene disattivato; avviso se manca il file della foto; un oggetto in
  Edit Mode non resta bloccato cliccando la lista dei ruoli o creando il piano;
  il piano shadow catcher è legato alla camera (un duplicato non viene toccato) e
  misura 10 × la distanza; un albero FTC condiviso con un'altra scena viene
  copiato; nel modo trasparente un compositor dell'utente viene disattivato;
  lista ruoli con inverti/ordina funzionanti; l'avviso "scena non preparata"
  controlla anche esposizione, gamma, curve e display.
- Cubo di scala e *Misura di riferimento* si escludono: con la misura il cubo
  sparisce dallo schermo (e dal pannello *Opacity*).
- Sonda `render` (render di prova con cubo CG e ombra) e `paneltest` estesa.
- Pubblicazione: repository GitHub, README in inglese (`README.md`) e italiano
  (`README.it.md`), `LICENSE` GPL-3.0, `docs/DEVELOPMENT.md`,
  `docs/PUBLISHING.md`; manifest con `website`, tag *Render*, senza la sezione
  `[build]` di default.

## 0.6.1 – 2026-10-10 (audit)
- *Nota + guide*: le guide scavalcano la focale nota solo se non riescono ad
  accordarsi con essa (scarto > 1°) e con la propria vanno molto meglio. Prima
  guide imprecise di 10–25 px bastavano a buttare via una focale EXIF corretta.
  Il rettangolo tiene la focale nota (quattro angoli non bastano a scoprire uno zoom).
- Avvisi indipendenti: "linee non parallele" non viene più nascosto da "le guide
  scavalcano la focale".
- Cubo di scala:
  - non rompe più la calibrazione passando a una parete (XZ/YZ);
  - cambiando piano o passando alla scala a cubo, la scala resta quella attuale;
  - la base sposta tutto il cubo senza cambiare la scala;
  - la cima conta solo lungo lo spigolo e non scende sotto la base;
  - i file salvati prima del cubo mantengono la distanza della camera;
  - le misure preimpostate rispettano la scala delle unità della scena.
- Trascinare origine, misura di riferimento o cubo non azzera più la correzione
  di beccheggio.
- Con il punto principale risolto la focale viene sempre dalle guide (la scelta è
  disattivata e spiegata).
- Rettangolo di default valido anche con ultragrandangoli.
- F con un gruppo attivo rimasto da un'altra modalità; limite dell'undo per il
  pulsante d'inversione; descrizioni delle misure del cubo.

## 0.6.0 – 2026-10-10
- **Cubo di scala** al posto di *Distanza camera*: cubo wireframe di lato noto
  (10 cm … 10 m o personalizzato) sul piano di riferimento; maniglia alla base sul
  piano, maniglia in cima lungo lo spigolo verticale per fissare la scala. Nelle
  altre modalità è un controllo visivo.
- **Focale *Nota + guide*** (default): la focale di Camera Data viene raffinata
  dalle guide ai minimi quadrati, con un vincolo robusto (±5%) che cede quando le
  guide la contraddicono nettamente (foto zoomate). Anche per il rettangolo noto.
  Opzioni *Solo guide* e *Solo nota*; avviso e riga *Rispetto alla nota*.
- Guide e rettangolo di default coerenti con la focale nota della foto.
- Pulsante di inversione accanto a ogni asse; asse 3 mostrato con segno anche con
  2 punti di fuga, freccia del terzo asse nel verso reale.
- Frecce sulle guide più grandi del 50%.

## 0.5.2 – 2026-10-10
- Raffinamento ai minimi quadrati con passi limitati: niente più `OverflowError`
  trascinando le guide; gli errori numerici diventano messaggi nel pannello.
  Test di fuzzing su configurazioni casuali e degeneri.
- **Aderenza guide** (scarto massimo in gradi) nei risultati; avviso quando le guide
  contraddicono la focale nota (foto ritagliate o zoomate).
- Sensore inserito a mano = lato lungo del sensore intero (come nelle schede
  tecniche), corretto anche per foto ritagliate.
- Guide del terzo asse posizionate in modo coerente con la camera corrente al
  passaggio a 3 punti di fuga o all'attivazione della linea del terzo asse.
- Dati di regressione da una foto di decking (zoomata, focale EXIF fuorviante).

## 0.5.1 – 2026-10-10
- Minimi quadrati su tutte le guide (Levenberg-Marquardt su focale e rotazione).
- 3 punti di fuga: punto principale al centro per default; ortocentro come opzione.
- *Usa focale nota* anche con 2 e 3 punti di fuga; *Linea terzo asse* con 2.
- Segno degli assi lungo la prima guida (freccia): niente ribaltamenti di 180°.
- Incertezza calcolata al rilascio della maniglia; avvisi a capo.
- Messaggio chiaro per punti di fuga incompatibili; dati di regressione galleria.

## 0.5.0 – 2026-10-10
- Allineamento alla scena: piano di riferimento XY/XZ/YZ; 3D cursor, faccia attiva
  (con misure del rettangolo dalla faccia) o oggetto attivo; Ruota 90°, Inverti.
- Rettangolo noto anche sulle pareti; se visto dal retro si inverte il lato
  orizzontale (Z resta in alto).
- Maniglie a mirino sottili nel colore dell'asse; linee sottili.
- Tooltip su ogni pulsante (verificato da un test).

## 0.1.x – 2026-10-10
- Solver (punti di fuga 1/2/3, rettangolo, orizzonte), parser EXIF, add-on con
  operatore modale, overlay GPU, Move Along View, traduzione italiana.
- Avviso e rollio rimosso per *Raddrizza orizzonte*; stima d'incertezza; 1 punto di
  fuga con linea del secondo asse; focale EXIF su immagini ritagliate.
