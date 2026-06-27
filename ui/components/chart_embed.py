import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class ChartEmbed(ctk.CTkFrame):
    """Embeds a matplotlib Figure inside a CTk frame."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._canvas = None

    def show_figure(self, figure):
        if self._canvas is not None:
            self._canvas.get_tk_widget().destroy()
        self._canvas = FigureCanvasTkAgg(figure, master=self)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True)
