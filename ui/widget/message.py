from tkinter import *

class Message(Frame):

    def __init__(self, master, msg):
        super().__init__(master)
        self.msg = msg
        self.setup_ui()
    
    def setup_ui(self):

        self.msg_info = Frame(self, width = 400)
        self.text = Text(self, padx = 15, pady = 3, height = 3, width = 40, bd=0, fg="#264653", bg="#4ecdc4")
        self.text.insert(1.0, self.msg["text"])
        self.text.config(state = DISABLED, font = ("Lucida Grande", 12))

        self.msg_info.pack(fill = BOTH)
        self.text.pack()