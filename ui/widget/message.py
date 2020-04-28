from tkinter import *

class Message(Frame):

    def __init__(self, master, msg, show_username = True):
        super().__init__(master)
        self.msg = msg
        self.show_username = show_username
        self.setup_ui()
    
    def setup_ui(self):

        self.msg_info = Frame(self, width = 400)

        if self.show_username:
            self.username = Label(self.msg_info, text = self.msg["user"], anchor = W)
            self.username.pack(side = LEFT)

        self.text = Text(self, padx = 15, pady = self.show_username, width = 38, bd=0, fg="#264653", bg="#4ecdc4")
        self.text.config(height = min(10, int(len(self.msg["text"])/38)))
        self.text.insert(1.0, self.msg["text"])
        self.text.config(state = DISABLED, font = ("Lucida Grande", 12))

        self.msg_info.pack(fill = BOTH)
        self.text.pack()