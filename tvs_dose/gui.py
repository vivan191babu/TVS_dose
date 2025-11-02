
import tkinter as tk
from tkinter import ttk, messagebox
from .api import TestPlanAPI, Paths

class DoseGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TVS Dose — GUI")
        self.geometry("720x520")
        # Paths (defaults; adjust in the fields below)
        self.config_dir = tk.StringVar(value="Configs")
        self.mcu_fin_dir = tk.StringVar(value="MCU_FIN")
        self.greens_dir  = tk.StringVar(value="TVS_Green")
        self.origen_dir  = tk.StringVar(value="Origens")
        self.results_dir = tk.StringVar(value="Core_FAs")
        self.scale_bin   = tk.StringVar(value=r"d:\SCALE-6.2.4\bin\scalerte.exe")

        frm = ttk.Frame(self); frm.pack(fill="x", padx=10, pady=8)
        row=0
        for label,var in [("Configs",self.config_dir),("MCU_FIN",self.mcu_fin_dir),("TVS_Green",self.greens_dir),
                          ("Origens",self.origen_dir),("Core_FAs",self.results_dir),("SCALE exe",self.scale_bin)]:
            ttk.Label(frm, text=label, width=12).grid(row=row, column=0, sticky="e", padx=4, pady=2)
            ttk.Entry(frm, textvariable=var, width=48).grid(row=row, column=1, sticky="we", padx=4, pady=2)
            row+=1

        ttk.Button(frm, text="Инициализировать", command=self.on_init).grid(row=row, column=0, padx=4, pady=6)
        self.status = ttk.Label(frm, text="Статус: не инициализировано"); self.status.grid(row=row, column=1, sticky="w"); row+=1
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=6)

        # Cell + decay controls
        cf = ttk.Frame(self); cf.pack(fill="x", padx=10, pady=8)
        ttk.Label(cf, text="Ячейка (cell):").grid(row=0,column=0, sticky="e")
        self.cell_var = tk.StringVar(value="1-1")
        ttk.Entry(cf, textvariable=self.cell_var, width=10).grid(row=0,column=1, sticky="w", padx=4)
        ttk.Label(cf, text="Время охлаждения (ч):").grid(row=0,column=2, sticky="e")
        self.decay_var = tk.DoubleVar(value=320.0)
        ttk.Entry(cf, textvariable=self.decay_var, width=10).grid(row=0,column=3, sticky="w", padx=4)

        ttk.Button(cf, text="Расчёт по ячейке", command=self.on_cell).grid(row=0,column=4, padx=6)
        ttk.Button(cf, text="Расчёт Envelope", command=self.on_env).grid(row=0,column=5, padx=6)

        # Results text
        self.text = tk.Text(self, height=18); self.text.pack(fill="both", expand=True, padx=10, pady=8)

        self.api = None

    def on_init(self):
        try:
            self.api = TestPlanAPI(Paths(
                config_dir=self.config_dir.get(),
                mcu_fin_dir=self.mcu_fin_dir.get(),
                greens_dir=self.greens_dir.get(),
                origen_dir=self.origen_dir.get(),
                results_dir=self.results_dir.get(),
                scale_bin=self.scale_bin.get(),
            ))
            meta = self.api.initialize()
            self.status.config(text=f"Инициализировано. Алгоритмов: {meta.get('algorithms')}")
            self.text.insert("end", f"FA cells: {meta.get('fa_cells')[:10]} ...\n")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_cell(self):
        if not self.api:
            return messagebox.showwarning("Внимание","Сначала инициализируйте.")
        try:
            cell = self.cell_var.get().strip()
            h = float(self.decay_var.get())
            res = self.api.compute_cell(cell=cell, decay_hours=h, run_origen=False)
            self.text.insert("end", f"Cell {res.cell} times_h: {res.times_h}\n")
            # краткий вывод доз по одной зоне
            z = min(res.dose_uSv_per_h_by_zone.keys())
            self.text.insert("end", f"Zone {z} dose[μSv/h]: {res.dose_uSv_per_h_by_zone[z][:6]} ...\n")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_env(self):
        if not self.api:
            return messagebox.showwarning("Внимание","Сначала инициализируйте.")
        try:
            h = float(self.decay_var.get())
            res = self.api.compute_envelope(decay_hours=h, run_origen=False)
            zones = sorted(res.dose_uSv_per_h_by_zone.keys())
            self.text.insert("end", f"Envelope times_h: {res.times_h}\n")
            self.text.insert("end", f"Zone {zones[0]} dose[μSv/h]: {res.dose_uSv_per_h_by_zone[zones[0]][:6]} ...\n")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

def main():
    app = DoseGUI()
    app.mainloop()

if __name__ == "__main__":
    main()
