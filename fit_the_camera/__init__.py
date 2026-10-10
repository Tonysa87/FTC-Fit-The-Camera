# SPDX-License-Identifier: GPL-3.0-or-later
"""FTC – Fit The Camera: calibrate a Blender camera from a single image."""

from . import calibrate, ops_load, ops_modal, ops_move_view, props, translations, ui

if "bpy" in locals():
    # Support "Reload Scripts" during development.
    import importlib

    for module in (calibrate, props, ops_load, ops_modal, ops_move_view, ui, translations):
        importlib.reload(module)

import bpy  # noqa: E402,F401

modules = (translations, props, ops_load, ops_modal, ops_move_view, ui)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
