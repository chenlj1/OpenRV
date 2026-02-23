#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""SourceGroup edit mode - manages source cut in/out UI."""

import os
import sys

from rv import rvtypes
from rv import commands
from rv import rvui
from rv import qtutils

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt, QFile
    from PySide2.QtWidgets import QWidget, QCheckBox, QSpinBox, QPushButton
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6.QtCore import Qt, QFile
    from PySide6.QtWidgets import QWidget, QCheckBox, QSpinBox, QPushButton
    from PySide6.QtUiTools import QUiLoader

from session_manager_utils import block_signals, INT_MAX


class SourceGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVSourceGroup cut in/out properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._locked = False
        self._ui = None
        self._cutInEdit = None
        self._cutOutEdit = None
        self._syncCheckBox = None
        self._resetButton = None

        self.init(
            "SourceGroup_edit_mode",
            None,
            [
                ("new-in-point", self.newInPoint, "Update In Point"),
                ("new-out-point", self.newOutPoint, "Update Out Point"),
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            [
                ("Source", [
                    ("Clear Source Cut In/Out", self.resetCut, None, None),
                    ("Sync GUI With Source Cut In/Out", self.toggleSync, None, self.syncState),
                ])
            ],
            None
        )

    def syncGuiInOut(self):
        """Check if GUI sync is enabled."""
        p = "#RVFileSource.cut.syncGui"
        if commands.propertyExists(p):
            return commands.getIntProperty(p)[0] != 0
        return True

    def reset(self):
        """Reset cut in/out to source range."""
        self._locked = True
        try:
            if self.syncGuiInOut():
                commands.setInPoint(commands.frameStart())
                commands.setOutPoint(commands.frameEnd())
            commands.setIntProperty("#RVFileSource.cut.in", [-INT_MAX], True)
            commands.setIntProperty("#RVFileSource.cut.out", [INT_MAX], True)
        except Exception:
            pass
        finally:
            self._locked = False
        self.updateUI()
        commands.redraw()

    def updateUI(self):
        """Update UI to reflect current state."""
        if self._ui is None:
            return

        # Check if cut properties exist (only valid when viewing a source)
        cutInProp = "#RVFileSource.cut.in"
        cutOutProp = "#RVFileSource.cut.out"
        if not commands.propertyExists(cutInProp) or not commands.propertyExists(cutOutProp):
            return

        self._locked = True
        try:
            with block_signals(self._cutInEdit, self._cutOutEdit, self._syncCheckBox):
                cutIn = commands.getIntProperty(cutInProp)[0]
                cutOut = commands.getIntProperty(cutOutProp)[0]
                syncGui = self.syncGuiInOut()
                
                # Get the source's natural frame range
                frameStart = commands.frameStart()
                frameEnd = commands.frameEnd()

                # Show blank (-INT_MAX displays as blank due to special value text) if:
                # - cutIn equals -INT_MAX (unset sentinel), OR
                # - cutIn is outside the source's valid frame range (no custom cut or invalid)
                if cutIn == -INT_MAX or cutIn <= frameStart or cutIn > frameEnd:
                    self._cutInEdit.setValue(-INT_MAX)
                else:
                    self._cutInEdit.setValue(cutIn)
                
                # Show blank if:
                # - cutOut equals INT_MAX (unset sentinel), OR
                # - cutOut is outside the source's valid frame range (no custom cut or invalid)
                # Note: cutOut <= frameStart means it's at or before the start (invalid as a cut out point)
                if cutOut == INT_MAX or cutOut >= frameEnd or cutOut <= frameStart:
                    self._cutOutEdit.setValue(-INT_MAX)
                else:
                    self._cutOutEdit.setValue(cutOut)

                self._syncCheckBox.setCheckState(Qt.Checked if syncGui else Qt.Unchecked)
        except Exception:
            pass
        finally:
            self._locked = False

    def resetSlot(self, checked):
        self.reset()

    def syncSlot(self, checked):
        if self._locked:
            return

        p = "#RVFileSource.cut.syncGui"
        commands.setIntProperty(p, [1 if checked else 0], True)
        if checked:
            self.updateFromProps()
        self.updateUI()

    def toggleSync(self, event):
        self.syncSlot(not self.syncGuiInOut())

    def changedSlot(self, prop):
        """Create value changed slot for property."""
        def slot(v):
            if not self._locked and v != -INT_MAX:
                if v < commands.frameStart():
                    return
                if v > commands.frameEnd():
                    return

                if prop == "in" and v > commands.outPoint():
                    return
                if prop == "out" and v < commands.inPoint():
                    return

                self._locked = True
                commands.setIntProperty("#RVFileSource.cut." + prop, [v], True)

                try:
                    if self.syncGuiInOut() and prop == "in":
                        commands.setInPoint(v)
                    if self.syncGuiInOut() and prop == "out":
                        commands.setOutPoint(v)
                except Exception:
                    pass

                self._locked = False
            commands.redraw()
        return slot

    def finishedSlot(self, prop):
        """Create editing finished slot for property."""
        def slot():
            v = self._cutInEdit.value() if prop == "in" else self._cutOutEdit.value()

            if v != -INT_MAX:
                if v < commands.frameStart():
                    v = commands.frameStart()
                if v > commands.frameEnd():
                    v = commands.frameEnd()

                if prop == "in" and v > commands.outPoint():
                    v = commands.outPoint()
                if prop == "out" and v < commands.inPoint():
                    v = commands.inPoint()

                self._locked = True

                if prop == "in":
                    self._cutInEdit.setValue(v)
                if prop == "out":
                    self._cutOutEdit.setValue(v)

                commands.setIntProperty("#RVFileSource.cut." + prop, [v], True)

                try:
                    if self.syncGuiInOut() and prop == "in":
                        commands.setInPoint(v)
                    if self.syncGuiInOut() and prop == "out":
                        commands.setOutPoint(v)
                except Exception:
                    pass

                self._locked = False
            commands.redraw()
        return slot

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Only show for Source node types
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Source editor shows for RVSourceGroup
        if ntype != "RVSourceGroup":
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
                uifile = QFile(manager.auxFilePath("source.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()

                self._cutInEdit = self._ui.findChild(QSpinBox, "cutInEdit")
                self._cutInEdit.setRange(-INT_MAX, INT_MAX)
                self._cutInEdit.setSpecialValueText(" ")

                self._cutOutEdit = self._ui.findChild(QSpinBox, "cutOutEdit")
                self._cutOutEdit.setRange(-INT_MAX, INT_MAX)
                self._cutOutEdit.setSpecialValueText(" ")

                self._resetButton = self._ui.findChild(QPushButton, "resetButton")
                self._syncCheckBox = self._ui.findChild(QCheckBox, "syncCheckBox")

                manager.addEditor("Source", self._ui)

                self._resetButton.clicked.connect(self.resetSlot)

                self._cutInEdit.editingFinished.connect(self.finishedSlot("in"))
                self._cutOutEdit.editingFinished.connect(self.finishedSlot("out"))

                self._cutInEdit.valueChanged.connect(self.changedSlot("in"))
                self._cutOutEdit.valueChanged.connect(self.changedSlot("out"))

                self._syncCheckBox.clicked.connect(self.syncSlot)

            self.updateUI()
            manager.useEditor("Source")

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 1:
            node = parts[0]
            if not self._locked and commands.nodeType(node) == "RVFileSource":
                self.updateUI()
                if self.syncGuiInOut():
                    self.updateFromProps()

        event.reject()

    def resetCut(self, event):
        self.reset()

    def newInPoint(self, event):
        p = "#RVFileSource.cut.in"
        if not self._locked and self.syncGuiInOut() and commands.propertyExists(p):
            commands.setIntProperty(p, [commands.inPoint()], True)
        event.reject()

    def newOutPoint(self, event):
        p = "#RVFileSource.cut.out"
        if not self._locked and self.syncGuiInOut() and commands.propertyExists(p):
            commands.setIntProperty(p, [commands.outPoint()], True)
        event.reject()

    def updateFromProps(self):
        """Update GUI in/out from properties."""
        # Check if cut properties exist (only valid when viewing a source)
        cutInProp = "#RVFileSource.cut.in"
        cutOutProp = "#RVFileSource.cut.out"
        if not commands.propertyExists(cutInProp) or not commands.propertyExists(cutOutProp):
            return

        self._locked = True
        try:
            cutIn = commands.getIntProperty(cutInProp)[0]
            cutOut = commands.getIntProperty(cutOutProp)[0]

            cutIn = min(max(cutIn, commands.frameStart()), commands.frameEnd())
            cutOut = min(max(cutOut, commands.frameStart()), commands.frameEnd())
            commands.setInPoint(cutIn)
            commands.setOutPoint(cutOut)
        except Exception:
            pass
        finally:
            self._locked = False

    def activate(self):
        if self.syncGuiInOut():
            self.updateFromProps()
        rvtypes.MinorMode.activate(self)

    def syncState(self):
        return commands.CheckedMenuState if self.syncGuiInOut() else commands.UncheckedMenuState


def createMode():
    return SourceGroupEditMode()
