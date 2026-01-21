#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

import argparse
from typing import Any

from pyspark.sql import SparkSession, functions as f
from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker
import datetime

SPARK_WRITE_TO_JDBC: str = "spark_to_jdbc"
SPARK_READ_FROM_JDBC: str = "jdbc_to_spark"


def set_common_options(
    spark_source: Any,
    url: str = "localhost:5432",
    jdbc_table: str = None,
    user: str = "root",
    password: str = "root",
    driver: str = "driver",
    query: str = None
) -> Any:
    """
    Get Spark source from JDBC connection.

    :param spark_source: Spark source, here is Spark reader or writer
    :param url: JDBC resource url
    :param jdbc_table: JDBC resource table name
    :param user: JDBC resource user name
    :param password: JDBC resource password
    :param driver: JDBC resource driver
    """
    if jdbc_table:
        type_import = 'dbtable'
        name_import = jdbc_table
    else:
        type_import = 'query'
        name_import = query
        

    spark_source = (
        spark_source.format("jdbc")
        .option("url", url)
        .option(type_import, name_import)
        .option("user", user)
        .option("password", password)
        .option("driver", driver)
    )
    return spark_source


def spark_write_to_jdbc(
    spark_session: SparkSession,
    url: str,
    user: str,
    password: str,
    metastore_table: str,
    jdbc_table: str,
    driver: Any,
    truncate: bool,
    save_mode: str,
    batch_size: int,
    num_partitions: int,
    create_table_column_types: str,
) -> None:
    """Transfer data from Spark to JDBC source."""
    writer = spark_session.table(metastore_table).write
    # first set common options
    writer = set_common_options(writer, url, jdbc_table, user, password, driver)

    # now set write-specific options
    if truncate:
        writer = writer.option("truncate", truncate)
    if batch_size:
        writer = writer.option("batchsize", batch_size)
    if num_partitions:
        writer = writer.option("numPartitions", num_partitions)
    if create_table_column_types:
        writer = writer.option("createTableColumnTypes", create_table_column_types)

    writer.save(mode=save_mode)


def spark_read_from_jdbc(
    spark_session: SparkSession,
    url: str,
    user: str,
    password: str,
    metastore_table: str,
    jdbc_table: str,
    driver: Any,
    save_mode: str,
    save_format: str,
    fetch_size: int,
    num_partitions: int,
    partition_column: str,
    lower_bound: str,
    upper_bound: str,
    dag_name: str,
    task_name: str,
    check_column: str,
    last_value: str,
    output_path: str,
    connection_metastore: str,
    metastore_table_name: str,
    query: str,
    dest_connstring: str,
    dest_table: str,
    dest_driver: str,
    dest_keys: str,
    dest_writemode: str,
    dest_username: str,
    dest_password: str
) -> None:
    """Transfer data from JDBC source to Spark."""
    # first set common options
    reader = set_common_options(spark_session.read, url, jdbc_table, user, password, driver, query)

    if check_column is not None and last_value is not None:
        try:
            last_value = float(last_value)
        except ValueError:
            last_value = f"\'{last_value}\'"
        where_condition = f"{check_column} > {last_value}"
    else:
        where_condition = "true"

    # now set specific read options
    if fetch_size:
        reader = reader.option("fetchsize", fetch_size)
    if num_partitions:
        reader = reader.option("numPartitions", num_partitions)
    if partition_column and lower_bound and upper_bound:
        reader = (
            reader.option("partitionColumn", partition_column)
            .option("lowerBound", lower_bound)
            .option("upperBound", upper_bound)
        )

    # Load data
    df = reader.load().where(where_condition)

    # Write data
    if metastore_table:
        df.cache().write.saveAsTable(metastore_table, format=save_format, mode=save_mode)
    if output_path:
        df.cache().write.mode(save_mode).parquet(output_path)
    if dest_connstring and dest_table:
        truncate = 'false'
        if dest_writemode == 'upsert':
            write_table = dest_table + "_tmp"
            writemode = 'overwrite'
        elif dest_writemode == 'truncate':
            write_table = dest_table
            writemode = 'overwrite'
            truncate = 'true'
        else:
            write_table = dest_table
            writemode = dest_writemode

        # Add column with import timestamp
        df = df.withColumn('spark_import_timestamp', f.current_timestamp())

        df.cache().write.format("jdbc").options(
            url=dest_connstring,
            dbtable=write_table,
            user=dest_username,
            password=dest_password,
            driver=dest_driver,
            truncate=truncate
        ).mode(writemode).save()

        if dest_writemode == 'upsert':
            perform_upsert(dataset=df, table_name=dest_table, 
                            keys=dest_keys, url=dest_connstring, 
                            username=dest_username, password=dest_password)

    if check_column is not None:
        new_last_value = df.agg({check_column: "max"}).collect()[0][0]
        update_metadata_spark(connection_metastore=connection_metastore, 
                              metastore_table_name=metastore_table_name, 
                              last_value=new_last_value, 
                              check_column=check_column, 
                              dag_name=dag_name, 
                              task_name=task_name)

def perform_upsert(dataset, table_name, keys, url, username, password):

        # Convert keys in list in case it is a string
        if not isinstance(keys, list):
            keys = [keys]
        
        # Create connection string
        host = url.split('://')[-1]
        database_type = url.split('://')[0].split(':')[1]
        connection_url = '%s://%s:%s@%s' % (database_type, username, password, host)

        # Get session and connection
        engine = create_engine(connection_url, echo=False, pool_pre_ping=True)
        session_maker = sessionmaker(bind=engine)

        session = session_maker()
        connection = session.connection()
        
        # Upsert
        other_cols = list(set(dataset.columns).difference(keys))
        other_fields = ', '.join([f'{c} = EXCLUDED.{c}' for c in other_cols])

        # Then merge
        if len(other_fields) > 0:
            upsert_query = f"""insert into public.{table_name} 
                                select {",".join(dataset.columns)} from {table_name}_tmp
                                on conflict({",".join(keys)})
                                do update SET {other_fields}"""
        else:
            upsert_query = f"""INSERT INTO public.{table_name}
                                select {",".join(dataset.columns)} from {table_name}_tmp
                                ON CONFLICT ({",".join(keys)}) DO NOTHING
                            """

        connection.execute(text(upsert_query))

        # Drop temporaney table
        connection.execute(text(f"DROP TABLE {table_name}_tmp"))
        
        # Commit changes
        try:
            session.commit()
        except:
            session.rollout()

def update_metadata_spark(connection_metastore, metastore_table_name, last_value, check_column, dag_name, task_name):
        
        engine = create_engine(connection_metastore, echo=False, pool_pre_ping=True)
        metadata = MetaData(engine)
        metastore_table = Table(metastore_table_name, metadata, autoload=True)
      
        insert_query = insert(metastore_table).values(
            job='%s.%s' % (dag_name, task_name), last_value=last_value,
            update_datetime=datetime.datetime.now(), variable=check_column)
        insert_query = insert_query.on_conflict_do_update(constraint=metastore_table.primary_key,
                                                            set_=dict(insert_query.excluded))

        conn = engine.connect()
        try:
            conn.execute(insert_query)
        except:
            raise RuntimeError('Error in updating last value of Spark job.')
        finally:
            conn.close()

def _parse_arguments(args: list[str] | None = None) -> Any:
    parser = argparse.ArgumentParser(description="Spark-JDBC")
    parser.add_argument("-cmdType", dest="cmd_type", action="store")
    parser.add_argument("-url", dest="url", action="store")
    parser.add_argument("-user", dest="user", action="store")
    parser.add_argument("-password", dest="password", action="store")
    parser.add_argument("-metastoreTable", dest="metastore_table", action="store", default=None)
    parser.add_argument("-jdbcTable", dest="jdbc_table", action="store", default=None)
    parser.add_argument("-jdbcDriver", dest="jdbc_driver", action="store")
    parser.add_argument("-jdbcTruncate", dest="truncate", action="store", default=None)
    parser.add_argument("-saveMode", dest="save_mode", action="store")
    parser.add_argument("-saveFormat", dest="save_format", action="store")
    parser.add_argument("-batchsize", dest="batch_size", action="store", default=None)
    parser.add_argument("-fetchsize", dest="fetch_size", action="store", default=None)
    parser.add_argument("-name", dest="name", action="store", default='spark_ingestion')
    parser.add_argument("-numPartitions", dest="num_partitions", action="store", default=1)
    parser.add_argument("-partitionColumn", dest="partition_column", action="store", default=None)
    parser.add_argument("-lowerBound", dest="lower_bound", action="store", default=None)
    parser.add_argument("-upperBound", dest="upper_bound", action="store", default=None)
    parser.add_argument("-createTableColumnTypes", dest="create_table_column_types", action="store", default=None)
    parser.add_argument("-connectionMetastore", dest="connection_metastore", action="store", default=None)
    parser.add_argument("-dagName", dest="dag_name", action="store")
    parser.add_argument("-taskName", dest="task_name", action="store")
    parser.add_argument("-checkColumn", dest="check_column", action="store", default=None)
    parser.add_argument("-lastValue", dest="last_value", action="store", default=None)
    parser.add_argument("-outputPath", dest="output_path", action="store", default=None)
    parser.add_argument("-metastoreTableName", dest="metastore_table_name", action="store", default=None)
    parser.add_argument("-query", dest="query", action="store", default=None)
    parser.add_argument("-destinationConnectionString", dest="dest_connstring", action="store", default=None)
    parser.add_argument("-destinationTable", dest="dest_table", action="store", default=None)
    parser.add_argument("-destinationDriver", dest="dest_driver", action="store", default=None)
    parser.add_argument("-destinationKeys", dest="dest_keys", action="store", default=None)
    parser.add_argument("-destinationWriteMode", dest="dest_writemode", action="store", default=None)
    parser.add_argument("-destinationUsername", dest="dest_username", action="store", default=None)
    parser.add_argument("-destinationPassword", dest="dest_password", action="store", default=None)
    return parser.parse_args(args=args)

def _create_spark_session(arguments: Any) -> SparkSession:
    return SparkSession.builder.appName(arguments.name).enableHiveSupport().getOrCreate()


def _run_spark(arguments: Any) -> None:
    # Disable dynamic allocation by default to allow num_executors to take effect.
    spark = _create_spark_session(arguments)

    if arguments.cmd_type == SPARK_WRITE_TO_JDBC:
        spark_write_to_jdbc(
            spark,
            arguments.url,
            arguments.user,
            arguments.password,
            arguments.metastore_table,
            arguments.jdbc_table,
            arguments.jdbc_driver,
            arguments.truncate,
            arguments.save_mode,
            arguments.batch_size,
            arguments.num_partitions,
            arguments.create_table_column_types,
        )
    elif arguments.cmd_type == SPARK_READ_FROM_JDBC:
        spark_read_from_jdbc(
            spark,
            arguments.url,
            arguments.user,
            arguments.password,
            arguments.metastore_table,
            arguments.jdbc_table,
            arguments.jdbc_driver,
            arguments.save_mode,
            arguments.save_format,
            arguments.fetch_size,
            arguments.num_partitions,
            arguments.partition_column,
            arguments.lower_bound,
            arguments.upper_bound,
            arguments.dag_name,
            arguments.task_name,
            arguments.check_column,
            arguments.last_value,
            arguments.output_path,
            arguments.connection_metastore,
            arguments.metastore_table_name,
            arguments.query,
            arguments.dest_connstring,
            arguments.dest_table,
            arguments.dest_driver,
            arguments.dest_keys,
            arguments.dest_writemode,
            arguments.dest_username,
            arguments.dest_password
        )


if __name__ == "__main__":  # pragma: no cover
    _run_spark(arguments=_parse_arguments())
