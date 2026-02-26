#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Composite edit mode - manages stack composite operation properties UI."""

import os
import sys

from rv import rvtypes
from rv import commands
from rv import rvui
from rv import qtutils

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt, QFile
    from PySide2.QtWidgets import QWidget, QComboBox
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6.QtCore import Qt, QFile
    from PySide6.QtWidgets import QWidget, QComboBox
    from PySide6.QtUiTools import QUiLoader

from session_manager_utils import block_signals


class CompositeEditMode(rvtypes.MinorMode):
    """Edit mode for RVStack composite operation properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._comboBox = None

        self.init(
            "Composite_edit_mode",
            None,
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            [
                ("Stack", [
                    ("Composite Operation", None, None, self.inactiveState),
                    ("   Over", self.setOpEvent(0), None, self.opState("over")),
                    ("   Add", self.setOpEvent(1), None, self.opState("add")),
                    ("   Dissolve", self.setOpEvent(2), None, self.opState("dissolve")),
                    ("   Difference", self.setOpEvent(2), None, self.opState("difference")),
                    ("   Inverted Difference", self.setOpEvent(3), None, self.opState("-difference")),
                    ("   Replace", self.setOpEvent(4), None, self.opState("replace")),
                    ("   Topmost", self.setOpEvent(5), None, self.opState("topmost")),
                    ("_", None, None, None),
                    ("Cycle Forward", self.cycleStackForward, None, self.isStackMode),
                    ("Cycle Backward", self.cycleStackBackward, None, self.isStackMode)
                ])
            ],
            "b"
        )

    def inactiveState(self):
        return commands.DisabledMenuState

    def isStackMode(self):
        try:
            t = commands.nodeType(commands.viewNode())
            return commands.NeutralMenuState if t == "RVStackGroup" else commands.DisabledMenuState
        except Exception:
            return commands.DisabledMenuState

    def cycleStackForward(self, event):
        commands.sendInternalEvent("cycle-stack-forward")

    def cycleStackBackward(self, event):
        commands.sendInternalEvent("cycle-stack-backward")

    def setOp(self, index):
        """Set composite operation (matches Mu: indices 0-5 = over, add, difference, -difference, replace, topmost). Dissolve maps to difference."""
        name = "over"
        if index == 0:
            name = "over"
        elif index == 1:
            name = "add"
        elif index == 2:
            name = "difference"
        elif index == 3:
            name = "-difference"
        elif index == 4:
            name = "replace"
        elif index == 5:
            name = "topmost"

        commands.setStringProperty("#RVStack.composite.type", [name], True)
        commands.redraw()

    def setOpEvent(self, index):
        """Return event handler for setting op."""
        def handler(event):
            self.setOp(index)
        return handler

    def opState(self, name):
        """Return state function for menu checkmark."""
        def state():
            try:
                op = commands.getStringProperty("#RVStack.composite.type")[0]
                return commands.CheckedMenuState if op == name else commands.UncheckedMenuState
            except Exception:
                return commands.UncheckedMenuState
        return state

    def updateUI(self):
        """Update UI to reflect current state."""
        if self._ui is None:
            return

        index = 0
        try:
            with block_signals(self._comboBox):
                op = commands.getStringProperty("#RVStack.composite.type")[0]
                if op == "over":
                    index = 0
                elif op == "add":
                    index = 1
                elif op in ("difference", "dissolve"):
                    index = 2
                elif op == "-difference":
                    index = 3
                elif op == "replace":
                    index = 4
                elif op == "topmost":
                    index = 5
                else:
                    index = 6
                if self._comboBox:
                    self._comboBox.setCurrentIndex(min(index, 5))
        except Exception:
            pass

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 3:
            comp = parts[1]
            name = parts[2]

            if comp == "composite" and name == "type":
                self.updateUI()

        event.reject()

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Only show for Stack and Layout node types
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Composite editor shows for RVStackGroup and RVLayoutGroup
        if ntype not in ("RVStackGroup", "RVLayoutGroup"):
            event.reject()
            return
            
        state = commands.data()

        if hasattr(state, 'sessionManager') and state.sessionManager is not None:
            manager = state.sessionManager
            
            # Check if UI is ready before proceeding
            if not manager.isUIReady():
                event.reject()
                return
                
            m = qtutils.sessionWindow()

            if self._ui is None:
                loader = QUiLoader()
                uifile = QFile(manager.auxFilePath("composite.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()

                    self._comboBox = self._ui.findChild(QComboBox, "comboBox")

                    manager.addEditor("Composite Function", self._ui)

                    if self._comboBox:
                        self._comboBox.currentIndexChanged.connect(self.setOp)
                else:
                    event.reject()
                    return

            self.updateUI()
            manager.useEditor("Composite Function")

        event.reject()


def createMode():
    return CompositeEditMode()
