# Test GUI in Blender (Windows) – 1.1

Prova a mano della 1.1 (Fit Sun, sole dall'ombra, Fit HDRI, linee in più,
report). I test automatici passano (pytest, test headless in Blender con render
Cycles, sonde `scripts/probe.sh`); qui si controlla quello che solo l'interfaccia
mostra. La checklist della 1.0 resta in [`TEST_GUI.md`](TEST_GUI.md).

Zip: `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-<versione>.zip`
(l'ultima build; se manca: `pixi run build`). Le foto citate sono in `samples/`.

## Installazione
1. Se la 1.0.0 è installata da Extensions, disinstallala; poi *Edit › Preferences
   › Get Extensions › ⌄ › Install from Disk…* con lo zip.

## Fit Sun – data, luogo, nord
2. **Cabina** (`IMG_20260804_185218650.jpg`): Load Image, sezione **Fit Sun**:
   *Sun From* = *Date and Place*; data 4/8/2026, ora 18:52:19, fuso +2, tutti
   con l'icona EXIF; latitudine/longitudine EXIF. Sole: azimut ~278,6°,
   elevazione ~16,0°. *North* su **Side** (nessuna bussola: *Compass* è
   disattivato), lato −Y.
3. Calibra sulla facciata. **New Sun** (icona del sole accanto a *Light*).
   Con il calibro asse 1 +X (lungo il muro), asse 2 +Z, il sole arriva da
   **−Y** (dietro la camera, un po' da sinistra): Side −Y, **Turn** ~−16°
   guardando le ombre della CG (un palo davanti al muro, *Prepare Render*).
   Poi **Raise** finché l'ombra del palo è alta come quella del cartello: il
   pannello mostra *Sun Elevation* 16,0° → valore usato.
4. **Lago** (`IMG_20250630_152535968_HDR.jpg`): sole ~238,7° / 56,3°. Modalità
   *Horizon*, *Side*: scegli il lato da cui arriva la luce nella foto e ruota.
5. **Ponte levatoio** (`IMG_20230108_110414.jpg`): l'ora letta deve essere
   11:04:13 (orologio della fotocamera, non l'ora GPS di 22 s prima). Sole
   ~162,2° / 21,9°.
6. Foto senza EXIF: gli errori arrivano in ordine data/ora → fuso → luogo.
   Con un'ora notturna: "sole sotto l'orizzonte", la luce non si muove.
7. *Display › North* (spento di default): acceso, in *Calibrate* compaiono la
   freccia N e la linea tratteggiata verso il sole.

## Sole dall'ombra
8. **Ponte levatoio**: *Sun From* = *Shadow*. **Calibrate Shadow** (sezione
   Fit Sun): solo tre maniglie arancioni, niente guide, intestazione "Foot,
   top, shadow tip"; 1/2/3, F, H non fanno nulla. Piede e cima di un montante
   della ringhiera, punta della sua ombra sul ponte. Il pannello dà *Shadow
   Elevation* con ±; la luce segue mentre trascini. Invio o Esc chiudono senza
   toccare la camera. *Calibrate* mentre gira passa alla calibrazione completa
   (e viceversa).
9. Torna a *Date and Place* e scegli *North* = **Shadow**: stesse maniglie, il
   nord viene dall'ombra; *Shadow vs Date* confronta l'elevazione e la crocetta
   bianca segna dove il sole della data metterebbe la punta.
10. **Cabina**: ombra del cartello sul muro: *Shadow On* = parete (XZ o YZ),
    origine nello spigolo muro–marciapiede.

## Fit HDRI
11. World con un HDRI equirettangolare (Environment Texture). Con il sole
    impostato, **Fit HDRI**: si apre il visore sull'HDRI, anello bianco sul punto
    più luminoso, crocetta dove cade il sole della foto. Clic sul sole, **Invio**:
    l'HDRI ruota (nei nodi del World compare *FTC HDRI* o cambia solo la Z del
    tuo Mapping). Esc annulla senza cambiare nulla. Il visore occupa metà
    vista; tenendo **Shift** compare la lente ×4 sul mouse (cursore nascosto,
    mirino al centro, a colori invertiti: si vede anche sul sole bianco): il
    clic sceglie il punto sotto il mirino.
12. Render: ombre della Sun e luce dell'HDRI dalla stessa parte. Cambia la
    *North Correction*: l'HDRI segue (*Follow the Sun*). Ruota a mano la Z del
    Mapping: *Follow the Sun* si spegne.
    World di **Poly Haven** (gruppo con input *Rotation*): Fit HDRI cambia
    l'input *Rotation* del gruppo (in gradi), non il Mapping; il render segue;
    cambiando *Turn* il valore del gruppo si aggiorna.
13. HDRI non equirettangolare (Mirror Ball) o senza World: il pulsante è
    disattivato e un messaggio spiega perché.

## Linee in più
14. *Calibrate* con 2 punti di fuga: **+** accanto ad *Axis 1* aggiunge una
    linea tra le prime due, già puntata sul punto di fuga (nessun avviso). Fino a
    6; **−** toglie l'ultima. Ctrl+Z nella sessione ripristina anche il numero.

## Report e lingua
15. *Results* › **Export Report**: Markdown e JSON (il formato cambia
    l'estensione). Apri il .md: tabelle leggibili, sezione *Sun* se usata.
16. Interfaccia in italiano: *Fit Sun* e *Fit HDRI* restano in inglese; "Data",
    "Ora", "Sole da", "Lato", "Ruota", tooltip di *Fit HDRI* e dei pulsanti − / +
    tradotti.

## Da riportare
Comportamenti strani, errori in console (Window › Toggle System Console),
screenshot dell'overlay o del visore se qualcosa non torna.
