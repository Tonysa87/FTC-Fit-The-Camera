# Changelog

From 1.1 the changelog is in English. The full history in Italian, with every
release since 0.1, is in [`CHANGELOG.it.md`](CHANGELOG.it.md).

## 1.1.1 – unreleased

*A bug sweep after 1.1.0, and the whole interface in Italian.*

### Fixes

- **Make Upright Copy** of a 16-bit or float photo no longer comes back darker
  after saving and reopening the file. When the photo's file is missing it
  gives a message instead of an error.
- **Results**: *Camera Height* and *Distance* follow the scene's Unit Scale (a
  centimetre scene showed "160 m" for 1.6 m).
- **Known Rectangle on a wall**: corners placed from the top edge (or F pressed
  twice) no longer turn the camera upside down.
- **35 mm equivalent without a sensor size**: the focal length shown in Results
  and in the report is the one entered (27.04 mm was shown for 26 mm on a 4:3
  photo). The Blender camera was already right.
- **Two guide lines on one straight line** are reported instead of giving an
  arbitrary vanishing point.
- **Align to Scene**: switching *Use Stored Target* on or off moves the camera at
  once, like Rotate 90° and Flip. A plane change also updates the "FTC"
  orientation.
- **Fit Sun**:
  - *Read from Photo* keeps a place or time zone typed by hand when the photo
    has none.
  - The date-and-place sun follows an alignment that tilts the vertical (a
    sloped face), as the measured shadow already did.
  - Export Report no longer writes the place of the shot once the Fit Sun light
    has been deleted or the fitted HDRI is no longer the World's.
  - EXIF dates at the ends of the calendar no longer stop Load Image.
- **Fit HDRI**:
  - A Mapping with a Location now gets the "matched about Z only" warning.
  - A Texture Coordinate output other than *Generated* (e.g. *Object*, an HDRI
    turned by an Empty) is refused instead of giving a wrong sun.
  - A muted link into the HDRI is no longer switched back on.
  - A node group with a fake user is no longer called "used elsewhere".
  - An HDRI whose file vanished gives a message instead of an error.
- **Calibration session**:
  - Ctrl+Z also undoes the settings changed in the panel during the session.
  - Switching workspace no longer ends the session (it waits for its view), and
    it follows the view maximized with Ctrl+Space (header text written again
    in both cases).
  - I no longer inserts a keyframe on the camera.
- The tooltip of *Vanishing Point 1* describes the axis sign correctly (along
  the first guide, from its first handle to its second).

### Italian

Every tooltip, label, report and solver message is now translated, also those
with numbers in them (e.g. *calibrazione instabile (focale ±12%…)*). A test
checks that nothing is left in English.

## 1.1.0 – 2026-10-14

*FTC now gets the real sun: the light, the shadows and the HDRI match the photo.*

### Highlights

- **Fit Sun**: a Sun light turned like the sun of the photo, from the EXIF date,
  time and GPS or from a shadow in the photo, with no map or compass needed.
- **Fine-tuning on a real shadow**: a white × shows where the computed sun puts
  the tip of a shadow of the photo; *Turn* and *Raise* bring it onto the real
  tip, and the panel gives the exact values.
- **Calibrate Shadow**: a session for the shadow handles alone, without the
  calibration guides and without touching the camera.
- **Fit HDRI**: the World HDRI turned about Z onto the same sun, with a viewer
  to pick its sun and a Shift magnifier; it also works through the node groups
  that HDRI add-ons build (Poly Haven's *Rotation* input included).
- **Up to six guide lines per vanishing point** and an **Export Report**
  (Markdown / JSON) of the calibration.

### Fit Sun

New section after *Render*. It only sets the **rotation** of a Sun light:
strength, colour and angle stay yours. *New Sun* (the sun icon next to *Light*)
adds one; the light follows the camera on *Apply* and while calibrating. A
deleted or linked light, or keyframes, drivers and constraints that override its
rotation, are reported.

**Sun From** picks the source:

- **Date and Place**: the sun of the shooting time and place. The calibration
  already knows the vertical, so the height of the sun (the length of the
  shadows) is right whatever the north.
- **Shadow**: the sun measured on a shadow in the photo, with no date, place or
  north: any photo with a sharp shadow, also without EXIF.

**Date, time and place**

- Read from the EXIF (✓ next to every value read), or entered by hand; *Read
  from Photo* reads them again.
- Phones write the time of their last GPS fix: when the camera clock agrees with
  the GPS time (UTC), the clock gives the instant and the GPS only the time zone.
  A complete camera clock (time and offset) wins over a GPS time that disagrees;
  a warning says which one is used.
- The time zone is never guessed from the longitude (daylight saving time would
  break it). The nearest town is close enough for the place (100 km ≈ 1° on the
  sun).
- The sun uses NOAA's equations with atmospheric refraction, within 0.013° of
  NREL's SPA. A sun below the horizon (a night shot, a wrong time) is an error
  and the light is left alone.

**North: where the sun stands around the scene**

| North | How |
| --- | --- |
| Compass | automatic, from the EXIF image direction (magnetic: enter the *Declination*); *North Correction* turns it, since phone compasses are often 5–15° off |
| Side | the scene axis the sun comes from (**+X −X +Y −Y**: the shadows of the photo fall the other way), then *Turn* by eye; the default without a compass (−Y, usually behind the camera) |
| Shadow | from a shadow in the photo: the most precise |

Most Android phones write no compass, so no map, landmark or bearing measuring is
needed: an early design with map bearings and a landmark handle was dropped after
the first GUI test as too complex. A camera looking steeply up or down makes the
compass unreliable (warning).

**Fine-tuning on a shadow of the photo**

- **Raise** lifts or lowers the date's sun by eye when the CG shadows come out
  shorter or longer than the real ones. It makes up for small calibration or
  clock errors; the panel shows *Sun Elevation* as "date → used" (16.0° →
  12.5°), and the sun is never taken below 0.5° (alert).
- **Check with a Shadow** (with the compass or a side) shows three orange
  handles: the **foot** and the **top** of something vertical (a pole, a post,
  a sign) and the **tip of its shadow**, on the ground or on a wall through the
  origin (*Shadow On*).
- **Calibrate Shadow** places them in a session of their own: only those three
  handles, no guides, no cube, the camera never written; Shift magnifier, Ctrl
  snap and Ctrl+Z work as in *Calibrate*. Clicking *Calibrate* meanwhile
  switches to the full calibration, and back. The handles are also in
  *Calibrate*.
- The white **× "Fit Sun"** marks where the computed sun (date, place, *Turn* /
  *North Correction*, *Raise*) puts the shadow's tip. On the tip handle, the sun
  is right: *Turn* moves it sideways, *Raise* along the shadow. Hints in the
  panel and in the session header say so.
- The panel also gives the numbers: *Shadow vs Turn* / *Shadow vs Compass* is the
  turn to add, *Shadow vs Date* the Raise that matches (red until Raise reaches
  it). *Shadow Elevation* comes with a ± from the handles: a long shadow
  measures better than a short one.
- With *North* = *Shadow* the north comes from the shadow and only *Raise*
  remains; with *Sun From* = *Shadow* the shadow gives everything.
- *Display › North* (off by default) draws the north and the sun direction on
  the ground while calibrating.

### Fit HDRI

With an equirectangular HDRI in the World (an *Environment Texture*), **Fit
HDRI** turns it about Z so that its sun comes from the same side as the photo's:
ambient light, reflections and the Sun light then agree.

- **Viewer**: half the 3D view, over a 2048 px copy of the HDRI. FTC proposes the
  brightest spot (thin white ring, found on the luminance with the sun's disc
  averaged across the seam); click the sun if it is wrong (bright clouds,
  reflections, a hidden sun). The orange ring is your pick with its elevation;
  **Enter** applies, **Esc** cancels.
- **Shift magnifier**: ×4 on the mouse, as for the calibration handles, with
  the horizon and the marks magnified and a cross hair in inverted colours
  that shows on the white sun too.
- The white **× "Fit Sun"** is where the photo's sun lands, in the column of the
  orange ring: their vertical gap is the elevation difference. The elevation is
  never changed, only compared (warning beyond 10°): an HDRI whose sun lies near
  the × gives shadows of the right length.
- **Only the Z rotation changes**: an existing Mapping is reused (its X, Y and
  location stay), also behind reroutes; otherwise *Texture Coordinate ›
  Mapping* is inserted. Environment Textures showing the same image (one for the
  light, one for the camera) turn together. Texture-type Mappings get the
  inverse turn.
- **Follow the Sun**: the HDRI keeps turning with the sun (a new side or north,
  *Turn*, the time, a new calibration) with no new click; turning it by hand
  switches the following off, ticking it takes over again.
- **Node groups**: an HDRI inside a node group (as HDRI add-ons build the World)
  is found and turned inside the group.
- **A rotation fed by other nodes is followed back** to the value that sets it,
  and that value is written: a group's *Rotation* input (Poly Haven's World:
  degrees → Multiply → Combine XYZ → Mapping), Value nodes, reroutes, Combine
  XYZ, Math and Vector Math add / subtract / multiply / divide / scale and
  radians / degrees, groups in the middle and nested groups. The input's min /
  max are respected (the turn of the angle that fits is chosen).
- Every value is checked **before anything is written**: a refusal leaves the
  World as it was. Refused with a message: nodes that cannot be followed back (a
  sine, a texture, a muted node), keyframes or drivers on the way, a muted
  Mapping, a vector from other nodes, a World or group linked from a library,
  non-equirectangular projections. A group used twice in the World warns that
  only one instance turns.
- The equirectangular convention, the rotation sign and the group chains are
  checked by Cycles renders in the tests.

### Calibration

- **Up to six guide lines per vanishing point**: the − n + buttons next to each
  axis. A new line starts between the first two and aims at their meeting
  point; the session's undo restores the number of lines. 1.0 files keep two.
- **Export Report** in *Results*: Markdown or JSON with focal length, sensor,
  field of view, camera position and rotation, uncertainty, guide fit and the
  source of every input (EXIF or manual). The sun block (time, place, north,
  Turn, Raise, the light's elevation) is written only when Fit Sun is used, so
  a photo's GPS position does not end up in a report by accident. The
  manifest's file permission says so.

### Interface

- Every new control has a tooltip and an Italian translation; dynamic tooltips
  are translated too (a line break in a tooltip lost its translation), and five
  1.0 property descriptions got their missing Italian.
- *Fit Sun* and *Fit HDRI* keep their English names in the Italian interface.

### Other

- Manifest tags `Camera`, `Render` (the `3D View` tag was dropped, as asked by
  the Blender Extensions moderator).
- New logo (a crosshair in a frame); README credits to fSpy, Perspective
  Plotter and the papers FTC relies on.

### Shaped by the GUI tests

The 1.1 test builds were tried on real photos; these changes came from them:

- Map bearings and a landmark handle for the north → replaced by *Side* + *Turn*.
- CG shadows shorter than the photo's on a sunset shot → *Raise*.
- The shadow handles mixed with the calibration guides → *Calibrate Shadow*.
- An unexplained white cross → the labelled × "Fit Sun" with hints.
- HDRI worlds built by add-ons (Extreme PBR, Poly Haven) → node groups and
  rotation chains.
- A full-screen HDRI viewer → half size with a Shift magnifier and a cross hair
  visible on the sun.

## 1.0.0 – 2026-10-11

First public release, on Blender Extensions and GitHub.

- Calibration from 1, 2 or 3 vanishing points, a known rectangle, or the
  horizon with the camera height; known focal length refined by the guides.
- EXIF reading (focal length, 35 mm equivalent, sensor, GPS, compass) with the
  source of every field shown.
- Real scale from a reference distance or a scale cube; uncertainty and guide
  fit, with warnings for non-parallel lines and wrong EXIF focal lengths.
- Magnifier on the handles, one camera per photo, alignment to the 3D cursor,
  a face or an object, and the FTC transform orientation.
- *Prepare Render*: colour management, transparent film and compositor to render
  over the photo, with shadow catcher and holdout roles.
- English and Italian interface.

Details of 1.0.0 and earlier versions: [`CHANGELOG.it.md`](CHANGELOG.it.md).
