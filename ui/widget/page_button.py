from tkinter import *
from util.image import loadImage
import remote

class PageButton(Button):

    def __init__(self, master, page, file):
        img = loadImage(file, (40, 40))

        super().__init__(master, 
            activebackground = "#028090", 
            command = lambda: remote.ee.emit("change_page", page, "# " + page), 
            bg = "#05668d", bd = 0, 
            image = img
        )

        self.image = img
