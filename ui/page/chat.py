import tkinter as tk
from ui.widget import ScrollView, ChatRoom

class ChatPage(tk.Frame):

    def __init__(self, master):
        super().__init__(master)

        self.panel = tk.Frame(self, height=40)
        self.panel.pack(padx=10, pady=10, fill=tk.X)

        self.join_create = tk.Frame(self.panel)

        self.new_room_btn = tk.Button(self.join_create, 
            padx=12, fg="#f0f3bd", 
            activeforeground="white", 
            activebackground="#02c39a", 
            bd=0, bg="#2a9d8f", 
            text="▶ Create")

        self.join_room_btn = tk.Button(self.join_create, 
            padx=12, fg="#f0f3bd", 
            activeforeground="white", 
            activebackground="#e9c46a", 
            bd=0, bg="#f4a261", 
            text="➼ New")

        self.new_room_btn.config(font=("Lucida Grande ", 14))
        self.new_room_btn.grid(row=0, column=1, padx=3)

        self.join_room_btn.config(font=("Lucida Grande ", 14))
        self.join_room_btn.grid(row=0, column=0, padx=3)

        self.join_create.pack(side=tk.RIGHT)

        self.room = ScrollView(self)

        room = {
            "name": "Anh em sã hội :))",
            "ip": "127.0.0.1",
            "port": "5172",
            "online": 20,
            "msg": [
                { "username": "qninh", "text": "yo ?" },
                { "username": "abc", "text": "yo ?" },
                { "username": "qninh", "text": "yo ?" },
                { "username": "pop", "text": "yo ?" },
                { "username": "pap", "text": "yo ?" }
            ]
        }

        for i in range(10):
            chat_room = ChatRoom(self.room.frame, room)
            chat_room.grid(row=i, padx=20, pady=10)

        self.room.pack(fill=tk.BOTH, expand=True)


        