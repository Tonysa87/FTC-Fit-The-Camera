# FTC – Fit The Camera

**English** · [Italiano](README.it.md)

A Blender 5.2+ extension that matches a camera to a single image (a photo, a
render, a drawing). From a few lines drawn over the image it finds the focal
length, the position and the rotation of the camera, at real-world scale. It can
then set up the scene to render 3D objects over the photo, with their shadows on
the real ground.

- **Vanishing points**: 1, 2 or 3, two guide lines per axis, with the axis and
  direction of each group (X, Y, Z, ±).
- **Known rectangle**: the four corners of a rectangle of known width and height.
- **Horizon**: the horizon line, the camera height and the heading.
- **EXIF**: camera, lens, focal length, 35 mm equivalent, sensor size, GPS and
  compass direction are read from the image. The known focal length can be refined
  by the guides, or the guides can solve it on their own.
- **Real scale** from a *scale cube* of known size placed in the image (or a
  reference distance).
- **Uncertainty and guide fit**: how far the result can be trusted, with warnings
  for lines that are not really parallel, a wrong EXIF focal length, a vanishing
  point too far away.
- **Align to the scene**: put the calibrated floor or wall on the 3D cursor, a
  face or an object.
- **Render over the photo**: one button sets colour management, transparent film
  and the compositor; object roles (CG object, shadow catcher, holdout, hidden);
  a shadow catcher plane on the calibrated ground.
- Interface in English and Italian.

## Install

1. Download `fit_the_camera-<version>.zip` from the
   [Releases](https://github.com/Tonysa87/FTC---Fit-The-Camera/releases).
2. In Blender 5.2 or later: *Edit › Preferences › Get Extensions › ⌄ ›
   Install from Disk…* and pick the zip.

The extension only reads the image file you load (and its EXIF metadata). It
does not use the network.

## Quick start

Open the sidebar of the 3D viewport (N) and the **FTC** tab.

1. **Load Image** – uses the active camera (or creates one), sets the image as
   its background, matches the render resolution, reads the EXIF data and looks
   through the camera. Photos stored rotated (EXIF orientation) get an upright
   copy with **Make Upright Copy**.
2. **Camera Data** – check or enter the focal length and the sensor width (or the
   35 mm equivalent). Every field shows whether it comes from EXIF, is missing
   (red) or was typed in.
3. **Calibration** – pick a mode and press **Calibrate**: drag the handles of the
   guides onto edges of the image that are parallel in the real world.
   Shift = fine, Ctrl = snap, 1/2/3 = axis, F = flip the direction, H =
   straighten the horizon, Ctrl+Z / Ctrl+Shift+Z = undo / redo, Enter = apply,
   Esc / right click = exit.
4. **Align to Scene** – place the calibrated plane (XY, XZ or YZ) on the 3D
   cursor, on the active face (Edit Mode) or on the active object.
5. **Results** – focal length, field of view, camera height, angles, uncertainty
   and guide fit, with warnings.
6. **Render** – see below.
7. **Tools › Move Along View** – move objects or vertices along the camera rays:
   they keep their place in the image.

| Mode | Input | Notes |
| --- | --- | --- |
| 1 vanishing point | 2 guides for axis 1 + a line along axis 2 | needs the focal length |
| 2 vanishing points | 2 guides per axis | optional *Third Axis Line* |
| 3 vanishing points | 2 guides per axis | principal point at the centre, by hand or solved |
| Known rectangle | 4 corners, real width and height | on XY, XZ or YZ |
| Horizon | horizon line, camera height, heading | needs the focal length |

### Scale cube

A wireframe cube of known size (10 cm to 10 m, or custom) standing on the
reference plane. Put the base handle at the foot of something of known height and
drag the top handle up to its top: the scale of the scene follows. The cube and
the *Reference Distance* exclude each other: only the one chosen in the *Scale*
menu is shown. With a known rectangle or the horizon the scale is already known
and the cube is an optional visual check (*Opacity* panel).

### Render over the photo

**Prepare Render** (choose *Over the Photo* or *Transparent*, and *Use Cycles*):

- **Colour management**: sRGB display, **Standard** view transform, no look,
  exposure 0, gamma 1, no curves or white balance. The photo is an sRGB image and
  goes through the same view transform as the 3D objects: only Standard gives it
  back unchanged (measured: under 1/255). AgX, Filmic, ACES and Khronos PBR
  Neutral tone map it (about 9 levels out of 255 on average, over 120 on
  saturated colours). Light the objects with lights, not with the exposure.
- **Transparent film**: the world lights the scene but is not rendered. The
  render resolution goes back to the image size.
- **Compositor** (*Over the Photo*): a node group `FTC Compositing` scales the
  photo to the render size, multiplies it by the Cycles **Shadow Catcher** pass
  (shadows and light bounced by the objects onto the real surfaces) and puts the
  render over it with Alpha Over. A compositor of your own is kept in the file
  and replaced.
- **Transparent**: no compositor, the shadows stay in the alpha channel, PNG RGBA
  output: for compositing in another program.

**Object Roles** lists the objects of the scene with their role:

| Role | What it does | For |
| --- | --- | --- |
| CG Object | rendered normally | the objects added to the photo |
| Shadow Catcher | shows the photo, receives shadows and light, hides what is behind it (Cycles) | real floors, tables, walls |
| Holdout | shows the photo and hides the objects behind it, no shadows | real objects in front of the CG |
| Hidden | not rendered | reference geometry |

**Shadow Catcher Plane** adds a shadow catcher on the calibrated reference plane
(drawn as wireframe so it does not cover the photo).

## Tips

- The **+** direction of an axis runs along the **first** guide of its group,
  from its first to its second handle (arrow on the guide). F or the ⇄ button
  flips it. The third axis follows from the first two (the world is always
  right-handed).
- Two vanishing points **on the floor only** leave the vertical loosely measured:
  add the *Third Axis Line* (a door jamb, a corner) or use 3 vanishing points.
  A known focal length brings the error under 1°.
- A vanishing point very far away (a wall seen nearly front-on) leaves the focal
  length undetermined: use the known focal length or lines in another direction.
- Lines that *look* parallel are not always parallel (light rails, separate
  buildings, tiles). With 3 groups or a known focal length the *Guide Fit* shows
  it.
- The EXIF focal length can be wrong (zoomed or cropped photos). If the guides
  cannot agree with it and fit much better on their own, they overrule it and a
  warning says by how much.

## Documentation

- [Changelog](docs/CHANGELOG.md)
- [Italian user guide](README.it.md)
- [Development](docs/DEVELOPMENT.md) (Italian): structure, conventions, tests,
  build

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). © 2026 Antonio Sartini.
