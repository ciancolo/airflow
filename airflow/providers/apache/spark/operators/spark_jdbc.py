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

from typing import TYPE_CHECKING, Any

from airflow.providers.apache.spark.hooks.spark_jdbc import SparkJDBCHook
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.exceptions import AirflowException
import datetime

if TYPE_CHECKING:
    from airflow.utils.context import Context


class SparkJDBCOperator(SparkSubmitOperator):
    """
    Extend the SparkSubmitOperator to perform data transfers to/from JDBC-based databases with Apache Spark.

     As with the SparkSubmitOperator, it assumes that the "spark-submit" binary is available on the PATH.

    .. seealso::
        For more information on how to use this operator, take a look at the guide:
        :ref:`howto/operator:SparkJDBCOperator`

    :param spark_app_name: Name of the job (default airflow-spark-jdbc)
    :param spark_conn_id: The :ref:`spark connection id <howto/connection:spark-submit>`
        as configured in Airflow administration
    :param spark_conf: Any additional Spark configuration properties
    :param spark_py_files: Additional python files used (.zip, .egg, or .py)
    :param spark_files: Additional files to upload to the container running the job
    :param spark_jars: Additional jars to upload and add to the driver and
                       executor classpath
    :param cmd_type: Which way the data should flow. 2 possible values:
                     spark_to_jdbc: data written by spark from metastore to jdbc
                     jdbc_to_spark: data written by spark from jdbc to metastore
    :param jdbc_table: The name of the JDBC table
    :param jdbc_conn_id: Connection id used for connection to JDBC database
    :param jdbc_driver: Name of the JDBC driver to use for the JDBC connection. This
                        driver (usually a jar) should be passed in the 'jars' parameter
    :param metastore_table: The name of the metastore table,
    :param jdbc_truncate: (spark_to_jdbc only) Whether Spark should truncate or
                         drop and recreate the JDBC table. This only takes effect if
                         'save_mode' is set to Overwrite. Also, if the schema is
                         different, Spark cannot truncate, and will drop and recreate
    :param save_mode: The Spark save-mode to use (e.g. overwrite, append, etc.)
    :param save_format: (jdbc_to_spark-only) The Spark save-format to use (e.g. parquet)
    :param batch_size: (spark_to_jdbc only) The size of the batch to insert per round
                       trip to the JDBC database. Defaults to 1000
    :param fetch_size: (jdbc_to_spark only) The size of the batch to fetch per round trip
                       from the JDBC database. Default depends on the JDBC driver
    :param num_partitions: The maximum number of partitions that can be used by Spark
                           simultaneously, both for spark_to_jdbc and jdbc_to_spark
                           operations. This will also cap the number of JDBC connections
                           that can be opened
    :param partition_column: (jdbc_to_spark-only) A numeric column to be used to
                             partition the metastore table by. If specified, you must
                             also specify:
                             num_partitions, lower_bound, upper_bound
    :param lower_bound: (jdbc_to_spark-only) Lower bound of the range of the numeric
                        partition column to fetch. If specified, you must also specify:
                        num_partitions, partition_column, upper_bound
    :param upper_bound: (jdbc_to_spark-only) Upper bound of the range of the numeric
                        partition column to fetch. If specified, you must also specify:
                        num_partitions, partition_column, lower_bound
    :param create_table_column_types: (spark_to_jdbc-only) The database column data types
                                      to use instead of the defaults, when creating the
                                      table. Data type information should be specified in
                                      the same format as CREATE TABLE columns syntax
                                      (e.g: "name CHAR(64), comments VARCHAR(1024)").
                                      The specified types should be valid spark sql data
                                      types.
    :param kwargs: kwargs passed to SparkSubmitOperator.
    """

    def __init__(
        self,
        *,
        spark_app_name: str = "airflow-spark-jdbc",
        spark_conn_id: str = "spark-default",
        spark_conf: dict[str, Any] | None = None,
        spark_py_files: str | None = None,
        spark_files: str | None = None,
        spark_jars: str | None = None,
        cmd_type: str = "spark_to_jdbc",
        jdbc_table: str | None = None,
        jdbc_conn_id: str = "jdbc-default",
        jdbc_driver: str | None = None,
        metastore_table: str | None = None,
        jdbc_truncate: bool = False,
        save_mode: str | None = None,
        save_format: str | None = None,
        batch_size: int | None = None,
        fetch_size: int | None = None,
        num_partitions: int | None = None,
        partition_column: str | None = None,
        lower_bound: str | None = None,
        upper_bound: str | None = None,
        create_table_column_types: str | None = None,
        conn_metastore_id: str | None = None,
        metastore_table_name: str | None = None,
        check_column: str | None = None,
        overlap_type: str | None = None,
        overlap_value: str | None = None,
        overlap_format: str | None = None,
        output_path: str | None = None,
        spark_binary: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(spark_binary=spark_binary, **kwargs)
        self._spark_app_name = spark_app_name
        self._spark_conn_id = spark_conn_id
        self._spark_conf = spark_conf
        self._spark_py_files = spark_py_files
        self._spark_files = spark_files
        self._spark_jars = spark_jars
        self._cmd_type = cmd_type
        self._jdbc_table = jdbc_table
        self._jdbc_conn_id = jdbc_conn_id
        self._jdbc_driver = jdbc_driver
        self._metastore_table = metastore_table
        self._jdbc_truncate = jdbc_truncate
        self._save_mode = save_mode
        self._save_format = save_format
        self._batch_size = batch_size
        self._fetch_size = fetch_size
        self._num_partitions = num_partitions
        self._partition_column = partition_column
        self._lower_bound = lower_bound
        self._upper_bound = upper_bound
        self._create_table_column_types = create_table_column_types
        self._hook: SparkJDBCHook | None = None
        self.conn_metastore_id = conn_metastore_id
        self.metastore_table_name = metastore_table_name
        self.check_column = check_column
        self.overlap_type = overlap_type
        self.overlap_value = overlap_value
        self.overlap_format = overlap_format
        self.output_path = output_path
        self.last_value = None

    def execute(self, context: Context) -> None:
        """Call the SparkSubmitHook to run the provided spark job."""
        self.dag_name = context['dag'].dag_id
        self.task_name = context['task_instance'].task_id

        if self._hook is None:
            self._hook = self._get_hook()
        
        if self.conn_metastore_id and \
            self.check_column:

            self.log.info('Gather last-value for %s.%s and column %s from SqoopMetastore' %
                          (context['dag'].dag_id, context['task_instance'].task_id,
                           self.check_column))

            self._hook.last_value = self.__read_last_value(context)

            if self._hook.last_value:
                self._hook.last_value = self.__manage_incremental_overlap(self._hook.last_value)
        
        self._hook.submit_jdbc_job()

    def on_kill(self) -> None:
        if self._hook is None:
            self._hook = self._get_hook()
        self._hook.on_kill()

    def _get_hook(self) -> SparkJDBCHook:
        return SparkJDBCHook(
            spark_app_name=self._spark_app_name,
            spark_conn_id=self._spark_conn_id,
            spark_conf=self._spark_conf,
            spark_py_files=self._spark_py_files,
            spark_files=self._spark_files,
            spark_jars=self._spark_jars,
            num_executors=self._num_executors,
            executor_cores=self._executor_cores,
            executor_memory=self._executor_memory,
            driver_memory=self._driver_memory,
            verbose=self._verbose,
            keytab=self.keytab,
            principal=self.principal,
            cmd_type=self._cmd_type,
            jdbc_table=self._jdbc_table,
            jdbc_conn_id=self._jdbc_conn_id,
            jdbc_driver=self._jdbc_driver,
            metastore_table=self._metastore_table,
            jdbc_truncate=self._jdbc_truncate,
            save_mode=self._save_mode,
            save_format=self._save_format,
            batch_size=self._batch_size,
            fetch_size=self._fetch_size,
            num_partitions=self._num_partitions,
            partition_column=self._partition_column,
            lower_bound=self._lower_bound,
            upper_bound=self._upper_bound,
            create_table_column_types=self._create_table_column_types,
            use_krb5ccache=self._use_krb5ccache,
            conn_metastore_id = self.conn_metastore_id,
            metastore_table_name = self.metastore_table_name,
            check_column = self.check_column,
            dag_name = self.dag_name,
            task_name = self.task_name,
            last_value = self.last_value,
            output_path = self.output_path
        )

    def __read_last_value(self, context):
        session_maker = self._hook.get_session_maker()
        session = session_maker()
        result = session.query(self._hook.get_metastore_table()) \
                        .filter_by(job='%s.%s' % (context['dag'].dag_id, context['task_instance'].task_id)) \
                        .filter_by(variable='%s' % self.check_column) \
                        .all()

        if result != []:
            return result[0][1].strip()
        else:
            None

    def __manage_incremental_overlap(self, last_value) -> str:
        self.log.info('Manage overlap for incremental value')
        if not last_value or \
            last_value == ' null':
            return last_value

        if self.overlap_value and self.overlap_type:

            # Check overlap-type is a valid value
            if not self.overlap_type in ['numeric', 'timestamp']:
                self.log.error(f"{self.overlap_type} is not a valid value. Valid values are numeric or timestamp")
                raise AirflowException(f"{self.overlap_type} is not a valid value. Valid values are numeric or timestamp")
            
            # Check if overlap-format is present and with a valid value
            if self.overlap_type == 'timestamp':
                if self.overlap_format:
                    if not self.overlap_format in ['days', 'hours', 'minutes', 'seconds']:
                        self.log.error(f"{self.overlap_format} is not a valid value. Valid values are days, hours, minutes or seconds")
                        raise AirflowException(f"{self.overlap_format} is not a valid value. Valid values are days, hours, minutes or seconds")
                else:
                    self.log.error(f"overlap-format parameter not specified with overlap-type timestamp")
                    raise AirflowException(f"overlap-format parameter not specified with overlap-type timestamp")
                
            # Adjust the last-value with the overlap
            if self.overlap_type == 'timestamp':
                db_last_value = datetime.datetime.strptime(last_value, ' %Y-%m-%d %H:%M:%S.%f')
                updated_last_value = db_last_value - datetime.timedelta(**{self.overlap_format: self.overlap_value})
                last_value = datetime.datetime.strftime(updated_last_value,' %Y-%m-%d %H:%M:%S')
            else:
                last_value = f" {eval(last_value) - self.overlap_value}"

        return last_value