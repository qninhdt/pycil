from tkinter import *
from ui.page import *
from .sidebar import SideBar
from .headerbar import HeaderBar
from pyee import BaseEventEmitter

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
            "chat": ChatPage(self.vbox)
        }

        self.active_page: Frame = self.pages["home"];

        self.remote = BaseEventEmitter()

        # listen page
        self.remote.on("change_page", self.change_page)

    def open(self):

        self.setup_ui()

        self.mainloop()

    def setup_ui(self):

        self.content = self.active_page

        self.sidebar = SideBar(self)
        self.headerbar = HeaderBar(self.vbox)
        self.headerbar.title.set("# home")

        self.sidebar.pack(fill = BOTH, side = LEFT)
        self.headerbar.pack(fill = BOTH)
        self.content.pack(fill = BOTH, expand = True)
        self.vbox.pack(fill = BOTH, expand = True)

    def change_page(self, page, title):
        self.active_page.pack_forget()
        self.active_page = self.pages[page]
        self.headerbar.title.set(title)
        self.active_page.pack(fill = BOTH, expand = True)

pycil_ui = PycilUI()

