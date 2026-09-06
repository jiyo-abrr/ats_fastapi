from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.core.database import Base
from app.domains.applications import models as application_models  # noqa: F401
from app.domains.assessments.attempts import models as assessment_models  # noqa: F401
from app.domains.assessments.culture_fit_templates import (
    models as culture_fit_template_models,  # noqa: F401
)
from app.domains.assessments.pre_assessment_templates import (
    models as pre_assessment_template_models,  # noqa: F401
)
from app.domains.assessments.technical_assessment_templates import (
    models as technical_assessment_template_models,  # noqa: F401
)
from app.domains.auth import models  # noqa: F401  (registers User with Base.metadata)
from app.domains.company_addresses import models as company_address_models  # noqa: F401
from app.domains.job_posts import models as job_post_models  # noqa: F401
from app.domains.positions import models as position_models  # noqa: F401
from app.domains.rbac import models as rbac_models  # noqa: F401
from app.domains.tags import models as tag_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
