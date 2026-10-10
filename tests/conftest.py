# SPDX-License-Identifier: GPL-3.0-or-later
import sys
from pathlib import Path

import pytest

# The solver package has no bpy dependency: import it on its own, without the
# add-on package whose __init__ needs Blender.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fit_the_camera"))

from synthetic import make_camera  # noqa: E402


@pytest.fixture
def camera():
    return make_camera()
