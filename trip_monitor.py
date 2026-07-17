"""Poll vehicle telemetry and open/close trips accurately.

Works with real TeslaClient polling and demo mode (simulated drive via
TeslaClient.demo_set_driving / demo_set_parked).
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional, Set

import config
from tesla_client import TeslaAPIError, TeslaClient
from trip_logger import MIN_TRIP_KM_DEFAULT, TripLogger

# shift_state values that mean the car is in a drive gear
_DRIVING_SHIFTS: Set[str] = {"D", "R", "N"}
_PARKED_SHIFTS: Set[str] = {"P"}

OnTripEnd = Callable[[Dict[str, Any]], Awaitable[None]]
OnSnapshot = Callable[[Dict[str, Any]], Awaitable[None]]


def is_driving(snapshot: Dict[str, Any]) -> bool:
    """Heuristic: gear in D/R/N or non-zero speed."""
    shift = snapshot.get("shift_state")
    if shift is not None:
        shift_u = str(shift).upper()
        if shift_u in _DRIVING_SHIFTS:
            return True
        if shift_u in _PARKED_SHIFTS:
            return False

    label = str(snapshot.get("drive_state_label") or "").lower()
    if label == "driving":
        return True
    if label == "parked":
        return False

    speed = snapshot.get("speed_kmh")
    try:
        if speed is not None and float(speed) > 1.0:
            return True
    except (TypeError, ValueError):
        pass
    return False


def is_parked(snapshot: Dict[str, Any]) -> bool:
    return not is_driving(snapshot)


class TripMonitor:
    """Async poll loop that starts/ends trips from vehicle snapshots."""

    def __init__(
        self,
        tesla: Optional[TeslaClient] = None,
        logger: Optional[TripLogger] = None,
        poll_seconds: Optional[float] = None,
        min_trip_km: float = MIN_TRIP_KM_DEFAULT,
        park_debounce_polls: int = 2,
        wake_when_idle: bool = False,
        on_trip_end: Optional[OnTripEnd] = None,
        on_snapshot: Optional[OnSnapshot] = None,
    ):
        self.tesla = tesla or TeslaClient()
        self.logger = logger or TripLogger()
        self.poll_seconds = float(
            poll_seconds if poll_seconds is not None else config.TRIP_POLL_SECONDS
        )
        self.min_trip_km = min_trip_km
        self.park_debounce_polls = max(1, int(park_debounce_polls))
        self.wake_when_idle = wake_when_idle
        self.on_trip_end = on_trip_end
        self.on_snapshot = on_snapshot

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._parked_streak = 0
        self._last_snapshot: Optional[Dict[str, Any]] = None
        self._active_trip_id: Optional[int] = None

        # Resume in-memory pointer if DB already has an active trip
        active = self.logger.get_active_trip()
        if active:
            self._active_trip_id = int(active["id"])

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def active_trip_id(self) -> Optional[int]:
        return self._active_trip_id

    @property
    def last_snapshot(self) -> Optional[Dict[str, Any]]:
        return self._last_snapshot

    def status_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "demo": self.tesla.demo,
            "poll_seconds": self.poll_seconds,
            "active_trip_id": self._active_trip_id,
            "parked_streak": self._parked_streak,
            "last_drive_state": (
                (self._last_snapshot or {}).get("drive_state_label")
            ),
            "last_battery": (self._last_snapshot or {}).get("battery_level"),
        }

    async def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="trip-monitor")
        mode = "demo" if self.tesla.demo else "live"
        print(
            f"📡 TripMonitor started ({mode}, every {self.poll_seconds}s, "
            f"park debounce={self.park_debounce_polls})"
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.poll_seconds + 5)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        print("📡 TripMonitor stopped")

    async def poll_once(self) -> Optional[Dict[str, Any]]:
        """Fetch one snapshot and process transitions. Useful for tests."""
        snapshot = await self._fetch_snapshot()
        if snapshot is None:
            return None
        await self._process_snapshot(snapshot)
        if self.on_snapshot is not None:
            try:
                await self.on_snapshot(snapshot)
            except Exception as exc:
                print(f"⚠️ on_snapshot error: {exc}")
        return snapshot

    async def run_for(self, duration_s: float) -> None:
        """Run the monitor for a fixed duration then stop (tests / demos)."""
        await self.start()
        try:
            await asyncio.sleep(duration_s)
        finally:
            await self.stop()

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:  # keep loop alive
                print(f"⚠️ TripMonitor poll error: {exc}")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def _fetch_snapshot(self) -> Optional[Dict[str, Any]]:
        active = self._active_trip_id is not None
        wake = self.wake_when_idle or active
        try:
            # When idle and car likely asleep, avoid aggressive wake in live mode
            if not self.tesla.demo and not wake:
                # list-only soft check would still hit network; get_vehicle_data
                # with wake=False may 408 — treat as parked/asleep skip
                try:
                    return await self.tesla.get_vehicle_data(wake=False)
                except TeslaAPIError as exc:
                    if exc.status_code == 408:
                        print("😴 Vehicle asleep — skip poll (no active trip)")
                        return None
                    raise
            return await self.tesla.get_vehicle_data(wake=wake)
        except TeslaAPIError as exc:
            print(f"⚠️ Tesla API: {exc}")
            return None

    async def _process_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self._last_snapshot = snapshot
        driving = is_driving(snapshot)

        if self._active_trip_id is None:
            if driving:
                self._parked_streak = 0
                self._active_trip_id = self.logger.start_trip(snapshot)
            return

        # Active trip
        if driving:
            self._parked_streak = 0
            return

        # Parked while trip active — debounce end (traffic lights)
        self._parked_streak += 1
        if self._parked_streak < self.park_debounce_polls:
            print(
                f"⏸️ Parked signal {self._parked_streak}/"
                f"{self.park_debounce_polls} — waiting to end trip "
                f"#{self._active_trip_id}"
            )
            return

        trip_id = self._active_trip_id
        summary = self.logger.end_trip(
            trip_id,
            snapshot,
            min_distance_km=self.min_trip_km,
        )
        self._active_trip_id = None
        self._parked_streak = 0
        if self.on_trip_end is not None:
            await self.on_trip_end(summary)


async def _demo_simulation() -> None:
    """Simulate a short drive and verify trip logging. python -m trip_monitor"""
    import os
    import tempfile

    db_fd, db_path = tempfile.mkstemp(prefix="trips_test_", suffix=".db")
    os.close(db_fd)
    try:
        tesla = TeslaClient(demo=True)
        logger = TripLogger(db_path=db_path)
        completed = []

        async def on_end(summary: Dict[str, Any]) -> None:
            completed.append(summary)

        monitor = TripMonitor(
            tesla=tesla,
            logger=logger,
            poll_seconds=0.05,
            park_debounce_polls=2,
            min_trip_km=0.2,
            on_trip_end=on_end,
        )

        print("=== demo simulation: parked → drive → park ===")
        # 1) Parked
        tesla.demo_set_parked()
        s = await monitor.poll_once()
        assert s and is_parked(s)
        assert logger.get_active_trip() is None
        print("  parked: no active trip ✓")

        # 2) Start driving
        tesla.demo_set_driving(speed_kmh=60.0)
        s = await monitor.poll_once()
        assert s and is_driving(s)
        active = logger.get_active_trip()
        assert active is not None
        print(f"  driving: active trip #{active['id']} ✓")

        # Advance odometer / battery like a real poll loop would
        start_odo = float(s["odometer_km"])
        for _ in range(5):
            # ~1 km per poll at fixed bump for test determinism
            tesla._demo_odometer_km += 1.0
            tesla._demo_battery -= 0.3
            tesla._demo_lat += 0.001
            await monitor.poll_once()

        mid = await tesla.get_vehicle_data()
        assert float(mid["odometer_km"]) >= start_odo + 5.0 - 0.01
        print(f"  odometer advanced to {mid['odometer_km']} km ✓")

        # 3) Park — need debounce polls
        tesla.demo_set_parked()
        await monitor.poll_once()  # streak 1
        assert logger.get_active_trip() is not None
        print("  park debounce 1/2 — still active ✓")
        await monitor.poll_once()  # streak 2 → end
        assert logger.get_active_trip() is None
        assert len(completed) == 1
        summary = completed[0]
        assert summary["status"] == "completed"
        assert summary["distance_km"] >= 5.0
        assert summary["energy_used_kwh"] > 0
        assert summary["cost_cop"] > 0
        print(f"  trip completed: {summary}")

        # 4) Tiny move should cancel
        tesla.demo_set_driving(5.0)
        await monitor.poll_once()
        tesla._demo_odometer_km += 0.05  # < 0.2 km
        tesla.demo_set_parked()
        await monitor.poll_once()
        await monitor.poll_once()
        recent = logger.get_recent_trips(limit=5)
        # only the completed ~5km trip, not the tiny one
        assert all(t["distance_km"] >= 0.2 for t in recent)
        print("  tiny trip cancelled ✓")

        # 5) Summary
        summ = logger.get_summary("today")
        print(f"  summary: {summ}")
        assert summ["trip_count"] >= 1
        print(logger.format_recent())

        # 6) Live-style poll path with demo client still works via run_for
        print("\n=== short run_for loop ===")
        tesla.demo_set_driving(40)
        await monitor.run_for(0.2)
        print("  run_for OK ✓")

        print("\nALL TRIP MONITOR TESTS PASSED")
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(_demo_simulation())
