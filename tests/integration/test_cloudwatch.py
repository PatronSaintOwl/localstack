import unittest
import gzip
from localstack.utils.aws import aws_stack
from datetime import datetime, timedelta
from dateutil.tz import tzutc
from localstack.utils.common import short_uid
from localstack import config
from six.moves.urllib.request import Request, urlopen


class CloudWatchTest(unittest.TestCase):

    def test_put_metric_data(self):
        metric_name = 'metric-%s' % short_uid()
        namespace = 'namespace-%s' % short_uid()

        client = aws_stack.connect_to_service('cloudwatch')

        # Put metric data without value
        data = [
            {
                'MetricName': metric_name,
                'Dimensions': [{
                    'Name': 'foo',
                    'Value': 'bar'
                }],
                'Timestamp': datetime(2019, 1, 3, tzinfo=tzutc()),
                'Unit': 'Seconds'
            }
        ]
        rs = client.put_metric_data(
            Namespace=namespace,
            MetricData=data
        )
        self.assertEquals(rs['ResponseMetadata']['HTTPStatusCode'], 200)

        # Get metric statistics
        rs = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            StartTime=datetime(2019, 1, 1),
            EndTime=datetime(2019, 1, 10),
            Period=120,
            Statistics=[
                'Average'
            ]
        )
        self.assertEqual(rs['Label'], metric_name)
        self.assertEqual(len(rs['Datapoints']), 1)
        self.assertEqual(rs['Datapoints'][0]['Timestamp'], data[0]['Timestamp'])

        rs = client.list_metrics(
            Namespace=namespace,
            MetricName=metric_name
        )
        self.assertEqual(len(rs['Metrics']), 1)
        self.assertEqual(rs['Metrics'][0]['Namespace'], namespace)

    def test_put_metric_data_gzip(self):
        metric_name = 'test-metric'
        namespace = 'namespace'
        data = 'Action=PutMetricData&MetricData.member.1.' \
            'MetricName=%s&MetricData.member.1.Value=1&' \
            'Namespace=%s&Version=2010-08-01' \
            % (metric_name, namespace)
        bytes_data = bytes(data, encoding='utf-8')
        encoded_data = gzip.compress(bytes_data)

        url = config.get_edge_url()
        headers = aws_stack.mock_aws_request_headers('cloudwatch')

        authorization = 'AWS4-HMAC-SHA256 Credential=test/20201230/' \
            'us-east-1/monitoring/aws4_request, ' \
            'SignedHeaders=content-encoding;host;' \
            'x-amz-content-sha256;x-amz-date, Signature='\
            'bb31fc5f4e58040ede9ed751133fe'\
            '839668b27290bc1406b6ffadc4945c705dc'

        headers.update({
            'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
            'Content-Length': len(encoded_data),
            'Content-Encoding': 'GZIP',
            'User-Agent': 'aws-sdk-nodejs/2.819.0 linux/v12.18.2 callback',
            'Authorization': authorization,
        })
        request = Request(url, encoded_data, headers, method='POST')
        urlopen(request)

        client = aws_stack.connect_to_service('cloudwatch')
        rs = client.list_metrics(
            Namespace=namespace,
            MetricName=metric_name
        )
        self.assertEqual(len(rs['Metrics']), 1)
        self.assertEqual(rs['Metrics'][0]['Namespace'], namespace)

    def test_get_metric_data(self):

        conn = aws_stack.connect_to_service('cloudwatch')

        conn.put_metric_data(
            Namespace='some/thing', MetricData=[dict(MetricName='someMetric', Value=23)]
        )
        conn.put_metric_data(
            Namespace='some/thing', MetricData=[dict(MetricName='someMetric', Value=18)]
        )
        conn.put_metric_data(
            Namespace='ug/thing', MetricData=[dict(MetricName='ug', Value=23)]
        )

        # filtering metric data with current time interval
        response = conn.get_metric_data(
            MetricDataQueries=[{'Id': 'some', 'MetricStat': {'Metric':
                {'Namespace': 'some/thing', 'MetricName': 'someMetric'}, 'Period': 60, 'Stat': 'Sum'}},
                {'Id': 'part', 'MetricStat': {'Metric': {'Namespace': 'ug/thing', 'MetricName': 'ug'},
                'Period': 60, 'Stat': 'Sum'}}],
            StartTime=datetime.utcnow() - timedelta(hours=1),
            EndTime=datetime.utcnow(),
        )

        self.assertEquals(len(response['MetricDataResults']), 2)

        for data_metric in response['MetricDataResults']:
            if data_metric['Id'] == 'some':
                self.assertEquals(data_metric['Values'][0], 41.0)
            if data_metric['Id'] == 'part':
                self.assertEquals(data_metric['Values'][0], 23.0)

        # filtering metric data with current time interval
        response = conn.get_metric_data(
            MetricDataQueries=[{'Id': 'some', 'MetricStat': {'Metric':
                {'Namespace': 'some/thing', 'MetricName': 'someMetric'}, 'Period': 60, 'Stat': 'Sum'}},
                {'Id': 'part', 'MetricStat': {'Metric': {'Namespace': 'ug/thing', 'MetricName': 'ug'},
                'Period': 60, 'Stat': 'Sum'}}],
            StartTime=datetime.utcnow() + timedelta(hours=1),
            EndTime=datetime.utcnow() + timedelta(hours=2),
        )

        for data_metric in response['MetricDataResults']:
            if data_metric['Id'] == 'some':
                self.assertEquals(len(data_metric['Values']), 0)
            if data_metric['Id'] == 'part':
                self.assertEquals(len(data_metric['Values']), 0)
