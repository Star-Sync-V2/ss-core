from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# --- import your existing services (names match your tree) ---
from .request import RequestService
from .ground_station import GroundStationService
from app.entities.Visibility import Visibility  # you showed this class

# If you already have a Contact/Booking model, you can swap the dicts below for it
MIN_GAP = timedelta(seconds=300)  # 5-minute guard band per spec

@dataclass
class Candidate:
    station_id: int
    aos: datetime
    rf_on: datetime
    rf_off: datetime
    los: datetime
    score: float = 0.0
    reasons: List[str] = None

class SchedulerService:
    """
    Feasible-first scheduler. Hard constraints:
      - One contact per station at a time
      - >= 300s guard band between contacts on the same station
    Visibility windows are provided via your services, wrapped as `Visibility`.
    """

    def __init__(self, db):
        self.db = db
        self.req_svc = RequestService(db)
        self.gs_svc = GroundStationService(db)

    # ---------- public API ----------

    def replan(self, mission_id: Optional[int] = None) -> Dict[str, Any]:
        """Plan all pending RF-time requests; return scheduled + deferred + basic metrics."""
        pending = self.req_svc.list_pending_requests(mission_id=mission_id)
        # station_id -> list of already scheduled contact dicts (for overlap checks)
        per_station_schedule: Dict[int, List[Dict[str, datetime]]] = self._bootstrap_existing_contacts()

        scheduled, deferred = [], []
        for req in pending:
            res = self._plan_one_rf_time(req, per_station_schedule, persist=True)
            (scheduled if res["status"] == "scheduled" else deferred).append(res)

        metrics = self._metrics(scheduled=scheduled, deferred=deferred, per_station=per_station_schedule)
        run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        return {"run_id": run_id, "scheduled": scheduled, "deferred": deferred, "metrics": metrics}

    def whatif(self, request_id: int) -> Dict[str, Any]:
        """Dry-run a single request; never writes to DB."""
        req = self.req_svc.get_request(request_id)
        per_station_schedule = self._bootstrap_existing_contacts()
        return self._plan_one_rf_time(req, per_station_schedule, persist=False, dry_run=True)

    # ---------- internals ----------

    def _plan_one_rf_time(self, req, per_station_schedule, persist: bool, dry_run: bool = False) -> Dict[str, Any]:
        # 1) build candidates across stations within req.window
        stations = self.gs_svc.list_ground_stations()
        candidates = self._candidates_for_request(req, stations)

        # 2) choose first feasible (can replace with scoring later)
        for cand in candidates:
            if self._feasible_for_station(cand, per_station_schedule.get(cand.station_id, [])):
                if persist and not dry_run:
                    contact = self.req_svc.create_contact_from_candidate(req, cand.__dict__)
                    # Update in-memory timeline for subsequent checks
                    entry = {"aos": cand.aos, "los": cand.los}
                    per_station_schedule.setdefault(cand.station_id, []).append(entry)
                    return {"status": "scheduled", "request_id": req.id, "contact": self._as_report(contact)}
                else:
                    # Dry run: produce a report-shaped object without DB writes
                    contact_like = self.req_svc.compose_contact_like(req, cand.__dict__)
                    return {"status": "scheduled", "request_id": req.id, "contact": self._as_report(contact_like), "dry_run": True}

        return {"status": "deferred", "request_id": getattr(req, "id", None), "reason": "no_feasible_slot"}

    def _candidates_for_request(self, req, stations) -> List[Candidate]:
        """
        Build candidate contact windows for each station.
        Plug in your real visibility generator here. For now, we assume
        GroundStationService exposes a method to compute visibilities or you can
        stub one that returns a list[Visibility].
        """
        window_start = req.window_start
        window_end = req.window_end

        cands: List[Candidate] = []
        for gs in stations:
            # --- Replace this with your real visibility call if available ---
            # Example expectation: self.gs_svc.get_visibilities(satellite=req.satellite, station=gs, start=window_start, end=window_end)
            vis_list: List[Visibility] = self.gs_svc.get_visibilities(  # <-- implement this thin wrapper if it doesn't exist yet
                satellite=req.satellite, gs=gs, start=window_start, end=window_end
            )

            for vis in vis_list:
                # intersect with request window just in case
                aos = max(vis.start, window_start)
                los = min(vis.end, window_end)
                if aos >= los:
                    continue
                # naive RF-on/off at 5° (you can refine from your vis model)
                rf_on = aos + timedelta(seconds=30)    # placeholder
                rf_off = los - timedelta(seconds=30)   # placeholder
                cands.append(Candidate(
                    station_id=gs.id, aos=aos, rf_on=rf_on, rf_off=rf_off, los=los, score=0.0, reasons=[]
                ))

        # sort by earliest feasible end → favors earlier/smaller contacts
        cands.sort(key=lambda c: (c.los, c.aos))
        return cands

    def _feasible_for_station(self, cand: Candidate, scheduled_for_station: List[Dict[str, datetime]]) -> bool:
        """No overlap and keep ≥5-min guard band with already-scheduled contacts on the station."""
        for s in scheduled_for_station:
            if not self._gap_ok(cand.aos, cand.los, s["aos"], s["los"]):
                return False
        return True

    @staticmethod
    def _gap_ok(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
        # reject if windows are too close: (start < other_end + gap) and (other_start < end + gap)
        if a_start < (b_end + MIN_GAP) and b_start < (a_end + MIN_GAP):
            return False
        return True

    def _bootstrap_existing_contacts(self) -> Dict[int, List[Dict[str, datetime]]]:
        """
        Build current timeline per station from already scheduled contacts,
        so new planning respects what’s on the books.
        """
        per_station: Dict[int, List[Dict[str, datetime]]] = {}
        for c in self.req_svc.list_existing_contacts():
            per_station.setdefault(c.station_id, []).append({"aos": c.aos, "los": c.los})
        # keep station timelines sorted for faster checks
        for sid in per_station:
            per_station[sid].sort(key=lambda x: x["aos"])
        return per_station

    def _as_report(self, contact_like) -> Dict[str, str]:
        """Return a spec-shaped Contact Report dict (stringified fields for external I/O)."""
        return {
            "mission": str(getattr(contact_like, "mission_name", "")),
            "satellite": str(getattr(contact_like, "satellite_name", "")),
            "station": str(getattr(contact_like, "station_name", "")),
            "aos": getattr(contact_like, "aos").isoformat(),
            "rf_on": getattr(contact_like, "rf_on").isoformat(),
            "rf_off": getattr(contact_like, "rf_off").isoformat(),
            "los": getattr(contact_like, "los").isoformat(),
        }

    def _metrics(self, scheduled, deferred, per_station) -> Dict[str, Any]:
        total = len(scheduled) + len(deferred)
        fr = (len(scheduled) / total) if total else 0.0
        util = {sid: sum((x["los"] - x["aos"]).total_seconds() for x in per_station.get(sid, [])) for sid in per_station}
        util_vals = list(util.values())
        mean = (sum(util_vals) / len(util_vals)) if util_vals else 0.0
        variance = (sum((u - mean) ** 2 for u in util_vals) / len(util_vals)) if util_vals else 0.0
        return {"fulfillment_rate": fr, "utilization_seconds": util, "utilization_stddev": variance ** 0.5}
