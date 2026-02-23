#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""SwitchGroup edit mode - activates Switch mode for RVSwitchGroup nodes."""

from rv import rvtypes
from rv import commands


class SwitchGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVSwitchGroup nodes."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self.init(
            "SwitchGroup_edit_mode",
            None,
            None,
            None,
            None
        )

    def activateUI(self, on):
        """Activate or deactivate related edit modes."""
        state = commands.data()
        if not hasattr(state, 'modeManager') or state.modeManager is None:
            return
        mm = state.modeManager

        for mode in ["Switch_edit_mode"]:
            entry = mm.findModeEntry(mode)
            if entry:
                mm.activateEntry(entry, on)

    def activate(self):
        rvtypes.MinorMode.activate(self)
        self.activateUI(True)

    def deactivate(self):
        self.activateUI(False)
        rvtypes.MinorMode.deactivate(self)


def createMode():
    return SwitchGroupEditMode()
