from PyQt5.QtGui import QIcon, QImage, QPainter, QPen, QColor
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QFileDialog, QLineEdit
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
        mainMenu = self.menuBar()
        fileMenu = mainMenu.addMenu('File')
        brushMenu = mainMenu.addMenu(QIcon('icons/pen.png'), '')
        brushColor = mainMenu.addMenu(QIcon('icons/pencilColor.png'), '')
        eraserMenu = mainMenu.addMenu(QIcon('icons/eraser.png'), '')

        saveAction = QAction(QIcon('icons/save.png'), 'Save', self)
        saveAction.setShortcut('Ctrl+S')
        fileMenu.addAction(saveAction)
        saveAction.triggered.connect(self.save)

        clearAction = QAction(QIcon('icons/clear.png'), 'Clear', self)
        clearAction.setShortcut('Ctrl+C')
        fileMenu.addAction(clearAction)
        clearAction.triggered.connect(self.clear)

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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.lastPoint = event.pos()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) & self.drawing:
            painter = QPainter(self.image)
            painter.setPen(QPen(self.pencilColor, self.pencilSize, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

            painter.drawLine(self.lastPoint, event.pos())
            self.lastPoint = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = False

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
        self.update()

    def select_eraser(self):
        self.prevPencilColor = self.pencilColor
        self.pencilColor = Qt.white

    def pen3px(self):
        self.pencilSize = 3
        self.pencilColor = self.prevPencilColor
        self.update()

    def pen5px(self):
        self.pencilSize = 5
        self.pencilColor = self.prevPencilColor
        self.update()

    def pen7px(self):
        self.pencilSize = 7
        self.pencilColor = self.prevPencilColor
        self.update()

    def pen9px(self):
        self.pencilSize = 9
        self.pencilColor = self.prevPencilColor
        self.update()

    def eraser3px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 3
        self.prevPencilColor = self.pencilColor
        self.pencilColor = Qt.white

        self.update()

    def eraser5px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 5
        self.pencilColor = self.prevPencilColor
        self.pencilColor = Qt.white
        self.update()

    def eraser7px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 7
        self.pencilColor = self.prevPencilColor
        self.pencilColor = Qt.white
        self.update()

    def eraser9px(self):
        self.prevPencilSize = self.pencilSize
        self.pencilSize = 9
        self.pencilColor = self.prevPencilColor
        self.pencilColor = Qt.white
        self.update()

    def green(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.green
        self.prevPencilColor = Qt.green

    def red(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.red
        self.prevPencilColor = Qt.red

    def blue(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.blue
        self.prevPencilColor = Qt.blue

    def purple(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = QColor(128, 0, 150)
        self.prevPencilColor = QColor(128, 0, 150)

    def black(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.black
        self.prevPencilColor = Qt.black

    def yellow(self):
        self.pencilSize = self.prevPencilSize if self.pencilSize == Qt.white else self.pencilSize
        self.pencilColor = Qt.yellow
        self.prevPencilColor = Qt.yellow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    app.exec()
