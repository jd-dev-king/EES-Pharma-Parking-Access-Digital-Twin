import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import close_pool, connection, open_pool, run_sql_file

import asyncio
import random
from datetime import datetime, timedelta, time

BASE_DIR = Path(__file__).resolve().parent


def normalize_vehicle(value: str) -> str:
    return " ".join(value.strip().upper().split())


class VehicleRequest(BaseModel):
    vehicle_identifier: str = Field(min_length=2, max_length=64)


class SecurityDecision(BaseModel):
    security_user: str = Field(default="SECURITY-DEMO", min_length=2, max_length=80)
    notes: str | None = Field(default=None, max_length=500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(title="EES Pharma Parking Access API", version="3.0.4", lifespan=lifespan)

AUTO_RUN = {
    "active": False,
    "cycle": 0,
    "sim_day": "MONDAY",
    "sim_time": "05:30",
    "sim_minutes": 330,
    "speed": 1,
    "phase": "IDLE",
    "current_event": "Waiting",
    "next_event": "Start auto run",
    "overflow": 0,
    "overflow_vehicles": [],
    "completed_entries": 0,
    "completed_exits": 0,
    "started_at": None,
    "finished_at": None,
    "contractors_on_site": 0,
    "visitors_on_site": 0,
    "contractor_entries": 0,
    "visitor_entries": 0,
    "visitor_security_reviews": 0,
}

AUTO_RUN_TASK = None

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

AUTO_RUN_CONTRACTORS = [
    f"CONTRACTOR-AUTO-{n:02d}"
    for n in range(1, 13)
]

AUTO_RUN_VISITORS = [
    f"VISITOR-AUTO-{n:02d}"
    for n in range(1, 21)
]


def log_event(cur, gate_id, vehicle_identifier, event_type, result, reason=None, visitor_pass_id=None):
    cur.execute(
        """
        INSERT INTO parking_access.access_events
        (gate_id, vehicle_identifier, visitor_pass_id, event_type, access_result, reason)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (gate_id, vehicle_identifier, visitor_pass_id, event_type, result, reason),
    )


def allocate_space(cur):
    cur.execute(
        """
        SELECT space_id, space_number
        FROM parking_access.parking_spaces
        WHERE occupied=FALSE
        ORDER BY zone, space_number
        FOR UPDATE SKIP LOCKED
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=409, detail="Parking lot is full")
    return row

def allocate_overflow_space(cur):
    cur.execute(
        """
        SELECT overflow_space_id, space_number
        FROM parking_access.overflow_spaces
        WHERE occupied=FALSE
          AND active=TRUE
        ORDER BY overflow_space_id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
        """
    )

    row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=409,
            detail="Overflow parking lot is full",
        )

    return row


def create_overflow_session(
    cur,
    vehicle_identifier,
    occupant_type,
    *,
    employee_vehicle_id=None,
    visitor_pass_id=None,
    security_request_id=None,
    reason=None,
):
    """Persist an active overflow parking assignment."""

    cur.execute(
        """
        SELECT overflow_session_id
        FROM parking_access.overflow_sessions
        WHERE vehicle_identifier=%s
          AND session_status='ACTIVE'
        LIMIT 1
        """,
        (vehicle_identifier,),
    )

    existing = cur.fetchone()

    if existing:
        return {
            "result": "ALREADY_PRESENT",
            "overflow_session_id": existing["overflow_session_id"],
            "vehicle_identifier": vehicle_identifier,
        }

    overflow_space = allocate_overflow_space(cur)

    cur.execute(
        """
        UPDATE parking_access.overflow_spaces
        SET
            occupied=TRUE,
            updated_at=CURRENT_TIMESTAMP
        WHERE overflow_space_id=%s
        """,
        (overflow_space["overflow_space_id"],),
    )

    cur.execute(
        """
        INSERT INTO parking_access.overflow_sessions (
            vehicle_identifier,
            occupant_type,
            employee_vehicle_id,
            visitor_pass_id,
            security_request_id,
            overflow_space_id
        )
        VALUES (%s,%s,%s,%s,%s,%s)
        RETURNING overflow_session_id, entry_time
        """,
        (
            vehicle_identifier,
            occupant_type,
            employee_vehicle_id,
            visitor_pass_id,
            security_request_id,
            overflow_space["overflow_space_id"],
        ),
    )

    session = cur.fetchone()

    log_event(
        cur,
        "OVERFLOW",
        vehicle_identifier,
        f"{occupant_type}_OVERFLOW_ENTRY",
        "GRANTED",
        reason or (
            f"Secured lot full; routed to overflow "
            f"{overflow_space['space_number']}"
        ),
        visitor_pass_id,
    )

    return {
        "result": "OVERFLOW",
        "vehicle_identifier": vehicle_identifier,
        "overflow_session_id": session["overflow_session_id"],
        "entry_time": session["entry_time"],
        "overflow_space_number": overflow_space["space_number"],
    }


def sim_clock():
    hours = (AUTO_RUN["sim_minutes"] // 60) % 24
    minutes = AUTO_RUN["sim_minutes"] % 60
    return f"{hours:02d}:{minutes:02d}"


def set_sim_time(minutes):
    AUTO_RUN["sim_minutes"] = minutes % 1440
    AUTO_RUN["sim_time"] = sim_clock()


def auto_run_status():
    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE occupant_type='EMPLOYEE'
                ) AS employees,
                COUNT(*) FILTER (
                    WHERE occupant_type='VISITOR'
                ) AS visitors,
                COUNT(*) AS occupied
            FROM parking_access.parking_sessions
            WHERE session_status='ACTIVE'
        """)

        secured_counts = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS capacity
            FROM parking_access.parking_spaces
        """)

        secured_capacity = cur.fetchone()["capacity"]

        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE occupant_type='EMPLOYEE'
                ) AS employees,
                COUNT(*) FILTER (
                    WHERE occupant_type='CONTRACTOR'
                ) AS contractors,
                COUNT(*) FILTER (
                    WHERE occupant_type='VISITOR'
                ) AS visitors,
                COUNT(*) AS occupied
            FROM parking_access.overflow_sessions
            WHERE session_status='ACTIVE'
        """)

        overflow_counts = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS capacity
            FROM parking_access.overflow_spaces
            WHERE active=TRUE
        """)

        overflow_capacity = cur.fetchone()["capacity"]

        cur.execute("""
            SELECT vehicle_identifier
            FROM parking_access.overflow_sessions
            WHERE session_status='ACTIVE'
            ORDER BY entry_time, overflow_session_id
        """)

        overflow_vehicles = [
            row["vehicle_identifier"]
            for row in cur.fetchall()
        ]

        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE vehicle_identifier LIKE 'CONTRACTOR-AUTO-%'
                ) AS contractors,
                COUNT(*) FILTER (
                    WHERE vehicle_identifier LIKE 'VISITOR-AUTO-%'
                ) AS visitors
            FROM parking_access.parking_sessions
            WHERE session_status='ACTIVE'
              AND occupant_type='VISITOR'
        """)

        secured_auto_visitors = cur.fetchone()

    secured_occupied = int(secured_counts["occupied"] or 0)
    secured_employees = int(secured_counts["employees"] or 0)

    overflow_occupied = int(overflow_counts["occupied"] or 0)
    overflow_employees = int(overflow_counts["employees"] or 0)

    contractors_on_site = (
        int(secured_auto_visitors["contractors"] or 0)
        + int(overflow_counts["contractors"] or 0)
    )

    regular_visitors_on_site = (
        int(secured_auto_visitors["visitors"] or 0)
        + int(overflow_counts["visitors"] or 0)
    )

    return {
        **AUTO_RUN,
        "capacity": int(secured_capacity or 0),
        "occupied": secured_occupied,
        "remaining": max(
            int(secured_capacity or 0) - secured_occupied,
            0,
        ),
        "employees": secured_employees + overflow_employees,
        "visitors": regular_visitors_on_site,
        "contractors_on_site": contractors_on_site,
        "visitors_on_site": regular_visitors_on_site,
        "overflow": overflow_occupied,
        "overflow_capacity": int(overflow_capacity or 0),
        "overflow_remaining": max(
            int(overflow_capacity or 0) - overflow_occupied,
            0,
        ),
        "overflow_full": (
            overflow_occupied >= int(overflow_capacity or 0)
            if int(overflow_capacity or 0) > 0
            else True
        ),
        "overflow_vehicles": overflow_vehicles,
        "total_parked": secured_occupied + overflow_occupied,
    }

def load_auto_run_workforce():

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT
                w.employee_id,
                w.employee_number,
                w.display_name,
                w.department_name,

                ev.vehicle_id,
                ev.vehicle_identifier,

                s.shift_code,
                s.shift_name,
                s.start_time,
                s.end_time,
                s.crosses_midnight,
                s.operating_days

            FROM workforce.employees w

            JOIN parking_access.employee_vehicles ev
              ON ev.workforce_employee_id = w.employee_id
             AND ev.active = TRUE

            JOIN workforce.employee_shift_assignments esa
              ON esa.employee_id = w.employee_id
             AND esa.active = TRUE
             AND esa.is_primary = TRUE

            JOIN workforce.shifts s
              ON s.shift_id = esa.shift_id

            WHERE w.site_code = 'PHARMA-001'
              AND w.employment_status = 'ACTIVE'
              AND w.commute_mode = 'VEHICLE'

            ORDER BY
                s.start_time,
                w.department_name,
                w.display_name
        """)

        return cur.fetchall()  
    
def auto_enter_employee(employee):

    vehicle = employee["vehicle_identifier"]

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT session_id
            FROM parking_access.parking_sessions
            WHERE vehicle_identifier=%s
              AND session_status='ACTIVE'
        """, (vehicle,))

        if cur.fetchone():
            return {
                "result": "ALREADY_PRESENT",
                "vehicle_identifier": vehicle,
            }

        cur.execute("""
            SELECT overflow_session_id
            FROM parking_access.overflow_sessions
            WHERE vehicle_identifier=%s
              AND session_status='ACTIVE'
        """, (vehicle,))

        if cur.fetchone():
            return {
                "result": "ALREADY_PRESENT",
                "vehicle_identifier": vehicle,
            }

        employee_record = employee_record_for_vehicle(
            cur,
            vehicle,
        )

        exception = employee_exception_reason(
            employee_record
        )

        if not employee_record or exception:
            return {
                "result": "DENIED",
                "vehicle_identifier": vehicle,
                "reason": exception or "Employee not recognized",
            }

        try:
            space = allocate_space(cur)

        except HTTPException as exc:

            if exc.status_code != 409:
                raise

            try:
                result = create_overflow_session(
                    cur,
                    vehicle,
                    "EMPLOYEE",
                    employee_vehicle_id=employee_record["vehicle_id"],
                    reason=(
                        "Secured employee lot full; "
                        f"{employee['display_name']} routed to overflow."
                    ),
                )

            except HTTPException as overflow_exc:
                if overflow_exc.status_code == 409:
                    log_event(
                        cur,
                        "OVERFLOW",
                        vehicle,
                        "OVERFLOW_CAPACITY_EXHAUSTED",
                        "DENIED",
                        "Both secured and overflow parking are full.",
                    )
                    conn.commit()

                    return {
                        "result": "OVERFLOW_FULL",
                        "vehicle_identifier": vehicle,
                    }

                raise

            conn.commit()

            AUTO_RUN["completed_entries"] += 1

            return result

        cur.execute("""
            UPDATE parking_access.parking_spaces
            SET
                occupied=TRUE,
                updated_at=CURRENT_TIMESTAMP
            WHERE space_id=%s
        """, (space["space_id"],))

        cur.execute("""
            INSERT INTO parking_access.parking_sessions (
                vehicle_identifier,
                occupant_type,
                employee_vehicle_id,
                space_id
            )
            VALUES (%s,'EMPLOYEE',%s,%s)
            RETURNING session_id
        """, (
            vehicle,
            employee_record["vehicle_id"],
            space["space_id"],
        ))

        session = cur.fetchone()

        log_event(
            cur,
            "AUTO_ENTRY",
            vehicle,
            "AUTO_SHIFT_ENTRY",
            "GRANTED",
            (
                f"Accelerated auto-run: "
                f"{employee['shift_name']}"
            ),
        )

        conn.commit()

        AUTO_RUN["completed_entries"] += 1

        return {
            "result": "GRANTED",
            "vehicle_identifier": vehicle,
            "employee_number": employee["employee_number"],
            "display_name": employee["display_name"],
            "spot_number": space["space_number"],
            "session_id": session["session_id"],
        }

def allocate_visitor_pass(cur):

    cur.execute("""
        SELECT
            visitor_pass_id,
            visitor_code
        FROM parking_access.visitor_passes
        WHERE status='AVAILABLE'
        ORDER BY visitor_code
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """)

    return cur.fetchone()    

def auto_enter_contractor(vehicle):

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT session_id
            FROM parking_access.parking_sessions
            WHERE vehicle_identifier=%s
              AND session_status='ACTIVE'
        """, (vehicle,))

        if cur.fetchone():
            return "ALREADY_PRESENT"

        cur.execute("""
            SELECT overflow_session_id
            FROM parking_access.overflow_sessions
            WHERE vehicle_identifier=%s
              AND session_status='ACTIVE'
        """, (vehicle,))

        if cur.fetchone():
            return "ALREADY_PRESENT"

        secured_space = None
        overflow_space = None

        try:
            secured_space = allocate_space(cur)

        except HTTPException as exc:
            if exc.status_code != 409:
                raise

            try:
                overflow_space = allocate_overflow_space(cur)
            except HTTPException as overflow_exc:
                if overflow_exc.status_code == 409:
                    log_event(
                        cur,
                        "OVERFLOW",
                        vehicle,
                        "OVERFLOW_CAPACITY_EXHAUSTED",
                        "DENIED",
                        "Both secured and overflow parking are full.",
                    )
                    conn.commit()
                    return "OVERFLOW_FULL"

                raise

        visitor_pass = allocate_visitor_pass(cur)

        if not visitor_pass:
            return "NO_PASS"

        cur.execute("""
            UPDATE parking_access.visitor_passes
            SET
                status='ACTIVE',
                issued_at=CURRENT_TIMESTAMP,
                activated_at=CURRENT_TIMESTAMP,
                returned_at=NULL,
                reusable_after=NULL,
                updated_at=CURRENT_TIMESTAMP
            WHERE visitor_pass_id=%s
        """, (
            visitor_pass["visitor_pass_id"],
        ))

        if secured_space is not None:

            cur.execute("""
                UPDATE parking_access.parking_spaces
                SET
                    occupied=TRUE,
                    updated_at=CURRENT_TIMESTAMP
                WHERE space_id=%s
            """, (
                secured_space["space_id"],
            ))

            cur.execute("""
                INSERT INTO parking_access.parking_sessions (
                    vehicle_identifier,
                    occupant_type,
                    visitor_pass_id,
                    space_id
                )
                VALUES (%s,'VISITOR',%s,%s)
                RETURNING session_id, entry_time
            """, (
                vehicle,
                visitor_pass["visitor_pass_id"],
                secured_space["space_id"],
            ))

            cur.fetchone()

            log_event(
                cur,
                "AUTO_ENTRY",
                vehicle,
                "PLANNED_CONTRACTOR_ENTRY",
                "GRANTED",
                (
                    "Pre-authorized contractor auto-run arrival; "
                    f"visitor credential {visitor_pass['visitor_code']} issued"
                ),
                visitor_pass["visitor_pass_id"],
            )

            result = "GRANTED"

        else:

            cur.execute("""
                UPDATE parking_access.overflow_spaces
                SET
                    occupied=TRUE,
                    updated_at=CURRENT_TIMESTAMP
                WHERE overflow_space_id=%s
            """, (
                overflow_space["overflow_space_id"],
            ))

            cur.execute("""
                INSERT INTO parking_access.overflow_sessions (
                    vehicle_identifier,
                    occupant_type,
                    visitor_pass_id,
                    overflow_space_id
                )
                VALUES (%s,'CONTRACTOR',%s,%s)
            """, (
                vehicle,
                visitor_pass["visitor_pass_id"],
                overflow_space["overflow_space_id"],
            ))

            log_event(
                cur,
                "OVERFLOW",
                vehicle,
                "CONTRACTOR_OVERFLOW_ENTRY",
                "GRANTED",
                (
                    f"Secured lot full; planned contractor routed to "
                    f"{overflow_space['space_number']} with "
                    f"{visitor_pass['visitor_code']}."
                ),
                visitor_pass["visitor_pass_id"],
            )

            result = "OVERFLOW"

        conn.commit()

        AUTO_RUN["contractor_entries"] += 1
        AUTO_RUN["contractors_on_site"] += 1
        AUTO_RUN["completed_entries"] += 1

        return result

async def auto_enter_visitor(vehicle):

    AUTO_RUN["visitor_security_reviews"] += 1

    AUTO_RUN["phase"] = "SECURITY_REVIEW"
    AUTO_RUN["current_event"] = (
        f"Security reviewing {vehicle}"
    )

    await asyncio.sleep(1.25)

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT session_id
            FROM parking_access.parking_sessions
            WHERE vehicle_identifier=%s
              AND session_status='ACTIVE'
        """, (vehicle,))

        if cur.fetchone():
            return "ALREADY_PRESENT"

        cur.execute("""
            SELECT overflow_session_id
            FROM parking_access.overflow_sessions
            WHERE vehicle_identifier=%s
              AND session_status='ACTIVE'
        """, (vehicle,))

        if cur.fetchone():
            return "ALREADY_PRESENT"

        cur.execute("""
            INSERT INTO parking_access.security_requests (
                vehicle_identifier,
                status,
                decided_at,
                security_user,
                notes
            )
            VALUES (
                %s,
                'APPROVED',
                CURRENT_TIMESTAMP,
                'AUTO-SECURITY',
                'Approved by accelerated simulation'
            )
            RETURNING security_request_id
        """, (vehicle,))

        security_request = cur.fetchone()

        secured_space = None
        overflow_space = None

        try:
            secured_space = allocate_space(cur)

        except HTTPException as exc:
            if exc.status_code != 409:
                raise

            try:
                overflow_space = allocate_overflow_space(cur)
            except HTTPException as overflow_exc:
                if overflow_exc.status_code == 409:
                    log_event(
                        cur,
                        "OVERFLOW",
                        vehicle,
                        "OVERFLOW_CAPACITY_EXHAUSTED",
                        "DENIED",
                        "Security approved visitor, but all parking is full.",
                    )
                    conn.commit()
                    return "OVERFLOW_FULL"

                raise

        visitor_pass = allocate_visitor_pass(cur)

        if not visitor_pass:
            return "NO_PASS"

        cur.execute("""
            UPDATE parking_access.visitor_passes
            SET
                status='ACTIVE',
                issued_at=CURRENT_TIMESTAMP,
                activated_at=CURRENT_TIMESTAMP,
                returned_at=NULL,
                reusable_after=NULL,
                updated_at=CURRENT_TIMESTAMP
            WHERE visitor_pass_id=%s
        """, (
            visitor_pass["visitor_pass_id"],
        ))

        if secured_space is not None:

            cur.execute("""
                UPDATE parking_access.parking_spaces
                SET
                    occupied=TRUE,
                    updated_at=CURRENT_TIMESTAMP
                WHERE space_id=%s
            """, (
                secured_space["space_id"],
            ))

            cur.execute("""
                INSERT INTO parking_access.parking_sessions (
                    vehicle_identifier,
                    occupant_type,
                    visitor_pass_id,
                    security_request_id,
                    space_id
                )
                VALUES (
                    %s,
                    'VISITOR',
                    %s,
                    %s,
                    %s
                )
            """, (
                vehicle,
                visitor_pass["visitor_pass_id"],
                security_request["security_request_id"],
                secured_space["space_id"],
            ))

            log_event(
                cur,
                "AUTO_ENTRY",
                vehicle,
                "VISITOR_SECURITY_APPROVED",
                "GRANTED",
                (
                    "Unscheduled visitor approved by Security; "
                    f"visitor credential {visitor_pass['visitor_code']} issued"
                ),
                visitor_pass["visitor_pass_id"],
            )

            result = "GRANTED"

        else:

            cur.execute("""
                UPDATE parking_access.overflow_spaces
                SET
                    occupied=TRUE,
                    updated_at=CURRENT_TIMESTAMP
                WHERE overflow_space_id=%s
            """, (
                overflow_space["overflow_space_id"],
            ))

            cur.execute("""
                INSERT INTO parking_access.overflow_sessions (
                    vehicle_identifier,
                    occupant_type,
                    visitor_pass_id,
                    security_request_id,
                    overflow_space_id
                )
                VALUES (
                    %s,
                    'VISITOR',
                    %s,
                    %s,
                    %s
                )
            """, (
                vehicle,
                visitor_pass["visitor_pass_id"],
                security_request["security_request_id"],
                overflow_space["overflow_space_id"],
            ))

            log_event(
                cur,
                "OVERFLOW",
                vehicle,
                "VISITOR_OVERFLOW_ENTRY",
                "GRANTED",
                (
                    f"Security approved visitor routed to "
                    f"{overflow_space['space_number']} with "
                    f"{visitor_pass['visitor_code']}."
                ),
                visitor_pass["visitor_pass_id"],
            )

            result = "OVERFLOW"

        conn.commit()

        AUTO_RUN["visitor_entries"] += 1
        AUTO_RUN["visitors_on_site"] += 1
        AUTO_RUN["completed_entries"] += 1

        return result

def auto_exit_vehicle(vehicle):

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT
                ps.session_id,
                ps.space_id,
                sp.space_number

            FROM parking_access.parking_sessions ps

            JOIN parking_access.parking_spaces sp
              ON sp.space_id = ps.space_id

            WHERE ps.vehicle_identifier=%s
              AND ps.session_status='ACTIVE'

            FOR UPDATE OF ps
        """, (vehicle,))

        session = cur.fetchone()

        if not session:
            return False

        cur.execute("""
            UPDATE parking_access.parking_sessions
            SET
                session_status='CLOSED',
                exit_time=CURRENT_TIMESTAMP
            WHERE session_id=%s
        """, (session["session_id"],))

        cur.execute("""
            UPDATE parking_access.parking_spaces
            SET
                occupied=FALSE,
                updated_at=CURRENT_TIMESTAMP
            WHERE space_id=%s
        """, (session["space_id"],))

        log_event(
            cur,
            "AUTO_EXIT",
            vehicle,
            "AUTO_SHIFT_EXIT",
            "GRANTED",
            (
                f"Accelerated auto-run released "
                f"space {session['space_number']}"
            ),
        )

        conn.commit()

    AUTO_RUN["completed_exits"] += 1
    return True  

def auto_exit_session(vehicle):

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT
                ps.session_id,
                ps.occupant_type,
                ps.space_id,
                ps.visitor_pass_id,
                sp.space_number

            FROM parking_access.parking_sessions ps

            JOIN parking_access.parking_spaces sp
              ON sp.space_id = ps.space_id

            WHERE ps.vehicle_identifier=%s
              AND ps.session_status='ACTIVE'

            FOR UPDATE OF ps
        """, (vehicle,))

        session = cur.fetchone()

        if session:

            cur.execute("""
                UPDATE parking_access.parking_sessions
                SET
                    session_status='CLOSED',
                    exit_time=CURRENT_TIMESTAMP
                WHERE session_id=%s
            """, (session["session_id"],))

            cur.execute("""
                UPDATE parking_access.parking_spaces
                SET
                    occupied=FALSE,
                    updated_at=CURRENT_TIMESTAMP
                WHERE space_id=%s
            """, (session["space_id"],))

            if session["visitor_pass_id"]:

                cur.execute("""
                    UPDATE parking_access.visitor_passes
                    SET
                        status='AVAILABLE',
                        returned_at=CURRENT_TIMESTAMP,
                        reusable_after=NULL,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE visitor_pass_id=%s
                """, (session["visitor_pass_id"],))

            log_event(
                cur,
                "AUTO_EXIT",
                vehicle,
                "AUTO_EXIT",
                "GRANTED",
                f"Secured space {session['space_number']} released",
                session["visitor_pass_id"],
            )

            conn.commit()

            AUTO_RUN["completed_exits"] += 1
            return True

        cur.execute("""
            SELECT
                os.overflow_session_id,
                os.occupant_type,
                os.overflow_space_id,
                os.visitor_pass_id,
                sp.space_number

            FROM parking_access.overflow_sessions os

            JOIN parking_access.overflow_spaces sp
              ON sp.overflow_space_id = os.overflow_space_id

            WHERE os.vehicle_identifier=%s
              AND os.session_status='ACTIVE'

            FOR UPDATE OF os
        """, (vehicle,))

        overflow_session = cur.fetchone()

        if not overflow_session:
            return False

        cur.execute("""
            UPDATE parking_access.overflow_sessions
            SET
                session_status='CLOSED',
                exit_time=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE overflow_session_id=%s
        """, (
            overflow_session["overflow_session_id"],
        ))

        cur.execute("""
            UPDATE parking_access.overflow_spaces
            SET
                occupied=FALSE,
                updated_at=CURRENT_TIMESTAMP
            WHERE overflow_space_id=%s
        """, (
            overflow_session["overflow_space_id"],
        ))

        if overflow_session["visitor_pass_id"]:

            cur.execute("""
                UPDATE parking_access.visitor_passes
                SET
                    status='AVAILABLE',
                    returned_at=CURRENT_TIMESTAMP,
                    reusable_after=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE visitor_pass_id=%s
            """, (
                overflow_session["visitor_pass_id"],
            ))

        log_event(
            cur,
            "OVERFLOW_EXIT",
            vehicle,
            "OVERFLOW_EXIT",
            "GRANTED",
            (
                f"Overflow space "
                f"{overflow_session['space_number']} released"
            ),
            overflow_session["visitor_pass_id"],
        )

        conn.commit()

    AUTO_RUN["completed_exits"] += 1

    if vehicle in AUTO_RUN["overflow_vehicles"]:
        AUTO_RUN["overflow_vehicles"].remove(vehicle)

    return True

async def run_accelerated_cycle():

    global AUTO_RUN_TASK

    AUTO_RUN["active"] = True
    AUTO_RUN["cycle"] += 1

    AUTO_RUN["started_at"] = datetime.utcnow().isoformat()
    AUTO_RUN["finished_at"] = None

    AUTO_RUN["overflow_vehicles"] = []

    AUTO_RUN["completed_entries"] = 0
    AUTO_RUN["completed_exits"] = 0

    AUTO_RUN["contractors_on_site"] = 0
    AUTO_RUN["visitors_on_site"] = 0

    AUTO_RUN["contractor_entries"] = 0
    AUTO_RUN["visitor_entries"] = 0
    AUTO_RUN["visitor_security_reviews"] = 0

    try:

        workforce = load_auto_run_workforce()

        #
        # Build arrival/departure events from real Workforce shifts.
        #
        events = []

        for employee in workforce:

            start = employee["start_time"]
            end = employee["end_time"]

            start_minutes = (
                start.hour * 60
                + start.minute
            )

            end_minutes = (
                end.hour * 60
                + end.minute
            )

            #
            # Overnight shifts leave the following day.
            #
            if (
                employee["crosses_midnight"]
                or end_minutes <= start_minutes
            ):
                end_minutes += 1440

            events.append({
                "minute": max(start_minutes - 20, 0),
                "type": "EMPLOYEE_ENTRY",
                "employee": employee,
            })

            events.append({
                "minute": end_minutes + 10,
                "type": "EMPLOYEE_EXIT",
                "employee": employee,
            })

        #
        # Planned contractor arrivals/departures.
        #
        for index, vehicle in enumerate(
            AUTO_RUN_CONTRACTORS
        ):

            events.append({
                "minute": 350 + index,
                "type": "CONTRACTOR_ENTRY",
                "vehicle": vehicle,
            })

            events.append({
                "minute": 840 + index,
                "type": "CONTRACTOR_EXIT",
                "vehicle": vehicle,
            })

        #
        # Regular visitor traffic throughout the day.
        #
        visitor_times = [
            510, 525, 540, 555,
            570, 590, 610, 630,
            650, 675, 700, 725,
            750, 775, 800, 825,
            850, 875, 900, 930,
        ]

        for index, minute in enumerate(
            visitor_times
        ):

            vehicle = AUTO_RUN_VISITORS[index]

            events.append({
                "minute": minute,
                "type": "VISITOR_ENTRY",
                "vehicle": vehicle,
            })

            events.append({
                "minute": minute + random.randint(90, 210),
                "type": "VISITOR_EXIT",
                "vehicle": vehicle,
            })

        events.sort(
            key=lambda event: event["minute"]
        )

        #
        # Start at Monday 05:30.
        #
        simulation_start = 330

        set_sim_time(simulation_start)

        AUTO_RUN["phase"] = "STARTUP"
        AUTO_RUN["current_event"] = (
            "Accelerated plant cycle starting"
        )
        AUTO_RUN["next_event"] = (
            "First workforce arrivals"
        )

        await asyncio.sleep(2)

        previous_minute = simulation_start

        for event in events:

            if not AUTO_RUN["active"]:
                return

            minute = event["minute"]

            #
            # Convert next-day minutes back to display clock.
            #
            set_sim_time(minute)

            if minute >= 1440:
                AUTO_RUN["sim_day"] = "TUESDAY"
            else:
                AUTO_RUN["sim_day"] = "MONDAY"

            event_type = event["type"]

            if event_type == "EMPLOYEE_ENTRY":

                employee = event["employee"]

                AUTO_RUN["phase"] = "EMPLOYEE_ARRIVAL"

                AUTO_RUN["current_event"] = (
                    f"{employee['display_name']} arriving — "
                    f"{employee['department_name']}"
                )

                result = auto_enter_employee(
                    employee
                )

                if result["result"] == "OVERFLOW":
                    AUTO_RUN["phase"] = "OVERFLOW"
                    AUTO_RUN["current_event"] = (
                        f"{employee['display_name']} "
                        f"routed to overflow"
                    )

                elif result["result"] == "OVERFLOW_FULL":
                    AUTO_RUN["phase"] = "OVERFLOW_FULL"
                    AUTO_RUN["current_event"] = (
                        f"No parking available for "
                        f"{employee['display_name']}"
                    )

            elif event_type == "EMPLOYEE_EXIT":

                employee = event["employee"]

                AUTO_RUN["phase"] = "EMPLOYEE_DEPARTURE"

                AUTO_RUN["current_event"] = (
                    f"{employee['display_name']} departing"
                )

                auto_exit_session(
                    employee["vehicle_identifier"]
                )

            elif event_type == "CONTRACTOR_ENTRY":

                vehicle = event["vehicle"]

                AUTO_RUN["phase"] = "CONTRACTOR_ARRIVAL"

                AUTO_RUN["current_event"] = (
                    f"Planned contractor arriving — {vehicle}"
                )

                result = auto_enter_contractor(
                    vehicle
                )

                if result == "OVERFLOW":
                    AUTO_RUN["phase"] = "OVERFLOW"
                    AUTO_RUN["current_event"] = (
                        f"{vehicle} routed to overflow"
                    )

                elif result == "OVERFLOW_FULL":
                    AUTO_RUN["phase"] = "OVERFLOW_FULL"
                    AUTO_RUN["current_event"] = (
                        f"No parking available for {vehicle}"
                    )

            elif event_type == "CONTRACTOR_EXIT":

                vehicle = event["vehicle"]

                AUTO_RUN["phase"] = "CONTRACTOR_DEPARTURE"

                AUTO_RUN["current_event"] = (
                    f"Contractor departing — {vehicle}"
                )

                if auto_exit_session(vehicle):
                    AUTO_RUN["contractors_on_site"] = max(
                        AUTO_RUN["contractors_on_site"] - 1,
                        0,
                    )

            elif event_type == "VISITOR_ENTRY":

                vehicle = event["vehicle"]

                result = await auto_enter_visitor(
                    vehicle
                )

                if result == "OVERFLOW":
                    AUTO_RUN["phase"] = "OVERFLOW"
                    AUTO_RUN["current_event"] = (
                        f"{vehicle} routed to overflow"
                    )

                elif result == "OVERFLOW_FULL":
                    AUTO_RUN["phase"] = "OVERFLOW_FULL"
                    AUTO_RUN["current_event"] = (
                        f"No parking available for {vehicle}"
                    )

            elif event_type == "VISITOR_EXIT":

                vehicle = event["vehicle"]

                AUTO_RUN["phase"] = "VISITOR_DEPARTURE"

                AUTO_RUN["current_event"] = (
                    f"Visitor departing — {vehicle}"
                )

                if auto_exit_session(vehicle):
                    AUTO_RUN["visitors_on_site"] = max(
                        AUTO_RUN["visitors_on_site"] - 1,
                        0,
                    )

            AUTO_RUN["next_event"] = (
                "Processing accelerated schedule"
            )

            # Accelerated portfolio pacing:
            # fast enough to demonstrate a full shift cycle,
            # slow enough for a visitor to follow each arrival,
            # gate transition, overflow route, and departure.

            delta = max(
                minute - previous_minute,
                1,
            )

            await asyncio.sleep(
                min(
                    max(delta * 0.075, 0.65),
                    3.0,
                )
            )

            previous_minute = minute

        AUTO_RUN["phase"] = "COMPLETE"

        AUTO_RUN["current_event"] = (
            "Accelerated operating cycle complete"
        )

        AUTO_RUN["next_event"] = (
            "Ready for replay"
        )

        AUTO_RUN["finished_at"] = (
            datetime.utcnow().isoformat()
        )

    finally:

        AUTO_RUN["active"] = False
        AUTO_RUN_TASK = None
        
@app.get("/api/auto-run/status")
def get_auto_run_status():
    return auto_run_status()


@app.post("/api/auto-run/start")
async def start_auto_run():

    global AUTO_RUN_TASK

    if AUTO_RUN["active"]:
        raise HTTPException(
            status_code=409,
            detail="Auto-run is already active",
        )

    AUTO_RUN_TASK = asyncio.create_task(
        run_accelerated_cycle()
    )

    return {
        "ok": True,
        "message": "Accelerated parking auto-run started",
        "cycle": AUTO_RUN["cycle"] + 1,
    }


@app.post("/api/auto-run/stop")
def stop_auto_run():

    AUTO_RUN["active"] = False
    AUTO_RUN["phase"] = "STOPPED"
    AUTO_RUN["current_event"] = "Auto-run stopped"
    AUTO_RUN["next_event"] = "Ready to restart"

    return {
        "ok": True,
        "message": "Auto-run stop requested",
    }
    
            

@app.get("/api/health")
def health():
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database() AS database, CURRENT_TIMESTAMP AS server_time")
        row = cur.fetchone()
        return {"ok": True, **row}


@app.post("/api/admin/init")
def initialize_database():
    run_sql_file(BASE_DIR / "sql" / "001_parking_access_schema.sql")
    run_sql_file(BASE_DIR / "sql" / "002_seed_demo_data.sql")
    return {"ok": True, "message": "parking_access schema and demo data initialized"}


@app.get("/api/parking/status")
def parking_status():
    with connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE parking_access.visitor_passes SET status='AVAILABLE', reusable_after=NULL, updated_at=CURRENT_TIMESTAMP WHERE status='QUARANTINED' AND reusable_after <= CURRENT_TIMESTAMP")
        cur.execute("SELECT COUNT(*) AS capacity FROM parking_access.parking_spaces")
        capacity = cur.fetchone()["capacity"]
        cur.execute("""
            SELECT
              COUNT(*) FILTER (WHERE occupant_type='EMPLOYEE') AS employees,
              COUNT(*) FILTER (WHERE occupant_type='VISITOR') AS visitors,
              COUNT(*) AS occupied
            FROM parking_access.parking_sessions
            WHERE session_status='ACTIVE'
        """)
        counts = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS available FROM parking_access.visitor_passes WHERE status='AVAILABLE'")
        pass_count = cur.fetchone()["available"]
        cur.execute("""
            SELECT
                ps.vehicle_identifier,
                ps.occupant_type,
                sp.space_number,
                ps.entry_time,
                vp.visitor_code,
                e.employee_number,
                e.display_name
            FROM parking_access.parking_sessions ps
            
            JOIN parking_access.parking_spaces sp
                ON sp.space_id = ps.space_id
                
            LEFT JOIN parking_access.visitor_passes vp
                ON vp.visitor_pass_id = ps.visitor_pass_id
                
            LEFT JOIN parking_access.employee_vehicles ev
                ON ev.vehicle_id = ps.employee_vehicle_id

            LEFT JOIN workforce.employees e
                ON e.employee_id = ev.workforce_employee_id
                
            WHERE ps.session_status='ACTIVE'
            
            ORDER BY ps.occupant_type, sp.zone, sp.space_number
        """)
        sessions = cur.fetchall()
        occupied = counts["occupied"]
        conn.commit()
        return {
            "capacity": capacity,
            "occupied": occupied,
            "employees": counts["employees"],
            "visitors": counts["visitors"],
            "remaining": capacity - occupied,
            "full": occupied >= capacity,
            "empty": occupied == 0,
            "visitor_pool_available": pass_count,
            "active_sessions": sessions,
        }

@app.get("/api/parking/overflow-status")
def overflow_status():

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT COUNT(*) AS capacity
            FROM parking_access.overflow_spaces
            WHERE active=TRUE
        """)

        capacity = cur.fetchone()["capacity"]

        cur.execute("""
            SELECT COUNT(*) AS occupied
            FROM parking_access.overflow_sessions
            WHERE session_status='ACTIVE'
        """)

        occupied = cur.fetchone()["occupied"]

        cur.execute("""
            SELECT
                os.overflow_session_id,
                os.vehicle_identifier,
                os.occupant_type,
                sp.space_number,
                os.entry_time,

                vp.visitor_code,

                w.employee_number,
                w.display_name

            FROM parking_access.overflow_sessions os

            JOIN parking_access.overflow_spaces sp
              ON sp.overflow_space_id = os.overflow_space_id

            LEFT JOIN parking_access.visitor_passes vp
              ON vp.visitor_pass_id = os.visitor_pass_id

            LEFT JOIN parking_access.employee_vehicles ev
              ON ev.vehicle_id = os.employee_vehicle_id

            LEFT JOIN workforce.employees w
              ON w.employee_id = ev.workforce_employee_id

            WHERE os.session_status='ACTIVE'

            ORDER BY
                sp.overflow_space_id,
                os.entry_time
        """)

        sessions = cur.fetchall()

    occupied = int(occupied or 0)
    capacity = int(capacity or 0)

    return {
        "capacity": capacity,
        "occupied": occupied,
        "remaining": max(capacity - occupied, 0),
        "full": occupied >= capacity if capacity > 0 else True,
        "empty": occupied == 0,
        "active_sessions": sessions,
    }


@app.post("/api/admin/reset-demo")
def reset_demo():
    """Return secured and overflow parking to an empty demo state without deleting audit history."""

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM parking_access.parking_sessions
            WHERE session_status='ACTIVE'
        """)

        secured_active = cur.fetchone()["count"]

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM parking_access.overflow_sessions
            WHERE session_status='ACTIVE'
        """)

        overflow_active = cur.fetchone()["count"]

        cur.execute("""
            UPDATE parking_access.parking_sessions
            SET
                session_status='CLOSED',
                exit_time=CURRENT_TIMESTAMP
            WHERE session_status='ACTIVE'
        """)

        cur.execute("""
            UPDATE parking_access.parking_spaces
            SET
                occupied=FALSE,
                updated_at=CURRENT_TIMESTAMP
        """)

        cur.execute("""
            UPDATE parking_access.overflow_sessions
            SET
                session_status='CLOSED',
                exit_time=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE session_status='ACTIVE'
        """)

        cur.execute("""
            UPDATE parking_access.overflow_spaces
            SET
                occupied=FALSE,
                updated_at=CURRENT_TIMESTAMP
        """)

        cur.execute("""
            UPDATE parking_access.visitor_passes
            SET
                status='AVAILABLE',
                issued_at=NULL,
                activated_at=NULL,
                returned_at=NULL,
                reusable_after=NULL,
                updated_at=CURRENT_TIMESTAMP
        """)

        cur.execute("""
            UPDATE parking_access.security_requests
            SET
                status='CANCELLED',
                decided_at=CURRENT_TIMESTAMP,
                security_user=COALESCE(
                    security_user,
                    'SYSTEM-DEMO-RESET'
                ),
                notes=CASE
                    WHEN notes IS NULL OR notes=''
                    THEN 'Cancelled by demo restart'
                    ELSE notes || ' | Cancelled by demo restart'
                END
            WHERE status='PENDING'
        """)

        log_event(
            cur,
            "SYSTEM",
            None,
            "DEMO_RESET",
            "GRANTED",
            (
                f"Demo restarted; {secured_active} secured "
                f"session(s) and {overflow_active} overflow "
                f"session(s) closed."
            ),
        )

        conn.commit()

    AUTO_RUN["overflow"] = 0
    AUTO_RUN["overflow_vehicles"] = []
    AUTO_RUN["contractors_on_site"] = 0
    AUTO_RUN["visitors_on_site"] = 0

    return {
        "ok": True,
        "closed_sessions": int(secured_active or 0),
        "closed_overflow_sessions": int(overflow_active or 0),
        "message": (
            "Parking demo reset to empty secured and overflow lots. "
            "Audit history preserved."
        ),
    }

@app.get("/api/demo/identifiers")
def demo_identifiers():

    with connection() as conn, conn.cursor() as cur:

        cur.execute("""
            SELECT
                w.employee_id AS workforce_employee_id,
                w.employee_number,
                w.display_name,
                w.employment_type,
                w.employment_status,
                w.commute_mode,
                w.department_name,

                r.role_code,
                r.role_name,

                s.shift_code,
                s.shift_name,
                s.start_time,
                s.end_time,
                s.crosses_midnight,
                s.operating_days,

                COALESCE(
                    p.parking_authorized,
                    TRUE
                ) AS parking_authorized,

                ev.vehicle_id,
                ev.vehicle_identifier,
                ev.make,
                ev.model,
                ev.color

            FROM parking_access.employee_vehicles ev

            JOIN workforce.employees w
                ON w.employee_id =
                   ev.workforce_employee_id
               AND w.site_code = 'PHARMA-001'

            LEFT JOIN parking_access.employees p
                ON p.employee_id = ev.employee_id

            LEFT JOIN workforce.employee_role_assignments era
                ON era.employee_id = w.employee_id
               AND era.active = TRUE
               AND era.is_primary = TRUE

            LEFT JOIN workforce.roles r
                ON r.role_id = era.role_id

            LEFT JOIN workforce.employee_shift_assignments esa
                ON esa.employee_id = w.employee_id
               AND esa.active = TRUE
               AND esa.is_primary = TRUE

            LEFT JOIN workforce.shifts s
                ON s.shift_id = esa.shift_id

            WHERE ev.active = TRUE

            ORDER BY
                w.department_name,
                w.display_name
        """)

        rows = cur.fetchall()

        cur.execute("""
            SELECT visitor_code
            FROM parking_access.visitor_passes
            WHERE status='AVAILABLE'
            ORDER BY visitor_code
            LIMIT 1
        """)

        next_pass = cur.fetchone()

        authorized = []
        denied_examples = []

        for row in rows:

            normal_eligibility = (
                row["employment_status"] == "ACTIVE"
                and row["commute_mode"] == "VEHICLE"
                and row["parking_authorized"]
            )

            if normal_eligibility:
                authorized.append(row)
            else:
                denied_examples.append(row)

        return {
            "authorized": authorized,
            "denied_examples": denied_examples,

            "unknown_visitor_examples": [
                "VISITOR-DEMO-01",
                "DELIVERY-TRUCK-07",
                "CONTRACTOR-302",
            ],

            "next_available_visitor_code":
                next_pass["visitor_code"]
                if next_pass
                else None,
        }


def employee_record_for_vehicle(cur, vehicle):

    cur.execute("""
        SELECT
            ev.vehicle_id,
            ev.vehicle_identifier,

            w.employee_id AS workforce_employee_id,
            w.employee_number,
            w.display_name,
            w.employment_type,
            w.employment_status,
            w.commute_mode,
            w.department_name,

            r.role_code,
            r.role_name,

            s.shift_code,
            s.shift_name,
            s.start_time,
            s.end_time,
            s.crosses_midnight,
            s.operating_days,

            COALESCE(
                p.parking_authorized,
                TRUE
            ) AS parking_authorized

        FROM parking_access.employee_vehicles ev

        JOIN workforce.employees w
            ON w.employee_id = ev.workforce_employee_id
           AND w.site_code = 'PHARMA-001'

        LEFT JOIN parking_access.employees p
            ON p.employee_id = ev.employee_id

        LEFT JOIN workforce.employee_role_assignments era
            ON era.employee_id = w.employee_id
           AND era.active = TRUE
           AND era.is_primary = TRUE

        LEFT JOIN workforce.roles r
            ON r.role_id = era.role_id

        LEFT JOIN workforce.employee_shift_assignments esa
            ON esa.employee_id = w.employee_id
           AND esa.active = TRUE
           AND esa.is_primary = TRUE

        LEFT JOIN workforce.shifts s
            ON s.shift_id = esa.shift_id

        WHERE ev.vehicle_identifier = %s
          AND ev.active = TRUE

        LIMIT 1
    """, (vehicle,))

    return cur.fetchone()


def employee_exception_reason(employee):

    if not employee:
        return None

    if employee["employment_status"] == "LEAVE":
        return "Employee is currently on leave"

    if employee["employment_status"] != "ACTIVE":
        return "Employee record is inactive"

    if employee["commute_mode"] != "VEHICLE":
        return "Employee is not assigned to vehicle parking"

    if not employee["parking_authorized"]:
        return "Parking authorization is suspended"

    return None


@app.post("/api/access/entry")
def entry(req: VehicleRequest):
    vehicle = normalize_vehicle(req.vehicle_identifier)
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT session_id FROM parking_access.parking_sessions WHERE vehicle_identifier=%s AND session_status='ACTIVE'", (vehicle,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Vehicle already has an active parking session")

        employee = employee_record_for_vehicle(cur, vehicle)
        employee_exception = employee_exception_reason(employee)

        if employee and not employee_exception:
            space = allocate_space(cur)
            cur.execute("UPDATE parking_access.parking_spaces SET occupied=TRUE, updated_at=CURRENT_TIMESTAMP WHERE space_id=%s", (space["space_id"],))
            cur.execute("""
                INSERT INTO parking_access.parking_sessions
                (vehicle_identifier, occupant_type, employee_vehicle_id, space_id)
                VALUES (%s,'EMPLOYEE',%s,%s)
                RETURNING session_id, entry_time
            """, (vehicle, employee["vehicle_id"], space["space_id"]))
            session = cur.fetchone()
            log_event(cur, "EMPLOYEE_ENTRY", vehicle, "EMPLOYEE_RECOGNIZED", "GRANTED", f"Authorized employee {employee['employee_number']}")
            conn.commit()
            return {
                "decision": "GRANTED", "occupant_type": "EMPLOYEE", "vehicle_identifier": vehicle,
                "employee_number": employee["employee_number"], "display_name": employee["display_name"],
                "spot_number": space["space_number"], "session_id": session["session_id"], "entry_time": session["entry_time"]
            }

        cur.execute("SELECT security_request_id, requested_at FROM parking_access.security_requests WHERE vehicle_identifier=%s AND status='PENDING' ORDER BY requested_at DESC LIMIT 1", (vehicle,))
        pending = cur.fetchone()
        if not pending:
            cur.execute("INSERT INTO parking_access.security_requests (vehicle_identifier) VALUES (%s) RETURNING security_request_id, requested_at", (vehicle,))
            pending = cur.fetchone()
        cur.execute("""
            SELECT visitor_code
            FROM parking_access.visitor_passes
            WHERE status='AVAILABLE'
            ORDER BY visitor_code
            LIMIT 1
        """)
        next_pass = cur.fetchone()
        review_type = "EMPLOYEE_EXCEPTION" if employee else "VISITOR_UNKNOWN"
        review_reason = employee_exception or "Unknown vehicle; Security approval required"
        event_type = "EMPLOYEE_EXCEPTION" if employee else "UNKNOWN_VEHICLE"
        log_event(cur, "EMPLOYEE_ENTRY", vehicle, event_type, "PENDING", review_reason)
        conn.commit()
        return {
            "decision": "SECURITY_REVIEW",
            "review_type": review_type,
            "review_reason": review_reason,
            "vehicle_identifier": vehicle,
            "employee_number": employee["employee_number"] if employee else None,
            "display_name": employee["display_name"] if employee else None,
            "employment_status": employee["employment_status"] if employee else None,
            "parking_authorized": employee["parking_authorized"] if employee else None,
            "next_visitor_code": None if employee else (next_pass["visitor_code"] if next_pass else None),
            **pending,
        }


@app.get("/api/security/requests")
def security_requests(status: str = Query(default="PENDING")):
    status = status.upper()
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT security_request_id, vehicle_identifier, status, requested_at, decided_at, security_user, notes
            FROM parking_access.security_requests
            WHERE status=%s
            ORDER BY requested_at
            LIMIT 50
        """, (status,))
        requests = cur.fetchall()
        cur.execute("""
            SELECT visitor_code
            FROM parking_access.visitor_passes
            WHERE status='AVAILABLE'
            ORDER BY visitor_code
            LIMIT 1
        """)
        next_pass = cur.fetchone()
        next_code = next_pass["visitor_code"] if next_pass else None
        for request in requests:
            employee = employee_record_for_vehicle(cur, request["vehicle_identifier"])
            exception = employee_exception_reason(employee)
            if employee and exception:
                request["review_type"] = "EMPLOYEE_EXCEPTION"
                request["review_reason"] = exception
                request["employee_number"] = employee["employee_number"]
                request["display_name"] = employee["display_name"]
                request["employment_status"] = employee["employment_status"]
                request["parking_authorized"] = employee["parking_authorized"]
                request["next_visitor_code"] = None
            else:
                request["review_type"] = "VISITOR_UNKNOWN"
                request["review_reason"] = "Unknown vehicle; Security approval required"
                request["next_visitor_code"] = next_code
        return requests


@app.post("/api/security/requests/{request_id}/approve")
def approve_security_request(request_id: int, decision: SecurityDecision):
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM parking_access.security_requests WHERE security_request_id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if not request:
            raise HTTPException(status_code=404, detail="Security request not found")
        if request["status"] != "PENDING":
            raise HTTPException(status_code=409, detail=f"Security request already {request['status'].lower()}")

        vehicle_identifier = request["vehicle_identifier"]
        employee = employee_record_for_vehicle(cur, vehicle_identifier)
        employee_exception = employee_exception_reason(employee)
        space = allocate_space(cur)

        # Known employee exceptions may be admitted by Security as a temporary override.
        # They remain EMPLOYEE sessions and never consume a visitor credential.
        if employee and employee_exception:
            cur.execute("UPDATE parking_access.parking_spaces SET occupied=TRUE, updated_at=CURRENT_TIMESTAMP WHERE space_id=%s", (space["space_id"],))
            cur.execute("UPDATE parking_access.security_requests SET status='APPROVED', decided_at=CURRENT_TIMESTAMP, security_user=%s, notes=%s WHERE security_request_id=%s", (decision.security_user, decision.notes, request_id))
            cur.execute("""
                INSERT INTO parking_access.parking_sessions
                (vehicle_identifier, occupant_type, employee_vehicle_id, security_request_id, space_id)
                VALUES (%s,'EMPLOYEE',%s,%s,%s)
                RETURNING session_id, entry_time
            """, (vehicle_identifier, employee["vehicle_id"], request_id, space["space_id"]))
            session = cur.fetchone()
            notes = decision.notes or f"Security override approved: {employee_exception}"
            cur.execute("INSERT INTO parking_access.security_actions (security_request_id, action_type, security_user, notes) VALUES (%s,'EMPLOYEE_OVERRIDE',%s,%s)", (request_id, decision.security_user, notes))
            log_event(cur, "EMPLOYEE_ENTRY", vehicle_identifier, "EMPLOYEE_OVERRIDE_APPROVED", "GRANTED", notes)
            conn.commit()
            return {
                "decision": "GRANTED",
                "approval_type": "EMPLOYEE_OVERRIDE",
                "occupant_type": "EMPLOYEE",
                "vehicle_identifier": vehicle_identifier,
                "employee_number": employee["employee_number"],
                "display_name": employee["display_name"],
                "override_reason": employee_exception,
                "spot_number": space["space_number"],
                "session_id": session["session_id"],
                "entry_time": session["entry_time"],
            }

        # Unknown vehicle: normal visitor workflow with pooled VIS-#### credential.
        cur.execute("UPDATE parking_access.visitor_passes SET status='AVAILABLE', reusable_after=NULL, updated_at=CURRENT_TIMESTAMP WHERE status='QUARANTINED' AND reusable_after <= CURRENT_TIMESTAMP")
        cur.execute("SELECT visitor_pass_id, visitor_code FROM parking_access.visitor_passes WHERE status='AVAILABLE' ORDER BY visitor_code FOR UPDATE SKIP LOCKED LIMIT 1")
        visitor_pass = cur.fetchone()
        if not visitor_pass:
            raise HTTPException(status_code=409, detail="No visitor IDs are currently available")

        cur.execute("UPDATE parking_access.visitor_passes SET status='ACTIVE', issued_at=CURRENT_TIMESTAMP, activated_at=CURRENT_TIMESTAMP, returned_at=NULL, reusable_after=NULL, updated_at=CURRENT_TIMESTAMP WHERE visitor_pass_id=%s", (visitor_pass["visitor_pass_id"],))
        cur.execute("UPDATE parking_access.parking_spaces SET occupied=TRUE, updated_at=CURRENT_TIMESTAMP WHERE space_id=%s", (space["space_id"],))
        cur.execute("UPDATE parking_access.security_requests SET status='APPROVED', decided_at=CURRENT_TIMESTAMP, security_user=%s, notes=%s WHERE security_request_id=%s", (decision.security_user, decision.notes, request_id))
        cur.execute("""
            INSERT INTO parking_access.parking_sessions
            (vehicle_identifier, occupant_type, visitor_pass_id, security_request_id, space_id)
            VALUES (%s,'VISITOR',%s,%s,%s)
            RETURNING session_id, entry_time
        """, (vehicle_identifier, visitor_pass["visitor_pass_id"], request_id, space["space_id"]))
        session = cur.fetchone()
        cur.execute("INSERT INTO parking_access.security_actions (security_request_id, action_type, security_user, notes) VALUES (%s,'BUZZ_IN',%s,%s)", (request_id, decision.security_user, decision.notes))
        log_event(cur, "EMPLOYEE_ENTRY", vehicle_identifier, "VISITOR_APPROVED", "GRANTED", f"Visitor pass {visitor_pass['visitor_code']} issued", visitor_pass["visitor_pass_id"])
        conn.commit()
        return {
            "decision": "GRANTED", "approval_type": "VISITOR", "occupant_type": "VISITOR", "vehicle_identifier": vehicle_identifier,
            "visitor_pass_code": visitor_pass["visitor_code"], "spot_number": space["space_number"],
            "session_id": session["session_id"], "entry_time": session["entry_time"]
        }


@app.post("/api/security/requests/{request_id}/deny")
def deny_visitor(request_id: int, decision: SecurityDecision):
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT vehicle_identifier, status FROM parking_access.security_requests WHERE security_request_id=%s FOR UPDATE", (request_id,))
        request = cur.fetchone()
        if not request:
            raise HTTPException(status_code=404, detail="Security request not found")
        if request["status"] != "PENDING":
            raise HTTPException(status_code=409, detail=f"Security request already {request['status'].lower()}")
        cur.execute("UPDATE parking_access.security_requests SET status='DENIED', decided_at=CURRENT_TIMESTAMP, security_user=%s, notes=%s WHERE security_request_id=%s", (decision.security_user, decision.notes, request_id))
        cur.execute("INSERT INTO parking_access.security_actions (security_request_id, action_type, security_user, notes) VALUES (%s,'DENY',%s,%s)", (request_id, decision.security_user, decision.notes))
        employee = employee_record_for_vehicle(cur, request["vehicle_identifier"])
        exception = employee_exception_reason(employee)
        log_event(cur, "EMPLOYEE_ENTRY", request["vehicle_identifier"], "EMPLOYEE_OVERRIDE_DENIED" if employee and exception else "VISITOR_DENIED", "DENIED", decision.notes or exception)
        conn.commit()
        return {"decision": "DENIED", "vehicle_identifier": request["vehicle_identifier"]}


@app.post("/api/access/exit")
def exit_vehicle(req: VehicleRequest):
    vehicle = normalize_vehicle(req.vehicle_identifier)
    with connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT ps.session_id, ps.occupant_type, ps.space_id, sp.space_number,
                   ps.visitor_pass_id, vp.visitor_code
            FROM parking_access.parking_sessions ps
            JOIN parking_access.parking_spaces sp ON sp.space_id=ps.space_id
            LEFT JOIN parking_access.visitor_passes vp ON vp.visitor_pass_id=ps.visitor_pass_id
            WHERE ps.vehicle_identifier=%s AND ps.session_status='ACTIVE'
            FOR UPDATE OF ps
        """, (vehicle,))
        session = cur.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="No active parking session found for this vehicle")

        cur.execute("UPDATE parking_access.parking_sessions SET session_status='CLOSED', exit_time=CURRENT_TIMESTAMP WHERE session_id=%s", (session["session_id"],))
        cur.execute("UPDATE parking_access.parking_spaces SET occupied=FALSE, updated_at=CURRENT_TIMESTAMP WHERE space_id=%s", (session["space_id"],))
        reusable_after = None
        if session["occupant_type"] == "VISITOR":
            cur.execute("""
                UPDATE parking_access.visitor_passes
                SET status='QUARANTINED', returned_at=CURRENT_TIMESTAMP,
                    reusable_after=CURRENT_TIMESTAMP + INTERVAL '24 hours', updated_at=CURRENT_TIMESTAMP
                WHERE visitor_pass_id=%s
                RETURNING reusable_after
            """, (session["visitor_pass_id"],))
            reusable_after = cur.fetchone()["reusable_after"]
        log_event(cur, "EMPLOYEE_EXIT", vehicle, "VEHICLE_EXIT", "GRANTED", f"Space {session['space_number']} released", session["visitor_pass_id"])
        conn.commit()
        return {
            "decision": "GRANTED", "vehicle_identifier": vehicle, "occupant_type": session["occupant_type"],
            "spot_number": session["space_number"], "visitor_pass_code": session["visitor_code"],
            "reusable_after": reusable_after
        }


@app.get("/api/events")
def events(limit: int = Query(default=50, ge=1, le=200)):
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM parking_access.access_events ORDER BY event_time DESC LIMIT %s", (limit,))
        return cur.fetchall()