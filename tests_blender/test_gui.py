# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end test of the modal calibration with simulated input.

Needs a display. Run by scripts/blender_gui_tests.sh:
blender --enable-event-simulate --python tests_blender/test_gui.py -- <project root> <scratch dir>
"""

import importlib
import os
import struct
import sys
import traceback
import zlib

import bpy
import numpy as np

ROOT, SCRATCH = sys.argv[-2:]
PKG = "bl_ext.user_default.fit_the_camera"
calibrate = importlib.import_module(PKG + ".calibrate")
ops_modal = importlib.import_module(PKG + ".ops_modal")

results = []


def check(cond, message):
    results.append((bool(cond), message))
    print(("PASS  " if cond else "FAIL  ") + message)


def save_png(path, pixels):
    """Minimal PNG writer for an RGBA uint8 array stored bottom-up."""
    rows = np.ascontiguousarray(pixels[::-1, :, :4])
    h, w = rows.shape[:2]
    raw = b"".join(b"\0" + rows[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        f.write(chunk(b"IEND", b""))


def view3d():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region


def steps():
    win, area, region = view3d()
    path = os.path.join(SCRATCH, "gui.jpg")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.ftc.load_image(filepath=path)
    yield 0.5
    cam = bpy.context.scene.camera
    settings = cam.data.ftc
    check(settings.image is not None, "image loaded")
    check(area.spaces.active.region_3d.view_perspective == "CAMERA", "viewport switched to camera view")

    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.ftc.calibrate("INVOKE_DEFAULT")
    yield 0.5
    session = ops_modal.FTC_OT_calibrate._session
    check(session is not None, "calibration session running")
    check(session.view is not None, "overlay drawn and camera frame known")
    if session is None or session.view is None:
        return

    def to_window(key):
        x, y = session.view.to_region(calibrate.handle(settings, key))
        return int(region.x + x), int(region.y + y)

    # Drag the first vertex of vanishing point 1 by 40 px right, 30 px up.
    before = calibrate.handle(settings, "vp1_1a")
    lens_before = cam.data.lens
    x, y = to_window("vp1_1a")
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    yield 0.2
    check(session.hover == "vp1_1a", "hovering a handle highlights it")
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    for i in range(1, 5):
        win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x + 10 * i, y=y + 8 * i)
        yield 0.05
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x + 40, y=y + 32)
    yield 0.3
    after = calibrate.handle(settings, "vp1_1a")
    moved_px = (np.subtract(session.view.to_region(after), session.view.to_region(before))).tolist()
    check(abs(moved_px[0] - 40) < 1.5 and abs(moved_px[1] - 32) < 1.5, f"handle followed the mouse {moved_px}")
    check(cam.data.lens != lens_before, "live update wrote the camera")
    check(len(session.undo) == 1, "drag pushed one undo step")

    # Shift drag moves five times less.
    x, y = to_window("vp2_1a")
    start = session.view.to_region(calibrate.handle(settings, "vp2_1a"))
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x + 50, y=y, shift=True)
    yield 0.1
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x + 50, y=y, shift=True)
    yield 0.2
    end = session.view.to_region(calibrate.handle(settings, "vp2_1a"))
    check(abs((end[0] - start[0]) - 10) < 1.5, f"shift drag is fine-grained ({end[0] - start[0]:.1f} px)")

    # Keyboard events carry the mouse position: keep it inside the viewport.
    kx, ky = int(region.x + region.width / 2), int(region.y + region.height / 2)

    # Undo / redo.
    win.event_simulate(type="Z", value="PRESS", ctrl=True, x=kx, y=ky)
    yield 0.2
    check(abs(session.view.to_region(calibrate.handle(settings, "vp2_1a"))[0] - start[0]) < 0.5, "Ctrl+Z undoes")
    win.event_simulate(type="Z", value="PRESS", ctrl=True, shift=True, x=kx, y=ky)
    yield 0.2
    check(abs(session.view.to_region(calibrate.handle(settings, "vp2_1a"))[0] - end[0]) < 0.5, "Ctrl+Shift+Z redoes")

    # Axis keys: active vanishing point is 2 (last dragged); F flips it.
    win.event_simulate(type="F", value="PRESS", x=kx, y=ky)
    yield 0.2
    check(settings.vp2_axis == "-Y", f"F flips the active axis ({settings.vp2_axis})")
    win.event_simulate(type="F", value="PRESS", x=kx, y=ky)
    win.event_simulate(type="THREE", value="PRESS", x=kx, y=ky)
    yield 0.2
    check(settings.vp2_axis == "+Z", f"3 sets the active axis to Z ({settings.vp2_axis})")
    win.event_simulate(type="TWO", value="PRESS", x=kx, y=ky)
    yield 0.2
    check(settings.vp2_axis == "+Y", "2 sets it back to Y")

    win.event_simulate(type="H", value="PRESS", x=kx, y=ky)
    yield 0.2
    check(settings.straighten and abs(settings.results.roll) < 1e-6, "H straightens the horizon")

    # Pitch handle drag tilts the camera.
    pitch_before = settings.results.pitch
    from_px = importlib.import_module(PKG + ".draw").pitch_handle_px(calibrate.cached_solution(cam.data))
    hx, hy = session.view.px_to_region(from_px)
    hx, hy = int(region.x + hx), int(region.y + hy)
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=hx, y=hy)
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=hx, y=hy)
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=hx, y=hy + 40)
    yield 0.1
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=hx, y=hy + 40)
    yield 0.3
    check(settings.results.pitch < pitch_before - 1e-4, "dragging the horizon up tilts the camera down")

    # Ctrl snaps a handle onto another one (here the origin).
    x, y = to_window("vp1_1a")
    ox, oy = to_window("origin")
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=ox + 5, y=oy + 4, ctrl=True)
    yield 0.1
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=ox + 5, y=oy + 4, ctrl=True)
    yield 0.2
    snapped = np.subtract(calibrate.handle(settings, "vp1_1a"), calibrate.handle(settings, "origin"))
    check(np.abs(snapped).max() < 1e-6, "Ctrl snaps onto the origin")
    win.event_simulate(type="Z", value="PRESS", ctrl=True, x=kx, y=ky)
    yield 0.2

    # Frozen guides do not move.
    settings.freeze = True
    frozen_at = calibrate.handle(settings, "vp2_2a")
    x, y = to_window("vp2_2a")
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x + 30, y=y + 30)
    yield 0.1
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x + 30, y=y + 30)
    yield 0.2
    check(calibrate.handle(settings, "vp2_2a") == frozen_at, "frozen guides stay put")
    settings.freeze = False

    # Three vanishing points: axis keys on the third group permute the first two.
    settings.vp_count = "3"
    session.active_vp = 2
    win.event_simulate(type="ONE", value="PRESS", x=kx, y=ky)
    yield 0.2
    check(
        "X" not in (settings.vp1_axis[1], settings.vp2_axis[1]),
        f"third axis set to X ({settings.vp1_axis}, {settings.vp2_axis})",
    )
    settings.vp_count = "2"
    yield 0.2

    # Screenshot for visual inspection.
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=to_window("origin")[0], y=to_window("origin")[1])
    yield 0.5
    rect = ((area.x, area.y), (area.x + area.width, area.y + area.height))
    save_png(os.path.join(SCRATCH, "gui_calibrate.png"), np.asarray(win.screenshot(region=rect)))

    win.event_simulate(type="RET", value="PRESS", x=kx, y=ky)
    yield 0.3
    check(ops_modal.FTC_OT_calibrate._session is None, "Enter ends the session")
    orientation = importlib.import_module(PKG + ".ops_orientation")
    check(orientation.find(bpy.context.scene) is not None, "Enter (apply) created the FTC orientation")

    # Loading another file ends a running session cleanly.
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.ftc.calibrate("INVOKE_DEFAULT")
    yield 0.3
    check(ops_modal.FTC_OT_calibrate._session is not None, "session restarted")
    bpy.ops.wm.read_homefile()
    yield 0.5
    check(ops_modal.FTC_OT_calibrate._session is None, "loading a file ends the session")


def run():
    gen = steps()

    def tick():
        try:
            return next(gen)
        except StopIteration:
            pass
        except Exception:
            traceback.print_exc()
            results.append((False, "exception"))
        failed = [m for ok, m in results if not ok]
        print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
        with open(os.path.join(SCRATCH, "gui_result.txt"), "w") as f:
            f.write("FAILED\n" if failed or not results else "OK\n")
        bpy.ops.wm.quit_blender()
        return None

    bpy.app.timers.register(tick, first_interval=1.0)


run()
