#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""FolderGroup edit mode - manages folder view type selection."""

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


class FolderGroupEditMode(rvtypes.MinorMode):
    """Edit mode for RVFolderGroup nodes."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._ui = None
        self._viewTypeCombo = None

        self.init(
            "FolderGroup_edit_mode",
            None,
            [
                ("session-manager-load-ui", self.loadUI, "Load UI into Session Manager"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI")
            ],
            None,
            None
        )

    def activateUI(self, on):
        """Activate or deactivate related edit modes based on view type."""
        state = commands.data()
        if not hasattr(state, 'modeManager') or state.modeManager is None:
            return
        mm = state.modeManager

        try:
            currentType = commands.getStringProperty("#RVFolderGroup.mode.viewType")[0]
        except Exception:
            currentType = "layout"

        modes = []
        if currentType == "switch":
            modes = ["Switch_edit_mode"]
        elif currentType == "layout":
            modes = ["LayoutGroup_edit_mode"]
        elif currentType == "stack":
            modes = ["StackGroup_edit_mode"]
        else:
            modes = ["LayoutGroup_edit_mode"]

        for mode in modes:
            entry = mm.findModeEntry(mode)
            if entry:
                mm.activateEntry(entry, on)

    def setViewType(self, index):
        """Handle view type combo box change."""
        try:
            currentType = commands.getStringProperty("#RVFolderGroup.mode.viewType")[0]
        except Exception:
            currentType = ""

        newtype = self._viewTypeCombo.itemData(index, Qt.UserRole)

        if newtype != currentType:
            self.activateUI(False)
            commands.setStringProperty("#RVFolderGroup.mode.viewType", [newtype], True)
            commands.redraw()
            self.activateUI(True)

            state = commands.data()
            if hasattr(state, 'sessionManager') and state.sessionManager is not None:
                manager = state.sessionManager
                manager.reloadEditorTab()

    def updateUI(self):
        """Update UI to reflect current state."""
        vnode = commands.viewNode()
        if self._ui is None or vnode is None:
            return

        try:
            with block_signals(self._viewTypeCombo):
                vtype = commands.getStringProperty("#RVFolderGroup.mode.viewType")[0]

                if vtype == "switch":
                    index = 0
                elif vtype == "layout":
                    index = 1
                elif vtype == "stack":
                    index = 2
                else:
                    index = 1

                if self._viewTypeCombo:
                    self._viewTypeCombo.setCurrentIndex(index)
        except Exception:
            pass

    def loadUI(self, event):
        """Load UI into Session Manager."""
        # Only show for Folder node types
        vnode = commands.viewNode()
        if vnode is None:
            event.reject()
            return
            
        ntype = commands.nodeType(vnode)

        # Folder View editor shows for RVFolderGroup only
        if ntype != "RVFolderGroup":
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
                uifile = QFile(manager.auxFilePath("folder.ui"))
                if uifile.open(QFile.ReadOnly):
                    self._ui = loader.load(uifile, m)
                    uifile.close()

                self._viewTypeCombo = self._ui.findChild(QComboBox, "viewTypeCombo")

                self._viewTypeCombo.clear()
                self._viewTypeCombo.addItem("Switch", "switch")
                self._viewTypeCombo.addItem("Layout", "layout")
                self._viewTypeCombo.addItem("Stack", "stack")

                self._viewTypeCombo.currentIndexChanged.connect(self.setViewType)
                manager.addEditor("Folder View", self._ui)

            self.updateUI()
            manager.useEditor("Folder View")

        event.reject()

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

            if comp == "mode" and name == "viewType":
                self.updateUI()

        event.reject()


def createMode():
    return FolderGroupEditMode()
