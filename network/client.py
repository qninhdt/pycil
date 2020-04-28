from socketio import Client
from socketio.exceptions import ConnectionError
import remote

class PycilClient:

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

        self.socket = Client()

        @self.socket.on("new_msg")
        def on_new_msg(msg):
            remote.ee.emit("new_msg", msg)

        @remote.ee.on("send_msg")
        def send_msg(msg):
            self.socket.emit("send_msg", msg)

        @remote.ee.on("login")
        def login(room, name):
            def cb(data):
                remote.ee.emit("fetch_data", data)
            self.socket.emit("login", name, callback = cb)

        @remote.ee.on("logout")
        def logout():
            self.socket.emit("logout", remote.user["name"])
            self.socket.disconnect()

        @self.socket.on("new_user")
        def on_new_user(name):
            remote.ee.emit("new_user", name)

        @self.socket.on("remove_user")
        def on_remove_user(name):
            remote.ee.emit("remove_user", name)

    def connect(self):
        self.socket.connect("http://" + self.ip + ":" + str(self.port))
        return True
