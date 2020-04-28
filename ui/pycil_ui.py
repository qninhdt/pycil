from tkinter import *
from ui.page import *
from .sidebar import SideBar
from .headerbar import HeaderBar
import remote, os

class PycilUI(Tk):

    def __init__(self):
        super().__init__()

        self.geometry("600x400+300+300")
        self.resizable(False, False)
        self.title("Pycil v1.0.0 → qninh")
        self.iconbitmap("assets/icon.ico")

        self.vbox = Frame(self)
        self.pages = {
            "setting": SettingPage(self.vbox),
            "home": HomePage(self.vbox),
            "chat": ChatPage(self.vbox),
        }

        self.active_page: Frame = self.pages["home"];

        # listen page
        remote.ee.on("change_page", self.change_page)

        self.bind("<Return>", lambda e: remote.ee.emit("enter"))

    def open(self):

        self.setup_ui()

        self.mainloop()

        remote.ee.emit("logout")

        os._exit(0)

    def setup_ui(self):

        self.content = self.active_page

        self.sidebar = SideBar(self)
        self.headerbar = HeaderBar(self.vbox)
        self.headerbar.set_title("# home")
        self.headerbar.set_subtitle(None)

        self.sidebar.pack(fill = BOTH, side = LEFT)
        self.headerbar.pack(fill = BOTH)
        self.content.pack(fill = BOTH, expand = True)
        self.vbox.pack(fill = BOTH, expand = True)

    def change_page(self, page, title, subtitle = None, **kargs):
        self.active_page.pack_forget()

        if self.headerbar.title.get() == "# chatroom":
            self.active_page.free()
            remote.ee.emit("logout")

        if page == "chatroom":
            self.active_page = ChatRoom(self.vbox, kargs["room"])
        else:
            self.active_page = self.pages[page]

        self.headerbar.set_title(title)
        self.headerbar.set_subtitle(subtitle)
        self.active_page.pack(fill = BOTH, expand = True)

    def reload_chatroom_list(self):
        self.active_page.pack_forget()
        self.active_page = self.pages["chat"] = ChatPage(self.vbox)
        self.active_page.pack(fill = BOTH, expand = True)


