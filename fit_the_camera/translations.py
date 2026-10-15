# SPDX-License-Identifier: GPL-3.0-or-later
"""Italian translation of the interface (Preferences > Interface > Translation).

Only add-on specific phrases are listed: registered translations apply to the
whole interface, and generic words are already translated by Blender itself.
"""

import re

import bpy
from bpy.app.translations import pgettext_iface

_IT = {
    # Operators
    "Load Image": "Carica immagine",
    "Make Upright Copy": "Crea copia raddrizzata",
    "Calibrate": "Calibra",
    "Stop Calibrating": "Termina calibrazione",
    "Reset Guides": "Reset guide",
    "Flip Axis Direction": "Inverti verso dell'asse",
    "Camera not updated: {}": "Camera non aggiornata: {}",
    # Camera data
    "35 mm Equivalent": "Equivalente 35 mm",
    "Sensor Width": "Larghezza sensore",
    "From EXIF": "Da EXIF",
    "Focal length": "Focale",
    "Sensor size": "Dimensione sensore",
    "{} not in the image metadata": "{} assente nei metadati dell'immagine",
    "Look up the specifications of: {}": "Cerca le specifiche di: {}",
    "Enter focal length + sensor width, or the 35 mm equivalent": (
        "Inserisci focale + larghezza sensore, oppure l'equivalente 35 mm"
    ),
    "Image stored rotated (EXIF orientation {})": "Immagine salvata ruotata (orientamento EXIF {})",
    "Active camera '{}' is not the view camera": "La camera attiva '{}' non è la camera di vista",
    "No scene camera: load an image to create one": "Nessuna camera di scena: carica un'immagine per crearne una",
    # Calibration
    "Vanishing Points": "Punti di fuga",
    "Known Rectangle": "Rettangolo noto",
    "Axis 1": "Asse 1",
    "Axis 2": "Asse 2",
    "Axis 3": "Asse 3",
    "Axis 2 Line": "Linea asse 2",
    "Cropped image: 35 mm equivalent taken on the uncropped 4:3 sensor": (
        "Immagine ritagliata: equivalente 35 mm riferito al sensore 4:3 intero"
    ),
    "Scale Cube": "Cubo di scala",
    "Cube Size": "Lato del cubo",
    "Custom Size": "Misura personalizzata",
    "Reference Distance": "Misura di riferimento",
    "Reference Axis": "Asse di riferimento",
    "Reference Length": "Lunghezza di riferimento",
    "Known + Guides": "Nota + guide",
    "Guides Only": "Solo guide",
    "Known Only": "Solo nota",
    "vs Known": "Rispetto alla nota",
    "Focal length unknown: solved from the guides": "Focale sconosciuta: risolta dalle guide",
    "Solved principal point: the focal length comes from the guides": (
        "Punto principale risolto: la focale viene dalle guide"
    ),
    "Camera Height": "Altezza camera",
    "Principal Point": "Punto principale",
    "Live Update": "Aggiornamento live",
    "Freeze Guides": "Congela guide",
    "Straighten Horizon": "Raddrizza orizzonte",
    "Pitch Correction": "Correzione beccheggio",
    "Grid Opacity": "Opacità griglia",
    "Needs the focal length (Camera Data)": "Serve la focale (Dati camera)",
    "LMB drag: move  Shift: fine + magnifier  Ctrl: snap  1/2/3: axis  F: flip  H: straighten  "
    "Ctrl+Z / Ctrl+Shift+Z: undo/redo  Enter: apply  Esc/RMB: exit": (
        "LMB trascina: sposta  Shift: fine + lente  Ctrl: snap  1/2/3: asse  F: inverti  H: raddrizza  "
        "Ctrl+Z / Ctrl+Shift+Z: annulla/ripeti  Invio: applica  Esc/RMB: esci"
    ),
    "Align to Scene": "Allinea alla scena",
    "Reference Plane": "Piano di riferimento",
    "3D Cursor": "3D cursor",
    "Selection": "Selezione",
    "Scene Origin": "Origine scena",
    "Rotate 90°": "Ruota 90°",
    "Aligned To": "Allineato a",
    "Use Stored Target": "Usa bersaglio salvato",
    "Third Axis Line": "Linea terzo asse",
    "Measured On": "Misurata su",
    "Solve needs three vanishing points: using the centre": "Risolvi richiede tre punti di fuga: uso il centro",
    # Results
    "Not solved": "Non risolto",
    "Field of View": "Campo visivo",
    "Orientation": "Orientamento",
    "Guide Fit": "Aderenza guide",
    "max {:.2f}°": "max {:.2f}°",
    "Removed Roll": "Rollio rimosso",
    # Render
    "Prepare Render": "Prepara render",
    "Over the Photo": "Sopra la foto",
    "Use Cycles": "Usa Cycles",
    "View Transform: Standard, the photo unchanged": "Trasformazione vista: Standard, foto invariata",
    "Film: Transparent": "Pellicola: trasparente",
    "Scene not set up for the photo: use Prepare Render": "Scena non preparata per la foto: usa Prepara render",
    "Shadow catchers work only in Cycles: in other engines they cover the photo": (
        "Gli shadow catcher funzionano solo in Cycles: negli altri motori coprono la foto"
    ),
    "Object Roles": "Ruoli oggetti",
    "Set Role of Selected": "Ruolo dei selezionati",
    "No Role": "Nessun ruolo",
    "Render size has another aspect than the image: Apply or Calibrate fixes it": (
        "Il render ha proporzioni diverse dall'immagine: Applica o Calibra le correggono"
    ),
    "Keyframes, drivers or constraints on the camera (or its parent) override the calibration": (
        "Keyframe, driver o vincoli sulla camera (o sul suo genitore) sovrascrivono la calibrazione"
    ),
    "Only the active view layer is composited over the photo": ("Solo il view layer attivo viene composto sulla foto"),
    "First Side": "Primo lato",
    "Second Side": "Secondo lato",
    "Side {}": "Lato {}",
    # Camera choice
    "New Camera": "Nuova camera",
    "Name After Photo": "Nome dalla foto",
    "no photo": "nessuna foto",
    "Use Camera": "Usa camera",
    "Create a new camera for the photo": "Crea una nuova camera per la foto",
    "Load the photo into this camera": "Carica la foto in questa camera",
    "Load the photo into this camera, replacing its photo": "Carica la foto in questa camera, al posto della sua",
    "Look through this camera and calibrate it": "Guarda da questa camera e calibrala",
    "The chosen camera is no longer in the scene": "La camera scelta non è più nella scena",
    "Camera that receives the photo: a new one, or one of the scene (its photo is replaced)": (
        "Camera che riceve la foto: una nuova o una della scena (la sua foto viene sostituita)"
    ),
    'Name the new camera after the photo file (otherwise "FTC Camera")': (
        'Dà alla nuova camera il nome del file della foto (altrimenti "FTC Camera")'
    ),
    "Look through another camera with a photo and calibrate it (it becomes the scene camera)": (
        "Guarda da un'altra camera con foto e calibrala (diventa la camera della scena)"
    ),
    # Fit Sun
    "Read from Photo": "Rileggi dalla foto",
    "Read the date, time and place of the shot again from the photo, replacing what was entered by hand": (
        "Rilegge dalla foto data, ora e luogo dello scatto, sostituendo quanto inserito a mano"
    ),
    "New Sun": "Nuovo sole",
    "Add a Sun light that follows the sun of the photo (only its direction: strength and colour are yours)": (
        "Aggiunge una luce Sole che segue il sole della foto (solo la direzione: intensità e colore restano tuoi)"
    ),
    "Year of the shot": "Anno dello scatto",
    "Month of the shot": "Mese dello scatto",
    "Day of the shot": "Giorno dello scatto",
    "Local hour of the shot": "Ora locale dello scatto",
    "Minute of the shot": "Minuto dello scatto",
    "Second of the shot": "Secondo dello scatto",
    "Time zone of the local time, daylight saving included (e.g. +2 for Italy in summer)": (
        "Fuso orario dell'ora locale, ora legale compresa (es. +2 per l'Italia d'estate)"
    ),
    "The time is the GPS time (UTC) of the photo": "L'ora è quella GPS (UTC) della foto",
    "The GPS time and the camera clock disagree": "L'ora GPS e l'orologio della fotocamera non concordano",
    "Where the photo was taken, degrees north (negative south); a city is close enough for the sun": (
        "Dove è stata scattata la foto, gradi nord (negativi a sud); per il sole basta la città"
    ),
    "Where the photo was taken, degrees east (negative west); a city is close enough for the sun": (
        "Dove è stata scattata la foto, gradi est (negativi a ovest); per il sole basta la città"
    ),
    "Sun light that FTC turns towards the sun of the photo (only its rotation is changed)": (
        "Luce Sole che FTC orienta verso il sole della foto (cambia solo la rotazione)"
    ),
    "From the compass direction of the photo (EXIF), rarely written by Android phones": (
        "Dalla direzione della bussola nella foto (EXIF), che i telefoni Android scrivono di rado"
    ),
    "The HDRI's node group is linked from a library: make it local to fit its HDRI": (
        "Il gruppo di nodi dell'HDRI è collegato da una libreria: rendilo locale per adattarne l'HDRI"
    ),
    "The HDRI's node group is used elsewhere too: it turns there as well": (
        "Il gruppo di nodi dell'HDRI è usato anche altrove: ruota anche lì"
    ),
    "Magnetic declination at the place, east positive: added to a magnetic compass direction "
    "(look it up for the place and year)": (
        "Declinazione magnetica del luogo, positiva a est: si somma a una direzione di bussola magnetica "
        "(cercala per il luogo e l'anno)"
    ),
    "Show the scene north and the sun direction on the ground through the origin while calibrating": (
        "Mostra il nord della scena e la direzione del sole sul suolo per l'origine durante la calibrazione"
    ),
    "Sun Azimuth": "Azimut del sole",
    "Sun Elevation": "Elevazione del sole",
    "Pick a Sun light or add one: FTC turns it towards the sun": (
        "Scegli una luce Sole o aggiungine una: FTC la orienta verso il sole"
    ),
    "Date and time unknown: enter the local time of the shot, or Read from Photo": (
        "Data e ora sconosciute: inserisci l'ora locale dello scatto, o Rileggi dalla foto"
    ),
    "The GPS time and the camera clock disagree: check the time (camera clock and its time zone used)": (
        "L'ora GPS e l'orologio della fotocamera non concordano: controlla l'ora (usati orologio e fuso)"
    ),
    "The camera looks steeply up or down: its compass is unreliable, check the north": (
        "La camera guarda molto in alto o in basso: la sua bussola è inaffidabile, controlla il nord"
    ),
    "The light is in no scene (deleted?): pick another one or add a New Sun": (
        "La luce non è in nessuna scena (cancellata?): scegline un'altra o aggiungi un Nuovo sole"
    ),
    "The light cannot be edited (linked from a library): pick another one or add a New Sun": (
        "La luce non è modificabile (collegata da una libreria): scegline un'altra o aggiungi un Nuovo sole"
    ),
    "Keyframes, drivers or constraints on the light (or its parent) override its rotation": (
        "Keyframe, driver o vincoli sulla luce (o sul suo genitore) ne sovrascrivono la rotazione"
    ),
    "No date, time or place found in the photo": "Nessuna data, ora o luogo trovati nella foto",
    "Time zone unknown: enter the UTC offset of the local time, daylight saving included": (
        "Fuso orario sconosciuto: inserisci il fuso UTC dell'ora locale, ora legale compresa"
    ),
    "Invalid date": "Data non valida",
    "Place unknown: enter latitude and longitude (the nearest town is close enough)": (
        "Luogo sconosciuto: inserisci latitudine e longitudine (basta la città più vicina)"
    ),
    "The sun is below the horizon at that time: check date, time and UTC offset": (
        "A quell'ora il sole è sotto l'orizzonte: controlla data, ora e fuso UTC"
    ),
    "The GPS time and the camera clock disagree: check the time (GPS time used)": (
        "L'ora GPS e l'orologio della fotocamera non concordano: controlla l'ora (usata quella GPS)"
    ),
    "Magnetic compass: enter the declination of the place": "Bussola magnetica: inserisci la declinazione del luogo",
    "Calibrate the camera first: the north is found from its view": (
        "Calibra prima la camera: il nord si ricava dalla sua vista"
    ),
    "The camera looks straight up or down: no north from its compass": (
        "La camera guarda dritta in alto o in basso: la bussola non dà il nord"
    ),
    # Fit Sun: shadow
    "Where the direction of the sun comes from": "Da dove arriva la direzione del sole",
    "Computed from the date, time and place of the shot, with the scene north": (
        "Calcolata da data, ora e luogo dello scatto, con il nord della scena"
    ),
    "Measured on a shadow in the photo: no date, place or north needed": (
        "Misurata su un'ombra nella foto: non servono data, luogo né nord"
    ),
    "Plane through the origin where the tip of the shadow lies (the foot is always on the ground)": (
        "Piano per l'origine su cui sta la punta dell'ombra (il piede è sempre a terra)"
    ),
    "The ground: plane XY through the origin": "Il suolo: piano XY per l'origine",
    "The wall XZ through the origin: put the origin where the wall meets the ground": (
        "La parete XZ per l'origine: metti l'origine dove la parete incontra il suolo"
    ),
    "The wall YZ through the origin: put the origin where the wall meets the ground": (
        "La parete YZ per l'origine: metti l'origine dove la parete incontra il suolo"
    ),
    "the shadow tip is below the ground: put it on the ground, or the origin on the wall's foot": (
        "la punta dell'ombra è sotto il suolo: mettila a terra, o l'origine al piede della parete"
    ),
    "From a shadow in the photo (shadow handles in Calibrate Shadow) and the sun of the date and place": (
        "Da un'ombra nella foto (maniglie dell'ombra in Calibra ombra) e dal sole di data e luogo"
    ),
    "Calibrate Shadow: orange handles on the foot and the top of something vertical, and on the tip of its shadow": (
        "Calibra ombra: maniglie arancioni sul piede e sulla cima di qualcosa di verticale, e sulla punta della "
        "sua ombra"
    ),
    "Calibrate Shadow": "Calibra ombra",
    "End placing the shadow handles": "Termina il posizionamento delle maniglie dell'ombra",
    "Place the shadow handles in the camera view: the foot and the top of something vertical, the tip "
    "of its shadow. The calibration guides are hidden and the camera is not changed": (
        "Posiziona le maniglie dell'ombra nella vista camera: il piede e la cima di qualcosa di verticale, la "
        "punta della sua ombra. Le guide di calibrazione sono nascoste e la camera non cambia"
    ),
    "Only the shadow handles of Fit Sun: the guides are hidden and the camera is not changed": (
        "Solo le maniglie dell'ombra di Fit Sun: le guide sono nascoste e la camera non cambia"
    ),
    "Shadow Only": "Solo ombra",
    "Foot, top, shadow tip  |  LMB drag: move  Shift: fine + magnifier  Ctrl: snap  "
    "Ctrl+Z / Ctrl+Shift+Z: undo/redo  Enter/Esc/RMB: done": (
        "Piede, cima, punta dell'ombra  |  LMB trascina: sposta  Shift: fine + lente  Ctrl: snap  "
        "Ctrl+Z / Ctrl+Shift+Z: annulla/ripeti  Invio/Esc/RMB: fine"
    ),
    "Shadow Elevation": "Elevazione dall'ombra",
    "Shadow vs Date": "Ombra / data",
    "{:+.1f}° elevation": "{:+.1f}° di elevazione",
    "Calibrate the camera first: the shadow is measured through it": (
        "Calibra prima la camera: l'ombra si misura attraverso di lei"
    ),
    "Place the shadow handles on the photo (Calibrate Shadow)": (
        "Metti le maniglie dell'ombra sulla foto (Calibra ombra)"
    ),
    "The sun is almost overhead: its shadow gives no north": "Il sole è quasi allo zenit: la sua ombra non dà il nord",
    "the foot of the object is beyond the horizon: put it on the ground": (
        "il piede dell'oggetto è oltre l'orizzonte: mettilo a terra"
    ),
    "the top of the object must be above its foot": "la cima dell'oggetto deve stare sopra il piede",
    "the shadow tip is beyond the horizon of its plane": "la punta dell'ombra è oltre l'orizzonte del suo piano",
    "the shadow tip is on the top of the object": "la punta dell'ombra coincide con la cima dell'oggetto",
    "this shadow puts the sun below the horizon: check the handles and the shadow plane": (
        "quest'ombra mette il sole sotto l'orizzonte: controlla le maniglie e il piano dell'ombra"
    ),
    # Fit HDRI
    "Several Environment Textures reach the World output: using the first by name": (
        "Più Environment Texture arrivano all'uscita del World: uso la prima per nome"
    ),
    "Turn the World's HDRI about Z so that its sun takes the direction of the photo's sun: click the sun on "
    "the HDRI (FTC proposes the brightest spot), Enter applies": (
        "Ruota l'HDRI del World attorno a Z finché il suo sole prende la direzione del sole della foto: clicca "
        "il sole sull'HDRI (FTC propone il punto più luminoso), Invio applica"
    ),
    "Point of the sun on the HDRI (0..1, origin bottom-left); negative: let FTC find it": (
        "Punto del sole sull'HDRI (0..1, origine in basso a sinistra); negativo: lo trova FTC"
    ),
    "Point of the sun on the HDRI picked by Fit HDRI (0..1, origin bottom-left)": (
        "Punto del sole sull'HDRI scelto da Fit HDRI (0..1, origine in basso a sinistra)"
    ),
    "HDRI image fitted by Fit HDRI": "Immagine HDRI adattata da Fit HDRI",
    "The World has no nodes: add an Environment Texture with an HDRI": (
        "Il World non ha nodi: aggiungi un'Environment Texture con un HDRI"
    ),
    "No Environment Texture reaches the World output": "Nessuna Environment Texture arriva all'uscita del World",
    "The Environment Texture has no image": "L'Environment Texture non ha un'immagine",
    "The Environment Texture is not equirectangular: Fit HDRI needs an equirectangular HDRI": (
        "L'Environment Texture non è equirettangolare: Fit HDRI vuole un HDRI equirettangolare"
    ),
    "No sun yet: set Fit Sun first": "Ancora nessun sole: imposta prima Fit Sun",
    "The HDRI image cannot be read": "L'immagine HDRI non si può leggere",
    "The HDRI's sun is {:+.0f}° off the photo's in elevation: the shadows will not have the same length": (
        "Il sole dell'HDRI differisce di {:+.0f}° in elevazione da quello della foto: le ombre non avranno la "
        "stessa lunghezza"
    ),
    "Click the sun in the HDRI · Shift: magnifier · Enter: apply · Esc: cancel · ×: the photo's sun (Fit Sun)": (
        "Clicca il sole nell'HDRI · Shift: lente · Invio: applica · Esc: annulla · ×: il sole della foto (Fit Sun)"
    ),
    "HDRI Rotation": "Rotazione HDRI",
    "Sun Point": "Punto del sole",
    "The World is linked from a library: make it local to fit its HDRI": (
        "Il World è collegato da una libreria: rendilo locale per adattarne l'HDRI"
    ),
    "The HDRI's vector comes from other nodes (not a Mapping): Fit HDRI cannot turn it": (
        "Il vettore dell'HDRI arriva da altri nodi (non un Mapping): Fit HDRI non può ruotarlo"
    ),
    "The rotation of the HDRI's Mapping comes from nodes FTC cannot follow back: Fit HDRI cannot turn it": (
        "La rotazione del Mapping dell'HDRI arriva da nodi che FTC non sa ripercorrere: Fit HDRI non può ruotarlo"
    ),
    "The rotation of the HDRI is keyframed or driven: Fit HDRI cannot turn it": (
        "La rotazione dell'HDRI ha keyframe o driver: Fit HDRI non può ruotarlo"
    ),
    "The HDRI's rotation input cannot take the angle (its min / max): widen them or Fit HDRI cannot turn it": (
        "L'input di rotazione dell'HDRI non accetta l'angolo (min / max): allargali o Fit HDRI non può ruotarlo"
    ),
    "The HDRI's Mapping has an X or Y rotation or scale: its sun is matched about Z only, check it": (
        "Il Mapping dell'HDRI ha rotazione o scala in X o Y: il sole viene allineato solo attorno a Z, controllalo"
    ),
    "No clear sun in the HDRI: click it in the Fit HDRI viewer (3D view)": (
        "Nessun sole evidente nell'HDRI: cliccalo nel visore di Fit HDRI (vista 3D)"
    ),
    "The World HDRI changed: Fit HDRI again": "L'HDRI del World è cambiato: rifai Fit HDRI",
    "Z turn last given to the HDRI by FTC (radians)": "Ultima rotazione Z data all'HDRI da FTC (radianti)",
    "Keep the World HDRI on the sun when the sun moves (north, time). Fit HDRI turns it on; turning the "
    "HDRI's Mapping by hand turns it off": (
        "Tiene l'HDRI del World sul sole quando il sole si muove (nord, ora). Fit HDRI lo accende; ruotare a "
        "mano il Mapping dell'HDRI lo spegne"
    ),
    "HDRI Sun Elevation": "Elevazione del sole HDRI",
    "HDRI sun and Sun light both give direct light: lower one of them": (
        "Il sole dell'HDRI e la luce Sole danno entrambi luce diretta: abbassa uno dei due"
    ),
    "End the calibration session, keeping the guides": "Termina la sessione di calibrazione, tenendo le guide",
    "Edit the calibration guides in the camera view: drag the handles onto lines of the image. "
    "Shortcuts are listed in the header": (
        "Modifica le guide di calibrazione nella vista camera: trascina le maniglie sulle linee dell'immagine. "
        "Le scorciatoie sono nell'header"
    ),
    "Flip the third axis. It follows from the first two (the world is right-handed): "
    "axis 2 flips with it, or axis 1 when axis 2 is Z": (
        "Inverte il terzo asse. Segue dai primi due (il riferimento è destrorso): con lui si inverte l'asse 2, "
        "o l'asse 1 se il 2 è Z"
    ),
    "Flip the direction of this axis (the arrow on its first guide)": (
        "Inverte il verso di questo asse (la freccia sulla sua prima guida)"
    ),
    # Extra guide lines
    "Guide Lines": "Linee guida",
    "Add a guide line to this vanishing point (up to 6), between its first two lines: more lines average out "
    "the placement errors": (
        "Aggiunge una linea guida a questo punto di fuga (fino a 6), tra le prime due: più linee mediano gli "
        "errori di posizionamento"
    ),
    "Remove the last guide line of this vanishing point (two stay)": (
        "Toglie l'ultima linea guida di questo punto di fuga (due restano)"
    ),
    "Guide lines of vanishing point 1 (2 to 6): more lines average out the placement errors": (
        "Linee guida del punto di fuga 1 (da 2 a 6): più linee mediano gli errori di posizionamento"
    ),
    "Guide lines of vanishing point 2 (2 to 6): more lines average out the placement errors": (
        "Linee guida del punto di fuga 2 (da 2 a 6): più linee mediano gli errori di posizionamento"
    ),
    "Guide lines of vanishing point 3 (2 to 6): more lines average out the placement errors": (
        "Linee guida del punto di fuga 3 (da 2 a 6): più linee mediano gli errori di posizionamento"
    ),
    # Report
    "Export Report": "Esporta report",
    "Save the calibration report: focal length, sensor, field of view, camera position and rotation, "
    "accuracy, guide fit, the source of every input and the sun, as Markdown or JSON": (
        "Salva il report di calibrazione: focale, sensore, campo visivo, posizione e rotazione della camera, "
        "precisione, aderenza delle guide, la fonte di ogni dato e il sole, in Markdown o JSON"
    ),
    "File format of the report": "Formato del file del report",
    "A readable page (.md)": "Una pagina leggibile (.md)",
    "Data for other programs (.json)": "Dati per altri programmi (.json)",
    "Report saved: {}": "Report salvato: {}",
    # Fit Sun: side
    "How the sun is placed around the scene (its height comes from the date)": (
        "Come si colloca il sole attorno alla scena (l'altezza viene dalla data)"
    ),
    "Replaced by Side": "Sostituito da Lato",
    "Pick the scene axis the sun comes from, then turn it by eye until the CG shadows match the photo": (
        "Scegli l'asse della scena da cui arriva il sole, poi ruotalo a occhio finché le ombre della CG "
        "coincidono con la foto"
    ),
    "Scene axis the sun comes from: the shadows in the photo fall the other way (-Y is usually behind the camera)": (
        "Asse della scena da cui arriva il sole: le ombre nella foto cadono dalla parte opposta "
        "(-Y di solito è dietro la camera)"
    ),
    "The sun comes from the +X side": "Il sole arriva dal lato +X",
    "The sun comes from the -X side": "Il sole arriva dal lato -X",
    "The sun comes from the +Y side": "Il sole arriva dal lato +Y",
    "The sun comes from the -Y side": "Il sole arriva dal lato -Y",
    "Turns the sun about the vertical (with the compass: the scene north): adjust it until the CG "
    "shadows match the photo; phone compasses are often 5-15° off": (
        "Ruota il sole attorno alla verticale (con la bussola: il nord della scena): regolala finché le ombre "
        "della CG coincidono con la foto; le bussole dei telefoni sbagliano spesso di 5-15°"
    ),
    "Raises (or lowers) the sun from the height of the date and time: adjust it until the CG "
    "shadows are as long as in the photo (it makes up for small calibration and clock errors)": (
        "Alza (o abbassa) il sole rispetto all'altezza di data e ora: regolala finché le ombre della CG "
        "sono lunghe come nella foto (compensa piccoli errori di calibrazione e di orologio)"
    ),
    "No compass direction in the photo: use Side or Shadow": "Nessuna bussola nella foto: usa Lato o Ombra",
    "Shadow vs Compass": "Ombra / bussola",
    "Show the shadow handles (foot and top of something vertical, tip of its shadow) to check the north "
    "and the sun's height: the × marks where the Fit Sun sun puts the shadow tip": (
        "Mostra le maniglie dell'ombra (piede e cima di qualcosa di verticale, punta della sua ombra) per "
        "verificare il nord e l'altezza del sole: la × segna dove il sole di Fit Sun mette la punta dell'ombra"
    ),
    "×: the tip by the Fit Sun sun ({}, Raise)": "×: la punta data dal sole di Fit Sun ({}, Alza)",
    "×: the tip by the Fit Sun sun (Raise)": "×: la punta data dal sole di Fit Sun (Alza)",
    "No shadow handles in use: choose Sun From Shadow, North Shadow or Check with a Shadow": (
        "Nessuna maniglia dell'ombra in uso: scegli Sole da Ombra, Nord Ombra o Verifica con un'ombra"
    ),
    "The rotation of the HDRI is in a node group linked from a library: make it local to fit its HDRI": (
        "La rotazione dell'HDRI è in un gruppo di nodi collegato da libreria: rendilo locale per adattare l'HDRI"
    ),
    "The HDRI's Mapping node is muted: unmute it or remove it": (
        "Il nodo Mapping dell'HDRI è disattivato (mute): riattivalo o rimuovilo"
    ),
    "The HDRI's node group is used several times: only this instance's rotation input turns": (
        "Il gruppo di nodi dell'HDRI è usato più volte: ruota solo l'input di rotazione di questa istanza"
    ),
    "Show the cube of known size on the reference plane, to check the scale by eye (known rectangle and horizon)": (
        "Mostra il cubo di dimensione nota sul piano di riferimento, per verificare la scala a occhio "
        "(rettangolo noto e orizzonte)"
    ),
    "Direction of the reference distance: along the reference plane both ends lie on the plane, "
    "anywhere on it; along its normal it is a height above the first end": (
        "Direzione della distanza di riferimento: lungo il piano di riferimento entrambi gli estremi stanno sul "
        "piano, in qualsiasi punto; lungo la sua normale è un'altezza sopra il primo estremo"
    ),
    "Real length of the rectangle's first side (corner 1 to 2), along the "
    "reference plane's first axis: X on XY and XZ, Y on YZ": (
        "Lunghezza reale del primo lato del rettangolo (dall'angolo 1 al 2), lungo il primo asse del piano di "
        "riferimento: X su XY e XZ, Y su YZ"
    ),
    "Real length of the rectangle's second side (corner 2 to 3), along the "
    "reference plane's second axis: Y on XY, Z on XZ and YZ": (
        "Lunghezza reale del secondo lato del rettangolo (dall'angolo 2 al 3), lungo il secondo asse del piano "
        "di riferimento: Y su XY, Z su XZ e YZ"
    ),
    "With two vanishing points, add one line along the third axis (e.g. a vertical edge): it joins "
    "the calibration and keeps that axis on the image": (
        "Con due punti di fuga, aggiunge una linea lungo il terzo asse (es. uno spigolo verticale): entra nella "
        "calibrazione e tiene quell'asse sull'immagine"
    ),
    "×: where the Fit Sun sun puts the shadow tip; Raise moves it along the shadow": (
        "×: dove il sole di Fit Sun mette la punta dell'ombra; Alza la sposta lungo l'ombra"
    ),
    "×: where the Fit Sun sun puts the shadow tip; {} moves it sideways, Raise along the shadow": (
        "×: dove il sole di Fit Sun mette la punta dell'ombra; {} la sposta di lato, Alza lungo l'ombra"
    ),
    "Shadow vs Turn": "Ombra / Ruota",
    # FTC orientation
    "FTC Orientation": "Orientamento FTC",
    "No 3D view to create the orientation from": "Nessuna vista 3D da cui creare l'orientamento",
    # Settings (tooltips)
    "Original image file": "File originale dell'immagine",
    "What in the image defines the camera": "Cosa nell'immagine definisce la camera",
    "Calibrate from parallel lines converging to 1, 2 or 3 vanishing points": (
        "Calibra da linee parallele che convergono in 1, 2 o 3 punti di fuga"
    ),
    "Calibrate from the four corners of a rectangle of known size": (
        "Calibra dai quattro angoli di un rettangolo di dimensioni note"
    ),
    "Calibrate from the horizon line and the camera height": (
        "Calibra dalla linea dell'orizzonte e dall'altezza della camera"
    ),
    "Number of vanishing points to draw": "Numero di punti di fuga da tracciare",
    "One vanishing point: needs the focal length and the horizon direction": (
        "Un punto di fuga: servono la focale e la direzione dell'orizzonte"
    ),
    "Two vanishing points: solves the focal length": "Due punti di fuga: risolve la focale",
    "Three vanishing points: solves focal length and principal point": (
        "Tre punti di fuga: risolve focale e punto principale"
    ),
    "Vanishing Point 1": "Punto di fuga 1",
    "Vanishing Point 2": "Punto di fuga 2",
    "Vanishing Point 3": "Punto di fuga 3",
    "World axis of the first guide pair: + runs along its first guide, from the first handle to the second "
    "(the arrow)": (
        "Asse del mondo della prima coppia di guide: il + va lungo la sua prima guida, dalla prima maniglia "
        "alla seconda (la freccia)"
    ),
    "World axis of the second guide pair, or of the axis line with one vanishing point": (
        "Asse del mondo della seconda coppia di guide, o della linea d'asse con un punto di fuga"
    ),
    "World axis of the third guide pair (follows from the first two)": (
        "Asse del mondo della terza coppia di guide (deriva dalle prime due)"
    ),
    "Positive X axis": "Asse X positivo",
    "Negative X axis": "Asse X negativo",
    "Positive Y axis": "Asse Y positivo",
    "Negative Y axis": "Asse Y negativo",
    "Positive Z axis": "Asse Z positivo",
    "Negative Z axis": "Asse Z negativo",
    "How the real-world size of the scene is set": "Come si fissa la dimensione reale della scena",
    "A cube of known size standing on the reference plane: drag its top handle until it matches something "
    "of that height in the photo": (
        "Un cubo di dimensione nota appoggiato sul piano di riferimento: trascina la maniglia in cima finché "
        "corrisponde a qualcosa di quell'altezza nella foto"
    ),
    "A known length between two points of a plane (Measured On), or a height above it": (
        "Una lunghezza nota tra due punti di un piano (Misurata su), o un'altezza sopra di esso"
    ),
    "Edge length of the scale cube": "Lunghezza dello spigolo del cubo di scala",
    "Cube edge of 10 cm": "Spigolo del cubo di 10 cm",
    "Cube edge of 20 cm": "Spigolo del cubo di 20 cm",
    "Cube edge of 50 cm": "Spigolo del cubo di 50 cm",
    "Cube edge of 1 m": "Spigolo del cubo di 1 m",
    "Cube edge of 2 m": "Spigolo del cubo di 2 m",
    "Cube edge of 5 m": "Spigolo del cubo di 5 m",
    "Cube edge of 10 m": "Spigolo del cubo di 10 m",
    "Enter the edge length": "Inserisci la lunghezza dello spigolo",
    "The reference length runs along X": "La lunghezza di riferimento corre lungo X",
    "The reference length runs along Y": "La lunghezza di riferimento corre lungo Y",
    "The reference length runs along Z": "La lunghezza di riferimento corre lungo Z",
    "Real length between the two reference handles": "Lunghezza reale tra le due maniglie di riferimento",
    "Plane through the origin that holds the reference distance: both ends along an axis of it, or a height "
    "along its normal from the first end": (
        "Piano per l'origine che contiene la misura di riferimento: entrambi gli estremi lungo un suo asse, "
        "o un'altezza lungo la sua normale dal primo estremo"
    ),
    "Floor or any horizontal plane": "Pavimento o qualsiasi piano orizzontale",
    "Wall facing -Y, with Z up": "Parete rivolta verso -Y, con Z in alto",
    "Wall facing +X, with Z up": "Parete rivolta verso +X, con Z in alto",
    "Where the focal length comes from (vanishing points and rectangle)": (
        "Da dove viene la focale (punti di fuga e rettangolo)"
    ),
    "Start from the focal length in Camera Data and let the guides correct it as far as they measure it; "
    "when it is unknown, solve it from the guides": (
        "Parte dalla focale in Dati camera e lascia che le guide la correggano per quanto la misurano; "
        "se è sconosciuta, la risolve dalle guide"
    ),
    "Solve the focal length from the guides, ignoring Camera Data": (
        "Risolve la focale dalle guide, ignorando Dati camera"
    ),
    "Use the focal length in Camera Data as it is: the guides only set the orientation": (
        "Usa la focale di Dati camera così com'è: le guide fissano solo l'orientamento"
    ),
    "Height of the camera above the ground": "Altezza della camera dal suolo",
    "Where the camera heading comes from": "Da dove viene la direzione della camera",
    "Use the image direction from GPS metadata": "Usa la direzione dell'immagine dai metadati GPS",
    "Enter the heading by hand": "Inserisci la direzione a mano",
    "Heading of the camera, clockwise from +Y": "Direzione della camera, in senso orario da +Y",
    "Point of the image hit by the optical axis": "Punto dell'immagine colpito dall'asse ottico",
    "Principal point at the image centre": "Punto principale al centro dell'immagine",
    "Drag the principal point in the viewport": "Trascina il punto principale nella vista",
    "Three vanishing points only: solve it as their orthocentre (unstable when one is far away)": (
        "Solo con tre punti di fuga: lo risolve come loro ortocentro (instabile se uno è lontano)"
    ),
    "Force zero roll": "Forza il rollio a zero",
    "Manual tilt from the horizon handle; reset when the guides change": (
        "Inclinazione manuale dalla maniglia dell'orizzonte; azzerata quando cambiano le guide"
    ),
    "Write the camera on every change while calibrating": "Scrive la camera a ogni modifica durante la calibrazione",
    "Lock the guides against accidental edits": "Blocca le guide contro modifiche accidentali",
    "Show the verification grid on the reference plane": "Mostra la griglia di verifica sul piano di riferimento",
    "Opacity of the verification grid": "Opacità della griglia di verifica",
    "Calibrated plane used for the rectangle, the grid, the scale cube and the scene alignment": (
        "Piano calibrato usato per il rettangolo, la griglia, il cubo di scala e l'allineamento alla scena"
    ),
    "Place the reference plane on the stored scene target (3D cursor, face or object)": (
        "Mette il piano di riferimento sul bersaglio salvato nella scena (3D cursor, faccia od oggetto)"
    ),
    "Scene target of the alignment": "Bersaglio dell'allineamento nella scena",
    "Quarter turns of the reference plane about its normal on the target": (
        "Quarti di giro del piano di riferimento attorno alla sua normale sul bersaglio"
    ),
    "Turn the reference plane over on the target": "Capovolge il piano di riferimento sul bersaglio",
    "{} (face)": "{} (faccia)",
    "Normalised image position": "Posizione normalizzata nell'immagine",
    # Camera data (tooltips)
    "EXIF orientation (1 = upright)": "Orientamento EXIF (1 = dritta)",
    "Real focal length of the lens": "Focale reale dell'obiettivo",
    "Focal length equivalent on a 36x24 mm frame": "Focale equivalente su un formato 36x24 mm",
    "Long side of the camera sensor, as in its specifications (for cropped photos too)": (
        "Lato lungo del sensore della fotocamera, come nelle specifiche (anche per foto ritagliate)"
    ),
    "Not found in the image metadata": "Non trovato nei metadati dell'immagine",
    "Read from the image metadata": "Letto dai metadati dell'immagine",
    "Entered by hand": "Inserito a mano",
    "Compass bearing of the view, degrees clockwise from north": (
        "Direzione di bussola della vista, gradi in senso orario dal nord"
    ),
    "Direction Reference": "Riferimento della direzione",
    "T = true north, M = magnetic north": "T = nord geografico, M = nord magnetico",
    # Results (names)
    "Focal (px)": "Focale (px)",
    "Distance to Origin": "Distanza dall'origine",
    "Focal Uncertainty": "Incertezza focale",
    "Angle Uncertainty": "Incertezza angoli",
    # Render roles
    "Stand-in for a real surface of the photo: shows the photo, receives the shadows and light of the CG "
    "objects and hides what is behind it (Cycles only)": (
        "Sostituto di una superficie reale della foto: mostra la foto, riceve ombre e luce degli oggetti CG "
        "e nasconde ciò che sta dietro (solo Cycles)"
    ),
    "Stand-in for a real object in front: shows the photo and hides the CG objects behind it. It still casts "
    "shadows: turn off Object > Visibility > Shadow if its shadow is already in the photo": (
        "Sostituto di un oggetto reale davanti: mostra la foto e nasconde gli oggetti CG dietro. Proietta "
        "comunque ombre: disattiva Oggetto > Visibilità > Ombra se la sua ombra è già nella foto"
    ),
    "Object selected in the roles list": "Oggetto selezionato nella lista dei ruoli",
    "Cycles is not available (add-on disabled): engine unchanged": (
        "Cycles non è disponibile (add-on disattivato): motore invariato"
    ),
    "Custom colour configuration: set a view that leaves the photo unchanged by hand": (
        "Configurazione colore personalizzata: imposta a mano una vista che lasci la foto invariata"
    ),
    "The photo file is missing: the render will have no background": (
        "Il file della foto manca: il render non avrà sfondo"
    ),
    "Compositing turned off for the transparent output": "Compositing disattivato per l'uscita trasparente",
    # Reports
    "Render height changed to the image's aspect ratio": "Altezza del render adattata alle proporzioni dell'immagine",
    "Calibration ended: its 3D view was closed": "Calibrazione terminata: la sua vista 3D è stata chiusa",
    "Cannot read the image": "Impossibile leggere l'immagine",
    "The image is stored rotated: use 'Make Upright Copy' in Camera Data": (
        "L'immagine è salvata ruotata: usa 'Crea copia raddrizzata' in Dati camera"
    ),
    "Focal length not found in the image metadata": "Focale non trovata nei metadati dell'immagine",
    "The photo cannot be read: is its file missing?": "Impossibile leggere la foto: manca il file?",
    "Select one face (or make one face active)": "Seleziona una faccia (o rendine attiva una)",
    "The face has no area: select another face": "La faccia non ha area: selezionane un'altra",
    "The HDRI image cannot be read: is its file missing?": "Impossibile leggere l'immagine HDRI: manca il file?",
    "The HDRI's Mapping has a Location, an X or Y rotation or a scale: its sun is matched about Z only, check it": (
        "Il Mapping dell'HDRI ha una Location, una rotazione X o Y o una scala: il suo sole è allineato solo "
        "attorno a Z, controllalo"
    ),
    "The HDRI's vector comes from a Texture Coordinate output other than Generated: Fit HDRI cannot turn it": (
        "Il vettore dell'HDRI arriva da un'uscita di Texture Coordinate diversa da Generated: Fit HDRI non può ruotarlo"
    ),
    "The alignment stands the chosen side axis upright: pick another side": (
        "L'allineamento mette in verticale l'asse del lato scelto: scegli un altro lato"
    ),
    # Solver messages (shown in the panel and on the photo)
    "no image loaded": "nessuna immagine caricata",
    "the focal length is unknown: enter it in Camera Data": "la focale è sconosciuta: inseriscila in Dati camera",
    "one vanishing point needs the focal length: enter it in Camera Data": (
        "un punto di fuga richiede la focale: inseriscila in Dati camera"
    ),
    "the horizon mode needs the focal length: enter it in Camera Data": (
        "la modalità orizzonte richiede la focale: inseriscila in Dati camera"
    ),
    "unstable calibration (focal ±{}%, angles ±{}°): use longer guides further apart, add a third axis line "
    "or a third vanishing point, or use the known focal length": (
        "calibrazione instabile (focale ±{}%, angoli ±{}°): usa guide più lunghe e più distanti, aggiungi una "
        "linea del terzo asse o un terzo punto di fuga, oppure usa la focale nota"
    ),
    "the guides disagree with the known focal length by up to {}°: the photo may be cropped or zoomed, "
    "try solving the focal length": (
        "le guide non concordano con la focale nota fino a {}°: la foto può essere ritagliata o zoomata, "
        "prova a risolvere la focale"
    ),
    "the guides do not meet consistently (up to {}° off): some lines may not be parallel to their axis": (
        "le guide non si incontrano in modo coerente (fino a {}° di scarto): alcune linee potrebbero non "
        "essere parallele al loro asse"
    ),
    "the guides overrule the known focal length ({}%): the photo may be cropped or zoomed": (
        "le guide correggono la focale nota ({}%): la foto può essere ritagliata o zoomata"
    ),
    "straighten horizon removed {}° of roll: the camera no longer matches the guides": (
        "raddrizza orizzonte ha tolto {}° di rollio: la camera non corrisponde più alle guide"
    ),
    "a vanishing point needs at least two lines": "un punto di fuga richiede almeno due linee",
    "a guide line has zero length": "una guida ha lunghezza nulla",
    "the guide lines of a vanishing point lie on one line: move them apart": (
        "le guide di un punto di fuga stanno su una sola retta: separale"
    ),
    "the reference point lies on a line parallel to its axis": (
        "il punto di riferimento sta su una retta parallela al suo asse"
    ),
    "the three vanishing points are collinear": "i tre punti di fuga sono allineati",
    "the reference distance is zero": "la misura di riferimento è nulla",
    "the first reference handle is beyond the horizon of its plane: move it closer": (
        "la prima maniglia di riferimento è oltre l'orizzonte del suo piano: avvicinala"
    ),
    "the second reference handle is beyond the horizon of its plane: move it closer": (
        "la seconda maniglia di riferimento è oltre l'orizzonte del suo piano: avvicinala"
    ),
    "the vanishing points do not fit a real camera: the two directions are probably not perpendicular in "
    "reality (e.g. two facades that are nearly parallel), or one vanishes too far away; use the known focal "
    "length or other lines": (
        "i punti di fuga non corrispondono a una camera reale: le due direzioni probabilmente non sono "
        "perpendicolari nella realtà (es. due facciate quasi parallele), o una fugge troppo lontano; usa la "
        "focale nota o altre linee"
    ),
    "the second axis line has zero length": "la linea del secondo asse ha lunghezza nulla",
    "the second axis line points at the first vanishing point": (
        "la linea del secondo asse punta verso il primo punto di fuga"
    ),
    "guide lines are parallel in the image: the vanishing point is at infinity": (
        "le guide sono parallele nell'immagine: il punto di fuga è all'infinito"
    ),
    "use 1, 2 or 3 vanishing points": "usa 1, 2 o 3 punti di fuga",
    "two axes are required": "servono due assi",
    "the first two vanishing points must use different axes": "i primi due punti di fuga devono usare assi diversi",
    "one vanishing point needs a known focal length": "un punto di fuga richiede una focale nota",
    "one vanishing point needs a line along the second axis": (
        "un punto di fuga richiede una linea lungo il secondo asse"
    ),
    "the camera distance must be positive": "la distanza della camera deve essere positiva",
    "the camera is below the XY plane: flip an axis if this is not intended": (
        "la camera è sotto il piano XY: inverti un asse se non è voluto"
    ),
    "the horizon mode needs a known focal length": "la modalità orizzonte richiede una focale nota",
    "the camera height must be positive": "l'altezza della camera deve essere positiva",
    "the horizon line has zero length": "la linea dell'orizzonte ha lunghezza nulla",
    "the camera looks straight up or down: the horizon is undefined": (
        "la camera guarda dritta in alto o in basso: l'orizzonte non è definito"
    ),
    "a homography needs four point pairs": "un'omografia richiede quattro coppie di punti",
    "the rectangle corners are degenerate (three corners are collinear)": (
        "gli angoli del rettangolo sono degeneri (tre angoli allineati)"
    ),
    "the rectangle size must be positive": "le dimensioni del rettangolo devono essere positive",
    "the rectangle needs four corners": "il rettangolo richiede quattro angoli",
    "the rectangle corners must form a convex shape, in order": (
        "gli angoli del rettangolo devono formare una figura convessa, in ordine"
    ),
    "the focal length cannot be estimated from this rectangle": "la focale non si può stimare da questo rettangolo",
    "the rectangle is almost facing the camera: the focal length estimate is unstable": (
        "il rettangolo è quasi di fronte alla camera: la stima della focale è instabile"
    ),
    "the scale cube's base corner is beyond the horizon of the reference plane: move it closer": (
        "l'angolo di base del cubo di scala è oltre l'orizzonte del piano di riferimento: avvicinalo"
    ),
    "the scale cube size must be positive": "la dimensione del cubo di scala deve essere positiva",
    "the scale cube's vertical edge points at the camera": (
        "lo spigolo verticale del cubo di scala punta verso la camera"
    ),
    "the scale cube has no height: drag its top handle away from the base": (
        "il cubo di scala non ha altezza: allontana dalla base la maniglia in cima"
    ),
}

# Generic words, translated only where FTC asks with its own context ("FTC"):
# registered in the default context they would change the rest of Blender too.
CONTEXT = "FTC"
_IT_FTC = {
    "Results": "Risultati",
    "Yaw": "Imbardata",
    "Display": "Visualizzazione",
    # Fit Sun
    "Date": "Data",
    "Time": "Ora",
    "Year": "Anno",
    "Month": "Mese",
    "Day": "Giorno",
    "Hour": "Ora",
    "Minute": "Minuto",
    "Second": "Secondo",
    "UTC Offset": "Fuso UTC",
    "Latitude": "Latitudine",
    "Longitude": "Longitudine",
    "Light": "Luce",
    "North": "Nord",
    "Compass": "Bussola",
    "Declination": "Declinazione",
    "North Correction": "Correzione del nord",
    "Elevation Correction": "Correzione dell'elevazione",
    "Sun": "Sole",
    "Side": "Lato",
    "Sun From Axis": "Sole dall'asse",
    "Turn": "Ruota",
    "Raise": "Alza",
    "Check with a Shadow": "Verifica con un'ombra",
    "Sun From": "Sole da",
    "Date and Place": "Data e luogo",
    "Shadow": "Ombra",
    "Shadow On": "Ombra su",
    "Ground": "Suolo",
    "Wall XZ": "Parete XZ",
    "Wall YZ": "Parete YZ",
    "Follow the Sun": "Segui il sole",
    "Lines": "Linee",
    # Mode and yaw: "Horizon", "Manual"... alone are generic words.
    "Mode": "Modalità",
    "Vanishing Points": "Punti di fuga",
    "Known Rectangle": "Rettangolo noto",
    "Horizon": "Orizzonte",
    "From EXIF": "Da EXIF",
    "Manual": "Manuale",
    "Model": "Modello",
    # Development builds' north sources (kept for the enum index, never offered)
    "Map": "Mappa",
    "Landmark": "Punto di riferimento",
}

translations_dict = {"it_IT": {("*", en): it for en, it in _IT.items()}}
translations_dict["it_IT"].update({(CONTEXT, en): it for en, it in _IT_FTC.items()})
translations_dict["it_IT"].update({("Operator", en): it for en, it in _IT.items()})


def _template(key: str):
    """Regular expression matching ``key`` with any text in its ``{}`` fields."""
    parts = [re.escape(p) for p in key.split("{}")]
    return re.compile("^" + "(.+?)".join(parts) + "$", re.DOTALL)


# Messages with numbers or names in them (solver warnings, reports...), held in
# English in the results and the report: matched here and translated on screen.
_TEMPLATES = [(_template(key), key) for key in _IT if "{}" in key and "{:" not in key]


def message(text: str, translate=pgettext_iface) -> str:
    """``text`` translated for display, also when it was filled from a template.
    Fields that are phrases (an error inside a report) are translated too; single
    words are names (an object's) and stay."""
    if not text:
        return text
    out = translate(text)
    if out != text:
        return out
    for regex, key in _TEMPLATES:
        match = regex.match(text)
        if match is not None:
            done = translate(key)
            if done != key:
                fields = (message(g, translate) if " " in g else g for g in match.groups())
                return done.format(*fields)
    return text


def register():
    bpy.app.translations.register(__package__, translations_dict)


def unregister():
    bpy.app.translations.unregister(__package__)
