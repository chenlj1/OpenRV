#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""StackGroup edit mode - activates Stack and Composite modes for RVStackGroup nodes."""

from rv import rvtypes
from rv import commands
from rv import rvui


class StackGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVStackGroup nodes."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self.init(
            "StackGroup_edit_mode",
            None,
            [("graph-state-change", self.propertyChanged, "Maybe update session UI")],
            None,
            None
        )

    def activateUI(self, on):
        """Activate or deactivate related edit modes."""
        state = commands.data()
        if not hasattr(state, 'modeManager') or state.modeManager is None:
            return
        mm = state.modeManager

        for mode in ["Composite_edit_mode", "Stack_edit_mode"]:
            entry = mm.findModeEntry(mode)
            if entry:
                mm.activateEntry(entry, on)

        # Handle wipe state
        p = commands.viewNode() + ".ui.wipes"
        wipe = state.wipe if hasattr(state, 'wipe') else None

        if on:
            if commands.propertyExists(p):
                wipeon = commands.getIntProperty(p)[0] == 1
                if wipeon:
                    if wipe is None or not wipe._active:
                        commands.toggleWipe()
                else:
                    if wipe is not None and wipe._active:
                        wipe.toggle()
            else:
                if wipe is not None and wipe._active:
                    wipe.toggle()
        elif wipe is not None and wipe._active:
            wipe.toggle()

    def activate(self):
        rvtypes.MinorMode.activate(self)
        self.activateUI(True)

    def deactivate(self):
        self.activateUI(False)
        rvtypes.MinorMode.deactivate(self)

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 3:
            comp = parts[1]
            name = parts[2]

            if (comp == "ui" and name == "wipes") or \
               (comp == "timing" and name == "retimeToOutput"):
                self.activateUI(True)
                commands.redraw()

        event.reject()


def createMode():
    return StackGroupEditMode()
