import json
import os
import platform

from pyhocon import ConfigFactory as CF
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType


def set_spark_env():
    """
    # deleting SPARK_HOME, PYSPARK_PYTHON variables, disambiguation of spark for Scala and PySpark
    :return:
    """
    runtime_env = platform.system()
    if runtime_env == 'Darwin':
        try:
            del os.environ['SPARK_HOME']
        except:
            print('SPARK_HOME not found')

        try:
            del os.environ['PYSPARK_PYTHON']
        except:
            print('PYSPARK_PYTHON not found')


def rgb_to_hex(R, G, B):
    return f'#{int(R * 255):02x}{int(G * 255):02x}{int(B * 255):02x}'


rgb_to_hex_udf = udf(rgb_to_hex, StringType())


def color_by_range(min_val, max_val, cold=True):
    """
    Maps a range of values to a range of colors.
    Defaults to cold color from green to blue, warm is red to blue.
    :return:
    """
    range_size = max_val - min_val + 1

    color_codes = {}
    for i in range(range_size):
        # Normalize i to 0-1 range
        normalized_i = i / (range_size - 1)

        if cold:
            # Green to Blue gradient
            R = 0
            G = 1 - normalized_i  # Decreases from 255 to 0
        else:
            # Red to Blue gradient
            R = 1 - normalized_i  # Increases from 0 to 255
            G = 0

        B = normalized_i  # Increases from 0 to 255

        color_codes[str(min_val + i)] = rgb_to_hex(R, G, B)

    return color_codes


def to_unreal(df, dest, module_conf=None, main_table=None, table=None, default_table=False):

    df.toPandas().to_csv(dest, header=True, index=False)
    schema = json.loads(df.schema.json())

    if module_conf is not None:
        module_conf.data_types[main_table].tables[table]['columns'] = CF.from_dict(schema['fields'])
    if default_table:
        module_conf.data_types[main_table]['default_table'] = table

    return module_conf


def move_column_to_position(df, column_name, position=0):
    """
    Move a column to a specific position in the dataframe,
    default is first position
    :param df:
    :param column_name:
    :param position:
    :return:
    """
    columns = df.columns
    if column_name in columns:
        columns.remove(column_name)
        columns.insert(position, column_name)
    return df.select(*columns)

