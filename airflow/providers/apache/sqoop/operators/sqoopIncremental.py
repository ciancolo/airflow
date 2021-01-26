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
#
"""This module contains a sqoop 1 operator"""
import os
import signal
from typing import Any, Dict, Optional

from airflow.exceptions import AirflowException
from airflow.providers.apache.sqoop.hooks.sqoop import SqoopHook
from airflow.providers.apache.sqoop.operators.sqoop import SqoopOperator
from airflow.utils.decorators import apply_defaults
from sqlalchemy import create_engine, MetaData, func, Table
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
import sys
from airflow.configuration import conf
import datetime


# pylint: disable=too-many-instance-attributes
class SqoopOperatorIncremental(SqoopOperator):
    """
    Execute a Sqoop job.
    Documentation for Apache Sqoop can be found here:
    https://sqoop.apache.org/docs/1.4.2/SqoopUserGuide.html

    :param conn_id: str
    :param cmd_type: str specify command to execute "export" or "import"
    :param table: Table to read
    :param query: Import result of arbitrary SQL query. Instead of using the table,
        columns and where arguments, you can specify a SQL statement with the query
        argument. Must also specify a destination directory with target_dir.
    :param target_dir: HDFS destination directory where the data
        from the rdbms will be written
    :param append: Append data to an existing dataset in HDFS
    :param file_type: "avro", "sequence", "text" Imports data to
        into the specified format. Defaults to text.
    :param columns: <col,col,col> Columns to import from table
    :param num_mappers: Use n mapper tasks to import/export in parallel
    :param split_by: Column of the table used to split work units
    :param where: WHERE clause to use during import
    :param export_dir: HDFS Hive database directory to export to the rdbms
    :param input_null_string: The string to be interpreted as null
        for string columns
    :param input_null_non_string: The string to be interpreted as null
        for non-string columns
    :param staging_table: The table in which data will be staged before
        being inserted into the destination table
    :param clear_staging_table: Indicate that any data present in the
        staging table can be deleted
    :param enclosed_by: Sets a required field enclosing character
    :param escaped_by: Sets the escape character
    :param input_fields_terminated_by: Sets the input field separator
    :param input_lines_terminated_by: Sets the input end-of-line character
    :param input_optionally_enclosed_by: Sets a field enclosing character
    :param batch: Use batch mode for underlying statement execution
    :param direct: Use direct export fast path
    :param driver: Manually specify JDBC driver class to use
    :param verbose: Switch to more verbose logging for debug purposes
    :param relaxed_isolation: use read uncommitted isolation level
    :param hcatalog_database: Specifies the database name for the HCatalog table
    :param hcatalog_table: The argument value for this option is the HCatalog table
    :param create_hcatalog_table: Have sqoop create the hcatalog table passed
        in or not
    :param properties: additional JVM properties passed to sqoop
    :param extra_import_options: Extra import options to pass as dict.
        If a key doesn't have a value, just pass an empty string to it.
        Don't include prefix of -- for sqoop options.
    :param extra_export_options: Extra export options to pass as dict.
        If a key doesn't have a value, just pass an empty string to it.
        Don't include prefix of -- for sqoop options.
    :param conn_metastore_id: str
    :param metastore_table: str
    """

    template_fields = (
        'conn_id',
        'cmd_type',
        'table',
        'query',
        'target_dir',
        'file_type',
        'columns',
        'split_by',
        'where',
        'export_dir',
        'input_null_string',
        'input_null_non_string',
        'staging_table',
        'enclosed_by',
        'escaped_by',
        'input_fields_terminated_by',
        'input_lines_terminated_by',
        'input_optionally_enclosed_by',
        'properties',
        'extra_import_options',
        'driver',
        'extra_export_options',
        'hcatalog_database',
        'hcatalog_table',
        'conn_metastore_id',
        'metastore_table',
    )
    ui_color = '#7D8CA4'

    # pylint: disable=too-many-arguments,too-many-locals
    @apply_defaults
    def __init__(
        self,
        *,
        conn_id: str = 'sqoop_default',
        cmd_type: str = 'import',
        table: Optional[str] = None,
        query: Optional[str] = None,
        target_dir: Optional[str] = None,
        append: bool = False,
        file_type: str = 'text',
        columns: Optional[str] = None,
        num_mappers: Optional[int] = None,
        split_by: Optional[str] = None,
        where: Optional[str] = None,
        export_dir: Optional[str] = None,
        input_null_string: Optional[str] = None,
        input_null_non_string: Optional[str] = None,
        staging_table: Optional[str] = None,
        clear_staging_table: bool = False,
        enclosed_by: Optional[str] = None,
        escaped_by: Optional[str] = None,
        input_fields_terminated_by: Optional[str] = None,
        input_lines_terminated_by: Optional[str] = None,
        input_optionally_enclosed_by: Optional[str] = None,
        batch: bool = False,
        direct: bool = False,
        driver: Optional[Any] = None,
        verbose: bool = False,
        relaxed_isolation: bool = False,
        properties: Optional[Dict[str, Any]] = None,
        hcatalog_database: Optional[str] = None,
        hcatalog_table: Optional[str] = None,
        create_hcatalog_table: bool = False,
        extra_import_options: Optional[Dict[str, Any]] = None,
        extra_export_options: Optional[Dict[str, Any]] = None,
        conn_metastore_id: Optional[str] = None,
        metastore_table: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.conn_id = conn_id
        self.cmd_type = cmd_type
        self.table = table
        self.query = query
        self.target_dir = target_dir
        self.append = append
        self.file_type = file_type
        self.columns = columns
        self.num_mappers = num_mappers
        self.split_by = split_by
        self.where = where
        self.export_dir = export_dir
        self.input_null_string = input_null_string
        self.input_null_non_string = input_null_non_string
        self.staging_table = staging_table
        self.clear_staging_table = clear_staging_table
        self.enclosed_by = enclosed_by
        self.escaped_by = escaped_by
        self.input_fields_terminated_by = input_fields_terminated_by
        self.input_lines_terminated_by = input_lines_terminated_by
        self.input_optionally_enclosed_by = input_optionally_enclosed_by
        self.batch = batch
        self.direct = direct
        self.driver = driver
        self.verbose = verbose
        self.relaxed_isolation = relaxed_isolation
        self.hcatalog_database = hcatalog_database
        self.hcatalog_table = hcatalog_table
        self.create_hcatalog_table = create_hcatalog_table
        self.properties = properties
        self.extra_import_options = extra_import_options or {}
        self.extra_export_options = extra_export_options or {}
        self.hook: Optional[SqoopHook] = None
        self.conn_metastore_id = conn_metastore_id
        self.metastore_table = metastore_table

    def execute(self, context: Dict[str, Any]) -> None:
        if self.hook is None:
            self.hook = self._get_hook()

        if 'check-column' in self.extra_import_options.keys() and 'incremental' in self.extra_import_options.keys():
            if 'column-type' not in self.extra_import_options.keys():
                raise AirflowException('column-type properties needed for incremental Sqoop')
            self.log.info('Gather last-value for %s.%s and column %s from SqoopMetastore' %
                          (context['dag'].dag_id, context['task_instance'].task_id,
                           self.extra_import_options['check-column']))
            last_value = self.__read_last_value(context)
            self.extra_import_options['last-value'] = last_value

        if self.cmd_type == 'export':
            self.hook.export_table(
                table=self.table,  # type: ignore
                export_dir=self.export_dir,
                input_null_string=self.input_null_string,
                input_null_non_string=self.input_null_non_string,
                staging_table=self.staging_table,
                clear_staging_table=self.clear_staging_table,
                enclosed_by=self.enclosed_by,
                escaped_by=self.escaped_by,
                input_fields_terminated_by=self.input_fields_terminated_by,
                input_lines_terminated_by=self.input_lines_terminated_by,
                input_optionally_enclosed_by=self.input_optionally_enclosed_by,
                batch=self.batch,
                relaxed_isolation=self.relaxed_isolation,
                extra_export_options=self.extra_export_options,
            )
        elif self.cmd_type == 'import':
            # add create hcatalog table to extra import options if option passed
            # if new params are added to constructor can pass them in here
            # so don't modify sqoop_hook for each param
            if self.create_hcatalog_table:
                self.extra_import_options['create-hcatalog-table'] = ''

            if self.table and self.query:
                raise AirflowException('Cannot specify query and table together. Need to specify either or.')

            if self.table:
                self.hook.import_table(
                    table=self.table,
                    target_dir=self.target_dir,
                    append=self.append,
                    file_type=self.file_type,
                    columns=self.columns,
                    split_by=self.split_by,
                    where=self.where,
                    direct=self.direct,
                    driver=self.driver,
                    extra_import_options=self.extra_import_options,
                )
            elif self.query:
                self.hook.import_query(
                    query=self.query,
                    target_dir=self.target_dir,
                    append=self.append,
                    file_type=self.file_type,
                    split_by=self.split_by,
                    direct=self.direct,
                    driver=self.driver,
                    extra_import_options=self.extra_import_options,
                )
            else:
                raise AirflowException("Provide query or table parameter to import using Sqoop")
        else:
            raise AirflowException("cmd_type should be 'import' or 'export'")

        if 'check-column' in self.extra_import_options.keys() and 'incremental' in self.extra_import_options.keys():
            self.log.info('Update last-value for %s.%s and column %s from SqoopMetastore' %
                          (context['dag'].dag_id, context['task_instance'].task_id,
                           self.extra_import_options['check-column']))
            self.__update_metadata_sqoop(context)

    def __read_last_value(self, context):
        session_maker = self.hook.get_session_maker()
        session = session_maker()
        result = session.query(self.metastore_table) \
            .filter_by(job='%s.%s' % (context['dag'].dag_id, context['task_instance'].task_id)) \
            .filter_by(variable='%s' % self.extra_import_options['check-column']) \
            .all()

        if result != []:
            return result[0][1]
        else:
            if self.extra_import_options['column_type'] == 'int':
                return '%d' % (-sys.maxsize - 1)
            elif self.extra_import_options['column_type'] == 'datetime' or self.extra_import_options['column_type'] == 'date':
                return '1970-01-01'
            else:
                raise AirflowException("Unknown incremental column type")

    def __update_metadata_sqoop(self, context):

        base_log_folder = conf.get("logging", "base_log_folder").rstrip("/")

        dag_runs = os.listdir(os.path.join(base_log_folder, context['dag'].dag_id, context['task_instance'].task_id))
        latest_dag_run = sorted(dag_runs, reverse=True).pop(0)
        task_runs = os.listdir(
            os.path.join(base_log_folder, context['dag'].dag_id, context['task_instance'].task_id, latest_dag_run))
        latest_task_run = sorted(task_runs, reverse=True).pop(0)

        with open(os.path.join(base_log_folder, context['dag'].dag_id, context['task_instance'].task_id, latest_dag_run,
                               latest_task_run), 'rt') as file_log:
            data = file_log.read()
            if data.find('INFO tool.ImportTool:   --last-value') > 1:
                last_value = data.split('INFO tool.ImportTool:   --last-value')[1].split('\'\n')[0]
            else:
                raise AirflowException('Last-value parameter not found in Logs!')

            insert_query = insert(self.metastore_table).values(
                job='%s.%s' % (context['dag'].dag_id, context['task_instance'].task_id), last_value=last_value,
                update_datetime=datetime.datetime.now(), column=self.extra_import_options['check-column'])
            insert_query = insert_query.on_conflict_do_update(constraint='job_metadata_pk',
                                                              set_=dict(insert_query.excluded))

            conn = self.hook.get_engine().connect()
            try:
                conn.execute(insert_query)
            except:
                raise AirflowException('Error in updating last value of Sqoop job.')
            finally:
                conn.close()
