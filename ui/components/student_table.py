import customtkinter as ctk


class StudentTable(ctk.CTkScrollableFrame):
    """Scrollable list of rows with column headers.

    Use set_rows() to replace contents. Pass on_sort(col_idx) to make headers clickable
    for sorting, and on_row_click(row_idx) to make rows clickable (e.g. open a detail view)."""

    def __init__(self, master, headers: list, on_sort=None, on_row_click=None, **kwargs):
        super().__init__(master, **kwargs)
        self._headers = headers
        self._row_widgets = []
        self._on_sort = on_sort
        self._on_row_click = on_row_click
        self._render_headers()

    def _render_headers(self):
        for col_idx, header in enumerate(self._headers):
            text = f"{header} ⇕" if self._on_sort else header
            label = ctk.CTkLabel(self, text=text, font=ctk.CTkFont(weight="bold"),
                                  cursor="hand2" if self._on_sort else "")
            label.grid(row=0, column=col_idx, padx=8, pady=4, sticky="w")
            if self._on_sort:
                label.bind("<Button-1>", lambda e, idx=col_idx: self._on_sort(idx))

    def set_rows(self, rows: list):
        """rows: list of tuples, each matching len(headers)."""
        for widget in self._row_widgets:
            widget.destroy()
        self._row_widgets = []

        for row_idx, row in enumerate(rows, start=1):
            for col_idx, value in enumerate(row):
                label = ctk.CTkLabel(self, text=str(value), cursor="hand2" if self._on_row_click else "")
                label.grid(row=row_idx, column=col_idx, padx=8, pady=2, sticky="w")
                if self._on_row_click:
                    label.bind("<Button-1>", lambda e, idx=row_idx - 1: self._on_row_click(idx))
                self._row_widgets.append(label)
