from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from sqlalchemy import text

from app.core.database_pool import db_pool


async def _get_session():
    if db_pool.session_factory is None:
        await db_pool.initialize()
    if db_pool.session_factory is None:
        raise Exception("Database pool not available")
    return db_pool.get_session()


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month, in the property's timezone.
    """
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    query = text("""
        SELECT
            COALESCE(SUM(r.total_amount), 0) as total_revenue,
            COUNT(r.id) as reservation_count
        FROM reservations r
        JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
        AND r.tenant_id = :tenant_id
        AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
        AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    async with await _get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    query = text("""
        SELECT
            COALESCE(SUM(total_amount), 0) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
    """)

    async with await _get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count
    }


async def get_tenant_properties(tenant_id: str) -> list:
    query = text("""
        SELECT id, name, timezone
        FROM properties
        WHERE tenant_id = :tenant_id
        ORDER BY id
    """)

    async with await _get_session() as session:
        result = await session.execute(query, {"tenant_id": tenant_id})
        return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in result.fetchall()]


async def get_reservations(property_id: str, tenant_id: str, month: int = None, year: int = None) -> list:
    params = {"property_id": property_id, "tenant_id": tenant_id}
    month_filter = ""
    if month and year:
        params["start_date"] = datetime(year, month, 1)
        params["end_date"] = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        month_filter = """
        AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
        AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date"""

    query = text(f"""
        SELECT
            r.id,
            to_char(r.check_in_date AT TIME ZONE p.timezone, 'YYYY-MM-DD HH24:MI') as check_in,
            to_char(r.check_out_date AT TIME ZONE p.timezone, 'YYYY-MM-DD HH24:MI') as check_out,
            r.total_amount,
            r.currency
        FROM reservations r
        JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id AND r.tenant_id = :tenant_id{month_filter}
        ORDER BY r.check_in_date
    """)

    async with await _get_session() as session:
        result = await session.execute(query, params)
        return [
            {
                "id": r.id,
                "check_in": r.check_in,
                "check_out": r.check_out,
                "amount": str(r.total_amount),
                "currency": r.currency,
            }
            for r in result.fetchall()
        ]
