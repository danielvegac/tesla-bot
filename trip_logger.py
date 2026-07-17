"""Accurate trip logging using odometer, battery, and config energy rates."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import config

os.makedirs("logs", exist_ok=True)

DEFAULT_DB_PATH = os.path.join("logs", "trips.db")
MIN_TRIP_KM_DEFAULT = 0.2

# Full schema columns (order used for CREATE)
_SCHEMA_COLUMNS = """
    id INTEGER PRIMARY KEY,
    start_time TEXT NOT NULL,
    end_time TEXT,
    start_odometer_km REAL,
    end_odometer_km REAL,
    distance_km REAL,
    battery_start REAL,
    battery_end REAL,
    battery_used_pct REAL,
    energy_used_kwh REAL,
    efficiency_wh_per_km REAL,
    cost_cop REAL,
    charge_context TEXT,
    start_lat REAL,
    start_lon REAL,
    end_lat REAL,
    end_lon REAL,
    status TEXT
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Support both Z and offset forms
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class TripLogger:
    """SQLite-backed trip store with odometer-based distance and kWh cost."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_table()
        self._migrate_if_needed()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_table(self) -> None:
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS trips ({_SCHEMA_COLUMNS})"
        )
        self.conn.commit()

    def _column_names(self) -> set:
        rows = self.conn.execute("PRAGMA table_info(trips)").fetchall()
        return {r[1] for r in rows}

    def _migrate_if_needed(self) -> None:
        cols = self._column_names()
        required = {
            "start_time",
            "end_time",
            "start_odometer_km",
            "end_odometer_km",
            "distance_km",
            "battery_start",
            "battery_end",
            "battery_used_pct",
            "energy_used_kwh",
            "efficiency_wh_per_km",
            "cost_cop",
            "charge_context",
            "start_lat",
            "start_lon",
            "end_lat",
            "end_lon",
            "status",
        }
        if required.issubset(cols):
            return

        # Legacy table from scaffold: id, end_time, distance_km, battery_used, cost_cop
        self.conn.execute("ALTER TABLE trips RENAME TO trips_legacy")
        self.conn.execute(f"CREATE TABLE trips ({_SCHEMA_COLUMNS})")
        legacy_cols = self._column_names_for("trips_legacy")
        if "distance_km" in legacy_cols:
            self.conn.execute(
                """
                INSERT INTO trips (
                    id, start_time, end_time, distance_km,
                    battery_used_pct, cost_cop, status, charge_context
                )
                SELECT
                    id,
                    COALESCE(end_time, ?),
                    end_time,
                    distance_km,
                    battery_used,
                    cost_cop,
                    'completed',
                    'unknown'
                FROM trips_legacy
                """,
                (_utc_now_iso(),),
            )
        self.conn.execute("DROP TABLE trips_legacy")
        self.conn.commit()
        print("📦 Migrated trips table to accurate schema")

    def _column_names_for(self, table: str) -> set:
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r[1] for r in rows}

    # ------------------------------------------------------------------
    # Cost / energy math
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_energy_kwh(battery_used_pct: float, capacity_kwh: Optional[float] = None) -> float:
        cap = capacity_kwh if capacity_kwh is not None else config.BATTERY_CAPACITY_KWH
        return max(0.0, float(battery_used_pct)) / 100.0 * float(cap)

    @staticmethod
    def rate_for_context(charge_context: str) -> float:
        ctx = (charge_context or "home").lower()
        if ctx in {"supercharger", "sc", "fast"}:
            return float(config.SUPERCHARGER_RATE)
        if ctx in {"unknown", ""}:
            return float(config.HOME_ELECTRICITY_RATE)
        return float(config.HOME_ELECTRICITY_RATE)

    @classmethod
    def compute_cost_cop(
        cls,
        energy_used_kwh: float,
        charge_context: str = "home",
    ) -> float:
        return round(max(0.0, energy_used_kwh) * cls.rate_for_context(charge_context), 2)

    @staticmethod
    def infer_charge_context(snapshot: Optional[Dict[str, Any]] = None) -> str:
        """Best-effort charge context from a vehicle snapshot."""
        if not snapshot:
            return "home"
        charging = str(snapshot.get("charging_state") or "").lower()
        power = snapshot.get("charger_power") or 0
        try:
            power = float(power)
        except (TypeError, ValueError):
            power = 0.0
        # Superchargers typically report high kW; also keyword heuristics
        if "supercharger" in charging or power >= 50:
            return "supercharger"
        return "home"

    # ------------------------------------------------------------------
    # Trip lifecycle
    # ------------------------------------------------------------------

    def start_trip(
        self,
        snapshot: Dict[str, Any],
        charge_context: Optional[str] = None,
    ) -> int:
        """Open a new active trip from a vehicle snapshot. Returns trip id."""
        active = self.get_active_trip()
        if active is not None:
            return int(active["id"])

        ctx = charge_context or self.infer_charge_context(snapshot)
        start_time = _utc_now_iso()
        cur = self.conn.execute(
            """
            INSERT INTO trips (
                start_time, start_odometer_km, battery_start,
                start_lat, start_lon, charge_context, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                start_time,
                snapshot.get("odometer_km"),
                snapshot.get("battery_level"),
                snapshot.get("latitude"),
                snapshot.get("longitude"),
                ctx,
            ),
        )
        self.conn.commit()
        trip_id = int(cur.lastrowid)
        print(
            f"🚗 Trip #{trip_id} started @ {snapshot.get('odometer_km')} km, "
            f"battery {snapshot.get('battery_level')}%"
        )
        return trip_id

    def end_trip(
        self,
        trip_id: int,
        snapshot: Dict[str, Any],
        *,
        min_distance_km: float = MIN_TRIP_KM_DEFAULT,
        cancel_if_tiny: bool = True,
    ) -> Dict[str, Any]:
        """Close an active trip using odometer delta and config rates."""
        row = self.conn.execute(
            "SELECT * FROM trips WHERE id = ? AND status = 'active'",
            (trip_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No active trip with id={trip_id}")

        start_odo = row["start_odometer_km"]
        end_odo = snapshot.get("odometer_km")
        battery_start = row["battery_start"]
        battery_end = snapshot.get("battery_level")

        if start_odo is not None and end_odo is not None:
            distance_km = max(0.0, float(end_odo) - float(start_odo))
        else:
            distance_km = 0.0

        if (
            cancel_if_tiny
            and distance_km < min_distance_km
            and (start_odo is not None and end_odo is not None)
        ):
            self.conn.execute(
                """
                UPDATE trips SET
                    end_time = ?, end_odometer_km = ?, distance_km = ?,
                    battery_end = ?, end_lat = ?, end_lon = ?,
                    status = 'cancelled'
                WHERE id = ?
                """,
                (
                    _utc_now_iso(),
                    end_odo,
                    round(distance_km, 3),
                    battery_end,
                    snapshot.get("latitude"),
                    snapshot.get("longitude"),
                    trip_id,
                ),
            )
            self.conn.commit()
            summary = {
                "id": trip_id,
                "status": "cancelled",
                "distance_km": round(distance_km, 3),
                "reason": f"below min distance {min_distance_km} km",
            }
            print(f"↩️ Trip #{trip_id} cancelled (only {distance_km:.3f} km)")
            return summary

        if battery_start is not None and battery_end is not None:
            battery_used_pct = max(0.0, float(battery_start) - float(battery_end))
        else:
            battery_used_pct = 0.0

        energy_used_kwh = self.estimate_energy_kwh(battery_used_pct)
        efficiency = None
        if distance_km > 0:
            efficiency = round((energy_used_kwh * 1000.0) / distance_km, 1)

        charge_context = row["charge_context"] or "home"
        cost_cop = self.compute_cost_cop(energy_used_kwh, charge_context)
        end_time = _utc_now_iso()

        self.conn.execute(
            """
            UPDATE trips SET
                end_time = ?,
                end_odometer_km = ?,
                distance_km = ?,
                battery_end = ?,
                battery_used_pct = ?,
                energy_used_kwh = ?,
                efficiency_wh_per_km = ?,
                cost_cop = ?,
                end_lat = ?,
                end_lon = ?,
                status = 'completed'
            WHERE id = ?
            """,
            (
                end_time,
                end_odo,
                round(distance_km, 3),
                battery_end,
                round(battery_used_pct, 2),
                round(energy_used_kwh, 3),
                efficiency,
                cost_cop,
                snapshot.get("latitude"),
                snapshot.get("longitude"),
                trip_id,
            ),
        )
        self.conn.commit()

        summary = {
            "id": trip_id,
            "status": "completed",
            "start_time": row["start_time"],
            "end_time": end_time,
            "distance_km": round(distance_km, 3),
            "battery_start": battery_start,
            "battery_end": battery_end,
            "battery_used_pct": round(battery_used_pct, 2),
            "energy_used_kwh": round(energy_used_kwh, 3),
            "efficiency_wh_per_km": efficiency,
            "cost_cop": cost_cop,
            "charge_context": charge_context,
        }
        print(
            f"📝 Trip #{trip_id} completed: {summary['distance_km']} km, "
            f"{summary['battery_used_pct']}% → {summary['energy_used_kwh']} kWh, "
            f"COP {cost_cop}"
        )
        return summary

    # Back-compat helper from original scaffold
    def log_trip(
        self,
        distance_km: float,
        battery_start: float,
        battery_end: float,
        charge_context: str = "home",
    ) -> Dict[str, Any]:
        """Manual one-shot trip insert (no live odometer). Prefer start/end_trip."""
        battery_used = max(0.0, float(battery_start) - float(battery_end))
        energy = self.estimate_energy_kwh(battery_used)
        cost = self.compute_cost_cop(energy, charge_context)
        efficiency = None
        if distance_km > 0:
            efficiency = round((energy * 1000.0) / float(distance_km), 1)
        now = _utc_now_iso()
        cur = self.conn.execute(
            """
            INSERT INTO trips (
                start_time, end_time, distance_km,
                battery_start, battery_end, battery_used_pct,
                energy_used_kwh, efficiency_wh_per_km, cost_cop,
                charge_context, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed')
            """,
            (
                now,
                now,
                float(distance_km),
                battery_start,
                battery_end,
                battery_used,
                round(energy, 3),
                efficiency,
                cost,
                charge_context,
            ),
        )
        self.conn.commit()
        result = {
            "id": int(cur.lastrowid),
            "distance_km": float(distance_km),
            "battery_used": battery_used,
            "battery_used_pct": battery_used,
            "energy_used_kwh": round(energy, 3),
            "cost_cop": cost,
            "efficiency_wh_per_km": efficiency,
        }
        print(
            f"📝 Trip logged: {distance_km}km, {battery_used}% used, "
            f"{result['energy_used_kwh']} kWh, COP {cost}"
        )
        return result

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_trip(self) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM trips WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_recent_trips(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM trips
            WHERE status = 'completed'
            ORDER BY COALESCE(end_time, start_time) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self, period: str = "today") -> Dict[str, Any]:
        """Aggregate completed trips for today or the last 7 days."""
        now = datetime.now(timezone.utc)
        if period == "week":
            since = (now - timedelta(days=7)).replace(microsecond=0).isoformat()
        else:
            since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            period = "today"

        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS trip_count,
                COALESCE(SUM(distance_km), 0) AS total_distance_km,
                COALESCE(SUM(energy_used_kwh), 0) AS total_energy_kwh,
                COALESCE(SUM(cost_cop), 0) AS total_cost_cop,
                AVG(efficiency_wh_per_km) AS avg_efficiency_wh_per_km
            FROM trips
            WHERE status = 'completed'
              AND COALESCE(end_time, start_time) >= ?
            """,
            (since,),
        ).fetchone()

        return {
            "period": period,
            "since": since,
            "trip_count": int(row["trip_count"] or 0),
            "total_distance_km": round(float(row["total_distance_km"] or 0), 3),
            "total_energy_kwh": round(float(row["total_energy_kwh"] or 0), 3),
            "total_cost_cop": round(float(row["total_cost_cop"] or 0), 2),
            "avg_efficiency_wh_per_km": (
                round(float(row["avg_efficiency_wh_per_km"]), 1)
                if row["avg_efficiency_wh_per_km"] is not None
                else None
            ),
        }

    def format_recent(self, limit: int = 5) -> str:
        trips = self.get_recent_trips(limit=limit)
        if not trips:
            return "No completed trips yet."
        lines = ["Recent trips:"]
        for t in trips:
            lines.append(
                f"#{t['id']} {t.get('distance_km') or 0:.1f} km | "
                f"{t.get('battery_used_pct') or 0:.1f}% | "
                f"{t.get('energy_used_kwh') or 0:.2f} kWh | "
                f"COP {t.get('cost_cop') or 0:.0f}"
            )
        return "\n".join(lines)
