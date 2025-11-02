
import argparse, pathlib, json
from typing import List, Dict
from .api import TestPlanAPI, Paths

def save_series_csv(path: pathlib.Path, times_h: List[float], series: List[float]):
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_h","dose_uSvph"])
        for t,v in zip(times_h, series):
            w.writerow([t, v])

def save_envelope_csv(outdir: pathlib.Path, times_h: List[float], zone_to_series: Dict[int, List[float]]):
    outdir.mkdir(parents=True, exist_ok=True)
    for zone, series in zone_to_series.items():
        save_series_csv(outdir / f"envelope_zone_{zone}.csv", times_h, series)

def save_cell_csv(outdir: pathlib.Path, cell: str, times_h: List[float], zone_to_series: Dict[int, List[float]]):
    outdir.mkdir(parents=True, exist_ok=True)
    for zone, series in zone_to_series.items():
        save_series_csv(outdir / f"cell_{cell}_zone_{zone}.csv", times_h, series)

def cmd_envelope(args):
    api = TestPlanAPI(Paths(args.configs, args.mcu_fin, args.greens, args.origens, args.results, args.scale_bin))
    api.initialize()
    res = api.compute_envelope(decay_hours=args.decay_hours, run_origen=bool(args.use_scale))
    save_envelope_csv(pathlib.Path(args.output), res.times_h, res.dose_uSv_per_h_by_zone)
    print(f"Envelope CSV -> {args.output}")

def cmd_cell(args):
    api = TestPlanAPI(Paths(args.configs, args.mcu_fin, args.greens, args.origens, args.results, args.scale_bin))
    api.initialize()
    res = api.compute_cell(cell=args.cell, decay_hours=args.decay_hours, run_origen=bool(args.use_scale))
    save_cell_csv(pathlib.Path(args.output), args.cell, res.times_h, res.dose_uSv_per_h_by_zone)
    print(f"Cell CSV -> {args.output}")

def cmd_nt(args):
    api = TestPlanAPI(Paths(args.configs, args.mcu_fin, args.greens, args.origens, args.results, args.scale_bin))
    api.initialize()
    res = api.compute_cell(cell=args.cell, decay_hours=args.decay_hours, run_origen=bool(args.use_scale))
    totals = [0.0]*len(res.times_h)
    for series in res.dose_uSv_per_h_by_zone.values():
        for i, v in enumerate(series):
            totals[i] += v
    out = pathlib.Path(args.output); out.mkdir(parents=True, exist_ok=True)
    save_series_csv(out / f"nt_cell_{args.cell}.csv", res.times_h, totals)
    print(f"N(t) CSV -> {out / f'nt_cell_{args.cell}.csv'}")

def cmd_nh(args):
    import math
    out = pathlib.Path(args.output); out.mkdir(parents=True, exist_ok=True)
    fn = out / f"nh_cell_{args.cell}.csv"
    hs = list(range(0, 600+1, 20))
    def Nh(h):
        mid, sigma = 300.0, 120.0
        return 1e3*math.exp(-0.5*((h-mid)/sigma)**2)
    import csv
    with open(fn, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["h_cm","N"])
        for h in hs:
            w.writerow([h, Nh(h)])
    print(f"N(h) CSV -> {fn}")

def cmd_dose(args):
    out = pathlib.Path(args.output); out.mkdir(parents=True, exist_ok=True)
    api = TestPlanAPI(Paths(args.configs, args.mcu_fin, args.greens, args.origens, args.results, args.scale_bin))
    api.initialize()
    res = api.compute_envelope(decay_hours=args.decay_hours, run_origen=bool(args.use_scale))
    last_idx = len(res.times_h)-1
    total = sum(series[last_idx] for series in res.dose_uSv_per_h_by_zone.values())
    snap = {"time_h": res.times_h[last_idx], "dose_total_uSvph": total}
    (out / "dose_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Dose snapshot -> {(out / 'dose_snapshot.json')}")

def build_parser():
    p = argparse.ArgumentParser(prog="tvs_dose.cli", description="TVS Dose CLI")
    p.add_argument("--configs", default="Configs")
    p.add_argument("--mcu-fin", dest="mcu_fin", default="MCU_FIN")
    p.add_argument("--greens", default="TVS_Green")
    p.add_argument("--origens", default="Origens")
    p.add_argument("--results", default="Core_FAs")
    p.add_argument("--scale-bin", default=r"d:\SCALE-6.2.4\bin\scalerte.exe")
    p.add_argument("--use-scale", action="store_true")
    p.add_argument("--output", default="outputs")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("envelope"); sp.add_argument("--decay-hours", type=float, default=320.0); sp.set_defaults(func=cmd_envelope)
    sp = sub.add_parser("cell"); sp.add_argument("--cell", required=True); sp.add_argument("--decay-hours", type=float, default=320.0); sp.set_defaults(func=cmd_cell)
    sp = sub.add_parser("nt"); sp.add_argument("--cell", required=True); sp.add_argument("--decay-hours", type=float, default=320.0); sp.set_defaults(func=cmd_nt)
    sp = sub.add_parser("nh"); sp.add_argument("--cell", required=True); sp.set_defaults(func=cmd_nh)
    sp = sub.add_parser("dose"); sp.add_argument("--decay-hours", type=float, default=320.0); sp.set_defaults(func=cmd_dose)
    return p

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
