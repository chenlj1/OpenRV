#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""LayoutGroup edit mode - manages layout mode and properties UI."""

import os
import sys

from rv import rvtypes
from rv import commands
from rv import rvui
from rv import qtutils
from rv import extra_commands

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt, QFile
    from PySide2.QtWidgets import QWidget, QComboBox, QSlider, QLineEdit
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6.QtCore import Qt, QFile
    from PySide6.QtWidgets import QWidget, QComboBox, QSlider, QLineEdit
    from PySide6.QtUiTools import QUiLoader

from session_manager_utils import block_signals


class LayoutGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVLayoutGroup node properties."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._modeCombo = None
        self._spacingSlider = None
        self._gridRowsLineEdit = None
        self._gridColumnsLineEdit = None

        self.init(
            "LayoutGroup_edit_mode",
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            None,
            [
                ("Layout", [
                    ("Layout Method", lambda e: None, None, lambda: commands.DisabledMenuState),
                    ("    Packed", self.layoutPackedEvent, None, lambda: self.isLayoutMode("packed")),
                    ("    Packed With Fluid Layout", self.layoutPacked2Event, None, lambda: self.isLayoutMode("packed2")),
                    ("    Row", self.layoutInRowEvent, None, lambda: self.isLayoutMode("row")),
                    ("    Column", self.layoutInColumnEvent, None, lambda: self.isLayoutMode("column")),
                    ("    Grid", self.layoutInGridEvent, None, lambda: self.isLayoutMode("grid")),
                    ("    Manual", self.layoutManuallyEvent, None, lambda: self.isLayoutMode("manual")),
                    ("    Static", self.layoutStaticEvent, None, lambda: self.isLayoutMode("static")),
                ])
            ],
            "a"
        )
        self.activateTransformMode(self.layoutMode() == "manual")

    def layoutMode(self):
        """Get current layout mode."""
        modeProp = "#RVLayoutGroup.layout.mode"
        try:
            return commands.getStringProperty(modeProp)[0]
        except Exception:
            return ""

    def setLayoutMode(self, mode):
        """Set layout mode."""
        modeProp = "#RVLayoutGroup.layout.mode"
        commands.setStringProperty(modeProp, [mode], True)

    def setSpacing(self, value):
        """Set layout spacing."""
        prop = "#RVLayoutGroup.layout.spacing"
        commands.setFloatProperty(prop, [value], True)

    def setGridRowsColumns(self, rows, columns):
        """Set grid rows and columns."""
        prop = "#RVLayoutGroup.layout."
        commands.setIntProperty(prop + "gridRows", [rows], True)
        commands.setIntProperty(prop + "gridColumns", [columns], True)
        self.setLayoutMode("grid")

    def updateUI(self):
        """Update UI to reflect current state."""
        if self._ui is None:
            return

        try:
            with block_signals(self._modeCombo, self._spacingSlider, 
                              self._gridRowsLineEdit, self._gridColumnsLineEdit):
                
                mode = self.layoutMode()
                mode_map = {
                    "packed": 0, "packed2": 1, "row": 2, "column": 3,
                    "grid": 4, "manual": 5
                }
                index = mode_map.get(mode, 6)
                self._modeCombo.setCurrentIndex(index)

                sp = commands.getFloatProperty("#RVLayoutGroup.layout.spacing")[0]
                self._spacingSlider.setValue(int((max(0.5, min(1.0, sp)) * 2.0 - 1.0) * 999.0))

                r = commands.getIntProperty("#RVLayoutGroup.layout.gridRows")[0]
                self._gridRowsLineEdit.setText("%d" % r)

                c = commands.getIntProperty("#RVLayoutGroup.layout.gridColumns")[0]
                self._gridColumnsLineEdit.setText("%d" % c)
        except Exception:
            pass
            if self._modeCombo:
                with block_signals(self._modeCombo):
                    self._modeCombo.setCurrentIndex(0)

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 3:
            comp = parts[1]
            name = parts[2]

            if comp == "layout" and self._ui is not None:
                if name in ("mode", "spacing", "gridRows", "gridColumns"):
                    self.updateUI()
                    commands.redraw()

        event.reject()

    def spacingSliderChangedSlot(self, value):
        self.setSpacing(float(value) / 999.0 / 2.0 + 0.5)

    def gridRowsChangedSlot(self):
        try:
            newRows = int(self._gridRowsLineEdit.text())
            self.setGridRowsColumns(newRows, 0)
            commands.redraw()
        except (ValueError, TypeError):
            pass

    def gridColumnsChangedSlot(self):
        try:
            newColumns = int(self._gridColumnsLineEdit.text())
            self.setGridRowsColumns(0, newColumns)
            commands.redraw()
        except (ValueError, TypeError):
            pass

    def modeComboChangedSlot(self, index):
        if index == 0:
            self.layoutPacked()
        elif index == 1:
            self.layoutPacked2()
        elif index == 2:
            self.layoutInRow()
        elif index == 3:
            self.layoutInColumn()
        elif index == 4:
            self.layoutInGrid()
        elif index == 5:
            self.layoutManually()
        else:
            self.layoutStatic()

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Only show for Layout node types
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Layout editor shows for RVLayoutGroup only
        if ntype != "RVLayoutGroup":
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
                uifile = QFile(manager.auxFilePath("layout.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()

                self._modeCombo = self._ui.findChild(QComboBox, "modeCombo")
                self._spacingSlider = self._ui.findChild(QSlider, "spacingSlider")
                self._gridRowsLineEdit = self._ui.findChild(QLineEdit, "gridRowsLineEdit")
                self._gridColumnsLineEdit = self._ui.findChild(QLineEdit, "gridColumnsLineEdit")

                manager.addEditor("Layout", self._ui)
                self._modeCombo.currentIndexChanged.connect(self.modeComboChangedSlot)
                self._spacingSlider.sliderMoved.connect(self.spacingSliderChangedSlot)
                self._gridRowsLineEdit.editingFinished.connect(self.gridRowsChangedSlot)
                self._gridColumnsLineEdit.editingFinished.connect(self.gridColumnsChangedSlot)

            self.updateUI()
            manager.useEditor("Layout")

        event.reject()

    def layoutInRow(self):
        self.setLayoutMode("row")
        self.activateTransformMode(False)

    def layoutInColumn(self):
        self.setLayoutMode("column")
        self.activateTransformMode(False)

    def layoutPacked(self):
        self.setLayoutMode("packed")
        self.activateTransformMode(False)

    def layoutInGrid(self):
        self.setLayoutMode("grid")
        self.activateTransformMode(False)

    def layoutPacked2(self):
        self.setLayoutMode("packed2")
        self.activateTransformMode(False)

    def layoutManually(self):
        self.setLayoutMode("manual")
        self.activateTransformMode(True)

    def layoutStatic(self):
        self.setLayoutMode("static")
        self.activateTransformMode(False)

    def layoutPackedEvent(self, event):
        self.layoutPacked()

    def layoutPacked2Event(self, event):
        self.layoutPacked2()

    def layoutInRowEvent(self, event):
        self.layoutInRow()

    def layoutInColumnEvent(self, event):
        self.layoutInColumn()

    def layoutInGridEvent(self, event):
        self.layoutInGrid()

    def layoutManuallyEvent(self, event):
        self.layoutManually()

    def layoutStaticEvent(self, event):
        self.layoutStatic()

    def activateTransformMode(self, on):
        """Activate or deactivate transform manip mode."""
        state = commands.data()
        if not hasattr(state, 'modeManager') or state.modeManager is None:
            return
        mm = state.modeManager
        entry = mm.findModeEntry("transform_manip")
        if entry:
            mm.activateEntry(entry, on)

    def activateUI(self, on):
        """Activate or deactivate related edit modes."""
        state = commands.data()
        if not hasattr(state, 'modeManager') or state.modeManager is None:
            return
        mm = state.modeManager
        for mode in ["Stack_edit_mode", "Composite_edit_mode"]:
            entry = mm.findModeEntry(mode)
            if entry:
                mm.activateEntry(entry, on)

    def deactivate(self):
        self.activateUI(False)
        self.activateTransformMode(False)
        rvtypes.MinorMode.deactivate(self)

    def activate(self):
        rvtypes.MinorMode.activate(self)
        self.activateUI(True)
        self.activateTransformMode(self.layoutMode() == "manual")

    def isLayoutMode(self, name):
        """Return menu state for layout mode."""
        return commands.CheckedMenuState if self.layoutMode() == name else commands.UncheckedMenuState


def createMode():
    return LayoutGroupEditMode()
