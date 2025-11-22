from PyQt5.QtGui import QIcon, QImage, QPainter, QPen, QColor
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QFileDialog, QColorDialog, QSpinBox, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, QPoint
import sys

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        top = 400
        left = 400
        width = 800
        height = 600
        icon = "icons/paint.png"
        self.setWindowTitle('Paint Application')
        self.setGeometry(top, left, width, height)
        self.setWindowIcon(QIcon(icon))
        self.image = QImage(self.size(), QImage.Format_RGB32)
        self.image.fill(Qt.white)
        self.drawing = False
        self.pencilSize = 3
        self.brushSize = 3
        self.brushColor = Qt.black
        self.prevPencilSize = 3
        self.pencilColor = Qt.black
        self.prevPencilColor = Qt.black
        self.eraserColor = Qt.white
        self.lastPoint = QPoint()
        
        # History for Undo/Redo
        self.history = [self.image.copy()]
        self.history_index = 0
        
        # Shape drawing mode
        self.shape_mode = None
        self.shape_start_point = QPoint()
        
        # Brush style
        self.brush_style = Qt.SolidLine
        
        mainMenu = self.menuBar()
        fileMenu = mainMenu.addMenu('File')
        brushMenu = mainMenu.addMenu(QIcon('icons/pen.png'), '')
        brushColor = mainMenu.addMenu(QIcon('icons/pencilColor.png'), '')
        eraserMenu = mainMenu.addMenu(QIcon('icons/eraser.png'), '')
        editMenu = mainMenu.addMenu('Edit')
        shapesMenu = mainMenu.addMenu('Shapes')
        
        # File Menu
        saveAction = QAction(QIcon('icons/save.png'), 'Save', self)
        saveAction.setShortcut('Ctrl+S')
        fileMenu.addAction(saveAction)
        saveAction.triggered.connect(self.save)

        clearAction = QAction(QIcon('icons/clear.png'), 'Clear', self)
        clearAction.setShortcut('Ctrl+C')
        fileMenu.addAction(clearAction)
        clearAction.triggered.connect(self.clear)

        # Brush Size Menu
        threepx = QAction(QIcon('icons/3.png'), '3px', self)
        threepx.setShortcut('Ctrl+3')
        brushMenu.addAction(threepx)
        threepx.triggered.connect(self.pen3px)

        fivepx = QAction(QIcon('icons/5.png'), '5px', self)
        fivepx.setShortcut('Ctrl+5')
        brushMenu.addAction(fivepx)
        fivepx.triggered.connect(self.pen5px)

        sevenpx = QAction(QIcon('icons/7.png'), '7px', self)
        sevenpx.setShortcut('Ctrl+7')
        brushMenu.addAction(sevenpx)
        sevenpx.triggered.connect(self.pen7px)

        ninepx = QAction(QIcon('icons/9.png'), '9px', self)
        ninepx.setShortcut('Ctrl+9')
        brushMenu.addAction(ninepx)
        ninepx.triggered.connect(self.pen9px)

        # Eraser Menu
        eraser3px = QAction(QIcon('icons/3.png'), '3px', self)
        eraser3px.setShortcut('Ctrl+Alt+3')
        eraserMenu.addAction(eraser3px)
        eraser3px.triggered.connect(self.eraser3px)

        eraser5px = QAction(QIcon('icons/5.png'), '5px', self)
        eraser5px.setShortcut('Ctrl+Alt+5')
        eraserMenu.addAction(eraser5px)
        eraser5px.triggered.connect(self.eraser5px)

        eraser7px = QAction(QIcon('icons/7.png'), '7px', self)
        eraser7px.setShortcut('Ctrl+Alt+7')
        eraserMenu.addAction(eraser7px)
        eraser7px.triggered.connect(self.eraser7px)

        eraser9px = QAction(QIcon('icons/9.png'), '9px', self)
        eraser9px.setShortcut('Ctrl+Alt+9')
        eraserMenu.addAction(eraser9px)
        eraser9px.triggered.connect(self.eraser9px)

        # Color Menu
        blackAction = QAction(QIcon('icons/black.png'), 'Black', self)
        blackAction.setShortcut('Ctrl+b')
        brushColor.addAction(blackAction)
        blackAction.triggered.connect(self.black)

        blueAction = QAction(QIcon('icons/blue.png'), 'Blue', self)
        blueAction.setShortcut('Ctrl+Alt+b')
        brushColor.addAction(blueAction)
        blueAction.triggered.connect(self.blue)

        purpleAction = QAction(QIcon('icons/purple.png'), 'Purple', self)
        purpleAction.setShortcut('Ctrl+p')
        brushColor.addAction(purpleAction)
        purpleAction.triggered.connect(self.purple)

        yellowAction = QAction(QIcon('icons/yellow.png'), 'Yellow', self)
        yellowAction.setShortcut('Ctrl+y')
        brushColor.addAction(yellowAction)
        yellowAction.triggered.connect(self.yellow)

        greenAction = QAction(QIcon('icons/green.png'), 'Green', self)
        greenAction.setShortcut('Ctrl+g')
        brushColor.addAction(greenAction)
        greenAction.triggered.connect(self.green)

        redAction = QAction(QIcon('icons/red.png'), 'Red', self)
        redAction.setShortcut('Ctrl+r')
        brushColor.addAction(redAction)
        redAction.triggered.connect(self.red)
        
        # Custom Color
        customColorAction = QAction('Custom Color', self)
        customColorAction.setShortcut('Ctrl+Shift+c')
        brushColor.addAction(customColorAction)
        customColorAction.triggered.connect(self.pick_color)

        # Edit Menu (Undo/Redo)
        undoAction = QAction('Undo', self)
        undoAction.setShortcut('Ctrl+Z')
        editMenu.addAction(undoAction)
        undoAction.triggered.connect(self.undo)

        redoAction = QAction('Redo', self)
        redoAction.setShortcut('Ctrl+Y')
        editMenu.addAction(redoAction)
        redoAction.triggered.connect(self.redo)

        # Shapes Menu
        lineAction = QAction('Draw Line', self)
        lineAction.setShortcut('Ctrl+l')
        shapesMenu.addAction(lineAction)
        lineAction.triggered.connect(self.set_line_mode)

        circleAction = QAction('Draw Circle', self)
        circleAction.setShortcut('Ctrl+o')
        shapesMenu.addAction(circleAction)
        circleAction.triggered.connect(self.set_circle_mode)

        rectAction = QAction('Draw Rectangle', self)
        rectAction.setShortcut('Ctrl+e')
        shapesMenu.addAction(rectAction)
        rectAction.triggered.connect(self.set_rect_mode)
        
        pencilAction = QAction('Free Draw', self)
        pencilAction.setShortcut('Ctrl+f')
        shapesMenu.addAction(pencilAction)
        pencilAction.triggered.connect(self.set_pencil_mode)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.lastPoint = event.pos()
            self.shape_start_point = event.pos()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) & self.drawing:
            if self.shape_mode == "pencil":
                painter = QPainter(self.image)
                painter.setPen(QPen(self.pencilColor, self.pencilSize, self.brush_style, Qt.RoundCap, Qt.RoundJoin))
                painter.drawLine(self.lastPoint, event.pos())
                self.lastPoint = event.pos()
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            
            if self.shape_mode in ["line", "circle", "rect"]:
                self.draw_shape(self.shape_start_point, event.pos())
            
            self.save_history()

    def draw_shape(self, start_point, end_point):
        painter = QPainter(self.image)
        painter.setPen(QPen(self.pencilColor, self.pencilSize, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        
        if self.shape_mode == "line":
            painter.drawLine(start_point, end_point)
        
        elif self.shape_mode == "circle":
            radius = int(((end_point.x() - start_point.x())**2 + (end_point.y() - start_point.y())**2)**0.5)
            painter.drawEllipse(start_point, radius, radius)
        
        elif self.shape_mode == "rect":
            painter.drawRect(start_point.x(), start_point.y(), 
                           end_point.x() - start_point.x(), 
                           end_point.y() - start_point.y())
        
        self.update()

    def paintEvent(self, event):
        canvasPainter = QPainter(self)
        canvasPainter.drawImage(self.rect(), self.image, self.image.rect())

    def save(self):
        filePath, _ = QFileDialog.getSaveFileName(self, "Save Image", "",
                                                  "PNG(*.png);;JPEG(*.jpg *.jpeg);;All Files (*)")
        if filePath == "":
            return
        self.image.save(filePath)

    def clear(self):
        self.image.fill(Qt.white)
        self.save_history()
        self.update()

    def save_history(self):
        self.history = self.history[:self.history_index + 1]
        self.history.append(self.image.copy())
        self.history_index += 1

    def undo(self):
        if self.history_index > 0:
            self.history_index -= 1
            self.image = self.history[self.history_index].copy()
            self.update()

    def redo(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.image = self.history[self.history_index].copy()
            self.update()

    def pick_color(self):
        color = QColorDialog.getColor(self.pencilColor, self, "انتخاب رنگ")
        if color.isValid():
            self.pencilColor = color
            self.prevPencilColor = color

    def set_line_mode(self):
        self.shape_mode = "line"
    
    def set_circle_mode(self):
        self.shape_mode = "circle"
    
    def set_rect_mode(self):
        self.shape_mode = "rect"
    
    def set_pencil_mode(self):
        self.shape_mode = "pencil"

    def pen3px(self):
        self.pencilSize = 3
        self.pencilColor = self.prevPencilColor
        self.shape_mode = "pencil"
        self.update()

    def pen5px(self):
        self.pencilSize = 5
        self.pencilColor = self.prevPencilColor
        self.shape_mode = "pencil"
        self.update()

    def pen7px(self):
        self.pencilSize = 7
        self.pencilColor = self.prevPencilColor
        self.shape_mode = "pencil"
        self.update()

    def pen9px(self):
        self.pencilSize = 9
        self.pencilColor = self.prevPencilColor
        self.shape_mode = "pencil"
        self.update()

    def eraser3px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 3
        self.prevPencilColor = self.pencilColor
        self.pencilColor = Qt.white
        self.shape_mode = "pencil"
        self.update()

    def eraser5px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 5
        self.prevPencilColor = self.pencilColor
        self.pencilColor = Qt.white
        self.shape_mode = "pencil"
        self.update()

    def eraser7px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 7
        self.prevPencilColor = self.pencilColor
        self.pencilColor = Qt.white
        self.shape_mode = "pencil"
        self.update()

    def eraser9px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 9
        self.prevPencilColor = self.pencilColor
        self.pencilColor = Qt.white
        self.shape_mode = "pencil"
        self.update()

    def green(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.green
        self.prevPencilColor = Qt.green
        self.shape_mode = "pencil"

    def red(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.red
        self.prevPencilColor = Qt.red
        self.shape_mode = "pencil"

    def blue(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.blue
        self.prevPencilColor = Qt.blue
        self.shape_mode = "pencil"

    def purple(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = QColor(128, 0, 150)
        self.prevPencilColor = QColor(128, 0, 150)
        self.shape_mode = "pencil"

    def black(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.black
        self.prevPencilColor = Qt.black
        self.shape_mode = "pencil"

    def yellow(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.yellow
        self.prevPencilColor = Qt.yellow
        self.shape_mode = "pencil"


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    app.exec()
