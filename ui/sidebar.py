from tkinter import *
from ui.widget import PageButton
from ui.page import *
from util.image import loadImage
from PIL import Image, ImageTk

class SideBar(Frame):

    def __init__(self, master):
        super().__init__(master) 
        self.setup_ui()

    def setup_ui(self):

        self.box = Frame(self, bg = "#00a896")
        self.box.grid_columnconfigure((0, 1, 2), weight = 1)

        logo_img = loadImage("assets/logo.png", (50, 50))
        self.logo = Label(self, image = logo_img, bd = 0)
        self.logo.image = logo_img

        # page button
        self.home_btn    = PageButton(self.box, "home", "assets/home.png")
        self.chat_btn    = PageButton(self.box, "chat", "assets/chat.png") 
        self.setting_btn = PageButton(self.box, "setting", "assets/setting.png")

        self.create_cv()

        self.logo.pack()
        self.home_btn.grid(row = 1, pady = 3, padx = 4)
        self.chat_btn.grid(row = 2, pady = 3, padx = 4)
        self.setting_btn.grid(row = 3, pady = 3, padx = 4)

        self.box.pack(fill = BOTH, expand = True)
        self.cv.pack()

    def create_cv(self):

        # create 2 canvas
        self.cv = Canvas(self, 
            width = 50, height = 150,
            bg = "#00a896", bd = 0, 
            highlightthickness = 0
        )

        # self.cv["height"] = 150

        # create shape
        offset = 0
        length = 50
        color = ["#02c39a", "#028090"]

        for i in [0, 1]:
            #   (0, 0) |\  |
            #          | \ |
            # (0, len) |\ \| (width, len)
            #          | \ |
            #          |  \| (width, len*2)
            self.cv.create_polygon([
                0  , offset + 0, 
                0  , offset + length,
                50 , offset + length*2,
                50 , offset + length
            ], fill = color[i])

            offset += length
