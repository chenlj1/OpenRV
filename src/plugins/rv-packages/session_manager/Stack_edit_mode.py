#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Stack edit mode - manages stack properties UI."""

import os
import sys

from rv import rvtypes
from rv import commands
from rv import extra_commands
from rv import rvui
from rv import qtutils

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt, QFile
    from PySide2.QtWidgets import QWidget, QCheckBox, QComboBox, QLineEdit
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6.QtCore import Qt, QFile
    from PySide6.QtWidgets import QWidget, QCheckBox, QComboBox, QLineEdit
    from PySide6.QtUiTools import QUiLoader

from session_manager_utils import block_signals


class StackEditMode(rvtypes.MinorMode):
    """Edit mode for RVStack node properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._alignCheckBox = None
        self._strictRangesCheckBox = None
        self._useCutInfoCheckBox = None
        self._retimeCheckBox = None
        self._autoSizeCheckBox = None
        self._interactiveSizeCheckBox = None
        self._chosenAudioInputCombo = None
        self._outputFPSEdit = None
        self._outputWidthEdit = None
        self._outputHeightEdit = None
        self._updating = False  # Prevent re-entrant updates

        self.init(
            "Stack_edit_mode",
            None,
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("range-changed", self.updateUIEvent, "Update UI"),
                ("image-structure-change", self.updateUIEvent, "Update UI"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            None,
            "z"
        )

    def updateUI(self):
        """Update UI to reflect current state."""
        vnode = commands.viewNode()
        if self._ui is None or vnode is None:
            return
        if self._updating:
            return
        
        self._updating = True
        try:
            with block_signals(self._alignCheckBox, self._strictRangesCheckBox, 
                              self._useCutInfoCheckBox, self._autoSizeCheckBox, 
                              self._interactiveSizeCheckBox, self._retimeCheckBox,
                              self._chosenAudioInputCombo, self._outputFPSEdit, 
                              self._outputWidthEdit, self._outputHeightEdit):
                
                a = commands.getIntProperty("#RVStack.mode.alignStartFrames")[0]
                st = commands.getIntProperty("#RVStack.mode.strictFrameRanges")[0]
                u = commands.getIntProperty("#RVStack.mode.useCutInfo")[0]
                c = commands.getStringProperty("#RVStack.output.chosenAudioInput")[0]
                asize = commands.getIntProperty("#RVStack.output.autoSize")[0]
                size = commands.getIntProperty("#RVStack.output.size")
                fps = commands.getFloatProperty("#RVStack.output.fps")[0]
                isize = commands.getIntProperty("#RVStack.output.interactiveSize")[0]

                self._alignCheckBox.setCheckState(Qt.Unchecked if a == 0 else Qt.Checked)
                self._strictRangesCheckBox.setCheckState(Qt.Unchecked if st == 0 else Qt.Checked)
                self._useCutInfoCheckBox.setCheckState(Qt.Unchecked if u == 0 else Qt.Checked)
                self._autoSizeCheckBox.setCheckState(Qt.Unchecked if asize == 0 else Qt.Checked)
                self._interactiveSizeCheckBox.setCheckState(Qt.Unchecked if isize == 0 else Qt.Checked)

                self._chosenAudioInputCombo.clear()
                self._chosenAudioInputCombo.addItem("All Inputs Mixed", ".all.")
                self._chosenAudioInputCombo.addItem("First Input Only", ".first.")
                self._chosenAudioInputCombo.addItem("First Visible Input", ".topmost.")

                chosenIndex = 0
                inputs = []
                try:
                    vn = commands.viewNode()
                    if vn:
                        conns = commands.nodeConnections(vn, False)
                        if conns and len(conns) > 0:
                            inputs = conns[0] if conns[0] else []
                except Exception:
                    inputs = []

                if c == ".first.":
                    chosenIndex = 1
                elif c == ".topmost.":
                    chosenIndex = 2

                for i, inp in enumerate(inputs):
                    try:
                        uiname = extra_commands.uiName(inp) if inp else str(inp)
                        self._chosenAudioInputCombo.addItem(uiname, inp)
                        if inp == c:
                            chosenIndex = i + 3
                    except Exception:
                        pass

                self._chosenAudioInputCombo.setCurrentIndex(chosenIndex)

                self._outputWidthEdit.setEnabled(asize == 0)
                self._outputHeightEdit.setEnabled(asize == 0)

                self._outputFPSEdit.setText("%g" % fps)
                self._outputWidthEdit.setText("%d" % size[0])
                self._outputHeightEdit.setText("%d" % size[-1])

                retimeProp = "#View.timing.retimeInputs"
                if commands.propertyExists(retimeProp):
                    r = commands.getIntProperty(retimeProp)[0]
                    self._retimeCheckBox.setCheckState(Qt.Checked if r == 1 else Qt.Unchecked)

        except Exception:
            pass
        finally:
            self._updating = False
            commands.redraw()

    def updateUIEvent(self, event):
        event.reject()
        self.updateUI()

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 3:
            comp = parts[1]
            name = parts[2]

            if comp in ("mode", "output"):
                if name in ("alignStartFrames", "strictFrameRanges", "useCutInfo",
                           "chosenAudioInput", "size", "autoSize", "fps", "interactiveSize"):
                    if self._ui is not None:
                        self.updateUI()

        event.reject()

    def checkBoxSlot(self, propName):
        """Create checkbox slot for property."""
        def slot(state):
            v = commands.getIntProperty(propName)[0]
            newV = 1 if state == Qt.Checked else 0
            if v != newV:
                commands.setIntProperty(propName, [newV], True)
        return slot

    def setChosenAudioInput(self, index):
        if self._updating:
            return
        if self._chosenAudioInputCombo is None:
            return

        try:
            currentName = commands.getStringProperty("#RVStack.output.chosenAudioInput")[0]
        except Exception:
            currentName = ""

        name = ".all."  # Default fallback
        try:
            if 0 <= index < self._chosenAudioInputCombo.count():
                data = self._chosenAudioInputCombo.itemData(index, Qt.UserRole)
                if data is not None:
                    name = str(data)  # Ensure it's a string
        except Exception:
            pass

        if name and name != currentName:
            try:
                commands.setStringProperty("#RVStack.output.chosenAudioInput", [name], True)
                commands.redraw()
            except Exception:
                pass

    def fpsChanged(self):
        try:
            newFPS = float(self._outputFPSEdit.text())
            commands.setFloatProperty("#RVStack.output.fps", [newFPS], True)
            commands.setFPS(newFPS)
        except (ValueError, TypeError):
            pass
        commands.redraw()

    def widthChanged(self):
        try:
            val = int(float(self._outputWidthEdit.text()))
            prop = commands.getIntProperty("#RVStack.output.size")
            commands.setIntProperty("#RVStack.output.size", [val, prop[-1]])
        except (ValueError, TypeError):
            pass
        commands.redraw()

    def heightChanged(self):
        try:
            val = int(float(self._outputHeightEdit.text()))
            prop = commands.getIntProperty("#RVStack.output.size")
            commands.setIntProperty("#RVStack.output.size", [prop[0], val])
        except (ValueError, TypeError):
            pass
        commands.redraw()

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Only show for Stack and Layout node types
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Stack editor shows for RVStackGroup and RVLayoutGroup
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
                uipath = manager.auxFilePath("stack.ui")
                uifile = QFile(uipath)
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()
                else:
                    event.reject()
                    return

                self._alignCheckBox = self._ui.findChild(QCheckBox, "alignCheckBox")
                self._strictRangesCheckBox = self._ui.findChild(QCheckBox, "strictRangesCheckBox")
                self._useCutInfoCheckBox = self._ui.findChild(QCheckBox, "useCutInfoCheckBox")
                self._retimeCheckBox = self._ui.findChild(QCheckBox, "retimeInputsCheckBox")
                self._autoSizeCheckBox = self._ui.findChild(QCheckBox, "autoSizeCheckBox")
                self._chosenAudioInputCombo = self._ui.findChild(QComboBox, "chosenAudioInputCombo")
                self._outputFPSEdit = self._ui.findChild(QLineEdit, "outputFPSEdit")
                self._outputWidthEdit = self._ui.findChild(QLineEdit, "outputWidthEdit")
                self._outputHeightEdit = self._ui.findChild(QLineEdit, "outputHeightEdit")
                self._interactiveSizeCheckBox = self._ui.findChild(QCheckBox, "interactiveResizeCheckBox")

                manager.addEditor("Stack", self._ui)

                self._alignCheckBox.stateChanged.connect(self.checkBoxSlot("#RVStack.mode.alignStartFrames"))
                self._strictRangesCheckBox.stateChanged.connect(self.checkBoxSlot("#RVStack.mode.strictFrameRanges"))
                self._useCutInfoCheckBox.stateChanged.connect(self.checkBoxSlot("#RVStack.mode.useCutInfo"))
                self._autoSizeCheckBox.stateChanged.connect(self.checkBoxSlot("#RVStack.output.autoSize"))
                self._retimeCheckBox.stateChanged.connect(self.checkBoxSlot("#View.timing.retimeInputs"))
                self._interactiveSizeCheckBox.stateChanged.connect(self.checkBoxSlot("#RVStack.output.interactiveSize"))

                self._chosenAudioInputCombo.currentIndexChanged.connect(self.setChosenAudioInput)
                self._outputFPSEdit.editingFinished.connect(self.fpsChanged)
                self._outputWidthEdit.editingFinished.connect(self.widthChanged)
                self._outputHeightEdit.editingFinished.connect(self.heightChanged)

            self.updateUI()
            manager.useEditor("Stack")

        event.reject()


def createMode():
    return StackEditMode()
