from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List
import importlib, logging, sys, os, pathlib, math

log = logging.getLogger(__name__)

# Корень репозитория (где лежат Test_plan.py и FA_Gamma.py)
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    TestPlan = importlib.import_module("Test_plan")
    FAGamma = importlib.import_module("FA_Gamma")
except Exception as e:
    raise ImportError(
        "Не найдены модули Test_plan.py / FA_Gamma.py. "
        f"Положите их в корень репозитория: {ROOT}"
    ) from e


@dataclass
class Paths:
    config_dir: str = "Configs"
    mcu_fin_dir: str = "MCU_FIN"
    greens_dir: str = "TVS_Green"
    origen_dir: str = "Origens"
    results_dir: str = "Core_FAs"
    scale_bin: str = r"d:\SCALE-6.2.4\bin\scalerte.exe"


@dataclass
class EnvelopeResult:
    times_h: List[float]
    dose_uSv_per_h_by_zone: Dict[int, List[float]]  # zone -> series


@dataclass
class CellResult:
    cell: str
    times_h: List[float]
    dose_uSv_per_h_by_zone: Dict[int, List[float]]


class TestPlanAPI:
    def __init__(self, paths: Paths):
        self.paths = paths
        self._algorithms = None
        self._greens = None

    def _apply_paths(self) -> None:
        """Подменяем глобальные пути в исходных модулях на переданные извне."""
        TestPlan.ConfigDIRName   = self.paths.config_dir
        TestPlan.MCUDIRName      = self.paths.mcu_fin_dir
        TestPlan.ResultsDIRName  = self.paths.results_dir
        TestPlan.OrigenDIRName   = self.paths.origen_dir
        TestPlan.scale_bin       = self.paths.scale_bin

        # Папка функций Грина
        FAGamma.MCUGreenDirName  = self.paths.greens_dir

        # Выходные папки — гарантируем наличие
        pathlib.Path(self.paths.results_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.paths.origen_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self) -> Dict:
        """Загрузка таблиц/алгоритмов и функций Грина. Возвращает мета-информацию."""
        self._apply_paths()
        self._algorithms = TestPlan.ReadStaticData(TestPlan.FINsListFile)
        self._greens = FAGamma.readGreenFuncs()

        try:
            first_alg = next(iter(self._algorithms.values()))
            fa_cells = sorted(first_alg.FAs.keys())
        except Exception:
            fa_cells = []

        spans = TestPlan.MCU_FA_spans
        return {
            "paths": asdict(self.paths),
            "algorithms": len(self._algorithms) if self._algorithms else 0,
            "fa_cells": fa_cells,
            "fa_spans": spans,
        }

    # ——— режим без SCALE: парсим готовые .out ———
    def _parse_origen_without_scale(self, core, max_reg_hours: float) -> None:
        # Восстанавливаем те же точки по времени, что и InvokeOrigen
        N_pts = 10
        precision = 1
        tmax_log = math.log(max_reg_hours)
        core.tregs = [round(math.exp(n / N_pts * tmax_log), precision) for n in range(1, N_pts + 1)]
        core.tregs = [0.0] + core.tregs

        # Контейнеры для спектров
        core.Wmax_src_spectrums = {}
        core.Wmax2_src_spectrums = {}
        core.Wenvelope_src_spectrums = {}

        containers = [core.Wmax_src_spectrums, core.Wmax2_src_spectrums, core.Wenvelope_src_spectrums]
        try:
            origen_fns = list(type(core).Origen_fns)   # ["max_burnup","max_2_hours","envelope"]
        except Exception:
            origen_fns = ["max_burnup", "max_2_hours", "envelope"]

        # ВАЖНО: внутри ParseOrigenOut путь формируется как .\Origens\ + fn,
        # поэтому сюда передаём ТОЛЬКО имя файла (basename), без директорий.
        for fn, container in zip(origen_fns, containers):
            full = pathlib.Path(self.paths.origen_dir) / f"{fn}.out"
            if not full.exists():
                raise FileNotFoundError(
                    f"Не найден файл ORIGEN: {full}\n"
                    f"Ожидался в папке: {self.paths.origen_dir}"
                )
            core.ParseOrigenOut(f"{fn}.out", container)


    def compute_envelope(self, decay_hours: float, run_origen: bool = True) -> EnvelopeResult:
        if self._algorithms is None or self._greens is None:
            self.initialize()

        core = TestPlan.TCoreHistory(self._algorithms, self._greens)

        if run_origen:
            core.InvokeOrigen(decay_hours)
        else:
            self._parse_origen_without_scale(core, decay_hours)

        dose_by_zone: Dict[int, List[float]] = {}
        for zone in range(130, 150):
            dozeRates = core.FADoseRate(core.Wenvelope_axial, zone, core.Wenvelope_src_spectrums)
            dose_by_zone[zone] = [Svs * 3600.0 * 1e6 for Svs in dozeRates]  # Sv/s → μSv/h

        return EnvelopeResult(times_h=core.tregs, dose_uSv_per_h_by_zone=dose_by_zone)

    def compute_cell(self, cell: str, decay_hours: float, run_origen: bool = True) -> CellResult:
        if self._algorithms is None or self._greens is None:
            self.initialize()

        core = TestPlan.TCoreHistory(self._algorithms, self._greens)
        dose_arrays_Svs = core.FACellDoseRate(cell, decay_hours)
        dose_by_zone: Dict[int, List[float]] = {
            z: [Svs * 3600.0 * 1e6 for Svs in series] for z, series in dose_arrays_Svs.items()
        }
        return CellResult(cell=cell, times_h=core.tregs, dose_uSv_per_h_by_zone=dose_by_zone)
