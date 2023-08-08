#!/usr/bin/env python

from pyspark.sql import functions as F


def estimate_dataset_boundaries(spark_session, src, spatial_reference):
    df = spark_session.read.parquet(src) \
        .select(f"{spatial_reference}.*", "*") \
        .drop(spatial_reference) \
        .na.drop(subset=["x", "y", "z"]) \
        .select(['IngestionId', "x", "y", "z"]) \
        .withColumnRenamed('IngestionId', 'Index') \
        .withColumnRenamed('X', 'x') \
        .withColumnRenamed('Y', 'y') \
        .withColumnRenamed('Z', 'z')

    df.show(5)
    df.printSchema()

    return estimate_df_boundaries(df)


def estimate_df_boundaries(df):
    # Compute the bounding box and its center
    boundaries = df.agg(
        ((F.min("x") + F.max("x")) / 2).alias("center_x"),
        F.min("x").alias("min_x"),
        F.max("x").alias("max_x"),
        ((F.min("y") + F.max("y")) / 2).alias("center_y"),
        F.min("y").alias("min_y"),
        F.max("y").alias("max_y"),
        ((F.min("z") + F.max("z")) / 2).alias("center_z"),
        F.min("z").alias("min_z"),
        F.max("z").alias("max_z"),
    )

    boundaries.show()
    boundaries.printSchema()

    as_dict = boundaries.collect()[0].asDict()

    # Get the largest value for each of the X, Y, and Z dimensions
    largest_x = max(abs(as_dict['min_x']), abs(as_dict['max_x']))
    largest_y = max(abs(as_dict['min_y']), abs(as_dict['max_y']))
    largest_z = max(abs(as_dict['min_z']), abs(as_dict['max_z']))
    radius = max(largest_x, largest_y, largest_z) / 2

    as_dict['radius'] = radius
    
    return as_dict


def combine_boundaries(boundaries1, boundaries2):

    boundaries = {
        'min_x': min(boundaries1['min_x'], boundaries2['min_x']),
        'max_x': max(boundaries1['max_x'], boundaries2['max_x']),
        'min_y': min(boundaries1['min_y'], boundaries2['min_y']),
        'max_y': max(boundaries1['max_y'], boundaries2['max_y']),
        'min_z': min(boundaries1['min_z'], boundaries2['min_z']),
        'max_z': max(boundaries1['max_z'], boundaries2['max_z']),
    }

    center_x = (boundaries['min_x'] + boundaries['max_x']) / 2
    center_y = (boundaries['min_y'] + boundaries['max_y']) / 2
    center_z = (boundaries['min_z'] + boundaries['max_z']) / 2

    boundaries['center_x'] = center_x
    boundaries['center_y'] = center_y
    boundaries['center_z'] = center_z

    # Get the largest value for each of the X, Y, and Z dimensions
    largest_x = max(abs(boundaries['min_x']), abs(boundaries['max_x']))
    largest_y = max(abs(boundaries['min_y']), abs(boundaries['max_y']))
    largest_z = max(abs(boundaries['min_z']), abs(boundaries['max_z']))
    radius = max(largest_x, largest_y, largest_z) / 2

    boundaries['radius'] = radius

    return boundaries

