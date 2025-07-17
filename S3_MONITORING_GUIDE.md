# Created: 2025-07-17 11:30:00
# Last Modified: 2025-07-17 11:22:54

# S3 Monitoring Guide for SurgiCase

This guide covers all methods to monitor S3 uploads and operations in the AWS console, plus integration with your existing Prometheus/Grafana monitoring stack.

## 🎯 Quick Start - AWS Console Monitoring

### 1. **Direct S3 Console Monitoring**

**Access your bucket:**
1. Go to [AWS S3 Console](https://console.aws.amazon.com/s3/)
2. Click on: `amplify-surgicalcasemanag-surgicaldocsbucket5a7ebd-8usdadqv6nnp`

**What you can monitor in real-time:**
- **Objects tab**: See all uploaded files instantly
- **Properties tab**: Check bucket settings, encryption, versioning
- **Management tab**: Lifecycle rules, replication settings
- **Permissions tab**: Bucket policies and access control

### 2. **CloudWatch S3 Metrics**

**Access CloudWatch:**
1. Go to [AWS CloudWatch Console](https://console.aws.amazon.com/cloudwatch/)
2. Navigate to **Metrics** → **S3** → **Bucket Metrics**

**Key metrics to monitor:**
- `PutRequests` - Number of upload operations
- `NumberOfObjects` - Total files in bucket
- `BucketSizeBytes` - Storage usage
- `4xxErrors`, `5xxErrors` - Upload failures
- `AllRequests` - Total requests (GET, PUT, DELETE)

**Create CloudWatch Dashboard:**
1. In CloudWatch → **Dashboards** → **Create dashboard**
2. Add widgets for S3 metrics
3. Set up alarms for error rates > 5%

### 3. **CloudTrail for Detailed API Logging**

**Enable CloudTrail (if not already):**
1. Go to [AWS CloudTrail Console](https://console.aws.amazon.com/cloudtrail/)
2. Create trail or check existing ones
3. Ensure S3 events are logged

**What CloudTrail shows:**
- All S3 API calls with timestamps
- User/role that made the request
- IP address of the requester
- Request parameters and response codes
- Object keys and bucket names

**Filter CloudTrail logs:**
```sql
-- Example CloudWatch Insights query
fields @timestamp, @message
| filter @message like /s3.amazonaws.com/
| filter @message like /PutObject/
| sort @timestamp desc
| limit 100
```

### 4. **S3 Access Logging**

**Enable access logging:**
1. In S3 Console → Your bucket → **Properties**
2. **Server access logging** → Enable
3. Choose target bucket for logs

**Logs include:**
- Request timestamp
- Requester IP
- Request type (PUT for uploads)
- Object key
- Response status
- Bytes transferred

## 🔧 Integration with Existing Monitoring Stack

### **Using the S3 Monitoring Module**

The project includes `utils/s3_monitoring.py` that integrates S3 operations with your existing Prometheus/Grafana monitoring.

**Basic usage:**
```python
from utils.s3_monitoring import S3Monitor

# Record upload success
S3Monitor.record_upload_operation(
    success=True, 
    file_type="provider-payment", 
    file_size=1024000, 
    duration=2.5
)

# Record upload failure
S3Monitor.record_upload_operation(
    success=False, 
    file_type="provider-payment"
)
```

**Using the decorator:**
```python
from utils.s3_monitoring import monitor_s3_operation

@monitor_s3_operation("upload")
def upload_report(file_path, s3_key):
    # Your upload logic here
    pass
```

### **Grafana Dashboard Integration**

**Add S3 panels to your existing dashboard:**

1. **S3 Upload Success Rate:**
   ```
   rate(utility_operations_total{operation=~"s3_upload.*"}[5m])
   ```

2. **S3 Upload Duration:**
   ```
   histogram_quantile(0.95, rate(utility_operations_total{operation="s3_upload_duration"}[5m]))
   ```

3. **S3 Errors:**
   ```
   rate(utility_operations_total{operation=~"s3_.*", status="failure"}[5m])
   ```

4. **File Type Distribution:**
   ```
   sum by (operation) (rate(utility_operations_total{operation=~"s3_upload_.*"}[5m]))
   ```

## 📊 Monitoring Alerts

### **CloudWatch Alarms**

**Create alarms for:**
1. **High Error Rate**: >10% S3 errors for 5 minutes
2. **High Upload Latency**: >5 seconds average upload time
3. **Bucket Size**: >80% of storage limit
4. **Access Denied**: Any 403 errors

**Example CloudWatch Alarm:**
```yaml
AlarmName: S3-High-Error-Rate
MetricName: 5xxError
Namespace: AWS/S3
Statistic: Sum
Period: 300
EvaluationPeriods: 2
Threshold: 5
ComparisonOperator: GreaterThanThreshold
```

### **Prometheus/Grafana Alerts**

**Add to `monitoring/prometheus/alerts.yml`:**
```yaml
- alert: S3UploadErrors
  expr: rate(utility_operations_total{operation=~"s3_upload.*", status="failure"}[5m]) > 0.1
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "S3 upload error rate is high"
    description: "S3 upload failures detected"

- alert: S3UploadLatency
  expr: histogram_quantile(0.95, rate(utility_operations_total{operation="s3_upload_duration"}[5m])) > 5
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "S3 upload latency is high"
    description: "95th percentile upload time exceeds 5 seconds"
```

## 🔍 Troubleshooting S3 Issues

### **Common Issues and Solutions**

1. **Upload Failures:**
   - Check IAM permissions
   - Verify bucket exists and is accessible
   - Check file size limits
   - Verify encryption settings

2. **Slow Uploads:**
   - Check network connectivity
   - Monitor CloudWatch metrics
   - Consider multipart uploads for large files
   - Check S3 region proximity

3. **Access Denied:**
   - Review bucket policies
   - Check IAM roles and permissions
   - Verify user/role has S3 access
   - Check VPC endpoints if applicable

### **Debug Commands**

**Test S3 connectivity:**
```bash
# Test with AWS CLI
aws s3 ls s3://your-bucket-name/

# Test upload
aws s3 cp test.txt s3://your-bucket-name/test.txt

# Check bucket policy
aws s3api get-bucket-policy --bucket your-bucket-name
```

**Check CloudTrail logs:**
```bash
# List recent S3 events
aws logs filter-log-events \
  --log-group-name CloudTrail/DefaultLogGroup \
  --filter-pattern "s3.amazonaws.com" \
  --start-time $(date -d '1 hour ago' +%s)000
```

## 📈 Performance Optimization

### **Best Practices**

1. **Use Multipart Uploads** for files > 100MB
2. **Enable Transfer Acceleration** for faster uploads
3. **Use S3 Intelligent Tiering** for cost optimization
4. **Implement retry logic** with exponential backoff
5. **Monitor and alert** on performance metrics

### **Cost Monitoring**

**Track S3 costs:**
1. **AWS Cost Explorer** → S3 service
2. **CloudWatch Billing Alarms**
3. **S3 Storage Lens** for organization-wide view

**Cost optimization:**
- Use appropriate storage classes
- Implement lifecycle policies
- Monitor and clean up unused objects
- Use S3 Analytics for access patterns

## 🚀 Next Steps

1. **Enable CloudTrail** for comprehensive logging
2. **Set up CloudWatch alarms** for critical metrics
3. **Add S3 panels** to your Grafana dashboard
4. **Implement the S3 monitoring module** in your upload functions
5. **Create automated cleanup** for old test files
6. **Set up cost alerts** to monitor S3 spending

## 📞 Support

For S3 monitoring issues:
1. Check AWS CloudWatch logs
2. Review CloudTrail events
3. Verify IAM permissions
4. Test with AWS CLI
5. Check the main SurgiCase monitoring documentation 