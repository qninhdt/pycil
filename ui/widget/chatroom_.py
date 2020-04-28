from tkinter import *
import remote, requests

MAX_ROOM_NAME = 30

class ChatRoom(Frame):

    def __init__(self, master, room):
        super().__init__(master, bg="#118ab2")
        self.room = room

        data = requests.get("http://" + self.room["ip"] + ":" + self.room["port"] + "/data").json()

        self.room["name"] = data["name"]
        self.room["msg"] = data["msg"]
        self.room["online"] = data["online"]

        if len(self.room["name"]) > MAX_ROOM_NAME:
            self.room["name"] = self.room["name"][:MAX_ROOM_NAME-1] + "..."

        self.setup_ui()

    def setup_ui(self):

        join_button = Button(self,
            bg = "#1a936f", text="▶", 
            bd = 0, fg = "#f0f3bd", 
            activebackground="#028090",
            activeforeground="white",
            command = lambda: remote.ee.emit("connect_server", self.room["ip"], self.room["port"])
        )
        room_info = Frame(self, bg = "#e9c46a")
        room_panel = Frame(self, bg = "#348aa7", width = 100)

        join_button.config(font = ("Lucida Grande", 20, "bold"))

        # style
        self.room_name = Label(room_info, 
            text = self.room["name"], 
            padx = 5, 
            pady = 3, 
            bg = "#e9c46a", 
            fg = "#264653"
        )

        self.addr = Label(room_info, 
            text = self.room["ip"] + " : " + self.room["port"], 
            padx = 3, 
            pady = 2, 
            bg = "#f4a261", 
            fg = "#264653",
            width = 25
        )

        self.online = Label(room_panel, 
            text = "Online: " + str(self.room["online"]),
            padx = 2,
            pady = 2,
            bg = "#247ba0",
            fg = "#f0f3bd"
        )
        self.online.config(font=("Lucida Grande", 10, "bold"))
        
        last_msg = self.room["msg"][len(self.room["msg"]) - 1]
        self.last_msg = Label(room_panel, 
            text = last_msg["user"] + ": " + last_msg["text"],
            padx = 2,
            pady = 2,
            bg = "#348aa7",
            fg = "#253237",
            anchor='w',
            width = 25
        )
        self.last_msg.config(font=("Lucida Grande", 13))

        self.delete_button = Button(room_panel,
            text = "✕",
            pady = 2,
            padx = 4,
            bd = 0, 
            bg = "#e63946",
            fg = "white"
        )

        # font, size
        self.room_name.config(font = ("Lucida Grande", 12))
        self.addr.config(font = ("Lucida Grande", 10, "bold"))

        self.join = Button(room_panel, text = "Join")

        self.room_name.pack()
        self.addr.pack(anchor = W)

        self.online.place(x = 0, y = 0)
        self.last_msg.pack(side = BOTTOM, anchor = W)
        self.delete_button.pack(side = RIGHT, anchor = N)

        join_button.pack(fill=Y, side = LEFT)
        room_info.pack(side = LEFT)
        room_panel.pack(fill=None, side = LEFT)