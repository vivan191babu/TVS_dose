from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .api import TestPlanAPI, Paths

app = FastAPI(title="TVS Dose API")

class InitReq(BaseModel):
    config_dir: str = "Configs"
    mcu_fin_dir: str = "MCU_FIN"
    greens_dir: str = "TVS_Green"
    origen_dir: str = "Origens"
    results_dir: str = "Core_FAs"
    scale_bin: str = r"d:\SCALE-6.2.4\bin\scalerte.exe"

class EnvelopeReq(BaseModel):
    decay_hours: float = 320.0
    use_scale: bool = False

class CellReq(BaseModel):
    cell: str
    decay_hours: float = 320.0
    use_scale: bool = False

_api: Optional[TestPlanAPI] = None

@app.post("/init")
def init(req: InitReq):
    global _api
    _api = TestPlanAPI(Paths(**req.dict()))
    return _api.initialize()

@app.post("/envelope")
def envelope(req: EnvelopeReq):
    if _api is None:
        raise HTTPException(400, "Not initialized. Call /init first.")
    res = _api.compute_envelope(decay_hours=req.decay_hours, run_origen=req.use_scale)
    return {"times_h": res.times_h, "dose_uSv_per_h_by_zone": res.dose_uSv_per_h_by_zone}

@app.post("/cell")
def cell(req: CellReq):
    if _api is None:
        raise HTTPException(400, "Not initialized. Call /init first.")
    res = _api.compute_cell(cell=req.cell, decay_hours=req.decay_hours, run_origen=req.use_scale)
    return {"cell": res.cell, "times_h": res.times_h, "dose_uSv_per_h_by_zone": res.dose_uSv_per_h_by_zone}
