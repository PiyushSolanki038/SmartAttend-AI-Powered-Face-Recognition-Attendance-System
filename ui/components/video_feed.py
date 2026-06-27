import cv2
import customtkinter as ctk
from PIL import Image


class VideoFeed(ctk.CTkLabel):
    """Displays BGR OpenCV frames inside a CTk widget."""

    def __init__(self, master, width=640, height=480, **kwargs):
        super().__init__(master, text="", width=width, height=height, **kwargs)
        self._width = width
        self._height = height

    def update_frame(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(self._width, self._height))
        self.configure(image=ctk_image)
        self.image = ctk_image
