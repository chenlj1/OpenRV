#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""
Shared utilities for session_manager package.

This module provides common constants, context managers, and helper functions
used across the session_manager package and its edit mode sub-modules.
"""

from contextlib import contextmanager

# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt
except ImportError:
    from PySide6.QtCore import Qt


# =============================================================================
# Qt UserRole Constants
# =============================================================================
# These constants define the offsets from Qt.UserRole for storing custom data
# in QStandardItem objects within the session manager tree view.

USER_ROLE_PARENT_NODE = Qt.UserRole + 1      # Parent node name
USER_ROLE_NODE = Qt.UserRole + 2             # Node name
USER_ROLE_SORT_KEY = Qt.UserRole + 3         # Sort key for ordering
USER_ROLE_SUBCOMPONENT_TYPE = Qt.UserRole + 4  # Sub-component type constant
USER_ROLE_SUBCOMPONENT_VALUE = Qt.UserRole + 5  # Sub-component value
USER_ROLE_HASH = Qt.UserRole + 6             # Sub-component hash
USER_ROLE_MEDIA = Qt.UserRole + 7            # Media path


# =============================================================================
# Sub-component Type Constants
# =============================================================================

NOT_A_SUBCOMPONENT = 0
MEDIA_SUBCOMPONENT = 1
VIEW_SUBCOMPONENT = 2
LAYER_SUBCOMPONENT = 3
CHANNEL_SUBCOMPONENT = 4


# =============================================================================
# Qt Widget Integer Limits
# =============================================================================
# Use 32-bit integer max for Qt widgets (not Python's sys.maxsize which is 64-bit)

INT_MAX = 2147483647  # 2^31 - 1


# =============================================================================
# Context Managers
# =============================================================================

@contextmanager
def block_signals(*widgets):
    """
    Context manager to block and unblock signals on Qt widgets.
    
    This prevents feedback loops when programmatically updating widget values
    that have signal connections (e.g., setCheckState triggering stateChanged).
    
    Usage:
        with block_signals(self._checkBox, self._comboBox, self._lineEdit):
            self._checkBox.setCheckState(Qt.Checked)
            self._comboBox.setCurrentIndex(0)
    
    Args:
        *widgets: Variable number of Qt widgets. None values are safely ignored.
    """
    valid_widgets = [w for w in widgets if w is not None]
    
    # Block signals on all valid widgets
    for w in valid_widgets:
        w.blockSignals(True)
    
    try:
        yield
    finally:
        # Always unblock signals, even if an exception occurred
        for w in valid_widgets:
            w.blockSignals(False)


# =============================================================================
# Helper Functions
# =============================================================================

def safe_get_property(get_func, prop_name, default=None):
    """
    Safely get a property value, returning default if it fails.
    
    Args:
        get_func: The getter function (e.g., commands.getIntProperty)
        prop_name: The property name to get
        default: Default value if property doesn't exist or fails
        
    Returns:
        The property value or default
    """
    try:
        result = get_func(prop_name)
        return result[0] if result else default
    except Exception:
        return default
