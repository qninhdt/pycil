import tkinter as tk
from ui.widget import ScrollView, ChatRoom
import remote

class ChatPage(tk.Frame):

    def __init__(self, master):
        super().__init__(master)

        self.panel = tk.Frame(self, height=40)
        self.panel.pack(padx=10, pady=10, fill=tk.X)

        self.join_create = tk.Frame(self.panel)
        
        self.reload_button = tk.Button(self.panel, 
            padx=12, fg="#f0f3bd", 
            activeforeground="white", 
            activebackground="#02c39a", 
            bd=0, bg="#2a9d8f", 
            command = lambda: remote.ee.emit("reload_chatroom_list"),
            text="↻"
        )

        self.new_room_btn = tk.Button(self.join_create, 
            padx=12, fg="#f0f3bd", 
            activeforeground="white", 
            activebackground="#02c39a", 
            bd=0, bg="#2a9d8f", 
            command=lambda: remote.ee.emit("new_room", name = "AE sẽ hỗij"),
            text="▶ Create")

        self.stop_room_btn = tk.Button(self.join_create, 
            padx=12, fg="#f0f3bd", 
            activeforeground="white", 
            activebackground="#02c39a", 
            bd=0, bg="#2a9d8f", 
            command=lambda: remote.ee.emit("stop_room"),
            text="▶ Close")

        self.join_room_btn = tk.Button(self.join_create, 
            padx=12, fg="#f0f3bd", 
            activeforeground="white", 
            activebackground="#e9c46a", 
            bd=0, bg="#f4a261", 
            command = self.load_local_server,
            text="➼ New")

        @remote.ee.on("new_room_ok")
        def new_room_ok():
            self.new_room_btn.grid_forget()
            self.stop_room_btn.grid(row=0, column=1, padx=3)

        @remote.ee.on("stop_room_ok")
        def stop_room_ok():
            self.stop_room_btn.grid_forget()
            self.new_room_btn.grid(row=0, column=1, padx=3)

        self.new_room_btn.config(font=("Lucida Grande ", 14))
        self.stop_room_btn.config(font=("Lucida Grande ", 14))
        self.new_room_btn.grid(row=0, column=1, padx=3)

        self.join_room_btn.config(font=("Lucida Grande ", 14))
        self.join_room_btn.grid(row=0, column=0, padx=3)

        self.reload_button.pack(side = tk.LEFT)
        self.reload_button.config(font=("Lucida Grande ", 16))

        self.join_create.pack(side=tk.RIGHT)

        self.room = ScrollView(self)

        self.display_text = tk.Label(self.room.frame, width=75, text = "Scanning local server ...")
        self.display_text.pack(fill=tk.BOTH)

        self.room.pack(fill=tk.BOTH, expand=True)

        # self.load_local_server()

    def load_local_server(self):
        ChatRoom(self.room.frame, room = {
            "ip" : "127.0.0.1",
            "port": "5000",
        }).pack()


        