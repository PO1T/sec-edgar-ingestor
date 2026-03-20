from __future__ import annotations


ANALYTICS_MATERIALIZED_VIEWS = (
    "thirteenf_filer_identities",
    "thirteenf_filer_positions",
    "thirteenf_filer_position_changes",
)


def refresh_analytics_views(connection: object) -> list[str]:
    refreshed: list[str] = []
    with connection.cursor() as cursor:
        for view_name in ANALYTICS_MATERIALIZED_VIEWS:
            cursor.execute(f"REFRESH MATERIALIZED VIEW {view_name}")
            refreshed.append(view_name)

    connection.commit()
    return refreshed
