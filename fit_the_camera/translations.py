# SPDX-License-Identifier: GPL-3.0-or-later
"""Italian translation of the interface (Preferences > Interface > Translation).

Only add-on specific phrases are listed: registered translations apply to the
whole interface, and generic words are already translated by Blender itself.
"""

import bpy

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
    "How the north of the scene is found": "Come si trova il nord della scena",
    "From the compass direction of the photo (EXIF), rarely written by Android phones": (
        "Dalla direzione della bussola nella foto (EXIF), che i telefoni Android scrivono di rado"
    ),
    "From the compass bearing of a scene axis, read on a map along a facade or a street": (
        "Dalla direzione di un asse della scena, letta su una mappa lungo una facciata o una strada"
    ),
    "From a distant landmark in the photo (Landmark handle in Calibrate) and its bearing on a map": (
        "Da un riferimento lontano nella foto (maniglia Riferimento in Calibra) e dalla sua direzione sulla mappa"
    ),
    "Scene axis whose bearing is read on the map": "Asse della scena di cui si legge la direzione sulla mappa",
    "Compass bearing of the scene axis, clockwise from true north": (
        "Direzione dell'asse della scena, in senso orario dal nord geografico"
    ),
    "Compass bearing from the camera to the landmark, read on a map, clockwise from true north": (
        "Direzione dalla camera al riferimento, letta su una mappa, in senso orario dal nord geografico"
    ),
    "Magnetic declination at the place, east positive: added to a magnetic compass direction "
    "(look it up for the place and year)": (
        "Declinazione magnetica del luogo, positiva a est: si somma a una direzione di bussola magnetica "
        "(cercala per il luogo e l'anno)"
    ),
    "Turns the scene north, and the sun with it, about the vertical: phone compasses are often "
    "5-15° off; adjust it until the CG shadows match the photo": (
        "Ruota il nord della scena, e il sole con lui, attorno alla verticale: le bussole dei telefoni "
        "sbagliano spesso di 5-15°; regolala finché le ombre del CG coincidono con la foto"
    ),
    "Show the scene north and the sun direction on the reference plane while calibrating": (
        "Mostra il nord della scena e la direzione del sole sul piano di riferimento durante la calibrazione"
    ),
    "No compass direction in the photo: use Map, Landmark or Shadow": (
        "Nessuna bussola nella foto: usa Mappa, Riferimento o Ombra"
    ),
    "Drag the Landmark handle (Calibrate) onto a distant feature": (
        "Trascina la maniglia Riferimento (Calibra) su un elemento lontano"
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
    "Place the Landmark handle on the landmark (Calibrate)": (
        "Metti la maniglia Riferimento sul riferimento (Calibra)"
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
    "The landmark is straight above or below the camera: move it": (
        "Il riferimento è dritto sopra o sotto la camera: spostalo"
    ),
    # Fit Sun: shadow
    "Where the direction of the sun comes from": "Da dove arriva la direzione del sole",
    "Computed from the date, time and place of the shot, with the scene north": (
        "Calcolata da data, ora e luogo dello scatto, con il nord della scena"
    ),
    "Measured on a shadow in the photo: no date, place or north needed": (
        "Misurata su un'ombra nella foto: non servono data, luogo né nord"
    ),
    "Show the shadow handles (foot and top of something vertical, tip of its shadow) to check the sun "
    "of the date and place, and the north": (
        "Mostra le maniglie dell'ombra (piede e cima di qualcosa di verticale, punta della sua ombra) per "
        "verificare il sole di data e luogo, e il nord"
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
    "From a shadow in the photo (shadow handles in Calibrate) and the sun of the date and place": (
        "Da un'ombra nella foto (maniglie dell'ombra in Calibra) e dal sole di data e luogo"
    ),
    "Calibrate: orange handles on the foot and the top of something vertical, and on the tip of its shadow": (
        "Calibra: maniglie arancioni sul piede e sulla cima di qualcosa di verticale, e sulla punta della sua ombra"
    ),
    "Shadow Elevation": "Elevazione dall'ombra",
    "Shadow vs Date": "Ombra / data",
    "{:+.1f}° elevation": "{:+.1f}° di elevazione",
    "Shadow vs North": "Ombra / nord",
    "Use Shadow North": "Usa il nord dell'ombra",
    "Calibrate the camera first: the shadow is measured through it": (
        "Calibra prima la camera: l'ombra si misura attraverso di lei"
    ),
    "Place the shadow handles on the photo (Calibrate)": "Metti le maniglie dell'ombra sulla foto (Calibra)",
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
    "Click the sun in the HDRI · Enter: apply · Esc: cancel · the cross is the photo's sun": (
        "Clicca il sole nell'HDRI · Invio: applica · Esc: annulla · la croce è il sole della foto"
    ),
    "HDRI Rotation": "Rotazione HDRI",
    "Sun Point": "Punto del sole",
    "The World is linked from a library: make it local to fit its HDRI": (
        "Il World è collegato da una libreria: rendilo locale per adattarne l'HDRI"
    ),
    "The Environment Texture is inside a node group: Fit HDRI needs it in the World's own nodes": (
        "L'Environment Texture è dentro un gruppo di nodi: Fit HDRI la vuole tra i nodi del World"
    ),
    "The HDRI's vector comes from other nodes (not a Mapping): Fit HDRI cannot turn it": (
        "Il vettore dell'HDRI arriva da altri nodi (non un Mapping): Fit HDRI non può ruotarlo"
    ),
    "The rotation of the HDRI's Mapping comes from other nodes: Fit HDRI cannot turn it": (
        "La rotazione del Mapping dell'HDRI arriva da altri nodi: Fit HDRI non può ruotarlo"
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
    # FTC orientation
    "FTC Orientation": "Orientamento FTC",
    "No 3D view to create the orientation from": "Nessuna vista 3D da cui creare l'orientamento",
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
    "Map": "Mappa",
    "Landmark": "Riferimento",
    "Axis": "Asse",
    "Bearing": "Direzione",
    "Landmark Bearing": "Direzione del riferimento",
    "Declination": "Declinazione",
    "North Correction": "Correzione del nord",
    "Sun": "Sole",
    "Sun From": "Sole da",
    "Date and Place": "Data e luogo",
    "Shadow": "Ombra",
    "Measure Shadow": "Misura un'ombra",
    "Shadow On": "Ombra su",
    "Ground": "Suolo",
    "Wall XZ": "Parete XZ",
    "Wall YZ": "Parete YZ",
    "Use Shadow North": "Usa il nord dell'ombra",
    "Follow the Sun": "Segui il sole",
    "Lines": "Linee",
}

translations_dict = {"it_IT": {("*", en): it for en, it in _IT.items()}}
translations_dict["it_IT"].update({(CONTEXT, en): it for en, it in _IT_FTC.items()})
translations_dict["it_IT"].update({("Operator", en): it for en, it in _IT.items()})


def register():
    bpy.app.translations.register(__package__, translations_dict)


def unregister():
    bpy.app.translations.unregister(__package__)
