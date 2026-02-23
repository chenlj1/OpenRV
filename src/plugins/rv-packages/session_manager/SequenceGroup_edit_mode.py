#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""SequenceGroup edit mode - manages sequence properties UI."""

import os
import sys

from rv import rvtypes
from rv import commands
from rv import rvui
from rv import qtutils

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt, QFile
    from PySide2.QtWidgets import QWidget, QCheckBox, QLineEdit
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6.QtCore import Qt, QFile
    from PySide6.QtWidgets import QWidget, QCheckBox, QLineEdit
    from PySide6.QtUiTools import QUiLoader

from session_manager_utils import block_signals


class SequenceGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVSequenceGroup node properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._autoEDLCheckBox = None
        self._useCutInfoCheckBox = None
        self._retimeCheckBox = None
        self._autoSizeCheckBox = None
        self._interactiveSizeCheckBox = None
        self._outputFPSEdit = None
        self._outputWidthEdit = None
        self._outputHeightEdit = None
        self._disableUpdates = False

        self.init(
            "SequenceGroup_edit_mode",
            None,
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("range-changed", self.updateUIEvent, "Update UI on range change"),
                ("image-structure-change", self.updateUIEvent, "Update UI on range change"),
                ("before-session-read", self.beforeSessionRead, "Freeze Updates"),
                ("after-session-read", self.afterSessionRead, "Resume Updates"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            [
                ("Sequence", [
                    ("_", None),
                    ("Auto EDL", self.autoEDL, None, lambda: self.stateFunc("autoEDL")),
                    ("Use Source Cut Info", self.useCutInfo, None, lambda: self.stateFunc("useCutInfo")),
                ])
            ],
            None
        )

    def beforeSessionRead(self, event):
        self._disableUpdates = True
        event.reject()

    def afterSessionRead(self, event):
        self._disableUpdates = False
        self.updateUI()
        event.reject()

    def updateUI(self):
        """Update UI to reflect current state."""
        if self._ui is None or self._disableUpdates:
            return

        try:
            if not commands.propertyExists("#RVSequence.mode.autoEDL"):
                return
        except Exception:
            return

        try:
            with block_signals(self._autoEDLCheckBox, self._useCutInfoCheckBox, 
                              self._retimeCheckBox, self._autoSizeCheckBox, 
                              self._interactiveSizeCheckBox, self._outputFPSEdit, 
                              self._outputWidthEdit, self._outputHeightEdit):
                
                a = commands.getIntProperty("#RVSequence.mode.autoEDL")[0]
                u = commands.getIntProperty("#RVSequence.mode.useCutInfo")[0]
                r = commands.getIntProperty("#RVSequenceGroup.timing.retimeInputs")[0]
                fps = commands.getFloatProperty("#RVSequence.output.fps")[0]
                asize = commands.getIntProperty("#RVSequence.output.autoSize")[0]
                size = commands.getIntProperty("#RVSequence.output.size")
                isize = commands.getIntProperty("#RVSequence.output.interactiveSize")[0]

                self._outputWidthEdit.setEnabled(asize == 0 and isize == 0)
                self._outputHeightEdit.setEnabled(asize == 0 and isize == 0)

                self._autoEDLCheckBox.setCheckState(Qt.Unchecked if a == 0 else Qt.Checked)
                self._useCutInfoCheckBox.setCheckState(Qt.Unchecked if u == 0 else Qt.Checked)
                self._retimeCheckBox.setCheckState(Qt.Unchecked if r == 0 else Qt.Checked)
                self._autoSizeCheckBox.setCheckState(Qt.Unchecked if asize == 0 else Qt.Checked)
                self._outputFPSEdit.setText("%g" % fps)
                self._outputWidthEdit.setText("%d" % size[0])
                self._outputHeightEdit.setText("%d" % size[-1])
                self._interactiveSizeCheckBox.setCheckState(Qt.Unchecked if isize == 0 else Qt.Checked)
        except Exception:
            pass

    def updateUIEvent(self, event):
        event.reject()
        self.updateUI()

    def fpsChanged(self):
        try:
            newFPS = float(self._outputFPSEdit.text())
            oldFPS = commands.getFloatProperty("#RVSequence.output.fps")[0]
            if newFPS != oldFPS:
                commands.setFloatProperty("#RVSequence.output.fps", [newFPS], True)
                commands.setFPS(newFPS)
                commands.redraw()
        except (ValueError, TypeError):
            pass

    def widthChanged(self):
        try:
            val = int(float(self._outputWidthEdit.text()))
            prop = commands.getIntProperty("#RVSequence.output.size")
            commands.setIntProperty("#RVSequence.output.size", [val, prop[-1]])
            commands.redraw()
        except (ValueError, TypeError):
            pass

    def heightChanged(self):
        try:
            val = int(float(self._outputHeightEdit.text()))
            prop = commands.getIntProperty("#RVSequence.output.size")
            commands.setIntProperty("#RVSequence.output.size", [prop[0], val])
            commands.redraw()
        except (ValueError, TypeError):
            pass

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 3:
            comp = parts[1]
            name = parts[2]

            if comp in ("mode", "output"):
                if name in ("autoEDL", "autoSize", "useCutInfo", "width", "fps", "height", "interactiveSize"):
                    self.updateUI()
                    commands.redraw()

        event.reject()

    def checkBoxSlot(self, propName):
        """Create checkbox slot for property."""
        def slot(state):
            current = commands.getIntProperty(propName)[0]
            value = 1 if state == Qt.Checked else 0
            if value != current:
                commands.setIntProperty(propName, [value], True)
        return slot

    def activateUI(self):
        """Activate UI and load into session manager."""
        # Only show for Sequence node types
        vnode = commands.viewNode()
        if vnode is None:
            return
            
        ntype = commands.nodeType(vnode)

        # Sequence editor shows for RVSequenceGroup
        if ntype != "RVSequenceGroup":
            return
            
        state = commands.data()

        if state is not None and hasattr(state, 'sessionManager') and state.sessionManager is not None:
            manager = state.sessionManager
            
            # Check if UI is ready before proceeding
            if not manager.isUIReady():
                return
                
            m = qtutils.sessionWindow()

            if self._ui is None:
                loader = QUiLoader()
                uifile = QFile(manager.auxFilePath("sequence.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()
                else:
                    return

                self._autoEDLCheckBox = self._ui.findChild(QCheckBox, "autoEDLCheckBox")
                self._useCutInfoCheckBox = self._ui.findChild(QCheckBox, "useCutInfoCheckBox")
                self._retimeCheckBox = self._ui.findChild(QCheckBox, "retimeInputsCheckBox")
                self._outputFPSEdit = self._ui.findChild(QLineEdit, "outputFPSEdit")
                self._outputWidthEdit = self._ui.findChild(QLineEdit, "outputWidthEdit")
                self._outputHeightEdit = self._ui.findChild(QLineEdit, "outputHeightEdit")
                self._autoSizeCheckBox = self._ui.findChild(QCheckBox, "autoSizeCheckBox")
                self._interactiveSizeCheckBox = self._ui.findChild(QCheckBox, "interactiveResizeCheckBox")
                manager.addEditor("Sequence", self._ui)

                self._autoEDLCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSequence.mode.autoEDL"))
                self._useCutInfoCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSequence.mode.useCutInfo"))
                self._autoSizeCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSequence.output.autoSize"))
                self._retimeCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSequenceGroup.timing.retimeInputs"))
                self._interactiveSizeCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSequence.output.interactiveSize"))

                self._outputFPSEdit.editingFinished.connect(self.fpsChanged)
                self._outputWidthEdit.editingFinished.connect(self.widthChanged)
                self._outputHeightEdit.editingFinished.connect(self.heightChanged)

            self.updateUI()
            manager.useEditor("Sequence")

    def loadUI(self, event):
        self._disableUpdates = False
        self.activateUI()
        event.reject()

    def activate(self):
        rvtypes.MinorMode.activate(self)
        self._disableUpdates = False
        # Only activate UI if session manager's UI is ready
        state = commands.data()
        if state is not None and hasattr(state, 'sessionManager') and state.sessionManager is not None:
            if state.sessionManager.isUIReady():
                self.activateUI()

    def autoEDL(self, event):
        p = "#RVSequence.mode.autoEDL"
        a = commands.getIntProperty(p)[0]
        commands.setIntProperty(p, [0 if a != 0 else 1], True)

    def useCutInfo(self, event):
        p = "#RVSequence.mode.useCutInfo"
        a = commands.getIntProperty(p)[0]
        commands.setIntProperty(p, [0 if a != 0 else 1], True)

    def stateFunc(self, name):
        try:
            p = commands.getIntProperty("#RVSequence.mode.%s" % name)[0]
            return commands.UncheckedMenuState if p == 0 else commands.CheckedMenuState
        except Exception:
            return commands.UncheckedMenuState


def createMode():
    return SequenceGroupEditMode()
