from tkinter import *
from ui.widget import ScrollView, Message
import remote

class ChatRoom(Frame):

    def __init__(self, master, room):
        super().__init__(master)
        self.room = room

        remote.ee.emit("login", self.room, remote.user["name"])

        @remote.ee.on("fetch_data")
        def fetch_data(data):
            self.room["msg"] = data["msg"]
            self.room["users"] = data["users"]

            self.setup_ui()

        @remote.ee.on("new_msg")
        def on_new_msg(msg):

            Message(self.msg_panel.frame, msg).grid(
                column = 0, 
                row = len(self.room["msg"]), 
                padx = 0, pady = 5
            )

            self.room["msg"].append(msg)

            self.msg_panel.canvas.update_idletasks()
            self.msg_panel.canvas.yview_moveto(1)

        @remote.ee.on("connect_server_ok")
        def on_connect_server_ok():
            pass

        @remote.ee.on("connect_server_error")
        def on_connect_server_error():
            remote.ee.emit("change_page", "chat", "# chat")

    
    def setup_ui(self):

        self.chat_panel = Frame(self)
        self.msg_panel = ScrollView(self.chat_panel, bd=0)
        self.room_panel = ScrollView(self)
        self.input_panel = Frame(self.chat_panel)
        
        self.input_value = StringVar("")
        self.input = Entry(self.input_panel, textvariable = self.input_value)
        self.input.config(font = ("Lucida Grande", 11))

        self.send_btn = Button(self.input_panel, text = "▶",
            command = lambda: self.send_msg()
        )

        self.chat_panel.pack(side = LEFT, fill = BOTH, expand = True)
        self.room_panel.pack(side = LEFT, fill = BOTH, expand = True)

        self.msg_panel.pack(fill = BOTH, expand = True)
        self.input_panel.pack(fill = BOTH)
        self.input.pack(side = LEFT, expand = True, fill = BOTH)
        self.send_btn.pack(side = RIGHT)

        for idx, msg in enumerate(self.room["msg"]):
            Message(self.msg_panel.frame, msg).grid(column = 0, row = idx, padx = 0, pady = 5)

        self.msg_panel.canvas.update_idletasks()
        self.msg_panel.canvas.yview_moveto(1)

    def send_msg(self):
        if self.input_value.get():
            remote.ee.emit("send_msg", { 
                "text": self.input_value.get(),
                "user": remote.user["name"],
                "ip": self.room["ip"],
                "port": self.room["port"]
            }) 
            self.input_value.set("")

    def free(self):
        remote.ee.remove_all_listeners("fetch_data")
        remote.ee.remove_all_listeners("new_msg")
        remote.ee.remove_all_listeners("connect_server_ok")
        remote.ee.remove_all_listeners("connect_server_error")
