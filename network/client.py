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
            # if msg["ip"] == self.ip and msg["port"] == self.port:
            self.socket.emit("send_msg", msg)

        @remote.ee.on("login")
        def login(room, name):
            def cb(data):
                remote.ee.emit("fetch_data", data)
            if room["ip"] == self.ip and room["port"] == self.port:
                self.socket.emit("login", name, callback = cb)

    def connect(self):
        self.socket.connect("http://" + self.ip + ":" + self.port)
        return True
