import tkinter as tk
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Quiet, compact desktop clock for Windows 10/11
BG = "#0B1020"
CARD = "#121C30"
BORDER = "#26344A"
TEXT = "#F4F7FF"
MUTED = "#91A0B8"
UAE_ACCENT = "#55D6B2"
EGYPT_ACCENT = "#E9B86B"
HOVER = "#1A2942"

TZ_UAE = ZoneInfo("Asia/Dubai")
TZ_EGYPT = ZoneInfo("Africa/Cairo")


class FloatingClock:
    def __init__(self, root):
        self.root = root
        self.root.title("UAE & Egypt Mini Clock")
        self.root.geometry("292x112+24+24")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", False)
        self.root.attributes("-alpha", 0.90)

        self.pinned = False
        self.drag_offset = (0, 0)
        self._build_ui()
        self._bind_drag(self.root)
        self.root.bind("<Enter>", self._on_enter)
        self.root.bind("<Leave>", self._on_leave)
        self.update_clock()

    def _build_ui(self):
        shell = tk.Frame(self.root, bg=BG, highlightthickness=1,
                         highlightbackground=BORDER)
        shell.pack(fill="both", expand=True)

        header = tk.Frame(shell, bg=BG, height=25)
        header.pack(fill="x", padx=9, pady=(4, 1))
        header.pack_propagate(False)

        tk.Label(header, text="◷", bg=BG, fg=UAE_ACCENT,
                 font=("Segoe UI Symbol", 12, "bold")).pack(side="left")
        tk.Label(header, text="  UAE  ·  EGYPT", bg=BG, fg=TEXT,
                 font=("Segoe UI", 8, "bold")).pack(side="left")

        self.pin_btn = tk.Label(header, text="PIN OFF", bg=BG, fg=MUTED,
                                font=("Segoe UI", 7, "bold"), cursor="hand2",
                                padx=5)
        self.pin_btn.pack(side="right", padx=(4, 0))
        self.pin_btn.bind("<Button-1>", self.toggle_pin)
        self.pin_btn.bind("<Enter>", lambda _e: self.pin_btn.config(fg=UAE_ACCENT))
        self.pin_btn.bind("<Leave>", lambda _e: self.pin_btn.config(fg=UAE_ACCENT if self.pinned else MUTED))

        close = tk.Label(header, text="×", bg=BG, fg=MUTED,
                         font=("Segoe UI", 13), cursor="hand2", width=2)
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.root.destroy())
        close.bind("<Enter>", lambda _e: close.config(fg="#F07180"))
        close.bind("<Leave>", lambda _e: close.config(fg=MUTED))

        cards = tk.Frame(shell, bg=BG)
        cards.pack(fill="both", expand=True, padx=7, pady=(1, 5))
        cards.grid_columnconfigure(0, weight=1, uniform="city")
        cards.grid_columnconfigure(1, weight=1, uniform="city")
        self.uae = self._make_card(cards, 0, "UAE", "DUBAI", UAE_ACCENT)
        self.egypt = self._make_card(cards, 1, "EGYPT", "CAIRO", EGYPT_ACCENT)

    def _make_card(self, parent, col, country, city, accent):
        card = tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER)
        card.grid(row=0, column=col, sticky="nsew",
                  padx=(0, 3) if col == 0 else (3, 0))

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=7, pady=(4, 0))
        tk.Label(top, text=country, bg=CARD, fg=accent,
                 font=("Segoe UI", 7, "bold")).pack(side="left")
        tk.Label(top, text=city, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 6)).pack(side="right")

        time_label = tk.Label(card, text="--:-- --", bg=CARD, fg=TEXT,
                              font=("Segoe UI", 15, "bold"))
        time_label.pack(anchor="w", padx=7, pady=(0, 2))
        date_label = tk.Label(card, text="", bg=CARD, fg=MUTED,
                              font=("Segoe UI", 6))
        date_label.pack(anchor="w", padx=8, pady=(0, 3))
        return {"time": time_label, "date": date_label}

    def _bind_drag(self, widget):
        # Drag from the background/cards; header controls remain clickable.
        if widget is self.root:
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._do_move)
        for child in widget.winfo_children():
            if child is self.pin_btn or child.cget("text") == "×" if isinstance(child, tk.Label) else False:
                continue
            if isinstance(child, (tk.Frame, tk.Label)):
                child.bind("<ButtonPress-1>", self._start_move)
                child.bind("<B1-Motion>", self._do_move)
                self._bind_drag(child)

    def _start_move(self, event):
        self.drag_offset = (event.x_root - self.root.winfo_x(),
                            event.y_root - self.root.winfo_y())

    def _do_move(self, event):
        x = event.x_root - self.drag_offset[0]
        y = event.y_root - self.drag_offset[1]
        self.root.geometry(f"+{x}+{y}")

    def toggle_pin(self, _event=None):
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)
        self.pin_btn.config(text="PIN ON" if self.pinned else "PIN OFF",
                            fg=UAE_ACCENT if self.pinned else MUTED)

    def _on_enter(self, _event=None):
        self.root.attributes("-alpha", 0.98)

    def _on_leave(self, _event=None):
        self.root.attributes("-alpha", 0.90)

    def update_clock(self):
        now = datetime.now(timezone.utc)
        for target, zone in ((self.uae, TZ_UAE), (self.egypt, TZ_EGYPT)):
            local = now.astimezone(zone)
            target["time"].config(text=local.strftime("%I:%M:%S %p").lstrip("0"))
            target["date"].config(text=local.strftime("%a, %d %b"))
        self.root.after(1000, self.update_clock)


if __name__ == "__main__":
    root = tk.Tk()
    FloatingClock(root)
    root.mainloop()
