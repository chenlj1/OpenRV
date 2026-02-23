#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Switch edit mode - manages switch properties UI."""

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


class SwitchEditMode(rvtypes.MinorMode):
    """Edit mode for RVSwitch node properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._alignCheckBox = None
        self._useCutInfoCheckBox = None
        self._autoSizeCheckBox = None
        self._selectedInputCombo = None
        self._outputWidthEdit = None
        self._outputHeightEdit = None
        self._updating = False  # Prevent re-entrant updates

        self.init(
            "Switch_edit_mode",
            None,
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("range-changed", self.updateUIEvent, "Update UI"),
                ("image-structure-change", self.updateUIEvent, "Update UI"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            [
                ("Switch", [
                    ("Align Start Frames", self.alignStartFrames, None, lambda: self.stateFunc("alignStartFrames")),
                    ("Use Source Cut Info", self.useCutInfo, None, lambda: self.stateFunc("useCutInfo")),
                ])
            ],
            "z0"
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
            with block_signals(self._alignCheckBox, self._useCutInfoCheckBox, 
                              self._autoSizeCheckBox, self._selectedInputCombo, 
                              self._outputWidthEdit, self._outputHeightEdit):
                
                a = commands.getIntProperty("#RVSwitch.mode.alignStartFrames")[0]
                u = commands.getIntProperty("#RVSwitch.mode.useCutInfo")[0]
                c = commands.getStringProperty("#RVSwitch.output.input")[0]
                asize = commands.getIntProperty("#RVSwitch.output.autoSize")[0]
                size = commands.getIntProperty("#RVSwitch.output.size")

                self._alignCheckBox.setCheckState(Qt.Unchecked if a == 0 else Qt.Checked)
                self._useCutInfoCheckBox.setCheckState(Qt.Unchecked if u == 0 else Qt.Checked)
                self._autoSizeCheckBox.setCheckState(Qt.Unchecked if asize == 0 else Qt.Checked)

                self._selectedInputCombo.clear()

                selectedIndex = 0
                inputs = []
                try:
                    vn = commands.viewNode()
                    if vn:
                        conns = commands.nodeConnections(vn, False)
                        if conns and len(conns) > 0:
                            inputs = conns[0] if conns[0] else []
                except Exception:
                    inputs = []

                for i, inp in enumerate(inputs):
                    try:
                        uiname = extra_commands.uiName(inp) if inp else str(inp)
                        self._selectedInputCombo.addItem(uiname, inp)
                        if inp == c:
                            selectedIndex = i
                    except Exception:
                        pass

                self._selectedInputCombo.setCurrentIndex(selectedIndex)

                self._outputWidthEdit.setEnabled(asize == 0)
                self._outputHeightEdit.setEnabled(asize == 0)

                self._outputWidthEdit.setText("%d" % size[0])
                self._outputHeightEdit.setText("%d" % size[-1])

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
                if name in ("alignStartFrames", "useCutInfo", "input", "size", "autoSize"):
                    if self._ui is not None:
                        self.updateUI()

        event.reject()

    def checkBoxSlot(self, propName):
        """Create checkbox slot for property."""
        def slot(state):
            commands.setIntProperty(propName, [1 if state == Qt.Checked else 0], True)
        return slot

    def setSelectedInput(self, index):
        if self._updating:
            return
        if self._selectedInputCombo is None:
            return

        try:
            currentName = commands.getStringProperty("#RVSwitch.output.input")[0]
        except Exception:
            currentName = ""

        name = None
        try:
            if 0 <= index < self._selectedInputCombo.count():
                data = self._selectedInputCombo.itemData(index, Qt.UserRole)
                if data is not None:
                    name = str(data)  # Ensure it's a string
        except Exception:
            pass

        if name and name != currentName:
            try:
                commands.setStringProperty("#RVSwitch.output.input", [name], True)
                commands.redraw()
            except Exception:
                pass

    def widthChanged(self):
        try:
            val = int(float(self._outputWidthEdit.text()))
            prop = commands.getIntProperty("#RVSwitch.output.size")
            commands.setIntProperty("#RVSwitch.output.size", [val, prop[-1]])
        except (ValueError, TypeError):
            pass
        commands.redraw()

    def heightChanged(self):
        try:
            val = int(float(self._outputHeightEdit.text()))
            prop = commands.getIntProperty("#RVSwitch.output.size")
            commands.setIntProperty("#RVSwitch.output.size", [prop[0], val])
        except (ValueError, TypeError):
            pass
        commands.redraw()

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Only show for Switch node types
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Switch editor shows for RVSwitchGroup only
        if ntype != "RVSwitchGroup":
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
                uifile = QFile(manager.auxFilePath("switch.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()

                self._alignCheckBox = self._ui.findChild(QCheckBox, "alignCheckBox")
                self._useCutInfoCheckBox = self._ui.findChild(QCheckBox, "useCutInfoCheckBox")
                self._autoSizeCheckBox = self._ui.findChild(QCheckBox, "autoSizeCheckBox")
                self._selectedInputCombo = self._ui.findChild(QComboBox, "selectedInputCombo")
                self._outputWidthEdit = self._ui.findChild(QLineEdit, "outputWidthEdit")
                self._outputHeightEdit = self._ui.findChild(QLineEdit, "outputHeightEdit")

                manager.addEditor("Switch", self._ui)

                self._alignCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSwitch.mode.alignStartFrames"))
                self._useCutInfoCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSwitch.mode.useCutInfo"))
                self._autoSizeCheckBox.stateChanged.connect(self.checkBoxSlot("#RVSwitch.output.autoSize"))

                self._selectedInputCombo.currentIndexChanged.connect(self.setSelectedInput)
                self._outputWidthEdit.editingFinished.connect(self.widthChanged)
                self._outputHeightEdit.editingFinished.connect(self.heightChanged)

            self.updateUI()
            manager.useEditor("Switch")

        event.reject()

    def alignStartFrames(self, event):
        p = "#RVSwitch.mode.alignStartFrames"
        a = commands.getIntProperty(p)[0]
        commands.setIntProperty(p, [0 if a != 0 else 1], True)

    def useCutInfo(self, event):
        p = "#RVSwitch.mode.useCutInfo"
        a = commands.getIntProperty(p)[0]
        commands.setIntProperty(p, [0 if a != 0 else 1], True)

    def stateFunc(self, name):
        try:
            p = commands.getIntProperty("#RVSwitch.mode.%s" % name)[0]
            return commands.UncheckedMenuState if p == 0 else commands.CheckedMenuState
        except Exception:
            return commands.UncheckedMenuState


def createMode():
    return SwitchEditMode()
