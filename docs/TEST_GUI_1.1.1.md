# Test GUI in Blender (Windows) – 1.1.1

Prova a mano delle correzioni dello sweep di bug dopo la 1.1.0. I test
automatici passano (pytest, test headless in Blender, sonde `scripts/probe.sh`);
qui si controlla quello che solo l'interfaccia mostra, soprattutto la sessione di
calibrazione, che headless non gira.

Zip: `\\wsl.localhost\Ubuntu-24.04\home\tony\Projects\FTC\dist\fit_the_camera-<versione>.zip`.
Installazione: *Edit › Preferences › Get Extensions › ⌄ › Install from Disk…*,
poi riavvia Blender.

## Sessione di calibrazione
1. **Workspace**: con la sessione aperta passa a *Shading* e torna a *Layout*:
   la sessione è ancora attiva (maniglie e intestazione), Ctrl+Z funziona.
2. **Ctrl+Space**: massimizza la vista durante la sessione: le maniglie restano
   trascinabili; Ctrl+Space di nuovo, la sessione continua.
3. **Ctrl+Z del pannello**: in sessione passa da 2 a 3 punti di fuga nel
   pannello, poi Ctrl+Z con il mouse sulla vista: torna a 2 punti di fuga, con le
   guide di prima. Ctrl+Shift+Z lo rifà.
4. **Tasto I** durante la sessione: nessun keyframe sulla camera (nessun avviso
   rosso "Keyframes, drivers...").

## Allineamento e risultati
5. *Align to Scene* › 3D Cursor, poi togli e rimetti la spunta **Use Stored
   Target**: la camera si sposta subito, senza Apply.
6. Scena in centimetri (*Scene › Units › Unit Scale* 0,01, *Length*
   Centimeters): in *Results* l'altezza camera è in cm sensata (non "160 m").
7. *Known Rectangle* su parete XZ: premi F due volte in sessione: la camera
   resta dritta.

## Italiano
8. Interfaccia in italiano: passa il mouse sui menu di *Mode*, *Scale*, *Focal
   Length*, *Principal Point*, sugli assi dei punti di fuga e sulle caselle di
   *Display*: tutti i tooltip in italiano. Sposta le guide fino a un avviso
   giallo (es. "calibrazione instabile (focale ±…%, angoli ±…°)…"): tradotto
   con i numeri, nel pannello e sulla foto. *Fit Sun* e *Fit HDRI* restano in
   inglese.

## Da riportare
Comportamenti strani, errori in console (Window › Toggle System Console),
screenshot se qualcosa non torna.
