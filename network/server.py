from flask import Flask, jsonify, request
from flask_socketio import SocketIO
from peewee import SqliteDatabase
from .ip import get_port

class PycilServer(Flask):

    def __init__(self, name):
        super().__init__(__name__)
        self.config['SECRET_KEY'] = 'qninhdz'
        self.socket = SocketIO(self)
        self.db = SqliteDatabase("data/room.db")

        self.name = name
        self.msg = [
            { "user": "Server", "text": "Chào :))" }
        ]
        self.users = []

        @self.socket.on("login")
        def login(name):
            self.users.append(name)
            self.socket.emit("new_user", name, broadcast=True)

            return {
                "name": self.name,
                "msg": self.msg,
                "users": self.users,
            }

        @self.route("/data")
        def get_data():
            return jsonify({
                "name": self.name, 
                "msg": self.msg,
                "online": len(self.users)
            })

        @self.route("/pycil")
        def pycil():
            return "Pycil"

        @self.socket.on("send_msg")
        def on_new_msg(msg):
            self.msg.append(msg)
            self.socket.emit("new_msg", msg)
        
        @self.socket.on("logout")
        def logout(name):
            self.users.remove(name)
            self.socket.emit("remove_user", name)

    def loop(self):
        self.socket.run(self, host="0.0.0.0", port=get_port())