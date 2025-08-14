# CloudWatch Agent Permissions Fix

## Issue
The CloudWatch agent cannot send memory metrics because the EC2 instance role lacks CloudWatch permissions.

**Error:**
```
AccessDenied: User: arn:aws:sts::002118831669:assumed-role/ec2-secrets-role/i-099fb57644b0c33ba 
is not authorized to perform: cloudwatch:PutMetricData
```

## Solution

### AWS Console Method (Recommended)

1. **Open AWS IAM Console**
   - Go to: https://console.aws.amazon.com/iam/

2. **Find the Role**
   - Click "Roles" in the left sidebar
   - Search for: `ec2-secrets-role`
   - Click on the role name

3. **Add CloudWatch Policy**
   - Click "Attach policies"
   - Search for: `CloudWatchAgentServerPolicy`
   - Check the box next to it
   - Click "Attach policy"

### AWS CLI Method

```bash
# Attach the CloudWatch agent policy to the EC2 role
aws iam attach-role-policy \
    --role-name ec2-secrets-role \
    --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
```

### Custom Policy Method (Alternative)

If you prefer minimal permissions, create a custom policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cloudwatch:PutMetricData",
                "logs:PutLogEvents",
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:DescribeLogStreams"
            ],
            "Resource": "*"
        }
    ]
}
```

## Verification

After adding permissions:

1. **Restart CloudWatch Agent**
   ```bash
   sudo systemctl restart amazon-cloudwatch-agent
   ```

2. **Check Logs**
   ```bash
   sudo tail -f /opt/aws/amazon-cloudwatch-agent/logs/amazon-cloudwatch-agent.log
   ```

3. **Wait 5-10 minutes** then test memory metrics:
   ```bash
   python tests/ec2_monitoring_script.py
   ```

## Expected Result

Once permissions are fixed:
- ✅ Memory metrics will appear in CloudWatch
- ✅ Monitoring script will show memory utilization
- ✅ No more permission errors in logs

## Timeline

- **Immediate**: Permission errors stop
- **5-10 minutes**: Memory metrics start appearing
- **Next monitoring cycle**: Script shows memory data
