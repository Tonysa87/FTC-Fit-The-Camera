# Changelog (italiano)

Storia completa in italiano. Dalla 1.1 il changelog principale è in inglese:
[`CHANGELOG.md`](CHANGELOG.md).

## 1.1.1 – in sviluppo
- Sweep di bug dopo la 1.1.0 (quattro revisioni in parallelo: solver, Fit Sun /
  EXIF / report, HDRI / render, sessione / interfaccia), chiesto da Antonio:
  - copia raddrizzata di foto a 16 bit o float non più scura dopo aver
    riaperto il file (la copia float resta lineare); file della foto mancante =
    messaggio;
  - Results: altezza e distanza con la Unit Scale della scena;
  - rettangolo su parete con gli angoli dal lato in alto (o F due volte): la
    camera non si capovolge più;
  - equivalente 35 mm senza sensore: la focale mostrata è quella inserita
    (sensore equivalente sulla diagonale del formato nativo);
  - due guide sulla stessa retta: errore chiaro;
  - Align to Scene: la casella *Usa bersaglio salvato* sposta subito la camera;
    il cambio di piano aggiorna l'orientamento FTC;
  - Fit Sun: *Rileggi dalla foto* non cancella luogo o fuso inseriti a mano se
    la foto non li ha; il sole di data e luogo segue un allineamento inclinato
    (tutto calcolato nel mondo calibrato, poi ruotato nella scena); il report non
    scrive il luogo se la luce è stata cancellata o l'HDRI non è più quello del
    World; date EXIF agli estremi del calendario non bloccano Load Image;
  - Fit HDRI: avviso per un Mapping con Location; uscite di Texture Coordinate
    diverse da Generated rifiutate; un link mutato non viene riattivato; fake
    user non conta come "usato altrove"; file HDRI sparito = messaggio;
  - sessione: Ctrl+Z annulla anche le modifiche del pannello; cambiare
    workspace non chiude la sessione (aspetta), Ctrl+Space la segue; I non
    mette keyframe sulla camera;
  - tooltip del segno dell'asse corretto.
- Interfaccia **tutta in italiano** (inglese lingua principale, italiano
  parallelo, chiesto da Antonio): tooltip, report e messaggi del solver, anche
  quelli con numeri (modelli tradotti da `translations.message`); il test
  `every_string_is_translated` lo verifica.

## 1.1.0 – 2026-10-14
- Dal primo test GUI (semplificazione chiesta da Antonio): *Mappa* e
  *Riferimento* tolti (misurare direzioni su Google Earth era troppo complesso).
  Il nord ora è **Bussola** (automatica), **Lato** (asse della scena da cui
  arriva il sole, +X −X +Y −Y, più *Ruota* a occhio; il default senza bussola,
  −Y) o **Ombra** (il nord dall'ombra si applica scegliendo *Ombra*, senza *Usa
  il nord dell'ombra*). *Fit HDRI* entra nei gruppi di nodi (gli add-on per HDRI
  costruiscono così il World).
- Dal test GUI della alpha.8: **Alza** (*Raise*) corregge a occhio l'elevazione
  del sole di data e ora, quando le ombre della CG vengono più corte o più lunghe
  che nella foto (cabina: lato −Y, Ruota −16°, ombra del cartello troppo corta).
- Dal test GUI della alpha.9: *Fit HDRI* ripercorre all'indietro una rotazione
  del Mapping che arriva da altri nodi e scrive il valore all'origine: l'input
  *Rotation* del gruppo di Poly Haven (gradi → Multiply → Combine XYZ), nodi
  Value, Math / Vector Math lineari, gruppi annidati; rispetta min / max
  dell'input. Il visore di Fit HDRI occupa metà vista e ha la lente con
  **Shift** (×4 sul mouse, come per le maniglie, mirino a colori invertiti per
  vederlo sul sole bianco), su una copia a 2048 px. **Calibra ombra** (sezione
  Fit Sun): una sessione con le sole maniglie dell'ombra, senza guide e senza
  toccare la camera. La × bianca con l'etichetta *Fit Sun* è ovunque il sole
  calcolato (punta dell'ombra nella vista camera, sole nel visore HDRI), con
  suggerimenti nel pannello e nell'intestazione; *Verifica con un'ombra* anche
  con *Lato* (*Ombra / Ruota*).
- Audit della alpha.14: in Calibra ombra il Ctrl+Z che riporta indietro le guide
  ricalcola; passare da Calibra a Calibra ombra non lascia il vecchio modal
  attivo (in un'altra finestra chiudeva la nuova sessione); la sessione si
  chiude se le maniglie dell'ombra vengono spente. Fit HDRI controlla ogni
  valore prima di scrivere (un rifiuto lascia il World com'era), rifiuta nodi
  disattivati, costanti con keyframe e gruppi da libreria, avvisa se il gruppo è
  usato due volte; la lente si chiude bene e lascia passare la navigazione da
  trackpad. Alza non porta il sole sotto 0,5°; *Ombra / data* è rossa solo oltre
  l'Alza impostato; il report scrive l'elevazione usata dalla luce e il lato.
- **Report di calibrazione** (1.1 A2): *Esporta report* in *Risultati*, in
  Markdown o JSON: focale, sensore, campo visivo, posizione e rotazione,
  incertezza, aderenza delle guide, fonte di ogni dato (EXIF o manuale) e sole.
  Permesso del manifest aggiornato ("…, save calibration reports").
- **Fino a sei linee per punto di fuga** (1.1 A1): pulsanti − n + accanto a ogni
  asse; la nuova linea nasce tra le prime due, puntata sul loro punto di
  incontro; l'undo della sessione ripristina anche il numero di linee. I file
  1.0 restano a due linee. Tooltip dinamici ora tradotti.
- *Visualizzazione › Nord* spento di default; tooltip di una riga (quelli su più
  righe perdevano la traduzione).
- **Fit Sun** (1.1, in corso): nuova sezione dopo *Render*. Data, ora e luogo
  dello scatto dall'EXIF (ora UTC del GPS, fuso dedotto confrontandola con
  l'orologio della fotocamera; avviso se l'ora GPS è vecchia), o a mano. Sole
  calcolato con l'algoritmo NOAA (< 0,013° dallo SPA del NREL). Nord della
  scena da **bussola** EXIF (declinazione a mano se magnetica), da **mappa**
  (direzione di un asse della scena) o da un **riferimento** lontano (maniglia
  nella calibrazione + sua direzione sulla mappa); *North Correction* per
  ruotarlo a occhio. FTC orienta la luce Sole scelta, o una nuova con *New Sun*;
  intensità e colore restano dell'utente. Freccia del nord e direzione del sole
  sul suolo per l'origine (*Display > North*, spento di default).
  Audit (alpha.2): orologio + fuso battono un'ora GPS discordante (fix vecchio);
  luce specchiata/genitori specchiati, luce cancellata o non modificabile,
  vincoli che sovrascrivono la rotazione (avviso); nord visibile anche senza ora;
  pannello corretto nei file riaperti; *Read from Photo* legge il file originale;
  *Reset Guides* non sposta il riferimento.
- **Sole da un'ombra** (1.1 S3): *Sole da* = *Ombra*: tre maniglie (piede e cima
  di un oggetto verticale, punta dell'ombra a terra o su una parete per
  l'origine) danno la direzione del sole con la sua incertezza, senza EXIF.
  Con *Misura un'ombra* accanto a data e luogo: confronto di elevazione e di
  nord, *Usa il nord dell'ombra*, crocetta dove il sole della data metterebbe
  la punta. Audit (alpha.3): il nord dell'ombra ignora la correzione del nord;
  ombre a terra indipendenti dall'altezza dell'origine; punta su parete sotto il
  suolo = errore; ± dell'azimut sulla riga *Ombra / nord*; la luce si riallinea
  dopo Esc/undo anche senza *Live Update*.
- **Fit HDRI** (1.1 S4): l'HDRI equirettangolare del World ruota attorno a Z
  finché il suo sole ha l'azimut del sole della foto. Visore sul viewport con
  la copia ridotta dell'HDRI, punto più luminoso proposto, clic per correggere,
  Invio/Esc; solo la rotazione Z di un nodo Mapping (riusato o inserito);
  elevazione confrontata (avviso oltre 10°). L'HDRI adattato segue il sole.
  Convenzione e segno verificati con render Cycles. Audit (alpha.4): Mapping
  trovato anche dietro i reroute, vettore/rotazione da altri nodi, gruppi e
  World collegati rifiutati; più Environment con la stessa immagine ruotano
  insieme; *Segui il sole* visibile, si spegne se il Mapping viene ruotato a
  mano; visore chiuso al caricamento di un file; redo con il punto cliccato;
  sole proposto pesato per luminanza (nuvole), sole "infinito" degli EXR half,
  nessuna proposta senza un sole evidente.
- Manifest: tag `Camera`, `Render` (tolto `3D View`, chiesto dal moderatore di
  Blender Extensions all'approvazione della 1.0.0).
- Nuovo logo (mirino in una cornice): il precedente somigliava a quello di fSpy.
  Cambiano solo README, pagina su Extensions e anteprima di GitHub: lo zip non
  contiene il logo.
- README: sezione *Credits* (fSpy come ispirazione, Perspective Plotter per le
  guide, articoli di riferimento); la stessa riga di crediti nella pagina su
  Extensions.

## 1.0.0 – 2026-10-11
- **Orientamento "FTC"** (Transform Orientation): gli assi calibrati della foto
  nella scena, creato/aggiornato da *Apply*, da Invio a fine sessione e dagli
  operatori di *Align to Scene*. Il pulsante *FTC Orientation* in *Tools* lo rende
  l'orientamento del viewport (gizmo di Blender, G/R/S con vincoli d'asse,
  snapping lungo gli assi della foto); ricliccato torna a Global. Senza
  allineamento coincide con Global.
- **Move Along View rimosso** (su richiesta, dopo la prova): per spostare,
  ruotare e scalare si usano gli strumenti nativi di Blender con l'orientamento
  FTC. Un gizmo "lungo i raggi della camera" è stato provato e scartato.
- **Rettangolo noto**: i lati si chiamano *Lato X* / *Lato Y* (o *Lato Z*) secondo
  il piano di riferimento, che ora si sceglie lì, sopra le misure (prima
  "Width / Height" facevano pensare a un'altezza lungo Z anche sul pavimento).
  I lati e gli angoli dell'overlay hanno i colori degli assi del piano (su XZ e
  YZ prima erano sempre rosso/verde).
- **Load Image sceglie la camera**: nella finestra file, menu *Camera* con
  *New Camera* o le camere della scena (con la loro foto). Propone la camera
  inquadrata se non ha ancora una foto, altrimenti una nuova: una calibrazione
  non viene più sostituita per errore. *Name After Photo* (attivo di default)
  dà alla nuova camera il nome del file. Con più camere calibrate il nome della
  camera nel pannello è un menu per passare dall'una all'altra.
- **Lente d'ingrandimento**: tenendo Shift mentre trascini una maniglia (movimento
  fine) si apre una lente ×4 centrata sulla maniglia: la maniglia resta ferma al
  centro e la foto scorre sotto, con guide e maniglie ingrandite. Il cursore è
  nascosto finché la lente è aperta.
- In *Vanishing Points* le foto nuove partono con la scala **Reference
  Distance** (prima il cubo da 1 m). I file salvati che non avevano scelto
  restano col cubo e mantengono la loro scala.
- Il pannello *Opacity* si chiama **Display**; nel rettangolo noto e
  nell'orizzonte il cubo di controllo è **spento di default** (si accende lì,
  con la sua dimensione).
- Nuova sezione **Render** nel pannello:
  - **Prepare Render**: view transform Standard (la foto esce identica), look
    None, display sRGB, esposizione/gamma neutre, film trasparente, risoluzione
    della foto, Cycles; compositor `FTC Compositing` (foto scalata › moltiplicata
    per il pass Shadow Catcher › Alpha Over col render) oppure uscita trasparente
    con le ombre nell'alpha.
  - **Object Roles**: lista degli oggetti della scena con gli interruttori
    *Shadow Catcher* e *Holdout* (si escludono) e *Set Role of Selected* per i
    selezionati. Cambiano solo le proprietà degli oggetti: FTC non crea oggetti.
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
- *Apply* durante *Calibrate* chiude anche la sessione, come Invio.
- Secondo audit:
  - Ctrl+Z durante la sessione è sempre l'undo della sessione (l'undo di Blender
    tornava a prima della sessione perdendone le modifiche);
  - la sessione non resta bloccata se il codice incontra un errore imprevisto;
    l'overlay segue la camera anche subito dopo una rinomina;
  - le proporzioni del render vengono corrette tenendo la larghezza (e la
    percentuale) scelta da te, con un messaggio; Apply lo fa solo se la
    calibrazione riesce; anche Prepare Render usa questa regola;
  - Cubo › Misura di riferimento con maniglie mai toccate mantiene la scala; il
    cubo resta nell'immagine passando a una parete; con un bersaglio di
    allineamento il cambio di piano muove subito la camera;
  - avviso anche per vincoli, driver, NLA, genitore animato e keyframe
    dell'obiettivo (sovrascrivono la calibrazione);
  - il compositor usa sempre la foto della camera di scena (anche dopo un nuovo
    Load Image, la copia raddrizzata o un cambio di camera);
  - la copia raddrizzata è davvero impacchettata in JPEG (pixel identici);
  - Holdout: il tooltip spiega che proietta ancora ombre; avviso più chiaro
    sugli shadow catcher fuori da Cycles (coprono la foto).
- Render (audit): niente crash con config colore OCIO personalizzate, uscita
  video, Cycles disattivato; il compositor usa il view layer attivo; il bordo
  ritagliato viene disattivato; avviso se manca il file della foto; un oggetto in
  Edit Mode non resta bloccato cliccando la lista dei ruoli;
  un albero FTC condiviso con un'altra scena viene
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
