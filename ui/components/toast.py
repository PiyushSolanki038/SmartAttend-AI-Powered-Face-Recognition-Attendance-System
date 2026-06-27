import customtkinter as ctk

COLORS = {
    "info": "#1F6AA5",
    "success": "#2ECC71",
    "warning": "#F39C12",
    "error": "#E74C3C",
}


def show_toast(parent, message: str, kind: str = "info", duration_ms: int = 2500):
    """Shows a small auto-dismissing banner pinned to the top of `parent` (a CTk widget)."""
    toast = ctk.CTkFrame(parent, fg_color=COLORS.get(kind, COLORS["info"]), corner_radius=8)
    label = ctk.CTkLabel(toast, text=message, text_color="white", font=ctk.CTkFont(weight="bold"))
    label.pack(padx=16, pady=8)
    toast.place(relx=0.5, rely=0.04, anchor="n")
    toast.after(duration_ms, toast.destroy)
    return toast
