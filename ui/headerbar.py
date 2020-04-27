from tkinter import *
from util.image import loadImage

class HeaderBar(Frame):

    def __init__(self, master):
        super().__init__(master, height=40)
        self.title = StringVar()
        self.setup_ui()

    def setup_ui(self):  

        header_content = Frame(self, bg="#02c39a")
        header_content.pack(fill = BOTH, expand = True, side=LEFT)

        self.page_title = Label(header_content, padx=10, fg="#f0f3bd", textvariable=self.title, bg="#028090")
        self.page_title.config(font=("Lucida Grande ", 14))
        self.page_title.grid(column=0, padx=5, pady=5)

        avt_img = loadImage("assets/user_avt.jpg", (40, 40))
        self.avt = Label(self, image=avt_img, bd=0)
        self.avt.image = avt_img

        self.avt.pack(fill=BOTH, side=LEFT)

        
