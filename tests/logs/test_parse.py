# Copyright 2015 Yelp
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from mrjob.logs.parse import _parse_hadoop_log_lines
from mrjob.logs.parse import _parse_hadoop_streaming_log
from mrjob.logs.parse import _parse_indented_counters
from mrjob.logs.parse import _parse_pre_yarn_counters
from mrjob.logs.parse import _parse_pre_yarn_history_file
from mrjob.logs.parse import _parse_python_task_stderr
from mrjob.logs.parse import _parse_task_syslog
from mrjob.logs.parse import _summarize_pre_yarn_history
from mrjob.py2 import StringIO
from mrjob.util import log_to_stream

from tests.py2 import TestCase
from tests.quiet import no_handlers_for_logger


class ParseHadoopLogLinesTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(list(_parse_hadoop_log_lines([])), [])

    def test_log_lines(self):
        lines = StringIO('15/12/11 13:26:07 INFO client.RMProxy:'
                         ' Connecting to ResourceManager at /0.0.0.0:8032\n'
                         '15/12/11 13:26:08 ERROR streaming.StreamJob:'
                         ' Error Launching job :'
                         ' Output directory already exists\n')
        self.assertEqual(
            list(_parse_hadoop_log_lines(lines)), [
                dict(
                    timestamp='15/12/11 13:26:07',
                    level='INFO',
                    logger='client.RMProxy',
                    thread=None,
                    message='Connecting to ResourceManager at /0.0.0.0:8032'),
                dict(
                    timestamp='15/12/11 13:26:08',
                    level='ERROR',
                    logger='streaming.StreamJob',
                    thread=None,
                    message=('Error Launching job :'
                             ' Output directory already exists'))
            ])

    def test_trailing_carriage_return(self):
        lines = StringIO('15/12/11 13:26:07 INFO client.RMProxy:'
                         ' Connecting to ResourceManager at /0.0.0.0:8032\r\n')
        self.assertEqual(
            list(_parse_hadoop_log_lines(lines)), [
                dict(
                    timestamp='15/12/11 13:26:07',
                    level='INFO',
                    logger='client.RMProxy',
                    thread=None,
                    message='Connecting to ResourceManager at /0.0.0.0:8032')
            ])

    def test_thread(self):
        lines = StringIO(
            '2015-08-22 00:46:18,411 INFO amazon.emr.metrics.MetricsSaver'
            ' (main): Thread 1 created MetricsLockFreeSaver 1\n')

        self.assertEqual(
            list(_parse_hadoop_log_lines(lines)), [
                dict(
                    timestamp='2015-08-22 00:46:18,411',
                    level='INFO',
                    logger='amazon.emr.metrics.MetricsSaver',
                    thread='main',
                    message='Thread 1 created MetricsLockFreeSaver 1')
            ])

    def test_multiline_message(self):
        lines = StringIO(
            '2015-08-22 00:47:35,323 INFO org.apache.hadoop.mapreduce.Job'
            ' (main): Counters: 54\r\n'
            '        File System Counters\r\n'
            '                FILE: Number of bytes read=83\r\n')

        self.assertEqual(
            list(_parse_hadoop_log_lines(lines)), [
                dict(
                    timestamp='2015-08-22 00:47:35,323',
                    level='INFO',
                    logger='org.apache.hadoop.mapreduce.Job',
                    thread='main',
                    # strip \r's, no trailing \n
                    message=('Counters: 54\n'
                             '        File System Counters\n'
                             '                FILE: Number of bytes read=83'))
            ])

    def test_non_log_lines(self):
        lines = StringIO('foo\n'
                         'bar\n'
                         '15/12/11 13:26:08 ERROR streaming.StreamJob:'
                         ' Error Launching job :'
                         ' Output directory already exists\n'
                         'Streaming Command Failed!')

        with no_handlers_for_logger('mrjob.logs.parse'):
            stderr = StringIO()
            log_to_stream('mrjob.logs.parse', stderr)

            self.assertEqual(
            list(_parse_hadoop_log_lines(lines)), [
                # ignore leading non-log lines
                dict(
                    timestamp='15/12/11 13:26:08',
                    level='ERROR',
                    logger='streaming.StreamJob',
                    thread=None,
                    # no way to know that Streaming Command Failed! wasn't part
                    # of a multi-line message
                    message=('Error Launching job :'
                             ' Output directory already exists\n'
                             'Streaming Command Failed!'))
            ])

            # should be one warning for each leading non-log line
            log_lines = stderr.getvalue().splitlines()
            self.assertEqual(len(log_lines), 2)


class ParseHadoopStreamingLogTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(
            _parse_hadoop_streaming_log([]),
            dict(application_id=None,
                 counters=None,
                 job_id=None,
                 output_dir=None))

    def test_yarn_output(self):
        # abbreviated version of real output from Hadoop 2.7.0.
        # Including things that might be interesting to parse later on
        lines = StringIO(
            '15/12/11 13:32:44 INFO client.RMProxy:'
            ' Connecting to ResourceManager at /0.0.0.0:8032\n'
            '15/12/11 13:32:45 INFO mapreduce.JobSubmitter:'
            ' Submitting tokens for job: job_1449857544442_0002\n'
            '15/12/11 13:32:45 INFO impl.YarnClientImpl:'
            ' Submitted application application_1449857544442_0002\n'
            '15/12/11 13:32:45 INFO mapreduce.Job:'
            ' The url to track the job:'
            ' http://0a7802e19139:8088/proxy/application_1449857544442_0002/\n'
            '15/12/11 13:33:11 INFO mapreduce.Job:  map 100% reduce 100%\n'
            '15/12/11 13:33:11 INFO mapreduce.Job:'
            ' Job job_1449857544442_0002 completed successfully\n'
            '15/12/11 13:33:11 INFO mapreduce.Job: Counters: 49\n'
            '        File System Counters\n'
            '                FILE: Number of bytes read=86\n'
            '15/12/11 13:33:11 INFO streaming.StreamJob:'
            ' Output directory:'
            ' hdfs:///user/root/tmp/mrjob/mr_wc.root.20151211.181326.984074'
            '/output\n')

        self.assertEqual(
            _parse_hadoop_streaming_log(lines),
            dict(application_id='application_1449857544442_0002',
                 counters={
                     'File System Counters': {
                         'FILE: Number of bytes read': 86,
                     }
                 },
                 job_id='job_1449857544442_0002',
                 output_dir=('hdfs:///user/root/tmp/mrjob'
                             '/mr_wc.root.20151211.181326.984074/output')))

    def test_pre_yarn_output(self):
        # actual output from Hadoop 1.0.3 on EMR AMI 2.4.9
        # Including things that might be interesting to parse later on
        lines = StringIO(
            '15/12/11 23:08:37 INFO streaming.StreamJob:'
            ' getLocalDirs(): [/mnt/var/lib/hadoop/mapred]\n'
            '15/12/11 23:08:37 INFO streaming.StreamJob:'
            ' Running job: job_201512112247_0003\n'
            '15/12/11 23:08:37 INFO streaming.StreamJob:'
            ' Tracking URL:'
            ' http://ip-172-31-27-129.us-west-2.compute.internal:9100'
            '/jobdetails.jsp?jobid=job_201512112247_0003\n'
            '15/12/11 23:09:16 INFO streaming.StreamJob:'
            '  map 100%  reduce 100%\n'
            '15/12/11 23:09:22 INFO streaming.StreamJob:'
            ' Output: hdfs:///user/hadoop/tmp/mrjob'
            '/mr_wc.hadoop.20151211.230352.433691/output\n')

        self.assertEqual(
            _parse_hadoop_streaming_log(lines),
            dict(application_id=None,
                 counters=None,
                 job_id='job_201512112247_0003',
                 output_dir=('hdfs:///user/hadoop/tmp/mrjob'
                             '/mr_wc.hadoop.20151211.230352.433691/output')))


class ParseIndentedCountersTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(_parse_indented_counters([]), {})

    def test_without_header(self):
        lines = [
            '  File System Counters',
            '    FILE: Number of bytes read=86',
            '    FILE: Number of bytes written=359982',
            '  Job Counters',
            '    Launched map tasks=2',
        ]

        self.assertEqual(_parse_indented_counters(lines), {
            'File System Counters': {
                'FILE: Number of bytes read': 86,
                'FILE: Number of bytes written': 359982,
            },
            'Job Counters': {
                'Launched map tasks': 2,
            },
        })

    def test_with_header(self):
        lines = [
            'Counters: 1',
            '  File System Counters',
            '    FILE: Number of bytes read=86',
        ]

        with no_handlers_for_logger('mrjob.logs.parse'):
            stderr = StringIO()
            log_to_stream('mrjob.logs.parse', stderr)

            self.assertEqual(_parse_indented_counters(lines), {
                'File System Counters': {
                    'FILE: Number of bytes read': 86,
                },
            })

            # header shouldn't freak it out
            self.assertEqual(stderr.getvalue(), '')

    def test_indentation_is_required(self):
        lines = [
            'File System Counters',
            '   FILE: Number of bytes read=8',
        ]

        with no_handlers_for_logger('mrjob.logs.parse'):
            stderr = StringIO()
            log_to_stream('mrjob.logs.parse', stderr)

            # counter line is interpreted as group
            self.assertEqual(_parse_indented_counters(lines), {})

            # should complain
            self.assertNotEqual(stderr.getvalue(), '')

    def test_no_empty_groups(self):
        lines = [
            '  File System Counters',
            '  Job Counters',
            '    Launched map tasks=2',
        ]

        self.assertEqual(_parse_indented_counters(lines), {
            'Job Counters': {
                'Launched map tasks': 2,
            },
        })


class ParseTaskSyslogTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(_parse_task_syslog([]),
                         dict(error=None, split=None))

    def test_split(self):
        lines = [
            '2015-12-21 14:06:17,707 INFO [main]'
            ' org.apache.hadoop.mapred.MapTask: Processing split:'
            ' hdfs://e4270474c8ee:9000/user/root/tmp/mrjob'
            '/mr_boom.root.20151221.190511.059097/files/bootstrap.sh:0+335\n',
        ]

        self.assertEqual(
            _parse_task_syslog(lines),
            dict(error=None, split=dict(
                path=('hdfs://e4270474c8ee:9000/user/root/tmp/mrjob'
                     '/mr_boom.root.20151221.190511.059097/files'
                     '/bootstrap.sh'),
                start_line=0,
                num_lines=335)))

    def test_opening_file(self):
        lines = [
            '2010-07-27 17:54:54,344 INFO'
            ' org.apache.hadoop.fs.s3native.NativeS3FileSystem (main):'
            " Opening 's3://yourbucket/logs/2010/07/23/log2-00077.gz'"
            ' for reading\n'
        ]

        self.assertEqual(
            _parse_task_syslog(lines),
            dict(error=None, split=dict(
                path='s3://yourbucket/logs/2010/07/23/log2-00077.gz',
                start_line=None,
                num_lines=None)))

    def test_yarn_error(self):
        lines = [
            '2015-12-21 14:06:18,538 WARN [main]'
            ' org.apache.hadoop.mapred.YarnChild: Exception running child'
            ' : java.lang.RuntimeException: PipeMapRed.waitOutputThreads():'
            ' subprocess failed with code 1\n',
            '        at org.apache.hadoop.streaming.PipeMapRed'
            '.waitOutputThreads(PipeMapRed.java:322)\n',
            '        at org.apache.hadoop.streaming.PipeMapRed'
            '.mapRedFinished(PipeMapRed.java:535)\n',
        ]

        self.assertEqual(
            _parse_task_syslog(lines),
            dict(split=None, error=dict(
                exception=('java.lang.RuntimeException:'
                           ' PipeMapRed.waitOutputThreads():'
                           ' subprocess failed with code 1'),
                stack_trace=[
                    '        at org.apache.hadoop.streaming.PipeMapRed'
                    '.waitOutputThreads(PipeMapRed.java:322)',
                    '        at org.apache.hadoop.streaming.PipeMapRed'
                    '.mapRedFinished(PipeMapRed.java:535)',
                ])))

    def test_pre_yarn_error(self):
        lines = [
            '2015-12-30 19:21:39,980 WARN'
            ' org.apache.hadoop.mapred.Child (main): Error running child\n',
            'java.lang.RuntimeException: PipeMapRed.waitOutputThreads():'
            ' subprocess failed with code 1\n',
            '        at org.apache.hadoop.streaming.PipeMapRed'
            '.waitOutputThreads(PipeMapRed.java:372)\n',
        ]

        self.assertEqual(
            _parse_task_syslog(lines),
            dict(split=None, error=dict(
                exception=('java.lang.RuntimeException:'
                           ' PipeMapRed.waitOutputThreads():'
                           ' subprocess failed with code 1'),
                stack_trace=[
                    '        at org.apache.hadoop.streaming.PipeMapRed'
                    '.waitOutputThreads(PipeMapRed.java:372)',
                ])))



class ParsePythonTaskStderrTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(_parse_python_task_stderr([]),
                         dict(error=None))

    def test_exception(self):
        lines = [
            '+ python mr_boom.py --step-num=0 --mapper\n',
            'Traceback (most recent call last):\n',
            '  File "mr_boom.py", line 10, in <module>\n',
            '    MRBoom.run()\n',
            'Exception: BOOM\n',
        ]

        self.assertEqual(
            _parse_python_task_stderr(lines),
            dict(error=dict(
                exception='Exception: BOOM',
                traceback=[
                    'Traceback (most recent call last):',
                    '  File "mr_boom.py", line 10, in <module>',
                    '    MRBoom.run()',
                ])))


class ParsePreYARNHistoryFileTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(list(_parse_pre_yarn_history_file([])), [])

    def test_basic(self):
        lines = [
            'Meta VERSION="1" .\n',
            'Job JOBID="job_201601081945_0005" JOB_PRIORITY="NORMAL" .\n',
        ]
        self.assertEqual(
            list(_parse_pre_yarn_history_file(lines)),
            [
                dict(
                    fields=dict(
                        VERSION='1'
                    ),
                    start_line=0,
                    num_lines=1,
                    type='Meta',
                ),
                dict(
                    fields=dict(
                        JOBID='job_201601081945_0005',
                        JOB_PRIORITY='NORMAL'
                    ),
                    num_lines=1,
                    start_line=1,
                    type='Job',
                )
            ])

    def test_unescape(self):
        lines = [
            'Task TASKID="task_201512311928_0001_m_000003" TASK_TYPE="MAP"'
            ' START_TIME="1451590341378"'
            ' SPLITS="/default-rack/172\\.31\\.22\\.226" .\n',
        ]

        self.assertEqual(
            list(_parse_pre_yarn_history_file(lines)),
            [
                dict(
                    fields=dict(
                        TASKID='task_201512311928_0001_m_000003',
                        TASK_TYPE='MAP',
                        START_TIME='1451590341378',
                        SPLITS='/default-rack/172.31.22.226',
                    ),
                    num_lines=1,
                    start_line=0,
                    type='Task',
                ),
            ])

    def test_multiline(self):
        lines = [
            'MapAttempt TASK_TYPE="MAP"'
            ' TASKID="task_201601081945_0005_m_000001"'
            ' TASK_STATUS="FAILED"'
            ' ERROR="java\.lang\.RuntimeException:'
            ' PipeMapRed\.waitOutputThreads():'
            ' subprocess failed with code 1\n',
            '        at org\\.apache\\.hadoop\\.streaming\\.PipeMapRed'
            '\\.waitOutputThreads(PipeMapRed\\.java:372)\n',
            '        at org\\.apache\\.hadoop\\.streaming\\.PipeMapRed'
            '\\.mapRedFinished(PipeMapRed\\.java:586)\n',
            '" .\n',
        ]

        self.assertEqual(
            list(_parse_pre_yarn_history_file(lines)),
            [
                dict(
                    fields=dict(
                        ERROR=(
                            'java.lang.RuntimeException: PipeMapRed'
                            '.waitOutputThreads():'
                            ' subprocess failed with code 1\n'
                            '        at org.apache.hadoop.streaming.PipeMapRed'
                            '.waitOutputThreads(PipeMapRed.java:372)\n'
                            '        at org.apache.hadoop.streaming.PipeMapRed'
                            '.mapRedFinished(PipeMapRed.java:586)\n'),
                        TASK_TYPE='MAP',
                        TASKID='task_201601081945_0005_m_000001',
                        TASK_STATUS='FAILED',
                    ),
                    num_lines=4,
                    start_line=0,
                    type='MapAttempt',
                ),
            ])

    def test_bad_records(self):
        # should just silently ignore bad records and yield good ones
        lines = [
            '\n',
            'Foo BAZ .\n',
            'Job JOBID="job_201601081945_0005" JOB_PRIORITY="NORMAL" .\n',
            'Job JOBID="\n',
        ]

        self.assertEqual(
            list(_parse_pre_yarn_history_file(lines)),
            [
                dict(
                    fields=dict(
                        JOBID='job_201601081945_0005',
                        JOB_PRIORITY='NORMAL'
                    ),
                    num_lines=1,
                    start_line=2,
                    type='Job',
                )
            ])


class ParsePreYARNCountersTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(_parse_pre_yarn_counters(''), {})

    def test_basic(self):
        counter_str = (
            '{(org.apache.hadoop.mapred.JobInProgress$Counter)'
            '(Job Counters )'
            '[(TOTAL_LAUNCHED_REDUCES)(Launched reduce tasks)(1)]'
            '[(TOTAL_LAUNCHED_MAPS)(Launched map tasks)(2)]}'
            '{(FileSystemCounters)(FileSystemCounters)'
            '[(FILE_BYTES_READ)(FILE_BYTES_READ)(10547174)]}')

        self.assertEqual(
            _parse_pre_yarn_counters(counter_str), {
                'Job Counters ': {
                    'Launched reduce tasks': 1,
                    'Launched map tasks': 2,
                },
                'FileSystemCounters': {
                    'FILE_BYTES_READ': 10547174,
                },
            })

    def test_escape_sequences(self):
        counter_str = (
            r'{(\)\(\)\(\)\})(\)\(\)\(\)\})'
            r'[(\\)(\\)(1)]'
            r'[(\[\])(\[\])(2)]'
            r'[(\{\})(\{\})(3)]'
            r'[(\(\))(\(\))(4)]}')

        self.assertEqual(
            _parse_pre_yarn_counters(counter_str), {
                ')()()}': {
                    '\\': 1,
                    '[]': 2,
                    '{}': 3,
                    '()': 4,
                },
            })


class SummarizePreYARNHistoryFileTestCase(TestCase):

    def test_empty(self):
        self.assertEqual(
            _summarize_pre_yarn_history([]),
            dict(counters={}, errors=[]))

    def test_job_counters(self):
        lines = [
            'Job JOBID="job_201106092314_0003" FINISH_TIME="1307662284564"'
            ' JOB_STATUS="SUCCESS" FINISHED_MAPS="2" FINISHED_REDUCES="1"'
            ' FAILED_MAPS="0" FAILED_REDUCES="0" COUNTERS="'
            '{(org\.apache\.hadoop\.mapred\.JobInProgress$Counter)'
            '(Job Counters )'
            '[(TOTAL_LAUNCHED_REDUCES)(Launched reduce tasks)(1)]}" .\n'
        ]

        self.assertEqual(
            _summarize_pre_yarn_history(_parse_pre_yarn_history_file(lines)),
            dict(counters={'Job Counters ': {'Launched reduce tasks': 1}},
                 errors=[]))

    maxDiff = None

    def test_task_counters(self):
        lines = [
            'Task TASKID="task_201601081945_0005_m_000005" TASK_TYPE="SETUP"'
            ' TASK_STATUS="SUCCESS" FINISH_TIME="1452283612363"'
            ' COUNTERS="{(FileSystemCounters)(FileSystemCounters)'
            '[(FILE_BYTES_WRITTEN)(FILE_BYTES_WRITTEN)(27785)]}" .\n',
            'Task TASKID="task_201601081945_0005_m_000000" TASK_TYPE="MAP"'
            ' TASK_STATUS="SUCCESS" FINISH_TIME="1452283651437"'
            ' COUNTERS="{'
            '(org\.apache\.hadoop\.mapred\.FileOutputFormat$Counter)'
            '(File Output Format Counters )'
            '[(BYTES_WRITTEN)(Bytes Written)(0)]}'
            '{(FileSystemCounters)(FileSystemCounters)'
            '[(FILE_BYTES_WRITTEN)(FILE_BYTES_WRITTEN)(27785)]'
            '[(HDFS_BYTES_READ)(HDFS_BYTES_READ)(248)]}" .\n',
        ]

        self.assertEqual(
            _summarize_pre_yarn_history(_parse_pre_yarn_history_file(lines)),
            dict(
                counters={
                    'FileSystemCounters': {
                        'FILE_BYTES_WRITTEN': 55570,
                        'HDFS_BYTES_READ': 248,
                    },
                    'File Output Format Counters ': {
                        'Bytes Written': 0,
                        },
                },
                errors=[]))

    def test_errors(self):
        lines = [
            'MapAttempt TASK_TYPE="MAP"'
            ' TASKID="task_201601081945_0005_m_000001"'
            ' TASK_ATTEMPT_ID='
            '"task_201601081945_0005_m_00000_2"'
            ' TASK_STATUS="FAILED"'
            ' ERROR="java\.lang\.RuntimeException:'
            ' PipeMapRed\.waitOutputThreads():'
            ' subprocess failed with code 1\n',
            '        at org\\.apache\\.hadoop\\.streaming\\.PipeMapRed'
            '\\.waitOutputThreads(PipeMapRed\\.java:372)\n',
            '        at org\\.apache\\.hadoop\\.streaming\\.PipeMapRed'
            '\\.mapRedFinished(PipeMapRed\\.java:586)\n',
            '" .\n',
        ]

        path = '/history/history.jar'

        self.assertEqual(
            _summarize_pre_yarn_history(_parse_pre_yarn_history_file(lines),
                                        path=path),
            dict(
                counters={},
                errors=[
                    dict(
                        java_error=dict(
                            error=(
                                'java.lang.RuntimeException: PipeMapRed'
                                '.waitOutputThreads():'
                                ' subprocess failed with code 1\n'
                                '        at org.apache.hadoop.streaming'
                                '.PipeMapRed.waitOutputThreads'
                                '(PipeMapRed.java:372)\n'
                                '        at org.apache.hadoop.streaming'
                                '.PipeMapRed.mapRedFinished'
                                '(PipeMapRed.java:586)\n'),
                            num_lines=4,
                            path=path,
                            start_line=0,
                        ),
                        task_attempt_id='task_201601081945_0005_m_00000_2',
                    ),
                ]))
