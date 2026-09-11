from sqlalchemy import text


async def test_harness_gives_a_migrated_database(db_session):
    # every domain's tables exist
    for tbl in (
        "users",
        "job_posts",
        "applications",
        "assessment_attempts",
        "interview_requests",
        "application_evaluations",
    ):
        got = (
            await db_session.execute(
                text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"}
            )
        ).scalar_one()
        assert got == tbl, f"missing table {tbl}"


async def test_health_ready_through_the_app(client):
    r = await client.get("/health")
    assert r.status_code == 200


async def test_rows_do_not_leak_between_tests_part1(db_session):
    await db_session.execute(
        text("INSERT INTO roles (id, name) VALUES (gen_random_uuid(), 'leak-check')")
    )
    await db_session.commit()  # savepoint release, not a real commit


async def test_rows_do_not_leak_between_tests_part2(db_session):
    n = (
        await db_session.execute(
            text("SELECT count(*) FROM roles WHERE name = 'leak-check'")
        )
    ).scalar_one()
    assert n == 0
