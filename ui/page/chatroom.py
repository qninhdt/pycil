from tkinter import *
from ui.widget import ScrollView, Message
import remote

class ChatRoom(Frame):

    def __init__(self, master, room):
        super().__init__(master)
        self.room = room
        self.users_ = []

        remote.ee.emit("login", self.room, remote.user["name"])

        @remote.ee.on("fetch_data")
        def fetch_data(data):
            self.room["msg"] = data["msg"]
            self.room["users"] = data["users"]

            self.setup_ui()

        @remote.ee.on("new_msg")
        def on_new_msg(msg):

            self.add_msg(len(self.room["msg"]), msg)

            self.room["msg"].append(msg)

            self.msg_panel.canvas.update_idletasks()
            self.msg_panel.canvas.yview_moveto(1)

        @remote.ee.on("remove_user")
        def on_remove_user(user):
            i = 0
            for user_ in self.users_:
                if user_[0] == user:
                    user_[1].grid_forget()
                    self.users_.pop(i)
                    break
                i += 1

        @remote.ee.on("new_user")
        def on_new_user(user):
            if remote.user["name"] != user:
                self.add_user(len(self.room["users"]), user)
                self.room["users"].append(user)

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
        
        remote.ee.on("enter", self.send_msg)

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
            self.add_msg(idx, msg)

        for idx, user in enumerate(self.room["users"]):
            self.add_user(idx, user)

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
        remote.ee.remove_all_listeners("enter")
        remote.ee.remove_all_listeners("new_user")
        remote.ee.remove_all_listeners("remove_user")

    def add_msg(self, idx, msg):
        show_username = True

        if idx != 0 and msg["user"] == self.room["msg"][idx-1]["user"]:
            show_username = False
                
        Message(self.msg_panel.frame, msg, show_username).grid(
            column = 0, row = idx, padx = 0, pady = 5)

    def add_user(self, idx, name):

        user_ = Label(self.room_panel.frame, width = 12, text = name, bg = "orange", pady= 3, padx = 5)
        user_.grid(column = 0, row = idx, padx = 0, pady = 5)
        self.users_.append((name, user_))
