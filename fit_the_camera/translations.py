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
    "LMB drag: move  Shift: fine  Ctrl: snap  1/2/3: axis  F: flip  H: straighten  "
    "Ctrl+Z / Ctrl+Shift+Z: undo/redo  Enter: apply  Esc/RMB: exit": (
        "LMB trascina: sposta  Shift: fine  Ctrl: snap  1/2/3: asse  F: inverti  H: raddrizza  "
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
    "Results": "Risultati",
    "Yaw": "Imbardata",
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
    "Shadow catchers work only in Cycles": "Gli shadow catcher funzionano solo in Cycles",
    "Object Roles": "Ruoli oggetti",
    "Render Role": "Ruolo nel render",
    "CG Object": "Oggetto CG",
    "Set Role of Selected": "Ruolo dei selezionati",
    "Shadow Catcher Plane": "Piano shadow catcher",
    "Render size has another aspect than the image: Apply or Calibrate fixes it": (
        "Il render ha proporzioni diverse dall'immagine: Applica o Calibra le correggono"
    ),
    "The camera has location/rotation keyframes: they override the calibration": (
        "La camera ha keyframe di posizione/rotazione: sovrascrivono la calibrazione"
    ),
    "Only the active view layer is composited over the photo": (
        "Solo il view layer attivo viene composto sulla foto"
    ),
    # Move Along View
    "Move Along View": "Sposta lungo la vista",
    "Distance Factor": "Fattore distanza",
    "Scale with Distance": "Scala con la distanza",
}

translations_dict = {"it_IT": {("*", en): it for en, it in _IT.items()}}
translations_dict["it_IT"].update({("Operator", en): it for en, it in _IT.items()})


def register():
    bpy.app.translations.register(__package__, translations_dict)


def unregister():
    bpy.app.translations.unregister(__package__)
