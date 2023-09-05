import json
from enum import Enum

from pyhocon import ConfigFactory as CF


class UnrealTableType(Enum):
    """
    Unreal tables are Key Value, the first column is the index
    Each data type must have a main table with the schema: Index, x, y, z color, size, opacity
    one to many means there are many different states of the same Index e.g. changes through time for animation
    """

    MAIN = 'main'
    SECONDARY = 'secondary'
    ONE_TO_MANY = 'one_to_many'


def to_unreal(df, dest, module_conf=None, main_table=None, table=None, table_type=UnrealTableType.MAIN):
    df.toPandas().to_csv(dest, header=True, index=False)
    schema = json.loads(df.schema.json())

    if module_conf is not None:
        match table_type:
            case UnrealTableType.MAIN:
                module_conf.data_types[main_table]['default_table'] = table
            case UnrealTableType.SECONDARY:
                module_conf.data_types[main_table].tables[table]['columns'] = CF.from_dict(schema['fields'])
            case UnrealTableType.ONE_TO_MANY:
                module_conf.data_types[main_table].many_to_one_tables[table]['columns'] = CF.from_dict(schema['fields'])

    return module_conf

