from network.server import PycilServer
from network.client import PycilClient
from ui.pycil_ui import PycilUI
from threading import Thread
from tkinter.messagebox import *
import remote

class Pycil:

    def __init__(self):

        self.server: PycilServer = None
        self.client: PycilClient = None

        @remote.ee.on("new_room")
        def on_new_room(name):
            if self.server == None:
                sv_thread = Thread(target = self.start_server, args=[name])
                sv_thread.name = "Room server (Flask)"
                sv_thread.start()
                remote.ee.emit("new_room_ok")

        @remote.ee.on("stop_room")
        def on_stop_room():
            if self.server != None:
                remote.ee.emit("stop_room_ok")

        @remote.ee.on("connect_server")
        def connect_server(ip, port):
  
            self.client = PycilClient(ip, port)

            if self.client.connect():
                remote.ee.emit("connect_server_ok")

                remote.ee.emit("change_page", "chatroom", "# chatroom", ip + ": " + str(port), 
                    type = "local",
                    room = {
                        "port": port,
                        "ip": ip
                    }
                )
            else:
                showerror("Lỗi !", "Không thể kết nối với máy chủ")
                remote.ee.emit("connect_server_error")

    def start(self):
        self.ui = PycilUI()
        self.ui.open()

    def start_server(self, name):
        self.server = PycilServer(name)
        self.server.loop()