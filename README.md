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
  and the compositor; shadow catcher and holdout roles for the objects that
  stand in for real surfaces and objects of the photo.
- Interface in English and Italian.

## Install

1. Download `fit_the_camera-<version>.zip` from the
   [Releases](https://github.com/Tonysa87/FTC-Fit-The-Camera/releases).
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
   Esc / right click = exit. With *Live Update* (default) the camera follows the
   guides while you drag; Enter or **Apply** writes it and ends the session.
   Outside a session, changes made in the panel move the camera only on
   **Apply**. In the camera view the photo moves with the camera: to see the
   result, look at the scene objects or at the camera's location.
4. **Align to Scene** – place the calibrated plane (XY, XZ or YZ) on the 3D
   cursor, on the active face (Edit Mode) or on the active object.
5. **Results** – focal length, field of view, camera height, angles, uncertainty
   and guide fit, with warnings.
6. **Render** – see below.
7. **Tools › FTC Orientation** – makes the "FTC" transform orientation the viewport's:
     the photo's calibrated axes in the scene (created on Apply and by Align to
     Scene). Blender's gizmo, G/R/S with X/Y/Z and snapping then follow the photo
     also after aligning it to a face or the cursor. Click again for Global.

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
and the cube is an optional visual check (*Opacity* panel). Dragging the base
or the origin never flips the cube: it extends the way the camera looks (on a
wall: upwards).

### Reference distance

Two handles at the ends of a known length (a door width, a tile, a table), on
the plane chosen in *Measured On* (through the origin; XY = the floor by default,
independent of the plane used to align the scene). Along an axis of that plane
both ends lie on it, anywhere (not necessarily on the axis through the origin).
Along its normal the length is a height: the first handle at the foot on the
plane, the second at the top.

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
- **Transparent**: no compositor, the shadows stay in the alpha channel (Cycles);
  the output format is kept if it stores alpha (PNG, EXR, TIFF…), otherwise it
  becomes PNG RGBA: for compositing in another program.
- Only the active view layer is composited over the photo. With a custom colour
  configuration (OCIO) without an sRGB display / Standard view, set an identity
  view by hand (a warning says so).

**Object Roles** lists the renderable objects of the scene with two toggles,
*Shadow Catcher* and *Holdout*, which exclude each other. They only change the
objects' own settings: nothing is created. Objects without a role are the CG,
rendered normally.

| Role | What it does | For |
| --- | --- | --- |
| Shadow Catcher | shows the photo, receives shadows and light, hides what is behind it (Cycles) | real floors, tables, walls you modelled |
| Holdout | shows the photo and hides the objects behind it, no shadows | real objects in front of the CG |

A click on a row selects the object; *Set Role of Selected* gives *Shadow
Catcher*, *Holdout* or *No Role* to all the selected objects.

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
