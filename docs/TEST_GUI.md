# Test GUI in Blender (Windows) – da fare per la 1.0.0

Stato: **prova a mano in corso** (2026-10-10). Tutti i test automatici passano
(106 pytest, 29 test headless in Blender, compreso un render Cycles reale) e le
sonde `scripts/probe.sh` (pannello, overlay, trascinamento simulato, render) sono
pulite. Dopo questa prova arrivano l'orientamento "FTC" e il gizmo lungo la vista
camera (vedi `CLAUDE.md`, *Status / next session*), da provare a loro volta.

Zip: `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-1.0.0.zip`
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
9. Passa a *Misura di riferimento* e torna a *Cubo*: la scala resta la stessa; con
   la misura il cubo sparisce (anche da *Opacity*), col cubo spariscono i due
   estremi della misura.
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

## Render (1.0.0)
17. Dopo una calibrazione, apri **Render** (in fondo, sopra *Tools*): con AgX
    compare "Scene not set up for the photo".
18. **Prepare Render** › dialogo › *Over the Photo*, *Use Cycles* › OK. Controlla:
    Render › Color Management = sRGB / Standard / None; Film › Transparent;
    View Layer › Passes › Shadow Catcher attivo; workspace **Compositing**: albero
    `FTC Compositing` (Render Layers, Photo › Scale › Shadows on Photo › Alpha
    Over › Group Output + Viewer).
19. Aggiungi un cubo appoggiato sul pavimento, una luce Sun e un piano grande sul
    pavimento (Shift+A, tuo): nella lista *Object Roles* attiva *Catcher* sul
    piano. Nessun oggetto nuovo viene creato.
20. F12: la CG sopra la foto con l'ombra sul pavimento; fuori dalla CG la foto è
    identica all'originale (nessun cambio di colori/contrasto).
21. **Object Roles**: clic su una riga seleziona l'oggetto; *Catcher* e *Holdout*
    si escludono (attivarne uno spegne l'altro) e si spengono ricliccandoli.
    Holdout: un oggetto davanti al cubo ne nasconde la parte dietro mostrando la
    foto. *Set Role of Selected* › *Shadow Catcher* / *Holdout* / *No Role* su più
    oggetti selezionati.
22. **Prepare Render** › *Transparent*: F12 dà la CG con l'ombra su sfondo
    trasparente; il compositor FTC sparisce, formato PNG RGBA.
23. Con un tuo albero compositor già presente: Prepare Render lo sostituisce ma
    resta nel file (fake user, si ritrova nel selettore dei gruppi nodi).

## Misura di riferimento e cubo (correzioni dopo la prima prova)
25. Foto dell'ascensore, 2 punti di fuga (X soglia, Z stipiti), *Misura di
    riferimento* 0.8 m tra i piedi degli stipiti (*Measured On* XY), origine più
    indietro sulla soglia: un piano 0.8 × 0.8 m (Shift+A › Plane, Size 0.8) spostato con il lato
    anteriore sulla misura combacia con i due estremi.
26. *Cubo di scala*: trascina la base da sinistra a destra davanti alla camera e
    avanti/indietro, poi l'origine: il cubo non si ribalta mai dall'altra parte.
27. Con la misura di riferimento, cambia *Reference Plane* in *Align to Scene*
    (XY › XZ › YZ): la scala (*Distanza*) non cambia.

## Robustezza della sessione (audit 1.0.0)
28. *Calibrate*, poi chiudi la finestra (o apri una nuova finestra, calibra lì e
    chiudila): *Calibrate* riparte normalmente.
29. Durante la sessione cambia la camera di scena (o Ctrl+Numpad0 su un'altra
    camera): la sessione si chiude, i clic nel viewport tornano a funzionare.
30. Durante la sessione: *Ruota 90°* / *Inverti* in *Align to Scene* muovono subito
    la camera; Ctrl+Spazio chiude la sessione senza lasciare testo nell'header.
31. Metti un keyframe di posizione alla camera: compare l'avviso rosso.
32. Cambia la risoluzione di render in 1000×1000: compare l'avviso; *Apply* tiene
    la larghezza 1000 e porta l'altezza alle proporzioni della foto (messaggio).
33. Durante *Calibrate*, Ctrl+Z con il mouse sull'Outliner: annulla l'ultima
    modifica della sessione (non torna a prima della sessione).
34. *Prepare Render*, poi *Load Image* con un'altra foto: il nodo *Photo* nel
    compositor mostra la nuova foto (F12 la usa).
35. *Cubo di scala* › *Reference Distance* senza aver mai toccato le maniglie della
    misura: la *Distanza* non cambia.
36. Con *Align to Scene* attivo, cambia XY › XZ: la camera si sposta subito.

37. Durante *Calibrate* premi *Apply* nel pannello: la camera viene scritta e la
    sessione si chiude (come Invio).

## Orientamento FTC (ultima aggiunta alla 1.0.0; Move Along View e Ray Gizmo rimossi)
38. Calibra, *Apply*: nel menu *Transform Orientations* (in alto nel viewport)
    compare **FTC**; senza *Align to Scene* è uguale a Global.
39. *Align to Scene* › *3D Cursor* con il cursore ruotato (o *Selection* su una
    faccia inclinata): **Tools › FTC Orientation** (resta premuto) → il gizmo
    nativo di spostamento/rotazione/scala e G X / R Z / S Y seguono gli assi della
    foto. *Rotate 90°* / *Flip* / *Scene Origin* aggiornano l'orientamento.
    Ricliccando il pulsante torna Global.
40. Edit Mode su una mesh: con *FTC Orientation* attivo, G X su vertici/spigoli/
    facce si muove lungo l'asse X della foto; con lo snapping idem.
41. Il menu *Object › Transform* non ha più *Move Along View*.

## Da riportare
Comportamenti strani, errori in console (Window › Toggle System Console),
screenshot dell'overlay se qualcosa non torna.
