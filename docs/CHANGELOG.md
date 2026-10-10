# Changelog

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
