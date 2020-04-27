from tkinter import *

class SettingPage(Frame):

    def __init__(self, master):
        super().__init__(master)

        text = Label(self, text = "SETTING")
        text.pack(side = LEFT)