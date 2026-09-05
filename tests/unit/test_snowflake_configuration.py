from app.services.config_service import validate_configuration


def test_snowflake_url_can_be_cleared():
    validate_configuration(
        "snowflake",
        {
            "account": "acct",
            "username": "user",
            "pat": "token",
            "url": "",
            "warehouse": "wh",
            "database": "db",
            "schema": "public",
        },
    )