"""Main window: menus, docks, status bar, file handling."""
import os
import sys

from PyQt5.QtCore import QPointF, QRectF, QSettings, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPalette
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QDockWidget, QFileDialog, QGridLayout, QLabel,
                             QMainWindow, QMessageBox, QToolButton, QUndoView, QWidget)

from . import __version__, imageutil
from .canvas import Canvas
from .dialogs import CanvasSizeDialog, FilterDialog, NewImageDialog, ResizeDialog, ShortcutsDialog
from .document import FMT, FLAT_EXTS, PROJECT_EXT, Document, blank_image
from .state import AppState
from .tools import TOOL_CLASSES
from .widgets import ColorPanel, LayerPanel, OptionBar, make_icon

OPEN_FILTER = "Images and projects (*.pnt *.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All files (*)"
SAVE_FILTERS = {"Paint project (*.pnt)": "pnt", "PNG image (*.png)": "png", "JPEG image (*.jpg *.jpeg)": "jpg",
                "BMP image (*.bmp)": "bmp", "WebP image (*.webp)": "webp"}
MAX_RECENT_FILES = 8
ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons", "paint.png")


def apply_theme(app, dark):
    app.setStyle("Fusion")
    if not dark:
        app.setPalette(app.style().standardPalette())
        return
    pal = QPalette()
    roles = {
        QPalette.Window: "#2d2d30", QPalette.WindowText: "#e6e6e6", QPalette.Base: "#1f1f22",
        QPalette.AlternateBase: "#2d2d30", QPalette.ToolTipBase: "#3c3c40", QPalette.ToolTipText: "#e6e6e6",
        QPalette.Text: "#e6e6e6", QPalette.Button: "#3a3a3e", QPalette.ButtonText: "#e6e6e6",
        QPalette.BrightText: "#ff5555", QPalette.Link: "#6aa9ff", QPalette.Highlight: "#3d7eff",
        QPalette.HighlightedText: "#ffffff",
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        pal.setColor(QPalette.Disabled, role, QColor("#777777"))
    app.setPalette(pal)


class MainWindow(QMainWindow):
    _windows = []

    def __init__(self, doc=None, settings=None):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.settings = settings if settings is not None else QSettings("PaintApp", "Paint")
        self.state = AppState()
        self.dark = self.settings.value("dark", True, type=bool)
        self._stack = None
        self.doc = doc or Document(1280, 720)
        self.canvas = Canvas(self.doc, self.state)
        self.canvas.set_dark(self.dark)
        self.setCentralWidget(self.canvas)
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setAcceptDrops(True)
        self.resize(1360, 860)

        self.options = OptionBar(self.state)
        self.addToolBar(Qt.TopToolBarArea, self.options)
        self._build_actions()
        self._build_menus()
        self._build_docks()
        self._build_status()
        self._wire()
        self.bind_document(self.doc)
        self.select_tool("brush")
        self._refresh_icons()
        self._rebuild_recent()
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        MainWindow._windows.append(self)

    # ------------------------------------------------------------ construction
    def _act(self, text, slot=None, shortcut=None, checkable=False, tip=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcuts([QKeySequence(s) for s in ([shortcut] if isinstance(shortcut, str) else shortcut)])
        a.setCheckable(checkable)
        if tip:
            a.setStatusTip(tip)
        if slot:
            a.triggered.connect(lambda _checked=False: slot())
        return a

    def _build_actions(self):
        A = self._act
        d = lambda: self.doc
        self.a = dict(
            new=A("&New…", self.new_image, "Ctrl+N"), open=A("&Open…", self.open_dialog, "Ctrl+O"),
            save=A("&Save", self.save, "Ctrl+S"), save_as=A("Save &As…", self.save_as, "Ctrl+Shift+S"),
            close=A("&Close Window", self.close, "Ctrl+W"), quit=A("&Quit", QApplication.closeAllWindows, "Ctrl+Q"),
            undo=A("Undo", lambda: d().undo_stack.undo(), "Ctrl+Z"),
            redo=A("Redo", lambda: d().undo_stack.redo(), ["Ctrl+Y", "Ctrl+Shift+Z"]),
            cut=A("Cu&t", self.cut, "Ctrl+X"), copy=A("&Copy", self.copy, "Ctrl+C"),
            copy_merged=A("Copy &Merged", lambda: self.copy(merged=True), "Ctrl+Shift+C"),
            paste=A("&Paste as New Layer", self.paste, "Ctrl+V"),
            select_all=A("Select &All", lambda: d().select_all(), "Ctrl+A"),
            deselect=A("&Deselect", lambda: d().set_selection(None, "Deselect"), "Ctrl+D"),
            invert_sel=A("&Invert Selection", lambda: d().invert_selection(), "Ctrl+Shift+I"),
            clear=A("C&lear", self.clear_selection, ["Delete", "Backspace"]),
            fill_primary=A("Fill with &Primary Colour", lambda: self.fill_selection(False), "Alt+Backspace"),
            fill_secondary=A("Fill with &Secondary Colour", lambda: self.fill_selection(True), "Ctrl+Backspace"),
            resize=A("&Resize Image…", self.resize_image, "Ctrl+Alt+I"),
            canvas_size=A("&Canvas Size…", self.canvas_size, "Ctrl+Alt+C"),
            crop=A("Crop to &Selection", self.crop, "Ctrl+Shift+X"),
            rot_cw=A("Rotate 90° &Clockwise", lambda: d().rotate(90)),
            rot_ccw=A("Rotate 90° C&ounter-clockwise", lambda: d().rotate(-90)),
            rot_180=A("Rotate &180°", lambda: d().rotate(180)),
            flip_h=A("Flip &Horizontal", lambda: d().flip(True)), flip_v=A("Flip &Vertical", lambda: d().flip(False)),
            flatten=A("&Flatten Image", lambda: d().flatten()),
            layer_new=A("&New Layer", lambda: d().add_layer(), "Ctrl+Shift+N"),
            layer_dup=A("&Duplicate Layer", lambda: d().duplicate_layer(), "Ctrl+J"),
            layer_del=A("D&elete Layer", lambda: d().delete_layer()),
            layer_merge=A("&Merge Down", lambda: d().merge_down(), "Ctrl+E"),
            layer_up=A("Move Layer &Up", lambda: d().move_layer(d().active, 1), "Ctrl+]"),
            layer_down=A("Move Layer D&own", lambda: d().move_layer(d().active, -1), "Ctrl+["),
            layer_flip_h=A("Flip Layer Horizontal", lambda: d().flip_layer(True)),
            layer_flip_v=A("Flip Layer Vertical", lambda: d().flip_layer(False)),
            layer_lock=A("&Lock Layer", self.toggle_lock, checkable=True),
            zoom_in=A("Zoom &In", lambda: self.canvas.zoom_to(self.canvas.zoom * 1.25), ["Ctrl+=", "Ctrl++"]),
            zoom_out=A("Zoom &Out", lambda: self.canvas.zoom_to(self.canvas.zoom / 1.25), "Ctrl+-"),
            fit=A("&Fit to Window", self.canvas.fit, "Ctrl+0"),
            actual=A("&Actual Size", self.canvas.actual_size, "Ctrl+1"),
            grid=A("Show &Grid", self.toggle_grid, "Ctrl+'", checkable=True),
            dark=A("&Dark Theme", self.toggle_theme, checkable=True),
            fullscreen=A("&Full Screen", self.toggle_fullscreen, "F11", checkable=True),
            help=A("&Keyboard Shortcuts", lambda: ShortcutsDialog(self).exec_(), "F1"),
            about=A("&About Paint", self.about),
            swap=A("Swap Colours", self.state.swap_colors, "X"),
            reset=A("Default Colours", self.state.reset_colors, "D"),
            smaller=A("Smaller Brush", lambda: self.step_size(-1), "["),
            bigger=A("Bigger Brush", lambda: self.step_size(1), "]"),
        )
        self.a["dark"].setChecked(self.dark)
        for key in ("undo", "redo", "cut", "copy", "copy_merged", "paste", "select_all", "deselect", "invert_sel",
                    "clear", "fill_primary", "fill_secondary", "swap", "reset", "smaller", "bigger"):
            self.addAction(self.a[key])              # make single-key shortcuts work without a menu

        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        for cls in TOOL_CLASSES:
            act = QAction(cls.label + (" (%s)" % cls.shortcut if cls.shortcut else ""), self)
            act.setCheckable(True)
            if cls.shortcut:
                act.setShortcut(QKeySequence(cls.shortcut))
            act.setStatusTip(cls.hint)
            act.triggered.connect(lambda _c=False, k=cls.key: self.select_tool(k))
            self.tool_group.addAction(act)
            self.tool_actions[cls.key] = act

    def _build_menus(self):
        a, mb = self.a, self.menuBar()
        m = mb.addMenu("&File")
        for k in ("new", "open"):
            m.addAction(a[k])
        self.recent_menu = m.addMenu("Open &Recent")
        m.addSeparator()
        for k in ("save", "save_as"):
            m.addAction(a[k])
        m.addSeparator()
        for k in ("close", "quit"):
            m.addAction(a[k])
        m = mb.addMenu("&Edit")
        for k in ("undo", "redo", None, "cut", "copy", "copy_merged", "paste", None, "select_all", "deselect",
                  "invert_sel", None, "clear", "fill_primary", "fill_secondary"):
            m.addAction(a[k]) if k else m.addSeparator()
        m = mb.addMenu("&Image")
        for k in ("resize", "canvas_size", "crop", None, "rot_cw", "rot_ccw", "rot_180", None, "flip_h", "flip_v",
                  None, "flatten"):
            m.addAction(a[k]) if k else m.addSeparator()
        m = mb.addMenu("&Layer")
        for k in ("layer_new", "layer_dup", "layer_del", "layer_merge", None, "layer_up", "layer_down", None,
                  "layer_flip_h", "layer_flip_v", None, "layer_lock"):
            m.addAction(a[k]) if k else m.addSeparator()
        m = mb.addMenu("&Tools")
        for cls in TOOL_CLASSES:
            m.addAction(self.tool_actions[cls.key])
        m = mb.addMenu("Fi&lters")
        for name in imageutil.FILTERS:
            m.addAction(self._act(name + ("…" if imageutil.FILTERS[name][1] else ""),
                                  lambda n=name: self.run_filter(n)))
        self.view_menu = mb.addMenu("&View")
        for k in ("zoom_in", "zoom_out", "fit", "actual", None, "grid", "dark", "fullscreen", None):
            self.view_menu.addAction(a[k]) if k else self.view_menu.addSeparator()
        m = mb.addMenu("&Help")
        m.addAction(a["help"])
        m.addAction(a["about"])

    def _build_docks(self):
        tools = QWidget()
        grid = QGridLayout(tools)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(2)
        self.tool_buttons = {}
        for i, cls in enumerate(TOOL_CLASSES):
            b = QToolButton()
            b.setDefaultAction(self.tool_actions[cls.key])
            b.setAutoRaise(True)
            b.setIconSize(QSize(22, 22))
            b.setFixedSize(34, 32)
            self.tool_buttons[cls.key] = b
            grid.addWidget(b, i // 3, i % 3)
        grid.setRowStretch(grid.rowCount(), 1)
        self.tools_dock = self._dock("Tools", tools, Qt.LeftDockWidgetArea)
        self.tools_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.tools_dock.setTitleBarWidget(QWidget())
        self.color_panel = ColorPanel(self.state)
        self.color_dock = self._dock("Colour", self.color_panel, Qt.RightDockWidgetArea)
        self.layer_panel = LayerPanel()
        self.layer_dock = self._dock("Layers", self.layer_panel, Qt.RightDockWidgetArea)
        self.history = QUndoView()
        self.history_dock = self._dock("History", self.history, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(self.layer_dock, self.history_dock)
        self.layer_dock.raise_()
        self.resizeDocks([self.color_dock, self.layer_dock], [330, 380], Qt.Vertical)
        self.resizeDocks([self.color_dock], [270], Qt.Horizontal)
        for dock in (self.color_dock, self.layer_dock, self.history_dock):
            self.view_menu.addAction(dock.toggleViewAction())

    def _dock(self, title, widget, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _build_status(self):
        sb = self.statusBar()
        self.pos_label = QLabel("")
        self.sel_label = QLabel("")
        self.size_label = QLabel("")
        self.zoom_label = QLabel("100%")
        for w in (self.pos_label, self.sel_label, self.size_label, self.zoom_label):
            w.setMinimumWidth(90)
            sb.addPermanentWidget(w)

    def _wire(self):
        c, s = self.canvas, self.state
        c.mouseMoved.connect(self._on_mouse)
        c.zoomChanged.connect(lambda z: self.zoom_label.setText("%d%%" % round(z * 100)))
        c.message.connect(lambda t: self.statusBar().showMessage(t, 3000))
        c.toolHint.connect(lambda t: self.statusBar().showMessage(t, 6000))
        s.toolChanged.connect(self._tool_changed)

    # ------------------------------------------------------------ document binding
    def bind_document(self, doc):
        if self._stack is not None:
            for sig in (self._stack.canUndoChanged, self._stack.canRedoChanged, self._stack.undoTextChanged,
                        self._stack.redoTextChanged):
                sig.disconnect(self._sync_undo)
            old = self.doc
            old.titleChanged.disconnect(self._update_title)
            old.selectionChanged.disconnect(self._update_selection)
            old.sizeChanged.disconnect(self._update_size)
            old.layersChanged.disconnect(self._sync_layer_actions)
        self.doc = doc
        self.canvas.set_document(doc)
        self.layer_panel.set_document(doc)
        self.history.setStack(doc.undo_stack)
        self._stack = doc.undo_stack
        for sig in (self._stack.canUndoChanged, self._stack.canRedoChanged, self._stack.undoTextChanged,
                    self._stack.redoTextChanged):
            sig.connect(self._sync_undo)
        doc.titleChanged.connect(self._update_title)
        doc.selectionChanged.connect(self._update_selection)
        doc.sizeChanged.connect(self._update_size)
        doc.layersChanged.connect(self._sync_layer_actions)
        self._sync_undo()
        self._update_title()
        self._update_selection()
        self._update_size()
        self._sync_layer_actions()

    def _sync_undo(self):
        try:
            st = self.doc.undo_stack
            st.canUndo()
        except RuntimeError:                       # stack already destroyed at shutdown
            return
        self.a["undo"].setEnabled(st.canUndo())
        self.a["redo"].setEnabled(st.canRedo())
        self.a["undo"].setText("Undo " + st.undoText() if st.canUndo() else "Undo")
        self.a["redo"].setText("Redo " + st.redoText() if st.canRedo() else "Redo")

    def _sync_layer_actions(self):
        self.a["layer_lock"].setChecked(self.doc.active_layer.locked)

    def _update_title(self):
        self.setWindowTitle("%s[*] — Paint" % self.doc.name)
        self.setWindowModified(self.doc.modified)

    def _update_selection(self):
        sel = self.doc.selection
        if sel is None:
            self.sel_label.setText("")
        else:
            r = sel.boundingRect()
            self.sel_label.setText("Sel %d×%d" % (round(r.width()), round(r.height())))

    def _update_size(self):
        self.size_label.setText("%d×%d px" % (self.doc.size.width(), self.doc.size.height()))

    def _on_mouse(self, p):
        self.pos_label.setText("" if p is None else "%d, %d" % (int(p.x()), int(p.y())))

    # ------------------------------------------------------------ tools
    def select_tool(self, key):
        self.canvas.set_tool(key)
        self._tool_changed(key)

    def _tool_changed(self, key):
        self.tool_actions[key].setChecked(True)
        tool = self.canvas.tools[key]
        self.options.show_for(tool.options, tool.hint)

    def step_size(self, direction):
        size = self.state.size
        step = 1 if size < 10 else 5 if size < 50 else 10
        self.state.set("size", max(1, min(300, size + direction * step)))

    def _refresh_icons(self):
        color = self.palette().color(QPalette.ButtonText)
        for key, act in self.tool_actions.items():
            act.setIcon(make_icon(key, color))
        self.layer_panel.set_icons(lambda k: make_icon(k, color, 20))
        self.color_panel.swap.setIcon(make_icon("swap", color, 20))

    # ------------------------------------------------------------ files
    def _is_pristine(self):
        return self.doc.path is None and not self.doc.modified

    def _show_document(self, doc):
        if self._is_pristine():
            self.bind_document(doc)
            return self
        win = MainWindow(doc, self.settings)
        win.show()
        return win

    def new_image(self):
        dlg = NewImageDialog(self, self.state.secondary)
        if dlg.exec_():
            w, h, color = dlg.result_values()
            doc = Document(w, h, color)
            self._show_document(doc)

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open", self.settings.value("last_dir", ""), OPEN_FILTER)
        for path in paths:
            self.open_path(path)

    def open_path(self, path):
        try:
            doc = Document.open(path)
        except Exception as exc:   # corrupt/unsupported file
            QMessageBox.critical(self, "Open failed", "Could not open %s:\n%s" % (path, exc))
            return None
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)
        return self._show_document(doc)

    def save(self):
        if self.doc.path:
            return self._save_to(self.doc.path)
        return self.save_as()

    def save_as(self):
        filters = list(SAVE_FILTERS)
        if len(self.doc.layers) < 2:
            filters.insert(0, filters.pop(1))      # prefer PNG for single-layer images
        start = self.doc.path or os.path.join(self.settings.value("last_dir", ""), "untitled")
        path, chosen = QFileDialog.getSaveFileName(self, "Save As", start, ";;".join(filters))
        if not path:
            return False
        if "." not in os.path.basename(path):
            path += "." + SAVE_FILTERS.get(chosen, PROJECT_EXT)
        return self._save_to(path)

    def _save_to(self, path):
        if not self.doc.save(path):
            QMessageBox.critical(self, "Save failed", "Could not write %s" % path)
            return False
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in FLAT_EXTS and len(self.doc.layers) > 1:
            self.statusBar().showMessage("Saved a flattened copy. Use a .pnt file to keep layers.", 6000)
        else:
            self.statusBar().showMessage("Saved " + path, 3000)
        return True

    def _add_recent(self, path):
        recent = [p for p in self.settings.value("recent", [], type=list) if p != path]
        recent.insert(0, path)
        self.settings.setValue("recent", recent[:MAX_RECENT_FILES])
        self._rebuild_recent()

    def _rebuild_recent(self):
        self.recent_menu.clear()
        for path in self.settings.value("recent", [], type=list):
            self.recent_menu.addAction(self._act(os.path.basename(path), lambda p=path: self.open_path(p)))
        self.recent_menu.setEnabled(not self.recent_menu.isEmpty())

    def closeEvent(self, e):
        if self.doc.modified:
            box = QMessageBox.question(self, "Unsaved changes", "Save changes to %s?" % self.doc.name,
                                       QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if box == QMessageBox.Cancel or (box == QMessageBox.Save and not self.save()):
                e.ignore()
                return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("dark", self.dark)
        if self in MainWindow._windows:
            MainWindow._windows.remove(self)
        e.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())

    # ------------------------------------------------------------ clipboard & selection
    def copy(self, merged=False):
        doc = self.doc
        if merged:
            src = doc.flattened()
            if doc.selection is not None:
                rect = doc.selection.boundingRect().toAlignedRect().intersected(doc.rect)
                out = blank_image(rect.size())
                p = QPainter(out)
                p.translate(-rect.x(), -rect.y())
                p.setClipPath(doc.selection)
                p.drawImage(0, 0, src)
                p.end()
                src = out
            img = src
        else:
            img = doc.selection_image()
        QApplication.clipboard().setImage(img.convertToFormat(QImage.Format_ARGB32))
        self.statusBar().showMessage("Copied %d×%d" % (img.width(), img.height()), 2000)

    def cut(self):
        if not self.canvas.can_paint():
            return
        self.doc.undo_stack.beginMacro("Cut")
        self.copy()
        self.doc.clear_selection_pixels()
        self.doc.undo_stack.endMacro()

    def paste(self):
        img = QApplication.clipboard().image()
        if img.isNull():
            self.statusBar().showMessage("Clipboard has no image.", 3000)
            return
        img = img.convertToFormat(FMT)
        doc = self.doc
        doc.undo_stack.beginMacro("Paste")
        if img.width() > doc.size.width() or img.height() > doc.size.height():
            doc.resize_canvas(max(img.width(), doc.size.width()), max(img.height(), doc.size.height()), (0, 0))
        origin = self.canvas.to_image(QPointF(24, 24))
        x = max(0, min(int(origin.x()), doc.size.width() - img.width()))
        y = max(0, min(int(origin.y()), doc.size.height() - img.height()))
        layer_img = blank_image(doc.size)
        p = QPainter(layer_img)
        p.drawImage(x, y, img)
        p.end()
        doc.add_layer("Pasted", layer_img, "Paste")
        path = QPainterPath()
        path.addRect(QRectF(x, y, img.width(), img.height()))
        doc.set_selection(path, "Paste selection")
        doc.undo_stack.endMacro()
        self.select_tool("move")

    def clear_selection(self):
        if self.canvas.can_paint():
            self.doc.clear_selection_pixels()

    def fill_selection(self, secondary):
        if self.canvas.can_paint():
            self.doc.fill_selection(self.state.secondary if secondary else self.state.primary)

    # ------------------------------------------------------------ image / layer operations
    def resize_image(self):
        dlg = ResizeDialog(self, self.doc.size.width(), self.doc.size.height())
        if dlg.exec_():
            self.doc.resize_image(dlg.w.value(), dlg.h.value(), dlg.smooth.isChecked())

    def canvas_size(self):
        dlg = CanvasSizeDialog(self, self.doc.size.width(), self.doc.size.height())
        if dlg.exec_():
            self.doc.resize_canvas(dlg.w.value(), dlg.h.value(), dlg.anchor_value())

    def crop(self):
        if self.doc.selection is None:
            self.statusBar().showMessage("Make a selection first.", 3000)
            return
        self.doc.crop_to_rect(self.doc.selection.boundingRect().toAlignedRect())

    def toggle_lock(self):
        layer = self.doc.active_layer
        self.doc.set_layer_prop(layer, "locked", not layer.locked, "Lock layer")

    def run_filter(self, name):
        if not self.canvas.can_paint():
            return
        func, params = imageutil.FILTERS[name]
        if params:
            FilterDialog(self, self.doc, name, func, params).exec_()
        else:
            self.doc.modify_layer(name, lambda im: imageutil.from_array(func(imageutil.to_array(im))))

    # ------------------------------------------------------------ view
    def toggle_grid(self):
        self.canvas.show_grid = self.a["grid"].isChecked()
        self.canvas.update()

    def toggle_theme(self):
        self.dark = self.a["dark"].isChecked()
        self.settings.setValue("dark", self.dark)
        apply_theme(QApplication.instance(), self.dark)
        for win in MainWindow._windows:
            win.dark = self.dark
            win.a["dark"].setChecked(self.dark)
            win.canvas.set_dark(self.dark)
            win._refresh_icons()

    def toggle_fullscreen(self):
        self.showFullScreen() if self.a["fullscreen"].isChecked() else self.showNormal()

    def about(self):
        QMessageBox.about(self, "About Paint", "<h3>Paint %s</h3><p>A layered raster editor built with PyQt5.</p>"
                          "<p>Layers, blend modes, selections, 25 tools, filters, symmetry painting, "
                          "unlimited-style history and a project format that keeps your layers.</p>" % __version__)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("Paint")
    app.setOrganizationName("PaintApp")
    dark = QSettings("PaintApp", "Paint").value("dark", True, type=bool)
    apply_theme(app, dark)
    win = MainWindow()
    win.show()
    for path in argv[1:]:
        if os.path.isfile(path):
            win = win.open_path(path) or win
    return app.exec_()
