# Changelog

From 1.1 the changelog is in English. The full history in Italian, with every
release since 0.1, is in [`CHANGELOG.it.md`](CHANGELOG.it.md).

## Unreleased (1.1)

*FTC now gets the real sun: the light and the HDRI match the photo.*

### Fit Sun

- New **Fit Sun** section after *Render*. A Sun light is turned like the sun of
  the photo; its strength, colour and angle stay yours (*New Sun* adds one).
- **Sun from the date and place**: the shooting time and place are read from
  the EXIF, or entered by hand. The GPS time is UTC; when the camera clock agrees
  with it, the clock gives the instant and the GPS only the time zone, since
  phones write the time of the last fix. A complete camera clock (time and
  offset) wins over a GPS time that disagrees. The time zone is never guessed
  from the longitude. The sun uses NOAA's equations, within 0.013° of NREL's SPA.
- **Where the sun stands around the scene**: from the EXIF **compass**
  (automatic; magnetic declination by hand), from the **side** it comes from
  (pick the scene axis +X −X +Y −Y, then *Turn* it by eye; the default without a
  compass), or from a **shadow**. Most Android phones write no compass: no map
  or measuring is needed (an early map/landmark design was dropped after the
  first GUI test as too complex). **Calibrate Shadow** places only the shadow
  handles (no guides, the camera untouched). The white × labelled *Fit Sun*
  is the computed sun everywhere (shadow tip in the camera view, sun in the
  HDRI viewer); *Check with a Shadow* also works with *Side* (*Shadow vs
  Turn*). **Raise** lifts or lowers the date's sun by
  eye when the CG shadows come out shorter or longer than in the photo.
- **Sun from a shadow**: three handles on the foot and top of something vertical
  and on the tip of its shadow, on the ground or on a wall through the origin.
  They give the sun with no EXIF, date or north, with a ± from the handles.
  Next to the date and place it gives the north (*North* = *Shadow*) and checks
  the date (*Shadow vs Date*); with the compass, *Check with a Shadow* shows
  *Shadow vs Compass*. A cross marks where the date's sun would put the tip.
- *Display › North* (off by default) draws the north and the sun direction on
  the ground while calibrating.

### Fit HDRI

- Turns the World's equirectangular HDRI about Z so that its sun has the
  azimuth of the photo's sun. A viewer over the 3D view shows a reduced copy of
  the HDRI with the brightest spot proposed; click the sun, Enter applies.
- Only the Z rotation of a Mapping node changes (an existing one is reused, also
  behind reroutes, and inside node groups as HDRI add-ons build them). The
  sun's elevation is compared, never changed: over 10°
  apart, a warning. *Follow the Sun* keeps the HDRI on the sun when it moves.
- The viewer takes half the view and has a **Shift** magnifier (×4 on the
  mouse, as for the calibration handles, with an inverted cross hair that
  shows on the white sun), on a 2048 px copy of the HDRI.
- A rotation fed by other nodes is followed back to its value and written
  there: a group's *Rotation* input (Poly Haven's World: degrees → Multiply →
  Combine XYZ), Value nodes, linear Math / Vector Math, nested groups; the
  input's min / max are respected.
- The equirectangular convention and the rotation sign are checked by Cycles
  renders in the tests.

### Calibration

- **Up to six guide lines per vanishing point**: the − n + buttons next to each
  axis. A new line starts between the first two and aims at their meeting point.
  1.0 files keep two lines.
- **Export Report** in *Results*: Markdown or JSON with focal length, sensor,
  field of view, camera position and rotation, uncertainty, guide fit, the
  source of every input (EXIF or manual) and the sun. The manifest's file
  permission now says so.
- Tooltips: one-line descriptions, and the dynamic ones are translated (a line
  break in a tooltip lost its Italian translation).

### Other

- Manifest tags `Camera`, `Render` (the `3D View` tag was dropped, as asked by
  the Blender Extensions moderator).
- New logo (a crosshair in a frame); README credits to fSpy, Perspective
  Plotter and the papers FTC relies on.

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
