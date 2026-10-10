# Test GUI in Blender (Windows) – da fare per la 0.6.1

Stato: **non ancora provata in GUI**. Tutti i test automatici passano (96 pytest,
22 test headless in Blender) e le sonde `scripts/probe.sh` (pannello, overlay,
trascinamento simulato) sono pulite; manca la prova a mano.

Zip: `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-0.6.1.zip`
(se manca: `pixi run build`).

## Installazione
1. Edit › Preferences › Get Extensions › ⌄ › *Install from Disk…* › lo zip
   (sostituisce la versione installata).

## Guide e assi (0.6.0)
2. Scena nuova, tab **FTC** › **Load Image** con una foto con EXIF (es. lift).
   Le guide di default non devono dare avvisi (sono generate per la focale EXIF).
3. **Calibrate** con 2 punti di fuga:
   - frecce sulle guide più grandi (+50%);
   - pulsante ⇄ accanto ad *Asse 1*, *Asse 2*, *Asse 3*: inverte il verso. *Asse 3*
     (col segno) è derivato: invertirlo inverte anche l'asse 2 (o l'1 se il 2 è Z);
   - con *Linea terzo asse* o 3 punti di fuga, la freccia della guida del terzo
     asse indica il verso reale (es. +Z verso l'alto) qualunque sia l'ordine delle
     maniglie;
   - tasto F: inverte l'asse del gruppo attivo.

## Cubo di scala (0.6.0 + correzioni 0.6.1)
4. Scala = *Cubo di scala*, scegli il lato (10 cm … 10 m o *Misura personalizzata*).
5. Base ai piedi di un oggetto di altezza nota, cima all'altezza dell'oggetto:
   *Distanza*/*Altezza camera* nei Risultati cambiano; etichetta del lato in cima.
6. Trascina la **base**: il cubo si sposta, la *Distanza* NON cambia.
7. Trascina la **cima** di lato: resta sullo spigolo; sotto la base: il cubo resta
   minimo, non si ribalta.
8. *Align to Scene* › piano **XZ**, poi **YZ**, poi XY: la calibrazione resta valida,
   il cubo va sulla parete, la scala non cambia.
9. Passa a *Misura di riferimento* e torna a *Cubo*: la scala resta la stessa.
10. Rettangolo noto e Orizzonte: il cubo è solo controllo visivo (solo maniglia alla
    base); si nasconde da *Opacity* › *Cubo di scala*.
11. Apri un .blend salvato con la 0.5.2 (scala "Distanza camera"): la camera resta
    alla stessa distanza.

## Focale (0.6.0 + correzioni 0.6.1)
12. *Focale* = *Nota + guide* (default), *Solo guide*, *Solo nota*: confronta
    *Focale ±%*, *Orientamento ±°* e *Rispetto alla nota* nei Risultati.
13. Sposta un po' una guida su una foto con EXIF giusto: con *Nota + guide* la
    focale resta vicina all'EXIF (pochi %).
14. Foto zoomata (deck) con 3 punti di fuga: la focale va a ~8800 px e compare
    l'avviso "the guides overrule the known focal length".
15. 3 punti di fuga + punto principale *Solve*: la scelta della focale è disattivata
    con la spiegazione.
16. Rettangolo noto con EXIF: tiene la focale nota (un rettangolo non scopre lo zoom).

## Da riportare
Comportamenti strani, errori in console (Window › Toggle System Console),
screenshot dell'overlay se qualcosa non torna.
