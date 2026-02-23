#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""RetimeGroup edit mode - manages retime properties UI."""

import os
import sys

from rv import rvtypes
from rv import commands
from rv import rvui
from rv import qtutils

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt, QFile
    from PySide2.QtWidgets import QWidget, QLineEdit, QPushButton
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6.QtCore import Qt, QFile
    from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton
    from PySide6.QtUiTools import QUiLoader

from session_manager_utils import block_signals


class RetimeGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVRetimeGroup node properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._fpsEdit = None
        self._voffsetEdit = None
        self._aoffsetEdit = None
        self._vscaleEdit = None
        self._ascaleEdit = None
        self._reverseButton = None
        self._resetButton = None

        self.init(
            "RetimeGroup_edit_mode",
            None,
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            [
                ("Retime", [
                    ("Convert to FPS", [
                        ("24", lambda e: self.convertToFPS(e, 24), None, None),
                        ("25", lambda e: self.convertToFPS(e, 25), None, None),
                        ("23.98", lambda e: self.convertToFPS(e, 23.98), None, None),
                        ("30", lambda e: self.convertToFPS(e, 30), None, None),
                        ("29.97", lambda e: self.convertToFPS(e, 29.97), None, None),
                    ]),
                    ("_", None),
                    ("Reverse", self.reverseTiming, None, None),
                    ("_", None),
                    ("Reset Timing", self.resetTiming, None, None),
                ])
            ],
            None
        )

    def reset(self):
        """Reset retime to default values."""
        commands.setFloatProperty("#RVRetime.visual.scale", [1.0], True)
        commands.setFloatProperty("#RVRetime.visual.offset", [0.0], True)
        commands.setFloatProperty("#RVRetime.audio.scale", [1.0], True)
        commands.setFloatProperty("#RVRetime.audio.offset", [0.0], True)
        commands.redraw()

    def reverse(self):
        """Toggle reverse playback."""
        length = commands.frameEnd() - commands.frameStart()
        scl = commands.getFloatProperty("#RVRetime.visual.scale")[0]

        if scl < 0:
            commands.setFloatProperty("#RVRetime.visual.scale", [1.0], True)
            commands.setFloatProperty("#RVRetime.visual.offset", [0.0], True)
            commands.setFloatProperty("#RVRetime.audio.scale", [1.0], True)
            commands.setFloatProperty("#RVRetime.audio.offset", [0.0], True)
        else:
            commands.setFloatProperty("#RVRetime.visual.scale", [-1.0], True)
            commands.setFloatProperty("#RVRetime.visual.offset", [float(-length)], True)
            commands.setFloatProperty("#RVRetime.audio.scale", [1.0], True)
            commands.setFloatProperty("#RVRetime.audio.offset", [0.0], True)

        commands.redraw()

    def updateUI(self):
        """Update UI to reflect current state."""
        if self._ui is None:
            return

        try:
            with block_signals(self._fpsEdit, self._vscaleEdit, self._ascaleEdit, 
                              self._voffsetEdit, self._aoffsetEdit):
                fps = commands.getFloatProperty("#RVRetime.output.fps")[0]
                vscale = commands.getFloatProperty("#RVRetime.visual.scale")[0]
                ascale = commands.getFloatProperty("#RVRetime.audio.scale")[0]
                voffset = commands.getFloatProperty("#RVRetime.visual.offset")[0]
                aoffset = commands.getFloatProperty("#RVRetime.audio.offset")[0]

                self._fpsEdit.setText("%g" % fps)
                self._vscaleEdit.setText("%g" % vscale)
                self._ascaleEdit.setText("%g" % ascale)
                self._voffsetEdit.setText("%g" % voffset)
                self._aoffsetEdit.setText("%g" % aoffset)
        except Exception:
            pass

    def resetSlot(self, checked):
        self.reset()

    def reverseSlot(self, checked):
        self.reverse()

    def editSlot(self, lineEdit, prop):
        """Create editing slot for property."""
        def slot():
            try:
                v = float(lineEdit.text())
                commands.setFloatProperty("#RVRetime" + prop, [v], True)
                if prop == ".output.fps":
                    commands.setFPS(v)
                commands.redraw()
            except (ValueError, TypeError):
                pass
        return slot

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Retime editor is typically shown only in specific contexts
        # For now, only show for source groups that have retime properties
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Only show for source groups (where retiming individual sources makes sense)
        # Skip for now - this can be enabled later if needed
        if ntype != "RVSourceGroup":
            event.reject()
            return
        
        # Additionally, only show if retime properties exist
        try:
            if not commands.propertyExists("#RVRetime.output.fps"):
                event.reject()
                return
        except Exception:
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
                uifile = QFile(manager.auxFilePath("retime.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()

                self._fpsEdit = self._ui.findChild(QLineEdit, "fpsEdit")
                self._ascaleEdit = self._ui.findChild(QLineEdit, "ascaleEdit")
                self._vscaleEdit = self._ui.findChild(QLineEdit, "vscaleEdit")
                self._aoffsetEdit = self._ui.findChild(QLineEdit, "aoffsetEdit")
                self._voffsetEdit = self._ui.findChild(QLineEdit, "voffsetEdit")
                self._resetButton = self._ui.findChild(QPushButton, "resetButton")
                self._reverseButton = self._ui.findChild(QPushButton, "reverseButton")

                manager.addEditor("Retime", self._ui)

                self._resetButton.clicked.connect(self.resetSlot)
                self._reverseButton.clicked.connect(self.reverseSlot)

                edits = [
                    (self._fpsEdit, ".output.fps"),
                    (self._ascaleEdit, ".audio.scale"),
                    (self._vscaleEdit, ".visual.scale"),
                    (self._aoffsetEdit, ".audio.offset"),
                    (self._voffsetEdit, ".visual.offset")
                ]

                for edit, prop in edits:
                    edit.editingFinished.connect(self.editSlot(edit, prop))

            self.updateUI()
            manager.useEditor("Retime")

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 1:
            node = parts[0]
            if commands.nodeType(node) == "RVRetime":
                self.updateUI()

        event.reject()

    def convertToFPS(self, event, newFPS):
        """Convert to specified FPS."""
        commands.setFloatProperty("#RVRetime.output.fps", [newFPS], True)
        commands.setFPS(newFPS)

    def resetTiming(self, event):
        self.reset()

    def reverseTiming(self, event):
        self.reverse()


def createMode():
    return RetimeGroupEditMode()
