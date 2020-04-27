from PIL import Image, ImageTk

def loadImage(file, size):
    pil_img = Image.open(file).resize(size)
    tk_img = ImageTk.PhotoImage(pil_img)

    return tk_img