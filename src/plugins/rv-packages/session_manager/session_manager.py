#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""
Session Manager - RV's session management interface.

Converted from session_manager.mu to Python.

This package provides a dock widget for managing RV sessions, including:
- Tree view of all nodes organized by type
- Input management for nodes
- Drag and drop support
- Node creation and deletion
- Sub-component viewing (views, layers, channels)
"""

import os
import re
import sys

from rv import rvtypes
from rv import commands
from rv import extra_commands
from rv import rvui

# PySide2/PySide6 compatibility
try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt, QSize, QPoint, QUrl, QFile, QTimer, QModelIndex, QItemSelectionModel
    from PySide2.QtGui import (
        QStandardItemModel, QStandardItem, QIcon, QPixmap, QImage,
        QColor, QBrush, QPalette, QPainter
    )
    from PySide2.QtWidgets import (
        QWidget, QDockWidget, QTreeView, QListView, QSplitter,
        QVBoxLayout, QToolButton, QTabWidget, QTreeWidget, QTreeWidgetItem,
        QLabel, QLineEdit, QGroupBox, QPushButton, QComboBox,
        QMenu, QAction, QActionGroup, QDialog, QColorDialog,
        QAbstractItemView, QApplication
    )
    from PySide2.QtUiTools import QUiLoader
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt, QSize, QPoint, QUrl, QFile, QTimer, QModelIndex, QItemSelectionModel
    from PySide6.QtGui import (
        QStandardItemModel, QStandardItem, QIcon, QPixmap, QImage,
        QColor, QBrush, QPalette, QAction, QActionGroup, QPainter
    )
    from PySide6.QtWidgets import (
        QWidget, QDockWidget, QTreeView, QListView, QSplitter,
        QVBoxLayout, QToolButton, QTabWidget, QTreeWidget, QTreeWidgetItem,
        QLabel, QLineEdit, QGroupBox, QPushButton, QComboBox,
        QMenu, QDialog, QColorDialog,
        QAbstractItemView, QApplication
    )
    from PySide6.QtUiTools import QUiLoader

from rv import qtutils

# =============================================================================
# Import shared utilities
# =============================================================================
from session_manager_utils import (
    USER_ROLE_PARENT_NODE, USER_ROLE_NODE, USER_ROLE_SORT_KEY,
    USER_ROLE_SUBCOMPONENT_TYPE, USER_ROLE_SUBCOMPONENT_VALUE,
    USER_ROLE_HASH, USER_ROLE_MEDIA,
    NOT_A_SUBCOMPONENT, MEDIA_SUBCOMPONENT, VIEW_SUBCOMPONENT,
    LAYER_SUBCOMPONENT, CHANNEL_SUBCOMPONENT,
    INT_MAX, block_signals
)

# =============================================================================
# Constants (aliases for backward compatibility)
# =============================================================================

NotASubComponent = NOT_A_SUBCOMPONENT
MediaSubComponent = MEDIA_SUBCOMPONENT
ViewSubComponent = VIEW_SUBCOMPONENT
LayerSubComponent = LAYER_SUBCOMPONENT
ChannelSubComponent = CHANNEL_SUBCOMPONENT


# =============================================================================
# Module-level helper functions
# =============================================================================

def itemNode(item):
    """Get the node name from a QStandardItem."""
    if item is None:
        return ""
    d = item.data(USER_ROLE_NODE)
    if d is None:
        return ""
    return str(d) if d else ""


def itemSubComponentTypeForName(n):
    """Convert sub-component name to type constant."""
    if n == "view":
        return ViewSubComponent
    elif n == "layer":
        return LayerSubComponent
    elif n == "channel":
        return ChannelSubComponent
    return NotASubComponent


def componentMatch(n, c):
    """Check if sub-component name matches type."""
    return itemSubComponentTypeForName(n) == c


def itemSubComponentStringData(item, role):
    """Get string data from item at specific user role."""
    if item is None:
        return ""
    d = item.data(role)
    if d is None:
        return ""
    return str(d) if d else ""


def itemSubComponentMedia(item):
    return itemSubComponentStringData(item, USER_ROLE_MEDIA)


def itemSubComponentHash(item):
    return itemSubComponentStringData(item, USER_ROLE_HASH)


def itemSubComponentValue(item):
    return itemSubComponentStringData(item, USER_ROLE_SUBCOMPONENT_VALUE)


def itemParentNode(item):
    return itemSubComponentStringData(item, USER_ROLE_PARENT_NODE)


def itemSubComponentType(item):
    """Get the sub-component type from item."""
    if item is None:
        return NotASubComponent
    d = item.data(USER_ROLE_SUBCOMPONENT_TYPE)
    if d is None:
        return NotASubComponent
    try:
        return int(d)
    except (TypeError, ValueError):
        return NotASubComponent


def itemIsSubComponent(item):
    """Check if item represents a sub-component."""
    if item is None:
        return False
    d = item.data(USER_ROLE_SUBCOMPONENT_TYPE)
    if d is None:
        return False
    try:
        return int(d) != 0
    except (TypeError, ValueError):
        return False


def includes(array, item):
    """Check if QModelIndex array contains item with same row."""
    for a in array:
        if a.row() == item.row():
            return True
    return False


def contains(array, value):
    """Check if array contains value."""
    return value in array


def indexOf(array, value):
    """Find index of value in array, -1 if not found."""
    try:
        return array.index(value)
    except ValueError:
        return -1


def remove(array, value):
    """Remove value from array and return new array."""
    return [a for a in array if a != value]


def getattr_or_key(obj, name):
    """Access attribute by name, handling both objects and dicts."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def sourceNodeOfGroup(group):
    """Find the source node within a group."""
    try:
        for node in commands.nodesInGroup(group):
            t = commands.nodeType(node)
            if t == "RVFileSource" or t == "RVImageSource":
                return node
    except Exception:
        pass
    return None


def hashedSubComponent(media, view=None, layer=None):
    """Create a hash string for a sub-component."""
    v = "@." if view is not None and view == "" else view
    l = "@." if layer is not None and layer == "" else layer

    if v is None and l is None:
        return "%s!~!~" % media
    elif v is None:
        return "%s!~%s!~" % (media, l)
    elif l is None:
        return "%s!~!~%s" % (media, v)
    else:
        return "%s!~%s!~%s" % (media, l, v)


def hashedSubComponentFromItem(item):
    """Create a hash string from item data."""
    value = itemSubComponentValue(item)
    subType = itemSubComponentType(item)
    parent = item.parent()
    pvalue = itemSubComponentValue(parent) if parent else ""

    if subType == MediaSubComponent:
        return hashedSubComponent(value, None, None)
    elif subType == LayerSubComponent:
        grandParent = parent.parent() if parent else None
        psubType = itemSubComponentType(parent) if parent else NotASubComponent
        if psubType == ViewSubComponent:
            arg0 = itemSubComponentValue(grandParent) if grandParent else ""
            arg1 = pvalue
        else:
            arg0 = pvalue
            arg1 = None
        return hashedSubComponent(arg0, arg1, value)
    elif subType == ViewSubComponent:
        return hashedSubComponent(pvalue, value, None)

    return ""


def isSubComponentExpanded(node, item):
    """Check if sub-component is expanded in tree."""
    propName = "%s.sm_state.expandedSubState" % node
    key = hashedSubComponentFromItem(item)

    if commands.propertyExists(propName):
        try:
            p = commands.getStringProperty(propName)
            return key in p
        except Exception:
            pass
    return False


def setSubComponentExpanded(node, item, expanded):
    """Set sub-component expanded state."""
    propName = "%s.sm_state.expandedSubState" % node
    key = hashedSubComponentFromItem(item)

    try:
        if commands.propertyExists(propName):
            p = list(commands.getStringProperty(propName))
            hasit = key in p

            if hasit and not expanded:
                commands.setStringProperty(propName, remove(p, key), True)
            elif not hasit and expanded:
                p.append(key)
                commands.setStringProperty(propName, p, True)
        else:
            commands.setStringProperty(propName, [key], True)
    except Exception:
        pass


def isExpandedInParent(node, parent):
    """Check if node is expanded under parent."""
    propName = "%s.sm_state.expandState" % node

    if commands.propertyExists(propName):
        try:
            p = commands.getStringProperty(propName)
            return parent in p
        except Exception:
            pass
    return False


def setExpandedInParent(node, parent, expanded):
    """Set node expanded state under parent."""
    propName = "%s.sm_state.expandState" % node

    try:
        if commands.propertyExists(propName):
            p = list(commands.getStringProperty(propName))
            hasNode = parent in p

            if hasNode and not expanded:
                commands.setStringProperty(propName, remove(p, parent), True)
            elif not hasNode and expanded:
                p.append(parent)
                commands.setStringProperty(propName, p, True)
        else:
            commands.setStringProperty(propName, [parent], True)
    except Exception:
        pass


def setToolTipProp(node, toolTip):
    """Set tooltip property on node."""
    propName = "%s.sm_state.toolTip" % node
    commands.setStringProperty(propName, [toolTip], True)


def toolTipFromProp(node):
    """Get tooltip from node property."""
    propName = "%s.sm_state.toolTip" % node

    if commands.propertyExists(propName):
        try:
            return commands.getStringProperty(propName)[0]
        except Exception:
            pass
    return None


def sortKeyInParent(node, parent):
    """Get sort key for node under parent."""
    propNameParent = "%s.sm_state.sortKeyParent" % node
    propNameKey = "%s.sm_state.sortKey" % node
    undefinedKey = 2147483547  # int.max - 100

    if commands.propertyExists(propNameParent) and commands.propertyExists(propNameKey):
        try:
            p = commands.getStringProperty(propNameParent)
            keys = commands.getIntProperty(propNameKey)
            i = indexOf(list(p), parent)

            if i == -1 or len(keys) != len(p):
                return undefinedKey
            return keys[i]
        except Exception:
            pass

    return undefinedKey


def setSortKeyInParent(node, parent, value):
    """Set sort key for node under parent."""
    propNameParent = "%s.sm_state.sortKeyParent" % node
    propNameKey = "%s.sm_state.sortKey" % node

    try:
        if commands.propertyExists(propNameParent) and commands.propertyExists(propNameKey):
            p = list(commands.getStringProperty(propNameParent))
            keys = list(commands.getIntProperty(propNameKey))
            i = indexOf(p, parent)

            if len(p) == len(keys):
                if i == -1:
                    p.append(parent)
                    keys.append(value)
                    commands.setStringProperty(propNameParent, p, True)
                    commands.setIntProperty(propNameKey, keys, True)
                else:
                    keys[i] = value
                    commands.setIntProperty(propNameKey, keys, True)
                return

        commands.setStringProperty(propNameParent, [parent], True)
        commands.setIntProperty(propNameKey, [value], True)
    except Exception:
        pass


def indexOfItem(array, item):
    """Find index of item in array."""
    for i, v in enumerate(array):
        if v == item:
            return i
    return -1


def nodeFromIndex(index, model):
    """Get node name from model index."""
    item = model.itemFromIndex(index)
    return itemNode(item)


def nodeInputs(node):
    """Get input nodes of a node."""
    try:
        return commands.nodeConnections(node, False)[0]
    except Exception:
        return []


def addRow(item, children):
    """Add a row of items as children."""
    row = item.rowCount()
    for count, child in enumerate(children):
        item.setChild(row, count, child)


def setInputs(node, inputs):
    """Set node inputs with validation."""
    try:
        msg = commands.testNodeInputs(node, inputs)

        if msg is not None:
            extra_commands.alertPanel(
                False,
                commands.ErrorAlert,
                "Some inputs are not allowed here",
                msg,
                "Ok", None, None
            )
        else:
            commands.setNodeInputs(node, inputs)

        return msg is None
    except Exception:
        return False


def removeInput(node, inputNode):
    """Remove an input from node."""
    if node != "":
        try:
            ins = commands.nodeConnections(node)[0]
            newInputs = [n for n in ins if n != inputNode]
            return setInputs(node, newInputs)
        except Exception:
            pass
    return True


def hasInput(node, inputNode):
    """Check if node has input."""
    if node is None or node == "":
        return True
    try:
        ins = commands.nodeConnections(node)[0]
        return inputNode in ins
    except Exception:
        return False


def addInput(node, inputNode):
    """Add an input to node."""
    if commands.nodeExists(node):
        try:
            ins = list(commands.nodeConnections(node)[0])
            ins.append(inputNode)
            return setInputs(node, ins)
        except Exception:
            pass
    return True


def mapModel(model, F, root=None):
    """Map function over model items, returning matching items."""
    def mapOverItem(item, model, F, result_list):
        for i in range(item.rowCount()):
            child = item.child(i, 0)
            if child:
                result_list = mapOverItem(child, model, F, result_list)

        if itemNode(item) != "" and F(item):
            result_list.append(item)
        return result_list

    result_list = []

    if root is None:
        for i in range(model.rowCount(QModelIndex())):
            item = model.item(i, 0)
            if item:
                result_list = mapOverItem(item, model, F, result_list)
    else:
        result_list = mapOverItem(root, model, F, result_list)

    return result_list


def itemOfNode(model, node):
    """Find item for node in model."""
    items = mapModel(model, lambda i: itemNode(i) == node and not itemIsSubComponent(i))
    return items[0] if items else None


def subComponentItemsOfNode(model, node):
    """Find sub-component items for node."""
    def check(i):
        subType = itemSubComponentType(i)
        return (itemNode(i) == node and
                subType != NotASubComponent and
                subType != MediaSubComponent and
                i.index().column() == 0)
    return mapModel(model, check)


def assignSortOrder(root):
    """Assign sort order to children of root."""
    if root is not None:
        try:
            rootNode = itemNode(root)
            index = 0
            for i in range(root.rowCount()):
                item = root.child(i, 0)
                if item is not None:
                    node = itemNode(item)
                    setSortKeyInParent(node, rootNode, index)
                    index += 1
        except Exception:
            pass


def resizeColumns(treeView, model):
    """Resize all columns to contents."""
    for i in range(model.columnCount(QModelIndex())):
        treeView.resizeColumnToContents(i)


def isImageRequestPropEqual(name, array):
    """Check if image request property equals array."""
    pname = "#RVSource.request." + name
    try:
        current = commands.getStringProperty(pname)
        return list(current) == list(array)
    except Exception:
        return False


def setImageRequestProp(name, array):
    """Set image request property."""
    pname = "#RVSource.request." + name
    try:
        current = commands.getStringProperty(pname)
        if list(current) != list(array):
            commands.setStringProperty(pname, array, True)
            commands.reload()
    except Exception:
        pass


def setImageRequest(value, toggle=True):
    """Set image component request."""
    pname = "imageComponent"

    if toggle and isImageRequestPropEqual(pname, value):
        setImageRequestProp(pname, [])
    else:
        setImageRequestProp(pname, value)


def subComponentPropValue(item):
    """Get property value for sub-component."""
    t = itemSubComponentType(item)
    result = []

    if t == MediaSubComponent:
        pass
    elif t == ViewSubComponent:
        result = ["view", itemSubComponentValue(item)]
    elif t == LayerSubComponent:
        parent = item.parent()
        view_val = ""
        if parent and itemSubComponentType(parent) == ViewSubComponent:
            view_val = itemSubComponentValue(parent)
        result = ["layer", view_val, itemSubComponentValue(item)]
    elif t == ChannelSubComponent:
        parent = item.parent()
        pvalue = subComponentPropValue(parent) if parent else []
        s = len(pvalue)
        value = itemSubComponentValue(item)

        if s == 0:
            result = ["channel", "", "", value]
        elif s == 2:
            result = ["channel", pvalue[1], "", value]
        elif s == 3:
            result = ["channel", pvalue[1], pvalue[2], value]

    return result


def setNodeRequest(node, value):
    """Set node image component request."""
    commands.setStringProperty(node + ".request.imageComponent", value, True)


# =============================================================================
# NodeModel - QStandardItemModel with custom mime types for drag/drop
# =============================================================================

class NodeModel(QStandardItemModel):
    """QStandardItemModel with modified drag and drop mime types."""

    def __init__(self, parent=None):
        super(NodeModel, self).__init__(parent)

    def mimeTypes(self):
        """Return supported mime types."""
        types = list(super(NodeModel, self).mimeTypes())
        types.append("text/uri-list")
        types.append("text/plain")
        return types

    def mimeData(self, indices):
        """Create mime data for indices."""
        d = super(NodeModel, self).mimeData(indices)
        urls = []
        text_parts = []

        try:
            for index in indices:
                n = nodeFromIndex(index, self)
                ntype = commands.nodeType(n)
                rvid = "%s@%s:%s" % (
                    commands.remoteLocalContactName(),
                    commands.myNetworkHost(),
                    commands.myNetworkPort()
                )

                if ntype == "RVSourceGroup":
                    try:
                        media = commands.getStringProperty("%s_source.media.movie" % n)
                        text_parts.append("RVFileSource %s.media.movie = %s" % (n, media))
                        for m in media:
                            urls.append(QUrl("rvnode://%s/%s/%s/%s" % (rvid, ntype, n, m)))
                    except Exception:
                        pass
                else:
                    text_parts.append("%s %s" % (ntype, n))
                    urls.append(QUrl("rvnode://%s/%s/%s" % (rvid, ntype, n)))

            d.setText("\n".join(text_parts))
            d.setUrls(urls)
        except Exception:
            pass

        return d


# =============================================================================
# NodeTreeView - QTreeView with custom drag/drop behavior
# =============================================================================

class NodeTreeView(QTreeView):
    """QTreeView with constrained drag/drop behavior for session manager."""

    def __init__(self, parent=None):
        super(NodeTreeView, self).__init__(parent)
        self._dropAction = Qt.IgnoreAction
        self._draggedNodePaths = []
        self._draggingNonFolders = False
        self._viewModel = None
        self._sortFolders = []
        self._sortTimer = QTimer(self)
        self._sortTimer.setSingleShot(True)
        self._sortTimer.timeout.connect(self._doSortFolders)
        self._foldersItem = None

    def sortFolderChildren(self, folder):
        """Queue folder for sorting."""
        try:
            if commands.nodeType(folder) == "RVFolderGroup":
                if folder not in self._sortFolders:
                    self._sortFolders.append(folder)
                self._sortTimer.start(0)
        except Exception:
            pass

    def _doSortFolders(self):
        """Sort queued folders."""
        for folder in self._sortFolders:
            try:
                item = itemOfNode(self._viewModel, folder)
                if item:
                    assignSortOrder(item)
            except Exception:
                pass
        self._sortFolders = []

    def selectedNodePaths(self):
        """Get paths for selected nodes."""
        indices = self.selectionModel().selectedIndexes()
        paths = []

        for index in indices:
            if index.column() == 0:
                path = []
                current = index
                while current.isValid():
                    item = self._viewModel.itemFromIndex(current)
                    node = itemNode(item)
                    path.append(node)
                    current = current.parent()
                paths.append(path)

        return paths

    def filteredDraggedPaths(self, F):
        """Filter dragged paths by predicate."""
        return [path for path in self._draggedNodePaths if F(path)]

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        sourceWidget = event.source()

        if sourceWidget == self:
            self._draggedNodePaths = self.selectedNodePaths()
            self._draggingNonFolders = False

            for path in self._draggedNodePaths:
                if path and commands.nodeExists(path[0]):
                    if commands.nodeType(path[0]) != "RVFolderGroup":
                        self._draggingNonFolders = True
                        break

            if self._foldersItem:
                if self._draggingNonFolders:
                    self._foldersItem.setFlags(Qt.ItemIsEnabled)
                else:
                    self._foldersItem.setFlags(Qt.ItemIsDropEnabled | Qt.ItemIsEnabled)

            super(NodeTreeView, self).dragEnterEvent(event)
        elif sourceWidget:
            pass  # Allow to be rejected
        else:
            mimeData = event.mimeData()
            if mimeData.hasUrls():
                pass

    def dragMoveEvent(self, event):
        """Handle drag move event."""
        super(NodeTreeView, self).dragMoveEvent(event)

    def dropEvent(self, event):
        """Handle drop event."""
        self._dropAction = event.dropAction()
        super(NodeTreeView, self).dropEvent(event)
        self._dropAction = Qt.IgnoreAction


# =============================================================================
# InputsView - QListView for node inputs
# =============================================================================

class InputsView(QListView):
    """QListView for displaying and managing node inputs."""

    def __init__(self, treeView, parent=None, updateCallback=None):
        super(InputsView, self).__init__(parent)
        self._treeView = treeView
        self._updateCallback = updateCallback

    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        sourceWidget = event.source()
        if sourceWidget == self._treeView or sourceWidget == self:
            super(InputsView, self).dragEnterEvent(event)

    def dropEvent(self, event):
        """Handle drop event."""
        # When dropping from the tree view, always use CopyAction to prevent
        # removing the source item from the tree. The inputs panel should
        # add items as inputs without affecting the source tree.
        sourceWidget = event.source()
        if sourceWidget == self._treeView:
            event.setDropAction(Qt.CopyAction)
        super(InputsView, self).dropEvent(event)


# =============================================================================
# SessionManagerMode - Main mode class
# =============================================================================

class SessionManagerMode(rvtypes.MinorMode):
    """Session Manager mode providing a dock widget for session management."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)

        # Initialize all member variables
        self._mainWindow = None
        self._dockWidget = None
        self._baseWidget = None
        self._splitter = None
        self._treeViewBase = None
        self._viewTreeView = None
        self._viewModel = None
        self._inputsModel = None
        self._addButton = None
        self._folderButton = None
        self._deleteButton = None
        self._configButton = None
        self._editViewInfoButton = None
        self._homeButton = None
        self._inputsViewBase = None
        self._inputsView = None
        self._tabWidget = None
        self._orderUpButton = None
        self._orderDownButton = None
        self._sortAscButton = None
        self._sortDescButton = None
        self._inputsDeleteButton = None
        self._uiTreeWidget = None
        self._editors = []
        self._typeIcons = []
        self._unknownTypeIcon = None
        self._viewIcon = None
        self._layerIcon = None
        self._channelIcon = None
        self._videoIcon = None
        self._editorDotIcon = None
        self._editorDotIconSelected = None
        self._selectionOnIcon = None
        self._selectionOffIcon = None
        self._inputOrderLock = False
        self._disableUpdates = False
        self._progressiveLoadingInProgress = False
        self._lazySetInputsTimer = None
        self._lazyUpdateTimer = None
        self._mainWinVisTimer = None
        self._css = None
        self._darkUI = True
        self._createImageDialog = None
        self._colorDialog = None
        self._viewContextMenu = None
        self._viewContextMenuActions = []
        self._createMenu = None
        self._folderMenu = None
        self._newNodeDialog = None
        self._nodeTypeCombo = None
        self._prevViewButton = None
        self._nextViewButton = None
        self._viewLabel = None
        self._selectedSubComp = None
        self._cidWidth = None
        self._cidHeight = None
        self._cidFPS = None
        self._cidLength = None
        self._cidPic = None
        self._cidGroupBox = None
        self._cidName = ""
        self._cidFMTSpec = ""
        self._cidColorButton = None
        self._cidColorLabel = None
        self._cidColor = None
        self._quitting = False
        self._uiCreated = False  # Track whether UI has been created

        self._progressiveLoadingInProgress = (commands.loadTotal() != 0)

        self.init(
            "session_manager",
            [
                ("new-node", self.updateTreeEvent, "New user node"),
                ("source-modified", self.updateTreeEvent, "New source media"),
                ("source-group-complete", self.updateTreeEvent, "Source group complete"),
                ("before-progressive-loading", self.beforeProgressiveLoading, "before loading"),
                ("after-progressive-loading", self.afterProgressiveLoading, "after loading"),
                ("after-node-delete", self.updateTreeEvent, "Node deleted"),
                ("after-clear-session", self.updateTreeEvent, "Session Cleared"),
                ("after-graph-view-change", self.afterGraphViewChange, "Update session UI"),
                ("before-graph-view-change", self.beforeGraphViewChange, "Update session UI"),
                ("graph-node-inputs-changed", self.nodeInputsChanged, "Update session UI"),
                ("graph-state-change", self.propertyChanged, "Maybe update session UI"),
                ("key-down--@", self.showRows, "show'em"),
                ("before-session-deletion", self.enterQuittingState, "Store quitting"),
                ("view-edit-mode-activated", self.viewEditModeActivated, "Per-view edit mode"),
                ("internal-sync-presenter-changed", self.onPresenterChanged, "Live Review presenter changed"),
            ],
            None,
            None
        )

        # Register with global state for edit modes to access
        state = commands.data()
        state.sessionManager = self

    def auxFilePath(self, filename):
        """Get path to auxiliary file in package support directory."""
        # supportPath expects a module object, not a string
        import sys
        module = sys.modules[__name__]
        return os.path.join(
            self.supportPath(module, "session_manager"),
            filename
        )

    def colorAdjustedIcon(self, rpath, invertSense):
        """Get color-adjusted icon based on UI theme."""
        icon0_path = re.sub("48x48", "out", rpath)
        swap = invertSense != self._darkUI

        if swap:
            qimage = QImage(icon0_path)
        else:
            qimage = QImage(rpath)

        return QIcon(QPixmap.fromImage(qimage))

    def auxIcon(self, name, colorAdjust=False):
        """Get icon from auxiliary files."""
        if colorAdjust:
            return self.colorAdjustedIcon(":images/" + name, False)
        return QIcon(":images/" + name)

    def _setupUI(self):
        """Set up the session manager UI."""
        self._mainWindow = qtutils.sessionWindow()  # Keep reference to prevent GC
        m = self._mainWindow

        self._dockWidget = QDockWidget("Session Manager", m)

        # Load the UI file
        loader = QUiLoader()
        uipath = self.auxFilePath("session_manager.ui")
        uifile = QFile(uipath)
        if uifile.open(QFile.ReadOnly):
            self._baseWidget = loader.load(uifile, m)
            uifile.close()
        else:
            return

        # Find child widgets
        self._treeViewBase = self._baseWidget.findChild(QWidget, "treeView")
        self._addButton = self._baseWidget.findChild(QToolButton, "addButton")
        self._folderButton = self._baseWidget.findChild(QToolButton, "folderButton")
        
        # Clear custom RV properties that override our menu behavior
        # The tbstyle property triggers RV's built-in menu system
        if self._addButton:
            self._addButton.setProperty("tbstyle", "")
        if self._folderButton:
            self._folderButton.setProperty("tbstyle", "")
        self._deleteButton = self._baseWidget.findChild(QToolButton, "deleteButton")
        self._configButton = self._baseWidget.findChild(QToolButton, "configButton")
        self._editViewInfoButton = self._baseWidget.findChild(QToolButton, "renameButton")
        self._homeButton = self._baseWidget.findChild(QToolButton, "selectCurrentButton")
        self._inputsViewBase = self._baseWidget.findChild(QWidget, "inputsListView")
        self._tabWidget = self._baseWidget.findChild(QTabWidget, "tabWidget")
        self._orderUpButton = self._baseWidget.findChild(QToolButton, "orderUpButton")
        self._orderDownButton = self._baseWidget.findChild(QToolButton, "orderDownButton")
        self._sortAscButton = self._baseWidget.findChild(QToolButton, "sortAscButton")
        self._sortDescButton = self._baseWidget.findChild(QToolButton, "sortDescButton")
        self._inputsDeleteButton = self._baseWidget.findChild(QToolButton, "inputsDeleteButton")
        self._uiTreeWidget = self._baseWidget.findChild(QTreeWidget, "uiTreeWidget")
        
        # Keep explicit references to prevent garbage collection of critical widgets
        self._widgetRefs = [
            self._baseWidget,
            self._uiTreeWidget,
            self._treeViewBase,
            self._splitter,
        ]
        self._splitter = self._baseWidget.findChild(QSplitter, "splitter")
        self._viewLabel = self._baseWidget.findChild(QLabel, "viewLabel")
        self._prevViewButton = self._baseWidget.findChild(QToolButton, "prevViewButton")
        self._nextViewButton = self._baseWidget.findChild(QToolButton, "nextViewButton")

        # Create timers
        self._lazySetInputsTimer = QTimer(self._dockWidget)
        self._lazyUpdateTimer = QTimer(self._dockWidget)
        self._mainWinVisTimer = QTimer(self._dockWidget)

        self._lazySetInputsTimer.setSingleShot(True)
        self._lazyUpdateTimer.setSingleShot(True)
        self._mainWinVisTimer.setSingleShot(True)

        # Create tree view
        if self._treeViewBase:
            vbox = QVBoxLayout(self._treeViewBase)
            vbox.setContentsMargins(0, 0, 0, 0)
            self._viewTreeView = NodeTreeView(self._treeViewBase)
            vbox.addWidget(self._viewTreeView)

        # Create inputs view
        if self._inputsViewBase:
            ivbox = QVBoxLayout(self._inputsViewBase)
            ivbox.setContentsMargins(0, 0, 0, 0)
            self._inputsView = InputsView(self._viewTreeView, self._inputsViewBase, self.updateTree)
            ivbox.addWidget(self._inputsView)
            self._inputsView.setObjectName("inputsViewList")

        # Set up dock widget
        self._dockWidget.setWidget(self._baseWidget)
        navPanel = self._baseWidget.findChild(QWidget, "navPanel")
        if navPanel:
            self._dockWidget.setTitleBarWidget(navPanel)
        self._dockWidget.setObjectName("session_manager")
        # Create models
        self._viewModel = NodeModel(m)
        self._inputsModel = QStandardItemModel(m)

        if self._viewTreeView:
            self._viewTreeView._viewModel = self._viewModel

        self._viewModel.setHorizontalHeaderLabels(["Name", "*", "*"])

        if self._viewTreeView:
            self._viewTreeView.header().setMinimumSectionSize(-1)
            self._viewTreeView.setModel(self._viewModel)
            self._viewTreeView.setDragEnabled(True)
            self._viewTreeView.setAcceptDrops(True)
            self._viewTreeView.setDropIndicatorShown(True)
            self._viewTreeView.setHeaderHidden(False)
            self._viewTreeView.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self._viewTreeView.setEditTriggers(QAbstractItemView.EditKeyPressed)
            self._viewTreeView.setContextMenuPolicy(Qt.CustomContextMenu)
            self._viewTreeView.setDragDropMode(QAbstractItemView.DragDrop)
            self._viewTreeView.setDefaultDropAction(Qt.MoveAction)
            self._viewTreeView.setExpandsOnDoubleClick(False)

        if self._inputsView:
            self._inputsView.setModel(self._inputsModel)
            self._inputsView.setDragEnabled(True)
            self._inputsView.setAcceptDrops(True)
            self._inputsView.setSelectionMode(QAbstractItemView.ExtendedSelection)
            self._inputsView.setSelectionBehavior(QAbstractItemView.SelectRows)
            self._inputsView.setDefaultDropAction(Qt.MoveAction)
            self._inputsView.setDropIndicatorShown(True)
            self._inputsView.setDragDropMode(QAbstractItemView.DragDrop)
            self._inputsView.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Add dock widget to main window
        m.addDockWidget(Qt.LeftDockWidgetArea, self._dockWidget)

        # Create actions and icons
        self._setupActions()
        self._setupIcons()
        self._setupMenus()
        self._connectSignals()

        # Mark UI as created BEFORE updateTree so the check passes
        self._uiCreated = True
        
        # Initial tree update
        self.updateTree()

        self._dockWidget.show()
        m.show()

        self.updateNavUI()

    def _setupActions(self):
        """Set up toolbar actions."""
        if self._addButton:
            addAction = QAction(self.auxIcon("add_48x48.png", True), "Create View", self._addButton)
            self._addButton.setDefaultAction(addAction)
            self._addButton.setPopupMode(QToolButton.InstantPopup)

        if self._folderButton:
            folderAction = QAction(self.auxIcon("foldr_48x48.png", True), "Create Folder", self._folderButton)
            self._folderButton.setDefaultAction(folderAction)

        if self._deleteButton:
            deleteAction = QAction(self.auxIcon("trash_48x48.png", True), "Delete View", self._deleteButton)
            self._deleteButton.setDefaultAction(deleteAction)
            deleteAction.triggered.connect(self.deleteViewableSlot)

        if self._configButton:
            configAction = QAction(self.auxIcon("confg_48x48.png", True), "Configure", self._configButton)
            self._configButton.setDefaultAction(configAction)
            self._configButton.setPopupMode(QToolButton.InstantPopup)

        if self._editViewInfoButton:
            editInfoAction = QAction(self.auxIcon("sinfo_48x48.png", True), "Edit View Info", self._editViewInfoButton)
            self._editViewInfoButton.setDefaultAction(editInfoAction)
            editInfoAction.triggered.connect(self.editViewInfoSlot)

        if self._homeButton:
            homeAction = QAction(self.auxIcon("home_48x48.png", True), "Select Current View", self._homeButton)
            self._homeButton.setDefaultAction(homeAction)
            homeAction.triggered.connect(self.selectCurrentViewSlot)

        if self._orderUpButton:
            orderUpAction = QAction(self.auxIcon("up_48x48.png", True), "Move Input Higher", self._orderUpButton)
            self._orderUpButton.setDefaultAction(orderUpAction)
            orderUpAction.triggered.connect(lambda checked: self.reorderSelected(True))

        if self._orderDownButton:
            orderDownAction = QAction(self.auxIcon("down_48x48.png", True), "Move Input Lower", self._orderDownButton)
            self._orderDownButton.setDefaultAction(orderDownAction)
            orderDownAction.triggered.connect(lambda checked: self.reorderSelected(False))

        if self._sortAscButton:
            self._sortAscButton.setText("A-Z")
            self._sortAscButton.setToolTip("Sort A to Z")
            self._sortAscButton.clicked.connect(lambda checked: self.sortInputs(True))

        if self._sortDescButton:
            self._sortDescButton.setText("Z-A")
            self._sortDescButton.setToolTip("Sort Z to A")
            self._sortDescButton.clicked.connect(lambda checked: self.sortInputs(False))

        if self._inputsDeleteButton:
            inputsDeleteAction = QAction(self.auxIcon("trash_48x48.png", True), "Delete Input", self._inputsDeleteButton)
            self._inputsDeleteButton.setDefaultAction(inputsDeleteAction)
            inputsDeleteAction.triggered.connect(self.inputsDeleteSlot)

        if self._prevViewButton:
            prevViewAction = QAction(self.auxIcon("back_48x48.png", True), "Previous View", self._prevViewButton)
            self._prevViewButton.setDefaultAction(prevViewAction)
            prevViewAction.triggered.connect(lambda checked: self.navButtonClicked("prev"))

        if self._nextViewButton:
            nextViewAction = QAction(self.auxIcon("forwd_48x48.png", True), "Next View", self._nextViewButton)
            self._nextViewButton.setDefaultAction(nextViewAction)
            nextViewAction.triggered.connect(lambda checked: self.navButtonClicked("next"))

    def _createCircleIcon(self, color, size=12):
        """Create a circle icon with the given color."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, size - 2, size - 2)
        painter.end()
        return QIcon(pixmap)

    def _setupIcons(self):
        """Set up node type icons."""
        self._typeIcons = []

        # Create circle icons for editor section markers (white/light grey)
        self._editorDotIcon = self._createCircleIcon(QColor(200, 200, 200))  # Light grey
        self._editorDotIconSelected = self._createCircleIcon(QColor(100, 149, 237))  # Cornflower blue for selected

        # Create selection indicator icons for tree (darker versions)
        self._selectionOnIcon = self._createCircleIcon(QColor(100, 149, 237))  # Blue for selected
        self._selectionOffIcon = self._createCircleIcon(QColor(80, 80, 80))  # Dark grey for unselected

        iconMappings = [
            ("RVSourceGroup", "videofile_48x48.png"),
            ("RVImageSource", "videofile_48x48.png"),
            ("RVSwitchGroup", "shuffle_48x48.png"),
            ("RVRetimeGroup", "tempo_48x48.png"),
            ("RVLayoutGroup", "lgicn_48x48.png"),
            ("RVStackGroup", "photoalbum_48x48.png"),
            ("RVSequenceGroup", "playlist_48x48.png"),
            ("RVFolderGroup", "foldr_48x48.png"),
            ("RVFileSource", "videofile_48x48.png"),
        ]

        for typeName, iconName in iconMappings:
            self._typeIcons.append((typeName, self.auxIcon(iconName, True)))

        self._viewIcon = self.auxIcon("view.png", True)
        self._videoIcon = self.auxIcon("video_48x48.png", True)
        self._channelIcon = self.auxIcon("channel.png", True)
        self._layerIcon = self.auxIcon("layer.png", True)
        self._unknownTypeIcon = self.auxIcon("new_48x48.png", True)

    def _setupMenus(self):
        """Set up menus."""
        # Create menu - matching original Mu package exactly
        self._createMenu = QMenu("New Viewable", self._addButton)

        # Menu items with icons - matching original Mu package order and naming
        # Format: (icon_file, name, protocol)
        menuActions = [
            ("playlist_48x48.png", "Sequence", "RVSequenceGroup"),
            ("photoalbum_48x48.png", "Stack", "RVStackGroup"),
            ("shuffle_48x48.png", "Switch", "RVSwitchGroup"),
            ("foldr_48x48.png", "Folder", "RVFolderGroup"),
            ("lgicn_48x48.png", "Layout", "RVLayoutGroup"),
            ("tempo_48x48.png", "Retime", "RVRetimeGroup"),
            ("new_48x48.png", "Color", "RVColor"),
            ("new_48x48.png", "OCIO", "RVOCIO"),
            ("new_48x48.png", "New Node by Type...", ""),
            ("_", "_", ""),  # Separator
            ("colorchart_48x48.png", "SRGB Color Chart...", "srgbcolorchart,%s.movieproc"),
            ("colorchart_48x48.png", "ACES Color Chart...", "acescolorchart,%s.movieproc"),
            ("ntscbars_48x48.png", "Color Bars...", "smptebars,%s.movieproc"),
            ("video_48x48.png", "Black...", "black,%s.movieproc"),
            ("video_48x48.png", "Color...", "solid,%s.movieproc"),
            ("video_48x48.png", "Blank...", "blank,%s.movieproc"),
        ]

        for iconFile, name, protocol in menuActions:
            if name == "_":
                self._createMenu.addSeparator()
            else:
                icon = self.auxIcon(iconFile, True) if iconFile else None
                if icon:
                    action = self._createMenu.addAction(icon, name)
                else:
                    action = self._createMenu.addAction(name)
                action.triggered.connect(lambda checked=False, p=protocol: self.addThingSlot(p))

        if self._addButton:
            # Clear any existing menu first
            self._addButton.setMenu(None)
            self._addButton.setMenu(self._createMenu)
            self._addButton.setPopupMode(QToolButton.InstantPopup)

        # Folder menu
        self._folderMenu = QMenu("Folder", self._folderButton)

        newFolderAction = self._folderMenu.addAction("Empty Folder")
        newFolderAction.triggered.connect(lambda checked=False: self.newFolderSlot(1))

        newFolder2Action = self._folderMenu.addAction("From Selection")
        newFolder2Action.triggered.connect(lambda checked=False: self.newFolderSlot(2))

        newFolder3Action = self._folderMenu.addAction("From Copy of Selection")
        newFolder3Action.triggered.connect(lambda checked=False: self.newFolderSlot(3))

        if self._folderButton:
            self._folderButton.setMenu(self._folderMenu)
            self._folderButton.setArrowType(Qt.NoArrow)
            self._folderButton.setPopupMode(QToolButton.InstantPopup)

        # Config menu
        if self._configButton:
            configMenu = QMenu("Config", self._configButton)
            configAlwaysOn = configMenu.addAction("Always Show at Start Up")
            configNeverOn = configMenu.addAction("Never Show at Start Up")
            configLastOn = configMenu.addAction("Restore Last State at Start Up")

            configGroup = QActionGroup(self._configButton)
            for a in [configAlwaysOn, configNeverOn, configLastOn]:
                a.setCheckable(True)
                configGroup.addAction(a)

            self._configButton.setMenu(configMenu)

            # Set initial state from settings
            try:
                configState = str(commands.readSettings("SessionManager", "showOnStartup", "no"))
                if configState == "yes":
                    configAlwaysOn.setChecked(True)
                elif configState == "last":
                    configLastOn.setChecked(True)
                else:
                    configNeverOn.setChecked(True)
            except Exception:
                configNeverOn.setChecked(True)

            configAlwaysOn.triggered.connect(lambda checked: self.configSlot("yes", True))
            configNeverOn.triggered.connect(lambda checked: self.configSlot("no", False))
            configLastOn.triggered.connect(lambda checked: self.configSlot("last", True))

    def _connectSignals(self):
        """Connect Qt signals to slots."""
        if self._tabWidget:
            self._tabWidget.currentChanged.connect(self.tabChangeSlot)

        if self._inputsModel:
            self._inputsModel.rowsRemoved.connect(self.inputRowsRemovedSlot)
            self._inputsModel.rowsInserted.connect(self.inputRowsInsertedSlot)

        if self._lazySetInputsTimer:
            self._lazySetInputsTimer.timeout.connect(self.rebuildInputsFromList)

        if self._lazyUpdateTimer:
            self._lazyUpdateTimer.timeout.connect(self.updateTree)

        if self._mainWinVisTimer:
            self._mainWinVisTimer.timeout.connect(self.mainWinVisTimeout)

        if self._splitter:
            self._splitter.splitterMoved.connect(self.splitterMoved)

        if self._viewModel:
            self._viewModel.itemChanged.connect(self.viewItemChanged)

        if self._viewTreeView:
            self._viewTreeView.expanded.connect(lambda idx: self.setItemExpandedState(idx, 1))
            self._viewTreeView.collapsed.connect(lambda idx: self.setItemExpandedState(idx, 0))
            self._viewTreeView.customContextMenuRequested.connect(self.viewContextMenuSlot)
            self._viewTreeView.doubleClicked.connect(lambda idx: self.viewByIndex(idx, self._viewModel))
            self._viewTreeView.pressed.connect(lambda idx: self.itemPressed(idx, self._viewModel))

        if self._inputsView:
            self._inputsView.doubleClicked.connect(lambda idx: self.viewByIndex(idx, self._inputsModel))

        if self._dockWidget:
            self._dockWidget.visibilityChanged.connect(self.visibilityChanged)

    # -------------------------------------------------------------------------
    # Mode lifecycle methods
    # -------------------------------------------------------------------------

    def activate(self):
        """Activate the session manager mode."""
        rvtypes.MinorMode.activate(self)

        # Create UI on first activation (not in __init__ to avoid Qt widget destruction)
        if not self._uiCreated:
            try:
                self._setupUI()
            except Exception:
                import traceback
                traceback.print_exc()
                return

        try:
            s = str(commands.readSettings("SessionManager", "showOnStartup", "no"))

            if s == "last":
                commands.writeSettings("Tools", "show_session_manager", True)
        except Exception:
            commands.writeSettings("SessionManager", "showOnStartup", "no")
            commands.writeSettings("Tools", "show_session_manager", False)

        if self._dockWidget:
            self._dockWidget.show()
        self.updateTree()
        # Hide all editors before showing applicable ones
        for e in self._editors:
            e.setHidden(True)
        commands.sendInternalEvent("session-manager-load-ui", commands.viewNode())

    def deactivate(self):
        """Deactivate the session manager mode."""
        try:
            s = str(commands.readSettings("SessionManager", "showOnStartup", "no"))

            if s == "last" and not self._quitting:
                commands.writeSettings("Tools", "show_session_manager", False)
        except Exception:
            commands.writeSettings("SessionManager", "showOnStartup", "no")
            commands.writeSettings("Tools", "show_session_manager", False)

        if self._lazySetInputsTimer:
            self._lazySetInputsTimer.stop()
        if self._lazyUpdateTimer:
            self._lazyUpdateTimer.stop()
        if self._dockWidget:
            self._dockWidget.hide()

        rvtypes.MinorMode.deactivate(self)

    # -------------------------------------------------------------------------
    # Event handlers
    # -------------------------------------------------------------------------

    def enterQuittingState(self, event):
        """Handle before-session-deletion event."""
        self._quitting = True
        event.reject()

    def viewEditModeActivated(self, event):
        """Handle view-edit-mode-activated event."""
        event.reject()
        commands.sendInternalEvent("session-manager-load-ui", commands.viewNode())

    def onPresenterChanged(self, event):
        """Close session manager when Live Review presenter changes."""
        if self._active and self._dockWidget and self._dockWidget.isVisible():
            self.toggle()
        event.reject()

    def updateTreeEvent(self, event):
        """Handle events that require tree update."""
        self.updateTree()
        event.reject()

    def beforeProgressiveLoading(self, event):
        """Handle before-progressive-loading event."""
        event.reject()
        self._progressiveLoadingInProgress = True

    def afterProgressiveLoading(self, event):
        """Handle after-progressive-loading event."""
        event.reject()
        self._progressiveLoadingInProgress = False
        self.updateTree()
        vnode = commands.viewNode()
        if vnode:
            self.updateInputs(vnode)

    def propertyChanged(self, event):
        """Handle graph-state-change event."""
        prop = event.contents()
        parts = prop.split(".")

        if len(parts) >= 3:
            node = parts[0]
            comp = parts[1]
            name = parts[2]

            if comp == "ui" and name == "name":
                self._lazyUpdateTimer.start(0)
                self.updateNavUI()
            elif comp == "sm_state" and name in ("sortKey", "sortKeyParent"):
                self._lazyUpdateTimer.start(0)
            elif comp == "request" and name == "imageComponent":
                try:
                    topNode = commands.nodeGroup(node)
                    pval = commands.getStringProperty(prop)

                    for item in subComponentItemsOfNode(self._viewModel, topNode):
                        selected = list(pval) == subComponentPropValue(item)
                        checkitem = item.parent().child(item.row(), 1)
                        if checkitem:
                            if selected:
                                checkitem.setIcon(self._selectionOnIcon)
                            else:
                                checkitem.setIcon(self._selectionOffIcon)
                except Exception:
                    pass

        event.reject()

    def nodeInputsChanged(self, event):
        """Handle graph-node-inputs-changed event."""
        vnode = commands.viewNode()
        if vnode is None:
            return

        node = event.contents()
        if node == vnode:
            self.updateInputs(node)

        try:
            if commands.nodeType(node) == "RVFolderGroup":
                if self._viewTreeView._dropAction == Qt.IgnoreAction:
                    self._lazyUpdateTimer.start(0)
        except Exception:
            pass

        event.reject()

    def afterGraphViewChange(self, event):
        """Handle after-graph-view-change event."""
        event.reject()

        n = commands.viewNode()
        if n is None:
            return

        self.selectViewableNode()
        self.setNodeStatus(commands.viewNode(), "\u2714")

        self.updateNavUI()
        self.restoreTabState()

        # Disable inputs for certain node types
        try:
            t = commands.nodeType(n)
            enabled = t not in ("RVSource", "RVFileSource", "RVImageSource", "RVSourceGroup")
            if self._inputsView:
                self._inputsView.setEnabled(enabled)
        except Exception:
            pass

        commands.sendInternalEvent("session-manager-load-ui", commands.viewNode())

    def beforeGraphViewChange(self, event):
        """Handle before-graph-view-change event."""
        for e in self._editors:
            e.setHidden(True)
        event.reject()
        self.saveTabState()
        self.setNodeStatus(commands.viewNode(), "")

    def showRows(self, event):
        """Debug function to print input rows."""
        self.printRows()

    # -------------------------------------------------------------------------
    # UI helper methods
    # -------------------------------------------------------------------------

    def iconForNode(self, node):
        """Get the icon for a node."""
        try:
            typeName = commands.nodeType(node)
            cprop = node + ".sm_state.componentSubType"

            if commands.propertyExists(cprop):
                prop = commands.getIntProperty(cprop)
                if prop:
                    subType = prop[0]
                    if subType == ViewSubComponent:
                        return self._viewIcon
                    elif subType == LayerSubComponent:
                        return self._layerIcon
                    elif subType == ChannelSubComponent:
                        return self._channelIcon

            for tname, icon in self._typeIcons:
                if tname == typeName:
                    return icon
        except Exception:
            pass

        return self._unknownTypeIcon

    def updateNavUI(self):
        """Update the navigation UI elements."""
        n = commands.viewNode()
        if n is None:
            return

        if self._viewLabel:
            try:
                self._viewLabel.setText(extra_commands.uiName(n))
            except Exception:
                pass

        if self._prevViewButton:
            try:
                self._prevViewButton.setEnabled(commands.previousViewNode() is not None)
            except Exception:
                pass

        if self._nextViewButton:
            try:
                self._nextViewButton.setEnabled(commands.nextViewNode() is not None)
            except Exception:
                pass

    def updateInputs(self, node):
        """Update the inputs list for a node."""
        if self._disableUpdates or self._progressiveLoadingInProgress:
            return

        self._inputOrderLock = True

        if self._inputsModel:
            self._inputsModel.clear()

            try:
                connections = nodeInputs(node)

                for innode in connections:
                    item = QStandardItem(self.iconForNode(innode), extra_commands.uiName(innode))
                    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled)
                    item.setData(innode, USER_ROLE_NODE)
                    item.setEditable(False)
                    self._inputsModel.appendRow(item)
            except Exception:
                pass

        self._inputOrderLock = False

    def updateTree(self):
        """Update the tree view with current session nodes."""
        if not self._uiCreated:
            return
        if self._disableUpdates:
            return

        if self._viewModel:
            self._viewModel.clear()
            self._viewModel.setHorizontalHeaderLabels(["Name", "*", "*"])

        if self._viewTreeView:
            self._viewTreeView.header().setMinimumSectionSize(-1)

        if commands.viewNode() is None:
            return

        try:
            self._viewModel.setSortRole(USER_ROLE_SORT_KEY)

            viewNodesList = commands.viewNodes()
            currentNode = commands.viewNode()

            # Create category items
            foldersItem = QStandardItem("FOLDERS")
            sourcesItem = QStandardItem("SOURCES")
            sequencesItem = QStandardItem("SEQUENCES")
            stackItem = QStandardItem("STACKS")
            layoutItem = QStandardItem("LAYOUTS")
            otherItem = QStandardItem("OTHER")

            categoryItems = [foldersItem, sourcesItem, sequencesItem, stackItem, layoutItem, otherItem]

            foreground = QBrush(QColor(125, 125, 125, 255), Qt.SolidPattern)

            for item in categoryItems:
                item.setFlags(Qt.ItemIsEnabled)
                item.setForeground(foreground)
                item.setSizeHint(QSize(-1, 25))
                item.setData("", USER_ROLE_PARENT_NODE)
                item.setData("", USER_ROLE_NODE)
                item.setData(INT_MAX, USER_ROLE_SORT_KEY)

            foldersItem.setFlags(Qt.ItemIsEnabled | Qt.ItemIsDropEnabled)
            if self._viewTreeView:
                self._viewTreeView._foldersItem = foldersItem

            # Populate tree
            for node in viewNodesList:
                try:
                    ntype = commands.nodeType(node)
                    outs = commands.nodeConnections(node)[1]

                    folderParent = False
                    for o in outs:
                        if commands.nodeType(o) == "RVFolderGroup":
                            folderParent = True
                            break

                    if not folderParent:
                        if ntype in ("RVFileSource", "RVImageSource", "RVSourceGroup"):
                            self.newNodeRow(sourcesItem, node, "", True)
                        elif ntype == "RVSequenceGroup":
                            self.newNodeRow(sequencesItem, node, "", True)
                        elif ntype == "RVStackGroup":
                            self.newNodeRow(stackItem, node, "", True)
                        elif ntype == "RVLayoutGroup":
                            self.newNodeRow(layoutItem, node, "", True)
                        elif ntype == "RVFolderGroup":
                            self.newNodeRow(foldersItem, node, "", True)
                        else:
                            self.newNodeRow(otherItem, node, "", True)
                except Exception:
                    pass

            # Add non-empty categories to model
            for item in categoryItems:
                if item.rowCount() != 0:
                    text = item.text()
                    propName = "#Session.sm_view.%s" % text

                    if not commands.propertyExists(propName):
                        commands.newProperty(propName, commands.IntType, 1)
                        commands.setIntProperty(propName, [1], True)

                    dummy1 = QStandardItem("")
                    dummy2 = QStandardItem("")
                    dummy1.setFlags(Qt.ItemIsEnabled)
                    dummy2.setFlags(Qt.ItemIsEnabled)
                    self._viewModel.appendRow([item, dummy1, dummy2])

                    try:
                        expanded = commands.getIntProperty(propName)[0] == 1
                        self._viewTreeView.setExpanded(self._viewModel.indexFromItem(item), expanded)
                    except Exception:
                        pass

            self._viewModel.sort(0, Qt.AscendingOrder)
            self._viewModel.invisibleRootItem().setFlags(Qt.ItemIsEnabled)
            self.selectViewableNode()

            resizeColumns(self._viewTreeView, self._viewModel)

        except Exception:
            pass

    def newNodeRow(self, parentItem, node, parent, recursive=False):
        """Create a new row in the tree for a node."""
        try:
            ntype = commands.nodeType(node)
            uiname = extra_commands.uiName(node)
            item = QStandardItem(uiname)
            folder = ntype == "RVFolderGroup"
            source = ntype == "RVSourceGroup"
            sortKey = sortKeyInParent(node, parent)
            toolTip = toolTipFromProp(node)
            icon = self.iconForNode(node)

            flags = Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled
            if folder:
                flags |= Qt.ItemIsDropEnabled

            item.setFlags(flags)
            item.setData(parent, USER_ROLE_PARENT_NODE)
            item.setData(node, USER_ROLE_NODE)
            item.setData(sortKey, USER_ROLE_SORT_KEY)
            item.setData(NotASubComponent, USER_ROLE_SUBCOMPONENT_TYPE)
            item.setEditable(True)
            item.setIcon(icon)
            item.setRowCount(0)

            # Status columns
            statusItems = self.newNodeStatusColumns(node)
            if node == commands.viewNode() and len(statusItems) > 1:
                statusItems[1].setText("\u2714")

            addRow(parentItem, [item] + statusItems)

            if toolTip:
                # Replace tabs which can crash Qt on Windows
                toolTip = toolTip.replace("\t", " ")
                item.setToolTip(toolTip)

            if folder and recursive:
                try:
                    for n in commands.nodeConnections(node)[0]:
                        self.newNodeRow(item, n, node, recursive)
                except Exception:
                    pass

            if isExpandedInParent(node, parent):
                self._viewTreeView.setExpanded(self._viewModel.indexFromItem(item), True)

            # Handle source sub-components
            if source:
                self._addSourceSubComponents(item, node, parent)

        except Exception:
            pass

    def _addSourceSubComponents(self, item, node, parent):
        """Add sub-component items for a source node."""
        if commands.propertyExists(node + ".sm_state.componentHash"):
            # This is a sub-component node
            try:
                pname = node + ".sm_state.componentOfNode"
                cnode = commands.getStringProperty(pname)[0]
                emptyItem = QStandardItem("(subcomponent of %s)" % extra_commands.uiName(cnode))
                font = emptyItem.font()
                font.setItalic(True)
                emptyItem.setFont(font)
                addRow(item, [emptyItem, QStandardItem("")])
            except Exception:
                pass
            return

        # Regular source - add media info
        try:
            snode = sourceNodeOfGroup(node)
            if snode is None:
                return

            pval = []
            try:
                pval = commands.getStringProperty(snode + ".request.imageComponent")
            except Exception:
                pass

            hasPval = len(pval) > 1
            iname = pval[-1] if hasPval else None
            itype = itemSubComponentTypeForName(pval[0]) if hasPval else NotASubComponent

            mediaInfoList = commands.sourceMediaInfoList(snode)

            for info in mediaInfoList:
                # Handle both object and dict access for sourceMediaInfoList results
                info_file = info["file"] if isinstance(info, dict) else info.file
                fileItem = self.newNodeSubComponent(
                    MediaSubComponent, item, info_file, info_file, node, parent, False
                )
                font = fileItem.font()
                font.setBold(True)
                fileItem.setFont(font)
                topItem = fileItem

                # Handle both object and dict access for viewInfos
                viewInfos = getattr_or_key(info, "viewInfos") or []
                
                for v in viewInfos:
                    v_name = getattr_or_key(v, "name") or ""
                    v_layers = getattr_or_key(v, "layers") or []
                    v_noLayerChannels = getattr_or_key(v, "noLayerChannels") or []
                    
                    if len(viewInfos) > 1 and v_name != "":
                        selected = itype == ViewSubComponent and iname == v_name
                        topItem = self.newNodeSubComponent(
                            ViewSubComponent, fileItem, info_file, v_name, node, parent, selected
                        )
                    else:
                        topItem = fileItem

                    nlayers = len(v_layers)

                    for l in v_layers:
                        layerItem = None
                        l_name = getattr_or_key(l, "name") or ""
                        l_channels = getattr_or_key(l, "channels") or []
                        unnamed = l_name == ""
                        selected = itype == LayerSubComponent and iname == l_name

                        if nlayers > 1 and unnamed:
                            layerItem = self.newNodeSubComponent(
                                LayerSubComponent, topItem, info_file, "", node, parent, selected
                            )
                        elif not unnamed:
                            layerItem = self.newNodeSubComponent(
                                LayerSubComponent, topItem, info_file, l_name, node, parent, selected
                            )
                        else:
                            layerItem = topItem

                        for c in l_channels:
                            c_name = getattr_or_key(c, "name") or ""
                            selected = itype == ChannelSubComponent and iname == c_name
                            self.newNodeSubComponent(
                                ChannelSubComponent, layerItem, info_file, c_name, node, parent, selected
                            )

                    if v_layers and v_noLayerChannels:
                        selected = itype == LayerSubComponent and iname == ""
                        topItem = self.newNodeSubComponent(
                            LayerSubComponent, topItem, info_file, "", node, parent, selected
                        )

                    for c in v_noLayerChannels:
                        c_name = getattr_or_key(c, "name") or ""
                        selected = itype == ChannelSubComponent and iname == c_name
                        self.newNodeSubComponent(
                            ChannelSubComponent, topItem, info_file, c_name, node, parent, selected
                        )
        except Exception:
            pass

    def newNodeSubComponent(self, subComponent, parentItem, media, fullName, node, parent, selected):
        """Create a sub-component item."""
        name = os.path.basename(fullName) if subComponent == MediaSubComponent else fullName
        item = QStandardItem("default" if name == "" else name)

        if name == "":
            font = item.font()
            font.setItalic(True)
            item.setFont(font)

        item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled)
        item.setData(parent, USER_ROLE_PARENT_NODE)
        item.setData(node, USER_ROLE_NODE)
        item.setData(subComponent, USER_ROLE_SUBCOMPONENT_TYPE)
        item.setData(fullName, USER_ROLE_SUBCOMPONENT_VALUE)
        item.setData(media, USER_ROLE_MEDIA)
        item.setEditable(True)

        if subComponent == ViewSubComponent:
            item.setIcon(self._viewIcon)
        elif subComponent == LayerSubComponent:
            item.setIcon(self._layerIcon)
        elif subComponent == ChannelSubComponent:
            item.setIcon(self._channelIcon)

        sitems = self.newNodeStatusColumns(node)
        selitem = sitems[0] if sitems else None

        if subComponent != MediaSubComponent and selitem:
            if selected:
                selitem.setIcon(self._selectionOnIcon)
            else:
                selitem.setIcon(self._selectionOffIcon)

        addRow(parentItem, [item] + sitems)

        item.setData(hashedSubComponentFromItem(item), USER_ROLE_HASH)

        if subComponent != ChannelSubComponent and isSubComponentExpanded(node, item):
            self._viewTreeView.setExpanded(self._viewModel.indexFromItem(item), True)

        return item

    def newNodeStatusColumns(self, node):
        """Create status column items."""
        result = []
        for _ in range(2):
            item = QStandardItem("")
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            result.append(item)
        return result

    def setNodeStatus(self, node, status):
        """Set status text for a node in the tree."""
        items = mapModel(
            self._viewModel,
            lambda i: itemNode(i) == node and not itemIsSubComponent(i)
        )

        for i in items:
            parent = i.parent()
            if parent:
                sitem = parent.child(i.row(), 2)
                if sitem is None:
                    parent.setChild(i.row(), 2, QStandardItem(status))
                else:
                    sitem.setText(status)

    def selectViewableNode(self):
        """Select the current view node in the tree."""
        vnode = commands.viewNode()
        if vnode is None:
            return

        uiname = extra_commands.uiName(vnode)
        cols = self._viewModel.columnCount(QModelIndex())
        smodel = self._viewTreeView.selectionModel()
        items = mapModel(self._viewModel, lambda i: itemNode(i) == vnode)

        smodel.clear()

        for item in items:
            index = self._viewModel.indexFromItem(item)
            # Select the row
            smodel.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.updateInputs(vnode)
            self._viewTreeView.scrollTo(index, QAbstractItemView.EnsureVisible)
            break

    # -------------------------------------------------------------------------
    # Slot methods
    # -------------------------------------------------------------------------

    def selectCurrentViewSlot(self, checked=False):
        """Slot for select current view button."""
        self.selectViewableNode()

    def deleteViewableSlot(self, checked=False):
        """Slot for delete view button."""
        items = self.selectedItems()

        for item in items:
            node = itemNode(item)
            parent = itemParentNode(item)

            try:
                outs = commands.nodeConnections(node)[1]
                parentType = commands.nodeType(parent) if commands.nodeExists(parent) else ""

                nfolders = sum(1 for o in outs if commands.nodeType(o) == "RVFolderGroup")

                if parentType == "RVFolderGroup" and nfolders > 1:
                    removeInput(parent, node)
                else:
                    self._disableUpdates = True
                    try:
                        commands.deleteNode(node)
                    except Exception:
                        pass
                    self._disableUpdates = False
            except Exception:
                pass

        self._lazyUpdateTimer.start(0)

    def editViewInfoSlot(self, checked=False):
        """Slot for edit view info button."""
        indices = self._viewTreeView.selectionModel().selectedIndexes()
        if indices:
            self._viewTreeView.edit(indices[0])

    def inputsDeleteSlot(self, checked=False):
        """Slot for delete input button."""
        if self._inputOrderLock or commands.viewNode() is None:
            return

        indices = self._inputsView.selectionModel().selectedIndexes()
        inputs = nodeInputs(commands.viewNode())

        newNodes = []
        for i, inp in enumerate(inputs):
            index = self._inputsModel.index(i, 0, QModelIndex())
            if not includes(indices, index):
                newNodes.append(nodeFromIndex(index, self._inputsModel))

        try:
            setInputs(commands.viewNode(), newNodes)
        except Exception:
            pass

        commands.redraw()

    def reorderSelected(self, up, checked=False):
        """Reorder selected inputs up or down."""
        indices = self._inputsView.selectionModel().selectedIndexes()
        if not indices:
            return

        inputs = nodeInputs(commands.viewNode())
        minRow = min(idx.row() for idx in indices)
        maxRow = max(idx.row() for idx in indices)

        if (up and minRow == 0) or (not up and maxRow == len(inputs) - 1):
            return

        numRows = self._inputsModel.rowCount(QModelIndex())

        # Calculate new positions
        newNodes = [""] * numRows
        includedList = []

        for i in range(numRows):
            index = self._inputsModel.index(i, 0, QModelIndex())
            included = includes(indices, index)
            newIndex = index.row()

            if included:
                newIndex = newIndex + (-1 if up else 1)
                includedList.append(newIndex)
            elif newIndex >= minRow + (-1 if up else 1) and newIndex <= maxRow + (-1 if up else 1):
                selectionSize = len([idx for idx in indices if idx.row() >= minRow and idx.row() <= maxRow])
                newIndex = newIndex + (1 if up else -1) * selectionSize

            if 0 <= newIndex < numRows:
                newNodes[newIndex] = nodeFromIndex(index, self._inputsModel)

        try:
            setInputs(commands.viewNode(), [n for n in newNodes if n])
            self.selectInputsRange(includedList)
        except Exception:
            pass

        commands.redraw()

    def selectInputsRange(self, selectionList):
        """Select inputs by row indices."""
        smodel = self._inputsView.selectionModel()
        for row in selectionList:
            index = self._inputsModel.index(row, 0, QModelIndex())
            smodel.select(index, QItemSelectionModel.Select)

    def sortInputs(self, ascending, checked=False):
        """Sort inputs alphabetically."""
        if self._inputOrderLock or commands.viewNode() is None:
            return

        node = commands.viewNode()
        inputs = nodeInputs(node)

        # Sort by UI name
        sorted_inputs = sorted(inputs, key=lambda n: extra_commands.uiName(n), reverse=not ascending)

        if not setInputs(node, sorted_inputs):
            self.updateInputs(node)

        if commands.nodeType(node) == "RVFolderGroup":
            for i, n in enumerate(sorted_inputs):
                setSortKeyInParent(n, node, i)
            self.updateTree()

    def addThingSlot(self, thingstring, checked=False):
        """Slot for adding new nodes."""
        if re.match(r".+\.movieproc$", thingstring):
            self.addMovieProc(thingstring)
        elif thingstring == "":
            self.addNodeByTypeName()
        else:
            self.addNodeOfType(thingstring)

    def addNodeOfType(self, typename):
        """Add a new node of specified type."""
        nodes = self.selectedConvertedSubComponents()
        n = commands.newNode(typename, "")

        if n is None or not setInputs(n, nodes):
            if n is not None:
                commands.deleteNode(n)
        else:
            self.renameByType(n, nodes)
            commands.setViewNode(n)

        return n

    def addNodeByTypeName(self):
        """Show dialog to add node by type name."""
        if self._newNodeDialog is None:
            m = qtutils.sessionWindow()

            loader = QUiLoader()
            uifile = QFile(self.auxFilePath("new_node.ui"))
            if uifile.open(QFile.ReadOnly):
                self._newNodeDialog = loader.load(uifile, m)
                uifile.close()

            self._nodeTypeCombo = self._newNodeDialog.findChild(QComboBox, "comboBox")
            if self._nodeTypeCombo:
                self._nodeTypeCombo.addItems(commands.nodeTypes(True))

            icon = self.auxIcon("new_48x48.png", True)
            label = self._newNodeDialog.findChild(QLabel, "pictureLabel")
            if label:
                label.setPixmap(icon.pixmap(QSize(48, 48), QIcon.Normal, QIcon.Off))

            self._newNodeDialog.accepted.connect(
                lambda: self.addNodeOfType(self._nodeTypeCombo.currentText())
            )

        if self._newNodeDialog:
            self._newNodeDialog.show()

    def addMovieProc(self, fmtspec):
        """Add a movieproc source."""
        if self._createImageDialog is None:
            m = qtutils.sessionWindow()

            loader = QUiLoader()
            uifile = QFile(self.auxFilePath("create_image_dialog.ui"))
            if uifile.open(QFile.ReadOnly):
                self._createImageDialog = loader.load(uifile, m)
                uifile.close()

            self._cidWidth = self._createImageDialog.findChild(QLineEdit, "widthEdit")
            self._cidHeight = self._createImageDialog.findChild(QLineEdit, "heightEdit")
            self._cidFPS = self._createImageDialog.findChild(QLineEdit, "fpsEdit")
            self._cidLength = self._createImageDialog.findChild(QLineEdit, "lengthEdit")
            self._cidPic = self._createImageDialog.findChild(QLabel, "pictureLabel")
            self._cidGroupBox = self._createImageDialog.findChild(QGroupBox, "groupBox")
            self._cidColorButton = self._createImageDialog.findChild(QPushButton, "colorButton")
            self._cidColorLabel = self._createImageDialog.findChild(QLabel, "colorLabel")

            try:
                fps = float(commands.readSettings("General", "fps", 24.0))
                if self._cidFPS:
                    self._cidFPS.setText("%g" % fps)
            except Exception:
                pass

            self._colorDialog = QColorDialog(m)
            self._colorDialog.setOption(QColorDialog.ShowAlphaChannel, False)

            self._createImageDialog.accepted.connect(self._makeImage)
            if self._cidColorButton:
                self._cidColorButton.clicked.connect(self.chooseColorSlot)
            self._colorDialog.currentColorChanged.connect(self.newColorSlot)

        ptype = fmtspec.split(",")[0]
        icon = None

        if self._cidColorButton:
            self._cidColorButton.setVisible(True)
            self._cidColorLabel.setVisible(True)
            self._cidColorButton.setEnabled(False)
            self._cidColorLabel.setEnabled(False)

        if ptype == "srgbcolorchart":
            self._cidName = "SRGBMacbethColorChart"
            icon = self.auxIcon("colorchart_48x48.png", True)
            if self._cidColorButton:
                self._cidColorButton.setStyleSheet("QPushButton { background-color: rgb(128,128,128); }")
                self._cidColorButton.setVisible(False)
                self._cidColorLabel.setVisible(False)
            self._cidColor = QColor(0, 0, 0, 255)
        elif ptype == "acescolorchart":
            self._cidName = "ACESMacbethColorChart"
            icon = self.auxIcon("colorchart_48x48.png", True)
            if self._cidColorButton:
                self._cidColorButton.setStyleSheet("QPushButton { background-color: rgb(128,128,128); }")
                self._cidColorButton.setVisible(False)
                self._cidColorLabel.setVisible(False)
            self._cidColor = QColor(0, 0, 0, 255)
        elif ptype == "smptebars":
            self._cidName = "SMTPEColorBars"
            icon = self.auxIcon("ntscbars_48x48.png", True)
            if self._cidColorButton:
                self._cidColorButton.setStyleSheet("QPushButton { background-color: rgb(128,128,128); }")
                self._cidColorButton.setVisible(False)
                self._cidColorLabel.setVisible(False)
            self._cidColor = QColor(0, 0, 0, 255)
        elif ptype == "blank":
            self._cidName = "Blank"
            icon = self.auxIcon("video_48x48.png", True)
            if self._cidColorButton:
                self._cidColorButton.setStyleSheet("QPushButton { background-color: rgb(128,128,128); }")
                self._cidColorButton.setVisible(False)
                self._cidColorLabel.setVisible(False)
            self._cidColor = QColor(0, 0, 0, 255)
            if self._cidWidth:
                self._cidWidth.setVisible(False)
            if self._cidHeight:
                self._cidHeight.setVisible(False)
        elif ptype == "black":
            self._cidName = "Black"
            icon = self.auxIcon("video_48x48.png", True)
            if self._cidColorButton:
                self._cidColorButton.setStyleSheet("QPushButton { background-color: rgb(0,0,0); }")
            self._cidColor = QColor(0, 0, 0, 255)
        elif ptype == "solid":
            self._cidName = "SolidColor"
            icon = self.auxIcon("video_48x48.png", True)
            if self._cidColorButton:
                self._cidColorButton.setStyleSheet("QPushButton { background-color: rgb(128,128,128); }")
                self._cidColorButton.setEnabled(True)
                self._cidColorLabel.setEnabled(True)
            self._cidColor = QColor(128, 128, 128, 255)

        if icon and self._cidPic:
            self._cidPic.setPixmap(icon.pixmap(QSize(48, 48), QIcon.Normal, QIcon.Off))

        if self._cidGroupBox:
            self._cidGroupBox.setTitle(self._cidName)

        self._cidFMTSpec = fmtspec

        if self._createImageDialog:
            self._createImageDialog.show()

    def _makeImage(self):
        """Create image from dialog settings."""
        try:
            mp = self._cidFMTSpec % (
                "width=%s,height=%s,fps=%s,start=1,end=%s,red=%g,green=%g,blue=%g" % (
                    self._cidWidth.text(),
                    self._cidHeight.text(),
                    self._cidFPS.text(),
                    self._cidLength.text(),
                    self._cidColor.redF(),
                    self._cidColor.greenF(),
                    self._cidColor.blueF()
                )
            )
            s = commands.addSourceVerbose([mp])
            extra_commands.setUIName(commands.nodeGroup(s), self._cidName)
        except Exception:
            pass

    def newFolderSlot(self, which, checked=False):
        """Create a new folder."""
        paths = self._viewTreeView.selectedNodePaths()
        folder = commands.newNode("RVFolderGroup", "Folder")

        nodes = [path[0] for path in paths if path]

        if paths:
            first = paths[0]

            if which != 1 and nodes:
                if not setInputs(folder, nodes):
                    if folder is not None:
                        commands.deleteNode(folder)
                        return

            self._disableUpdates = True

            if which == 2:
                for path in paths:
                    if len(path) > 1 and commands.nodeExists(path[1]):
                        removeInput(path[1], path[0])

            if len(first) > 1 and commands.nodeExists(first[1]):
                addInput(first[1], folder)
                setSortKeyInParent(folder, first[1], sortKeyInParent(first[0], first[1]))

            self._disableUpdates = False

        self._disableUpdates = True
        self.renameByType(folder, [] if which == 1 else nodes)
        self._disableUpdates = False

        if paths:
            commands.setViewNode(folder)

    def renameByType(self, node, inputs):
        """Rename node based on its type and inputs."""
        n = len(inputs)
        basename = commands.nodeType(node)

        if re.match("^RV", basename):
            basename = basename[2:]
        if re.match("Group$", basename):
            basename = basename[:-5]

        if n == 0:
            name = "Empty %s" % basename
        elif n < 3:
            name = "%s of " % basename
            for i, inp in enumerate(inputs):
                if i > 0 and n > 2:
                    name += ","
                if i > 0:
                    name += " "
                if i == n - 1 and n > 1:
                    name += "and "
                name += extra_commands.uiName(inp)
        else:
            name = "%s of %d views" % (basename, n)

        extra_commands.setUIName(node, name)

    def selectedNodes(self):
        """Get list of selected nodes."""
        indices = self._viewTreeView.selectionModel().selectedIndexes()
        nodes = []

        for index in indices:
            if index.column() == 0:
                n = itemNode(self._viewModel.itemFromIndex(index))
                if commands.nodeExists(n):
                    nodes.append(n)

        return nodes

    def selectedItems(self):
        """Get list of selected items."""
        indices = self._viewTreeView.selectionModel().selectedIndexes()
        items = []

        for index in indices:
            if index.column() == 0:
                items.append(self._viewModel.itemFromIndex(index))

        return items

    def selectedConvertedSubComponents(self):
        """Get nodes for selected items, converting sub-components if needed."""
        indices = self._viewTreeView.selectionModel().selectedIndexes()
        nodes = []

        for index in indices:
            if index.column() == 0:
                item = self._viewModel.itemFromIndex(index)
                n = itemNode(item)

                if commands.nodeExists(n):
                    if itemIsSubComponent(item):
                        self._disableUpdates = True
                        snode = self.sourceFromSubComponent(item, n)
                        self._disableUpdates = False
                        if snode:
                            nodes.append(snode)
                    else:
                        nodes.append(n)

        return nodes

    def sourceFromSubComponent(self, item, node):
        """Create or get source node for sub-component."""
        hash_val = hashedSubComponentFromItem(item)
        cnode, folder = self.componentAndFolderNodeFromHash(hash_val, node)

        if cnode is not None:
            return cnode

        mediaItem = None
        viewItem = None
        layerItem = None

        i = item
        while i is not None and itemSubComponentType(i) != NotASubComponent:
            subType = itemSubComponentType(i)
            if subType == MediaSubComponent:
                mediaItem = i
                break
            elif subType == LayerSubComponent:
                layerItem = i
            elif subType == ViewSubComponent:
                viewItem = i
            i = i.parent()

        subType = itemSubComponentType(item)
        filename = itemSubComponentValue(mediaItem) if mediaItem else ""
        fullName = itemSubComponentValue(item)

        return self.newSubComponentNode(
            hash_val, subType, filename, fullName,
            subComponentPropValue(item), node, folder
        )

    def componentAndFolderNodeFromHash(self, hash_val, node):
        """Find component and folder node from hash."""
        folder = None
        cnode = None

        for n in commands.nodes():
            try:
                ntype = commands.nodeType(n)

                if ntype == "RVSourceGroup" and cnode is None:
                    propName = n + ".sm_state.componentHash"
                    if commands.propertyExists(propName):
                        p = commands.getStringProperty(propName)
                        pn = commands.getStringProperty(n + ".sm_state.componentOfNode")
                        if p and p[0] == hash_val and pn and pn[0] == node:
                            cnode = n

                elif ntype == "RVFolderGroup":
                    pname = n + ".sm_state.componentFolderOfNode"
                    if commands.propertyExists(pname):
                        p = commands.getStringProperty(pname)
                        if p and p[0] == node:
                            folder = n
            except Exception:
                pass

        return (cnode, folder)

    def newSubComponentNode(self, hash_val, subType, filename, fullName, compPropValue, node, folder):
        """Create a new sub-component node."""
        snode = commands.addSourceVerbose([filename])
        nodeName = extra_commands.uiName(node)
        groupNode = commands.nodeGroup(snode)
        dname = "default" if fullName == "" else fullName

        if folder is None:
            folder = commands.newNode("RVFolderGroup", "%s_components" % node)
            extra_commands.setUIName(folder, "Components of %s" % extra_commands.uiName(node))
            commands.setStringProperty(folder + ".sm_state.componentFolderOfNode", [node], True)
            setExpandedInParent(folder, "", False)

        inputs = nodeInputs(folder)
        inputs.append(groupNode)
        commands.setNodeInputs(folder, inputs)

        commands.setStringProperty(groupNode + ".sm_state.componentOfNode", [node], True)
        commands.setStringProperty(groupNode + ".sm_state.componentHash", [hash_val], True)
        commands.setIntProperty(groupNode + ".sm_state.componentSubType", [subType], True)

        if subType == MediaSubComponent:
            extra_commands.setUIName(groupNode, "%s (Media %s)" % (nodeName, dname))
        elif subType == ViewSubComponent:
            extra_commands.setUIName(groupNode, "%s (View %s)" % (nodeName, dname))
            setNodeRequest(snode, compPropValue)
        elif subType == LayerSubComponent:
            extra_commands.setUIName(groupNode, "%s (Layer %s)" % (nodeName, dname))
            setNodeRequest(snode, compPropValue)
        elif subType == ChannelSubComponent:
            extra_commands.setUIName(groupNode, "%s (Channel %s)" % (nodeName, dname))
            setNodeRequest(snode, compPropValue)

        extra_commands.displayFeedback("NOTE: Created %s" % extra_commands.uiName(groupNode), 5.0)
        return groupNode

    def configSlot(self, onstart, show, checked=False):
        """Handle config menu selection."""
        commands.writeSettings("SessionManager", "showOnStartup", onstart)
        commands.writeSettings("Tools", "show_session_manager", show)

    def chooseColorSlot(self, checked=False):
        """Open color dialog."""
        if self._colorDialog:
            self._colorDialog.open()
            if self._cidColor:
                self._colorDialog.setCurrentColor(self._cidColor)

    def newColorSlot(self, color):
        """Handle color selection."""
        css = "QPushButton{background-color:rgb(%d,%d,%d);}" % (color.red(), color.green(), color.blue())
        if self._cidColorButton:
            self._cidColorButton.setStyleSheet(css)
        self._cidColor = color

    def splitterMoved(self, pos, index):
        """Handle splitter position change."""
        propName = "#Session.sm_window.splitter"
        if self._splitter:
            fpos = float(pos) / float(self._splitter.height()) if self._splitter.height() > 0 else 0

            if not commands.propertyExists(propName):
                commands.newProperty(propName, commands.FloatType, 1)

            commands.setFloatProperty(propName, [fpos], True)

    def visibilityChanged(self, vis):
        """Handle dock widget visibility change."""
        self._mainWinVisTimer.start(0)

    def mainWinVisTimeout(self):
        """Handle main window visibility timeout."""
        m = qtutils.sessionWindow()
        if m and m.isMinimized():
            return

        if self._dockWidget:
            if not self._dockWidget.isVisible() and self._active:
                self.toggle()
            if self._dockWidget.isVisible() and not self._active:
                self.toggle()

    def viewByIndex(self, index, model):
        """View node at model index."""
        item = model.itemFromIndex(index)
        node = itemNode(item)
        subType = itemSubComponentType(item)

        if not node:
            return

        self._disableUpdates = True

        try:
            viewChange = False
            currentView = commands.viewNode()
            if currentView != node:
                commands.setViewNode(node)
                viewChange = True

            if subType != NotASubComponent:
                setImageRequest(subComponentPropValue(item), not viewChange)
        except Exception:
            pass

        self._disableUpdates = False
        self.updateInputs(commands.viewNode())
        self.updateNavUI()

    def itemPressed(self, index, model):
        """Handle item press."""
        item0 = model.itemFromIndex(index)
        sindex = index.sibling(index.row(), 0)
        item = model.itemFromIndex(sindex)
        subType = itemSubComponentType(item)

        if item0.column() == 1:
            if subType != NotASubComponent and subType != MediaSubComponent:
                self.viewByIndex(sindex, model)

    def viewItemChanged(self, item):
        """Handle item data change in view model."""
        node = itemNode(item)
        subType = itemSubComponentType(item)
        parentItem = item.parent()
        parent = itemNode(parentItem) if parentItem else None
        nodePaths = self._viewTreeView.filteredDraggedPaths(lambda p: p and p[0] == node)

        if self._viewTreeView._dropAction == Qt.CopyAction:
            if not hasInput(parent, node):
                addInput(parent, node)
                item.setData(parent, USER_ROLE_PARENT_NODE)
                if parent and commands.nodeExists(parent) and commands.nodeType(parent) == "RVFolderGroup":
                    self._viewTreeView.sortFolderChildren(parent)

        elif self._viewTreeView._dropAction == Qt.MoveAction and nodePaths:
            parentExists = commands.nodeExists(parent) if parent else False

            if parentExists:
                if not hasInput(parent, node):
                    addInput(parent, node)

            item.setData(parent if parentExists else "", USER_ROLE_PARENT_NODE)

            for path in nodePaths:
                if len(path) > 1:
                    n = path[0]
                    p = path[1]
                    if commands.nodeExists(p) and (not commands.nodeExists(parent) or p != parent):
                        removeInput(p, n)

            if commands.nodeExists(parent) and commands.nodeType(parent) == "RVFolderGroup":
                self._viewTreeView.sortFolderChildren(parent)

        elif node != "" and subType == NotASubComponent:
            self._disableUpdates = True
            try:
                extra_commands.setUIName(node, item.text())
            except Exception:
                pass
            self._disableUpdates = False

    def setItemExpandedState(self, index, value):
        """Handle item expand/collapse."""
        item = self._viewModel.itemFromIndex(index)
        node = itemNode(item)
        subComp = itemIsSubComponent(item)

        if subComp:
            setSubComponentExpanded(node, item, value == 1)
        else:
            if commands.nodeExists(node):
                parent = itemNode(item.parent()) if item.parent() else ""
                setExpandedInParent(node, parent, value == 1)
            else:
                propName = "#Session.sm_view.%s" % item.text()
                commands.setIntProperty(propName, [value], True)

        resizeColumns(self._viewTreeView, self._viewModel)

    def viewContextMenuSlot(self, pos):
        """Show context menu."""
        if self._viewContextMenu is None:
            self._viewContextMenu = QMenu(self._viewTreeView)

            if self._folderMenu:
                folderMenu = self._viewContextMenu.addMenu(self._folderMenu)
                folderMenu.setIcon(self.auxIcon("foldr_48x48.png", True))

            if self._createMenu:
                createMenu = self._viewContextMenu.addMenu(self._createMenu)
                createMenu.setIcon(self.auxIcon("add_48x48.png", True))

            for a in self._viewContextMenuActions:
                self._viewContextMenu.addAction(a)

        self._viewContextMenu.exec_(self._viewTreeView.mapToGlobal(pos))

    def tabChangeSlot(self, index):
        """Handle tab change."""
        self.saveTabState()

    def saveTabState(self):
        """Save current tab state."""
        vnode = commands.viewNode()
        if vnode and self._tabWidget:
            try:
                prop = "%s.sm_state.tab" % vnode
                # Create property if it doesn't exist
                if not commands.propertyExists(prop):
                    commands.newProperty(prop, commands.IntType, 1)
                commands.setIntProperty(prop, [self._tabWidget.currentIndex()], True)
            except (RuntimeError, Exception):
                # Qt object may have been deleted, or property creation failed
                pass

    def restoreTabState(self):
        """Restore tab state for current view."""
        vnode = commands.viewNode()
        if vnode and self._tabWidget:
            try:
                prop = "%s.sm_state.tab" % vnode
                if commands.propertyExists(prop):
                    state = commands.getIntProperty(prop)[0]
                    self._tabWidget.setCurrentIndex(state)
                elif commands.nodeType(vnode) == "RVSourceGroup":
                    self._tabWidget.setCurrentIndex(1)
            except (RuntimeError, Exception):
                # Qt object may have been deleted
                pass

    def inputRowsRemovedSlot(self, parent, start, end):
        """Handle input rows removed."""
        if self._inputOrderLock or commands.viewNode() is None:
            return
        self._lazySetInputsTimer.start(100)

    def inputRowsInsertedSlot(self, parent, start, end):
        """Handle input rows inserted."""
        if self._inputOrderLock or commands.viewNode() is None:
            return
        self._lazySetInputsTimer.start(100)

    def rebuildInputsFromList(self):
        """Rebuild inputs from the list model."""
        if self._inputOrderLock or commands.viewNode() is None:
            return

        num = self._inputsModel.rowCount(QModelIndex())
        vnode = commands.viewNode()

        nodes = []
        self._disableUpdates = True

        for row in range(num):
            item = self._inputsModel.item(row, 0)
            if item is not None:
                node = itemNode(item)

                try:
                    if itemIsSubComponent(item):
                        hash_val = itemSubComponentHash(item)
                        cnode, folder = self.componentAndFolderNodeFromHash(hash_val, node)

                        if cnode is None:
                            fullName = itemSubComponentValue(item)
                            filename = itemSubComponentMedia(item)
                            subType = itemSubComponentType(item)
                            pval = subComponentPropValue(item)
                            snode = self.newSubComponentNode(
                                hash_val, subType, filename, fullName, pval, node, folder
                            )
                            nodes.append(snode)
                        else:
                            nodes.append(cnode)
                    else:
                        nodes.append(node)
                except Exception:
                    pass

        commands.setViewNode(vnode)
        self._disableUpdates = False

        if not setInputs(vnode, nodes):
            self.updateInputs(vnode)

    def navButtonClicked(self, which, checked=False):
        """Handle navigation button click."""
        self._disableUpdates = True

        try:
            if which == "next":
                nextNode = commands.nextViewNode()
                if nextNode is not None:
                    commands.setViewNode(nextNode)
            elif which == "prev":
                prevNode = commands.previousViewNode()
                if prevNode is not None:
                    commands.setViewNode(prevNode)
        except Exception:
            pass

        self._disableUpdates = False
        self.updateInputs(commands.viewNode())

    def printRows(self):
        """Debug: print all input rows."""
        pass

    def isUIReady(self):
        """Check if the UI is ready for editors to be added."""
        try:
            if not self._uiCreated:
                return False
            if self._uiTreeWidget is None:
                return False
            self._uiTreeWidget.topLevelItemCount()
            return True
        except RuntimeError:
            return False

    def addEditor(self, name, widget):
        """Add an editor widget to the UI tree."""
        try:
            if self._uiTreeWidget is None:
                return

            try:
                _ = self._uiTreeWidget.topLevelItemCount()
            except RuntimeError:
                return

            item = QTreeWidgetItem([name], QTreeWidgetItem.Type)
            child = QTreeWidgetItem([""], QTreeWidgetItem.Type)

            widget.setAutoFillBackground(True)
            # Use custom light grey circle icon instead of blue Qt resource
            item.setIcon(0, self._editorDotIcon)
            item.setFlags(Qt.ItemIsEnabled)

            item.addChild(child)
            self._uiTreeWidget.addTopLevelItem(item)
            self._uiTreeWidget.setItemWidget(child, 0, widget)
            widget.show()
            item.setExpanded(True)

            self._editors.append(item)
        except RuntimeError:
            pass

    def useEditor(self, name):
        """Show editor by name."""
        try:
            for e in self._editors:
                if name == e.text(0):
                    e.setHidden(False)
        except RuntimeError:
            # Qt object may have been deleted
            pass

    def reloadEditorTab(self):
        """Reload the editor tab."""
        try:
            for e in self._editors:
                e.setHidden(True)
            commands.sendInternalEvent("session-manager-load-ui", commands.viewNode())
        except RuntimeError:
            # Qt object may have been deleted
            pass


# =============================================================================
# Module-level functions
# =============================================================================

def createMode():
    """Create and return the SessionManagerMode instance."""
    return SessionManagerMode()


def theMode():
    """Get the current SessionManagerMode instance."""
    return rvui.minorModeFromName("session_manager")
