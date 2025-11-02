from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List
import importlib, logging, sys, os, pathlib, math

log = logging.getLogger(__name__)

# Добавляем корень проекта (где лежат Test_plan.py и FA_Gamma.py) в PYTHONPATH
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    TestPlan = importlib.import_module("Test_plan")
    FAGamma = importlib.import_module("FA_Gamma")
except Exception as e:
    raise ImportError(
        "Не найдены модули Test_plan.py / FA_Gamma.py. "
        f"Положите их в папку: {ROOT}"
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
        """
        Подменяем глобальные пути в исходных модулях на те,
        что пришли снаружи (вместо захардкоженных констант).
        """
        TestPlan.ConfigDIRName   = self.paths.config_dir
        TestPlan.MCUDIRName      = self.paths.mcu_fin_dir
        TestPlan.ResultsDIRName  = self.paths.results_dir
        TestPlan.OrigenDIRName   = self.paths.origen_dir
        TestPlan.scale_bin       = self.paths.scale_bin

        # Папка функций Грина для FA_Gamma
        FAGamma.MCUGreenDirName  = self.paths.greens_dir

        # Гарантируем наличие выходных папок
        pathlib.Path(self.paths.results_dir).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.paths.origen_dir).mkdir(parents=True, exist_ok=True)

    def initialize(self) -> Dict:
        """
        Загружаем таблицы/алгоритмы и функции Грина.
        Возвращаем краткую мета-информацию.
        """
        self._apply_paths()
        # ReadStaticData ожидает FINsListFile внутри Configs
        self._algorithms = TestPlan.ReadStaticData(TestPlan.FINsListFile)
        self._greens = FAGamma.readGreenFuncs()

        # Соберём список ячеек из первого алгоритма (как ориентир)
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

    def _parse_origen_without_scale(self, core, max_reg_hours: float) -> None:
        """
        Поведение как у InvokeOrigen, но без запуска SCALE:
        просто читаем уже готовые *.out в Origens.
        """
        # Восстанавливаем те же временные точки, что и в InvokeOrigen
        N_pts = 10
        precision = 1
        tmax_log = math.log(max_reg_hours)
        core.tregs = [round(math.exp(n / N_pts * tmax_log), precision) for n in range(1, N_pts + 1)]
        core.tregs = [0.0] + core.tregs

        # Контейнеры, которые далее использует FADoseRate / FACellDoseRate
        core.Wmax_src_spectrums = dict()
        core.Wmax2_src_spectrums = dict()
        core.Wenvelope_src_spectrums = dict()

        containers = [core.Wmax_src_spectrums, core.Wmax2_src_spectrums, core.Wenvelope_src_spectrums]
        # Список базовых имён файлов ORIGEN берём из класса (как в Test_plan)
        try:
            origen_fns = list(type(core).Origen_fns)
        except Exception:
            # На случай, если имя атрибута изменится — дефолт
            origen_fns = ["max_burnup", "max_2_hours", "envelope"]

        for fn, container in zip(origen_fns, containers):
            out_path = os.path.join(os.curdir, TestPlan.OrigenDIRName, fn + ".out")
            if not os.path.isfile(out_path):
                raise FileNotFoundError(
                    f"Не найден файл ORIGEN: {out_path}. "
                    "Положите готовые .out (или включите use_scale=True)."
                )
            core.ParseOrigenOut(out_path, container)

    def compute_envelope(self, decay_hours: float, run_origen: bool = True) -> EnvelopeResult:
        """
        Расчёт «конверта»: дозовые кривые по всем зонам (130..149).
        """
        if self._algorithms is None or self._greens is None:
            self.initialize()

        core = TestPlan.TCoreHistory(self._algorithms, self._greens)

        if run_origen:
            core.InvokeOrigen(decay_hours)
        else:
            self._parse_origen_without_scale(core, decay_hours)

        # Дозовые ряды по зонам (в коде Test_plan они в Sv/s → переведём к µSv/h)
        dose_by_zone: Dict[int, List[float]] = {}
        for zone in range(130, 150):
            dozeRates = core.FADoseRate(core.Wenvelope_axial, zone, core.Wenvelope_src_spectrums)
            dose_by_zone[zone] = [Svs * 3600.0 * 1e6 for Svs in dozeRates]

        return EnvelopeResult(times_h=core.tregs, dose_uSv_per_h_by_zone=dose_by_zone)

    def compute_cell(self, cell: str, decay_hours: float, run_origen: bool = True) -> CellResult:
        """
        Расчёт по одной ячейке ТВС.
        Внутри Test_plan.FACellDoseRate(..) уже работает с .out/.inp через CoreHistory,
        так что при run_origen=False будет использован парсинг готовых .out.
        """
        if self._algorithms is None or self._greens is None:
            self.initialize()

        core = TestPlan.TCoreHistory(self._algorithms, self._greens)

        # FACellDoseRate сам сформирует контейнеры и, если нужно, дёрнет ORIGEN
        # но .out мы уже положили — парсер отработает.
        dose_arrays_Svs = core.FACellDoseRate(cell, decay_hours)

        dose_by_zone: Dict[int, List[float]] = {
            z: [Svs * 3600.0 * 1e6 for Svs in series] for z, series in dose_arrays_Svs.items()
        }
        return CellResult(cell=cell, times_h=core.tregs, dose_uSv_per_h_by_zone=dose_by_zone)
