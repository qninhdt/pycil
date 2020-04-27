from tkinter import *

class HomePage(Frame):

    def __init__(self, master):
        super().__init__(master)

        text = Label(self, text="HOME")
        text.pack()