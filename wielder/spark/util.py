import os
import platform

import pyspark.sql.functions as F
from pyspark.sql.types import StringType, DoubleType
from pyspark.ml.feature import MinMaxScaler, VectorAssembler
from pyspark.sql import DataFrame as SparkDataFrame
import pandas as pd


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


def normalized_to_hex(r, g, b):
    return f'#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}'


normalized_to_hex_udf = F.udf(normalized_to_hex, StringType())


def rgb_to_hex(r, g, b):
    return f'#{int(r):02x}{int(g):02x}{int(b):02x}'


rgb_to_hex_udf = F.udf(rgb_to_hex, StringType())


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

        color_codes[str(min_val + i)] = normalized_to_hex(R, G, B)

    return color_codes


def move_column_to_position(df, column_name, position=0):
    """
    Move a column to a specific position in the DataFrame.

    Parameters:
        df: The original DataFrame (either pandas or PySpark).
        column_name (str): The name of the column to move.
        position (int): The target position (0-based indexing).

    Returns:
        DataFrame: DataFrame with the column moved to the desired position.
    """

    # Check if input is a pandas DataFrame
    if isinstance(df, pd.DataFrame):
        # Check if column_name exists in df
        if column_name not in df.columns:
            raise ValueError(f"'{column_name}' not found in DataFrame columns.")

        # Check if position is valid
        if position < 0 or position > len(df.columns) - 1:
            raise ValueError(f"Position {position} is out of range.")

        cols = df.columns.tolist()
        cols.insert(position, cols.pop(cols.index(column_name)))

        return df[cols]

    # Check if input is a PySpark DataFrame
    elif isinstance(df, SparkDataFrame):
        columns = df.columns
        if column_name in columns:
            columns.remove(column_name)
            columns.insert(position, column_name)
        return df.select(*columns)

    else:
        raise TypeError("Input should be either a pandas DataFrame or a PySpark DataFrame.")


def columns_ranges(df, columns):
    """
    Compute the minimum and maximum values for a list of columns
    :param df:
    :param columns:
    :return:
    """
    # List to store our aggregation functions
    agg_funcs = []

    # Loop through each column and add the min and max aggregation functions
    for col_name in columns:
        agg_funcs.append(F.min(col_name).alias(f"min_{col_name}"))
        agg_funcs.append(F.max(col_name).alias(f"max_{col_name}"))

    # Compute the ranges using the generated aggregation functions
    ranges = df.agg(*agg_funcs)

    return ranges.collect()[0].asDict()


def normalize_column(df, input_name, output_name, round_factor=6, enlarge=1):
    # df.show()

    vector_assembler = VectorAssembler(inputCols=[input_name], outputCol="features")

    df = vector_assembler.transform(df)

    # Initialize the MinMaxScaler with the input and output column names
    min_max_scaler = MinMaxScaler(inputCol="features", outputCol="normalized_features")

    # Compute the minimum and maximum values of the input column
    scaler_model = min_max_scaler.fit(df)

    # Transform the DataFrame to normalize the values to a range of 0 to 1
    df = scaler_model.transform(df)

    # Extract the normalized values from the vector column into a new column
    udf_extract_norm_value = F.udf(lambda x: round(float(x[0]) * enlarge, round_factor), DoubleType())
    df = df.withColumn(output_name, udf_extract_norm_value("normalized_features"))

    # Drop the intermediate columns (optional)
    df = df.drop("features", "normalized_features")

    # df.show()

    return df
