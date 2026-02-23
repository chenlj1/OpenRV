#
# Copyright (C) 2023  Autodesk, Inc. All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
"""Transform manip - 2D transform manipulation mode for manual layout."""

import math

from rv import rvtypes
from rv import commands
from rv import extra_commands

# The glyph module is Mu-only, stub it out for Python
class _GlyphStub:
    """Stub for glyph module - functions are no-ops."""
    @staticmethod
    def circleGlyph(filled):
        pass
    @staticmethod
    def translateIconGlyph(filled):
        pass

try:
    from rv import glyph
except ImportError:
    glyph = _GlyphStub()


# PySide2/PySide6 compatibility
try:
    from PySide2.QtCore import Qt
    # PySide2 enums are integers
    def cursor_value(cursor):
        return cursor
except ImportError:
    from PySide6.QtCore import Qt
    # PySide6 enums need .value
    def cursor_value(cursor):
        return cursor.value

def cursor_value(cursor):
    """Get integer value from cursor enum for commands.setCursor()."""
    return cursor.value

from OpenGL.GL import *
from OpenGL.GLU import *


# Control types
NoControl = 0
FreeTranslation = 1
TopLeftCorner = 2
TopRightCorner = 3
BotLeftCorner = 4
BotRightCorner = 5


def setStringTagProperty(propName, value):
    """Helper to set string property, creating it if needed."""
    try:
        if not commands.propertyExists(propName):
            commands.newProperty(propName, commands.StringType, 1)
        commands.setStringProperty(propName, [value], True)
    except Exception:
        # Property creation may fail on certain node types
        pass


class EditNodePair:
    """Holds transform node and input node pair."""
    def __init__(self, tformNode, inputNode):
        self.tformNode = tformNode
        self.inputNode = inputNode


class TransformManip(rvtypes.MinorMode):
    """2D transform manipulation mode."""

    def __init__(self):
        rvtypes.MinorMode.__init__(self)
        self._editNodes = []
        self._currentEditNode = None
        self._control = NoControl
        self._gc = (0.0, 0.0)
        self._corner = (0.0, 0.0)
        self._downPoint = (0.0, 0.0)
        self._editing = False
        self._didDrag = False

        self.init(
            "transform_manip",
            None,
            [
                ("pointer--move", self.move, "Search for Image"),
                ("pointer-1--push", self.push, "Grab Tile"),
                ("pointer-1--drag", self.drag, "Move/Scale Tile"),
                ("pointer-1--release", self.release, ""),
                ("graph-node-inputs-changed", self.nodeInputsChanged, "Update session UI"),
                ("after-graph-view-change", self.afterGraphViewChange, "Update UI"),
                ("before-graph-view-change", self.beforeGraphViewChange, "Update UI"),
                ("stylus-pen--move", self.move, "Search for Nearest Edge"),
                ("stylus-pen--push", self.push, "Move"),
                ("stylus-pen--drag", self.drag, "Move"),
                ("stylus-pen--release", self.release, ""),
            ],
            [
                ("Layout", [
                    ("_", None),
                    ("Fit All Images", self.fitAll, None, None),
                    ("Reset All Manips", self.resetAll, None, None),
                ])
            ],
            "zza"  # Process nearly last
        )

    def tagValue(self, tags, name):
        """Get tag value from tags list."""
        for n, v in tags:
            if n == name:
                return v
        return None

    def editNode(self, name):
        """Find edit node pair by transform node name."""
        for enode in self._editNodes:
            if enode.tformNode == name:
                return enode
        return None

    def activeImageIndex(self):
        """Get index of image with active manip state."""
        for i in commands.renderedImages():
            # Handle both object and dict access for renderedImages results
            i_tags = i["tags"] if isinstance(i, dict) else i.tags
            i_index = i["index"] if isinstance(i, dict) else i.index
            v = self.tagValue(i_tags, "tmanip_state")
            if v is not None and v != "":
                return i_index
        return -1

    def setManipState(self, p, value):
        """Set manip state tag on node."""
        if p is not None:
            if commands.nodeExists(p.tformNode):
                setStringTagProperty(p.tformNode + ".tag.tmanip_state", value)

    def computeGC(self, corners):
        """Compute geometric center of corners."""
        gc = [0.0, 0.0]
        for c in corners:
            gc[0] += c[0]
            gc[1] += c[1]
        gc[0] /= len(corners)
        gc[1] /= len(corners)
        return tuple(gc)

    def control(self, index, event):
        """Determine which control point is under the pointer."""
        corners = commands.imageGeometryByIndex(index)
        p = event.pointer()
        gc = self.computeGC(corners)

        for c in corners:
            v = (p[0] - c[0], p[1] - c[1])

            if abs(v[0]) < 25 and abs(v[1]) < 25:
                if c[0] < gc[0]:
                    ctrl = TopLeftCorner if c[1] > gc[1] else BotLeftCorner
                else:
                    ctrl = TopRightCorner if c[1] > gc[1] else BotRightCorner
                return (ctrl, gc, c)

        return (FreeTranslation, gc, gc)

    def move(self, event):
        """Handle pointer move - search for image under cursor."""
        last = self._currentEditNode
        self._currentEditNode = None
        self._control = NoControl
        commands.setCursor(cursor_value(Qt.ArrowCursor))

        for p in commands.imagesAtPixel(event.pointer()):
            # In Python, imagesAtPixel returns dicts, not objects
            p_inside = p["inside"] if isinstance(p, dict) else p.inside
            if p_inside:
                p_tags = p["tags"] if isinstance(p, dict) else p.tags
                p_index = p["index"] if isinstance(p, dict) else p.index
                v = self.tagValue(p_tags, "tmanip")

                if v is not None:
                    self._currentEditNode = self.editNode(v)
                    self.setManipState(self._currentEditNode, "hover")
                    con, gc, corner = self.control(p_index, event)
                    self._control = con
                    self._gc = gc
                    self._corner = corner

                    if self._control == TopRightCorner:
                        commands.setCursor(cursor_value(Qt.SizeBDiagCursor))
                    elif self._control == BotLeftCorner:
                        commands.setCursor(cursor_value(Qt.SizeBDiagCursor))
                    elif self._control == TopLeftCorner:
                        commands.setCursor(cursor_value(Qt.SizeFDiagCursor))
                    elif self._control == BotRightCorner:
                        commands.setCursor(cursor_value(Qt.SizeFDiagCursor))
                    elif self._control == FreeTranslation:
                        commands.setCursor(cursor_value(Qt.OpenHandCursor))
                    else:
                        commands.setCursor(cursor_value(Qt.WhatsThisCursor))
                    break

        if last is not self._currentEditNode:
            if last is not None:
                self.setManipState(last, "")
            commands.redraw()

        event.reject()

    def push(self, event):
        """Handle pointer push - start manipulation."""
        if self._currentEditNode is not None:
            commands.setCursor(cursor_value(Qt.ClosedHandCursor))
            self.setManipState(self._currentEditNode, "editing")

            if self.activeImageIndex() == -1:
                return

            self._downPoint = event.pointer()
            self._didDrag = False
            self._editing = True
            commands.redraw()

    def mag(self, v):
        """Calculate magnitude of 2D vector."""
        return math.sqrt(v[0] * v[0] + v[1] * v[1])

    def normalize(self, v):
        """Normalize 2D vector."""
        m = self.mag(v)
        if m == 0:
            return (0.0, 0.0)
        return (v[0] / m, v[1] / m)

    def dot(self, a, b):
        """Dot product of 2D vectors."""
        return a[0] * b[0] + a[1] * b[1]

    def drag(self, event):
        """Handle pointer drag - perform manipulation."""
        if self._currentEditNode is not None:
            index = self.activeImageIndex()
            commands.setCursor(cursor_value(Qt.ClosedHandCursor))

            if index == -1:
                return

            tformNode = self._currentEditNode.tformNode
            transProp = "%s.transform.translate" % tformNode
            scaleProp = "%s.transform.scale" % tformNode
            trans = commands.getFloatProperty(transProp)
            scale = commands.getFloatProperty(scaleProp)
            corners = commands.imageGeometryByIndex(index)
            a, b, c, d = corners[0], corners[1], corners[2], corners[3]
            pp = event.pointer()
            dp = self._downPoint
            ip = (pp[0] - dp[0], pp[1] - dp[1])
            ba = self.mag((b[0] - a[0], b[1] - a[1]))
            da = self.mag((d[0] - a[0], d[1] - a[1]))
            aspect = ba / da if da != 0 else 1.0
            dx = ip[0] / ba * scale[0] * aspect if ba != 0 else 0
            dy = ip[1] / da * scale[1] if da != 0 else 0

            diagDir = self.normalize((self._corner[0] - self._gc[0], self._corner[1] - self._gc[1]))
            diagDist = self.dot((pp[0] - self._gc[0], pp[1] - self._gc[1]), diagDir)
            downDist = self.dot((self._downPoint[0] - self._gc[0], self._downPoint[1] - self._gc[1]), diagDir)
            diff = diagDist - downDist
            scl = (diagDist - diff / 2.0) / downDist if downDist != 0 else 1.0
            sv = (diff * diagDir[0], diff * diagDir[1])
            sdx = sv[0] / ba * scale[0] * aspect if ba != 0 else 0
            sdy = sv[1] / da * scale[1] if da != 0 else 0

            if self._control == FreeTranslation:
                commands.setFloatProperty(transProp, [trans[0] + dx, trans[1] + dy], True)
            else:
                commands.setFloatProperty(transProp, [trans[0] + sdx / 2.0, trans[1] + sdy / 2.0], True)
                newscale = max(scale[0] * scl, 0.01)
                commands.setFloatProperty(scaleProp, [newscale, scale[1] * newscale / scale[0] if scale[0] != 0 else newscale], True)

            self._downPoint = pp
            self._didDrag = True
            commands.redraw()

    def release(self, event):
        """Handle pointer release - end manipulation."""
        if self._editing:
            self.setManipState(self._currentEditNode, "hover")
            commands.setCursor(cursor_value(Qt.OpenHandCursor))
        else:
            commands.setCursor(cursor_value(Qt.ArrowCursor))

        self._didDrag = False
        self._editing = False

    def resetAll(self, event):
        """Reset all transform manips to default."""
        for enode in self._editNodes:
            tformNode = enode.tformNode
            transProp = "%s.transform.translate" % tformNode
            scaleProp = "%s.transform.scale" % tformNode
            rotProp = "%s.transform.rotate" % tformNode

            commands.setFloatProperty(transProp, [0.0, 0.0], True)
            commands.setFloatProperty(scaleProp, [1.0, 1.0], True)
            commands.setFloatProperty(rotProp, [0.0], True)

        commands.redraw()

    def nodeAspect(self, node):
        """Get aspect ratio of node."""
        try:
            geom = commands.nodeImageGeometry(commands.viewNode(), commands.frame())
            pa = geom.pixelAspect
            xps = pa if pa > 1.0 else 1.0
            yps = pa if pa < 1.0 else 1.0
            return (geom.width * xps) / (geom.height / yps) if geom.height != 0 else 1.0
        except Exception:
            return 1.0

    def fitAll(self, event):
        """Fit all images to view."""
        aspect = self.nodeAspect(commands.viewNode())

        for enode in self._editNodes:
            tformNode = enode.tformNode
            transProp = "%s.transform.translate" % tformNode
            scaleProp = "%s.transform.scale" % tformNode
            rotProp = "%s.transform.rotate" % tformNode

            inaspect = self.nodeAspect(tformNode)
            s = aspect / inaspect if inaspect != 0 else 1.0

            commands.setFloatProperty(transProp, [0.0, 0.0], True)
            commands.setFloatProperty(scaleProp, [s, s], True)
            commands.setFloatProperty(rotProp, [0.0], True)

        commands.redraw()

    def removeTags(self):
        """Remove manipulation tags from all nodes."""
        for x in self._editNodes:
            node = x.tformNode
            pmanip = node + ".tag.tmanip"
            pstate = node + ".tag.tmanip_state"

            for p in [pmanip, pstate]:
                if commands.propertyExists(p):
                    commands.deleteProperty(p)

    def findEditingNodes(self, setStates=True):
        """Find all editing nodes in current view."""
        vnode = commands.viewNode()
        if vnode is None:
            self._editNodes = []
            return

        try:
            infos = commands.metaEvaluateClosestByType(commands.frame(), "RVTransform2D")
            ins, outs = commands.nodeConnections(vnode, False)
        except Exception:
            self._editNodes = []
            return

        self._editNodes = []

        # Check for size mismatch (happens when shutting down or deletion)
        if len(infos) != len(ins):
            return

        for i, info in enumerate(infos):
            # In Python, imagesAtPixel returns dicts, not objects
            node = info["node"] if isinstance(info, dict) else info.node
            pname = node + ".tag.tmanip"
            sname = node + ".tag.tmanip_state"

            self._editNodes.append(EditNodePair(node, ins[i]))

            if setStates or not commands.propertyExists(pname):
                setStringTagProperty(pname, node)
                setStringTagProperty(sname, "")

    def nodeInputsChanged(self, event):
        """Handle node inputs changed event."""
        node = event.contents()
        vnode = commands.viewNode()

        # Don't set the node states in this case
        if vnode is not None and node == vnode:
            self.findEditingNodes(False)

    def afterGraphViewChange(self, event):
        self.findEditingNodes()
        event.reject()

    def beforeGraphViewChange(self, event):
        self.removeTags()
        event.reject()

    def activate(self):
        rvtypes.MinorMode.activate(self)
        self.findEditingNodes()

    def deactivate(self):
        commands.setCursor(cursor_value(Qt.ArrowCursor))
        self.removeTags()
        rvtypes.MinorMode.deactivate(self)

    def setupProjection(self, w, h, flip):
        """Set up orthographic projection for rendering."""
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if flip:
            gluOrtho2D(0.0, float(w), float(h), 0.0)
        else:
            gluOrtho2D(0.0, float(w), 0.0, float(h))
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def render(self, event):
        """Render manipulation UI overlay."""
        if self._currentEditNode is None:
            return

        state = commands.data()
        domain = event.domain()
        bg = state.config.bg if hasattr(state, 'config') else (0.18, 0.18, 0.18, 1.0)
        fg = state.config.fg if hasattr(state, 'config') else (0.9, 0.9, 0.9, 1.0)
        index = self.activeImageIndex()

        if index == -1:
            return

        self.setupProjection(domain[0], domain[1], event.domainVerticalFlip())

        try:
            corners = commands.imageGeometryByIndex(index)
            gc = self.computeGC(corners)
            self._gc = gc

            glEnable(GL_BLEND)
            glEnable(GL_LINE_SMOOTH)
            glEnable(GL_POINT_SMOOTH)
            glLineWidth(2.0)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            # Draw outline
            glColor4f(1, 1, 1, 0.5)
            glBegin(GL_LINE_LOOP)
            for c in corners:
                glVertex2f(c[0], c[1])
            glEnd()

            # Draw corners
            self.drawCorners(corners, 25, 0.0, (0, 0, 0, 0.5), 8.0)
            self.drawCorners(corners, 25, 0.0, (1, 1, 1, 0.5), 6.0)

            glLineWidth(1.5)

            # Draw center handle
            glPushMatrix()
            glTranslatef(gc[0], gc[1], 0.0)
            glScalef(25.0, 25.0, 25.0)
            glColor4f(bg[0], bg[1], bg[2], 0.5)
            glyph.circleGlyph(False)
            glyph.circleGlyph(True)
            glPopMatrix()

            glPushMatrix()
            glTranslatef(gc[0], gc[1], 0.0)
            glScalef(25.0, 25.0, 25.0)
            glColor4f(fg[0], fg[1], fg[2], fg[3] if len(fg) > 3 else 1.0)
            glyph.translateIconGlyph(False)
            glColor4f(fg[0] * 0.5, fg[1] * 0.5, fg[2] * 0.5, 1.0)
            glLineWidth(1.0)
            glyph.translateIconGlyph(True)
            glPopMatrix()

            glDisable(GL_BLEND)
        except Exception:
            pass  # OpenGL errors are expected in some contexts

    def drawCorners(self, corners, mult, width, color, lineWidth):
        """Draw corner handles."""
        glColor4f(color[0], color[1], color[2], color[3])
        glLineWidth(lineWidth)

        for i, c in enumerate(corners):
            i0 = 3 if i == 0 else i - 1
            i1 = (i + 1) % 4
            c0 = corners[i0]
            c1 = corners[i1]

            m0 = self.mag((c0[0] - c[0], c0[1] - c[1]))
            m1 = self.mag((c1[0] - c[0], c1[1] - c[1]))

            if m0 == 0 or m1 == 0:
                continue

            dir0 = ((c0[0] - c[0]) / m0, (c0[1] - c[1]) / m0)
            dir1 = ((c1[0] - c[0]) / m1, (c1[1] - c[1]) / m1)

            nmult = 0.0 if m1 / 2.0 < mult or m0 / 2.0 < mult else mult

            glBegin(GL_LINES)
            glVertex2f(c[0] + dir0[0] * nmult, c[1] + dir0[1] * nmult)
            glVertex2f(c[0] - dir0[0] * width, c[1] - dir0[1] * width)
            glVertex2f(c[0] + dir1[0] * nmult, c[1] + dir1[1] * nmult)
            glVertex2f(c[0] - dir1[0] * width, c[1] - dir1[1] * width)
            glEnd()


def createMode():
    return TransformManip()
