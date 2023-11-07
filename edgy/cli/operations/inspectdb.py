import sys
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Union
from uuid import UUID

import click
import sqlalchemy
from loguru import logger
from sqlalchemy.dialects.mysql import types as mytypes
from sqlalchemy.dialects.postgresql import types as pgtypes
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import sqltypes

import edgy
from edgy import Database, Registry
from edgy.cli.env import MigrationEnv
from edgy.cli.exceptions import MissingParameterException
from edgy.core.sync import execsync
from edgy.core.terminal import Print

printer = Print()

SQL_GENERIC_TYPES = {
    sqltypes.BigInteger: edgy.BigIntegerField,
    sqltypes.Integer: edgy.IntegerField,
    sqltypes.JSON: edgy.JSONField,
    sqltypes.Date: edgy.DateField,
    sqltypes.String: edgy.CharField,
    sqltypes.BINARY: edgy.BinaryField,
    sqltypes.Boolean: edgy.BooleanField,
    sqltypes.Enum: edgy.ChoiceField,
    sqltypes.DateTime: edgy.DateTimeField,
    sqltypes.Numeric: edgy.DecimalField,
    sqltypes.Float: edgy.FloatField,
    sqltypes.SmallInteger: edgy.SmallIntegerField,
    sqltypes.Text: edgy.TextField,
    sqltypes.Time: edgy.TimeField,
    pgtypes.TIMESTAMP: edgy.TimeField,
    mytypes.TIMESTAMP: edgy.TimeField,
    sqltypes.Uuid: edgy.UUIDField,
}

FOREIGN_KEY_MAPPING = {sqlalchemy.ForeignKey: edgy.ForeignKey}


@click.option(
    "-u",
    "--user",
    default=None,
    help=("Database username."),
)
@click.option(
    "-p",
    "--password",
    default=None,
    help=("Database password"),
)
@click.option(
    "--host",
    default=None,
    help=("Database host."),
)
@click.option(
    "--database",
    default=None,
    help=("Database name."),
)
@click.option(
    "--port",
    default=5432,
    help=("Database port."),
)
@click.option(
    "--scheme",
    default="postgresql+asyncpg",
    help=("Scheme driver used for the connection. Example: 'postgresql+asyncpg'"),
)
@click.option(
    "--schema",
    default=None,
    help=("Database schema to be applied."),
)
@click.command()
def inspect_db(
    env: MigrationEnv,
    port: int,
    scheme: str,
    user: Union[str, None] = None,
    password: Union[str, None] = None,
    host: Union[str, None] = None,
    database: Union[str, None] = None,
    schema: Union[str, None] = None,
) -> None:
    """
    Inspects an existing database and generates the Edgy reflect models.
    """
    registry: Union[Registry, None] = None
    db_module = "edgy"

    try:
        registry = env.app._edgy_db["migrate"].registry  # type: ignore
    except AttributeError:
        registry = None

    # Generates a registry based on the passed connection details
    if registry is None:
        logger.info("`Registry` not found in the application. Using credentials...")
        connection_string = build_connection_string(
            port, scheme, user, password, host, database
        )
        _database: Database = Database(connection_string)
        registry = Registry(database=_database)

    # Get the engine to connect
    engine: AsyncEngine = registry.engine

    # Connect to a schema
    metadata: sqlalchemy.MetaData = (
        sqlalchemy.MetaData(schema=schema)
        if schema is not None
        else sqlalchemy.MetaData()
    )
    metadata = execsync(reflect)(engine=engine, metadata=metadata)

    # Generate the tables
    tables, models = generate_table_information(metadata, registry)

    for line in write_output(tables, models, db_module, connection_string):
        sys.stdout.writelines(line)


def generate_table_information(
    metadata: sqlalchemy.MetaData, registry: Registry
) -> List[Any]:
    """
    Generates the tables from the reflection and maps them into the
    `reflected` dictionary of the `Registry`.
    """
    tables_dict = dict(metadata.tables.items())
    tables = []
    models: Dict[str, str] = {}
    for key, table in tables_dict.items():
        table_details: Dict[str, Any] = {}
        table_details["tablename"] = key
        table_details["class_name"] = key.replace("_", "").capitalize()
        table_details["class"] = None
        table_details["table"] = table
        models[key] = key.replace("_", "").capitalize()

        # Get the details of the foreign key
        table_details["foreign_keys"] = get_foreign_keys(table)

        # Get the details of the indexes
        table_details["indexes"] = table.indexes
        tables.append(table_details)

    return tables, models


def get_foreign_keys(
    table_or_column: Union[sqlalchemy.Table, sqlalchemy.Column]
) -> List[Dict[str, Any]]:
    """
    Extracts all the information needed of the foreign keys.
    """
    details: List[Dict[str, Any]] = []

    for foreign_key in table_or_column.foreign_keys:
        fk: Dict[str, Any] = {}
        fk["column"] = foreign_key.column
        fk["column_name"] = foreign_key.column.name
        fk["tablename"] = foreign_key.column.table.name
        fk["class_name"] = foreign_key.column.table.name.replace("_", "").capitalize()
        fk["on_delete"] = foreign_key.ondelete
        fk["on_update"] = foreign_key.onupdate
        fk["null"] = foreign_key.column.nullable
        details.append(fk)

    return details


def get_field_type(column: sqlalchemy.Column, is_fk: bool = False) -> Any:
    """
    Gets the field type. If the field is a foreign key, this is evaluated,
    outside of the scope.
    """
    if is_fk:
        return "edgy.ForeignKey" if not column.unique else "edgy.OneToOne", {}

    real_field: sqlalchemy.Column.type.as_generic = column.type.as_generic()
    try:
        field_type = SQL_GENERIC_TYPES[type(real_field)].__name__
    except KeyError:
        logger.info(
            f"Unable to understand the field type for `{column.name}`, defaulting to TextField."
        )
        field_type = "TextField"

    field_params: Dict[str, Any] = {}

    if field_type == "CharField":
        field_params["max_length"] = real_field.length

    if field_type in {"CharField", "TextField"} and real_field.collation:
        field_params["collation"] = real_field.collation

    if field_type == "DecimalField":
        field_params["max_digitis"] = real_field.precision
        field_params["decimal_places"] = real_field.scale

    if field_type == "BinaryField":
        field_params["sql_nullable"] = getattr(real_field, "none_as_null", False)

    return f"edgy.{field_type}", field_params


def write_output(
    tables: List[Any], models: Dict[str, str], db_module: str, connection_string: str
) -> None:
    """
    Writes to stdout.
    """
    yield f"# This is an auto-generated Edgy model module. Edgy version `{edgy.__version__}`.\n"
    yield "#   * Rearrange models' order\n"
    yield "#   * Make sure each model has one field with primary_key=True\n"
    yield (
        "#   * Make sure each ForeignKey and OneToOneField has `on_delete` set "
        "to the desired behavior\n"
    )
    yield (
        "# Feel free to rename the models, but don't rename tablename values or "
        "field names.\n"
    )
    yield "# The automatic generated models will be subclassed as `%s.ReflectModel`.\n\n\n" % db_module
    yield "import %s \n" % db_module

    yield "\n"
    yield "\n"
    yield "database = %s.Database('%s')\n" % (db_module, connection_string)
    yield "registry = %s.Registry(database=database)\n" % db_module

    # Start writing the classes
    for table in tables:
        used_column_names: List[str] = []

        yield "\n"
        yield "\n"
        yield "class %s(%s.ReflectModel):\n" % (table["class_name"], db_module)
        # yield "    ...\n"

        sqla_table: sqlalchemy.Table = table["table"]
        columns = [col for col in sqla_table.columns]

        # Get the column information
        for column in columns:
            # ForeignKey related
            foreign_keys = get_foreign_keys(column)
            is_fk: bool = False if not foreign_keys else True
            attr_name = column.name

            field_type, field_params = get_field_type(column, is_fk)
            field_params["null"] = column.nullable

            if column.primary_key:
                field_params["primary_key"] = column.primary_key
            if column.comment:
                field_params["comment"] = column.comment

            if is_fk:
                field_params["to"] = foreign_keys[0]["class_name"]
                field_params["on_update"] = foreign_keys[0]["on_update"]
                field_params["on_delete"] = foreign_keys[0]["on_update"]
                field_params["related_name"] = "%s_%s_set" % (
                    attr_name,
                    field_params["to"].lower(),
                )

        yield from get_meta(table)
        # if column_type in FOREIGN_KEY_MAPPING:
        #     breakpoint()
        #     field_type = "edgy.ForeignKey" if not unique_column else "edgy.OneToOne"
        # else:
        #     breakpoint()
        #     field_type = SQL_MAPPING_TYPES[type(column.type)].__name__

        # Extract information
        # edgy_column = SQL_MAPPING_TYPES[type(column.type)]
        # edgy_column = edgy_column(
        #     primary_key=column.primary_key,
        #     null=column.nullable,
        #     comment=column.comment,
        #     unique=unique_column,
        # )


def get_meta(table: Dict[str, Any]) -> None:
    """
    Produces the Meta class.
    """
    unique_together = []
    indexes = []

    meta = [""]
    meta += [
        "    class Meta:\n",
        "        registry = registry\n",
        "        tablename = '%s'" % table["tablename"],
    ]
    return meta


async def reflect(
    *, engine: sqlalchemy.Engine, metadata: sqlalchemy.MetaData
) -> sqlalchemy.MetaData:
    """
    Connects to the database and reflects all the information about the
    schema bringing all the data available.
    """

    async with engine.connect() as connection:
        logger.info("Collecting database tables information...")
        await connection.run_sync(metadata.reflect)
    return metadata


def build_connection_string(
    port: int,
    scheme: str,
    user: Union[str, None] = None,
    password: Union[str, None] = None,
    host: Union[str, None] = None,
    database: Union[str, None] = None,
) -> str:
    """
    Builds the database connection string.

    If a user or a password are not provided,
    then it will generate a connection string without authentication.
    """
    if not host and not database:
        raise MissingParameterException(
            detail="`host` and `database` must be provided."
        )

    if not user or not password:
        printer.write_info("Logging in without authentication.")
        return f"{scheme}://{host}:{port}/{database}"

    return f"{scheme}://{user}:{password}@{host}:{port}/{database}"
