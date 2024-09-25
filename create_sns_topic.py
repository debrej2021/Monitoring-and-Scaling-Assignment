import boto3
import json

# Initialize boto3 clients
sns_client = boto3.client('sns')
cloudwatch_client = boto3.client('cloudwatch')

# Step 1: Create SNS Topics for different alerts
def create_sns_topic(topic_name):
    """Create an SNS topic"""
    response = sns_client.create_topic(Name=topic_name)
    topic_arn = response['TopicArn']
    print(f"SNS Topic {topic_name} created with ARN: {topic_arn}")
    return topic_arn

# Step 2: Subscribe to SNS topics (email or SMS)
def subscribe_to_topic(topic_arn, protocol, endpoint):
    """Subscribe an email or SMS to the SNS topic"""
    response = sns_client.subscribe(
        TopicArn=topic_arn,
        Protocol=protocol,  # 'email' or 'sms'
        Endpoint=endpoint  # Email address or phone number
    )
    print(f"Subscription to {topic_arn} with {protocol} endpoint {endpoint} created.")
    return response

# Step 3: Publish SNS notifications
def send_sns_notification(topic_arn, subject, message):
    """Publish a message to the SNS topic"""
    response = sns_client.publish(
        TopicArn=topic_arn,
        Subject=subject,
        Message=message
    )
    print(f"Notification sent to {topic_arn} with message: {message}")
    return response

# Step 4: Create CloudWatch Alarm to trigger Lambda for high CPU usage
def create_cpu_utilization_alarm(instance_id, lambda_function_arn):
    """Create a CloudWatch Alarm for high CPU utilization"""
    cloudwatch_client.put_metric_alarm(
        AlarmName='HighCPUUtilization',
        MetricName='CPUUtilization',
        Namespace='AWS/EC2',
        Statistic='Average',
        Period=300,  # 5 minutes
        EvaluationPeriods=1,
        Threshold=80.0,  # Trigger alarm if CPU > 80%
        ComparisonOperator='GreaterThanThreshold',
        AlarmActions=[lambda_function_arn],  # ARN of your Lambda function
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance_id  # EC2 instance ID hardcoded
            },
        ],
    )
    print(f"CloudWatch Alarm for CPU utilization on instance {instance_id} created.")

# Hardcoded Setup Function
def setup_sns_and_cloudwatch():
    """Set up SNS topics, subscriptions, and CloudWatch alarms with hardcoded values"""

    # Step 1: Create SNS topics and store the ARNs
    health_topic_arn = create_sns_topic("HealthIssuesAlert-deb-sep25")
    scaling_topic_arn = create_sns_topic("ScalingEventsAlert-deb-sep25")
    traffic_topic_arn = create_sns_topic("HighTrafficAlert-deb-sep25")

    # Step 2: Subscribe to SNS topics with provided email and phone number
    subscribe_to_topic(health_topic_arn, 'email', 'debkiitian@gmail.com')  # Health alerts to email
    subscribe_to_topic(health_topic_arn, 'sms', '+919731429550')  # Health alerts to SMS

    subscribe_to_topic(scaling_topic_arn, 'email', 'debkiitian@gmail.com')  # Scaling alerts to email
    subscribe_to_topic(scaling_topic_arn, 'sms', '+919731429550')  # Scaling alerts to SMS

    subscribe_to_topic(traffic_topic_arn, 'email', 'debkiitian@gmail.com')  # Traffic alerts to email
    subscribe_to_topic(traffic_topic_arn, 'sms', '+919731429550')  # Traffic alerts to SMS

    # Step 4: Create a CloudWatch alarm to monitor CPU utilization
    instance_id = 'i-0eb03044b7278fb4f'  # EC2 instance ID hardcoded
    lambda_function_arn = 'arn:aws:lambda:us-west-2:975050024946:function:create_s3_deb_sept25'  # Lambda ARN hardcoded
    create_cpu_utilization_alarm(instance_id, lambda_function_arn)

    # Return the ARNs to use them in notifications
    return {
        'health': health_topic_arn,
        'scaling': scaling_topic_arn,
        'traffic': traffic_topic_arn
    }

# Hardcoded Notification Sending Function
def send_notifications(topic_arns):
    """Send hardcoded notifications for different alert types using actual topic ARNs"""

    # Hardcoded Instance ID
    instance_id = 'i-0eb03044b7278fb4f'  # EC2 instance ID hardcoded
    
    # Send Scaling Notification
    subject = 'Scaling Event Detected'
    message = f"An Auto Scaling event occurred on instance {instance_id}."
    send_sns_notification(topic_arns['scaling'], subject, message)

    # Send Health Notification
    subject = 'Health Issue Detected'
    message = f"Health check failure detected for instance {instance_id}."
    send_sns_notification(topic_arns['health'], subject, message)

    # Send High Traffic Notification
    subject = 'High Traffic Alert'
    message = f"High traffic detected on instance {instance_id}."
    send_sns_notification(topic_arns['traffic'], subject, message)

# Combined Setup and Notification Function (Hardcoded)
def lambda_handler(event, context):
    """Lambda function to set up SNS topics, subscriptions, CloudWatch alarms, and send notifications"""

    # Step 1: Set up SNS topics, subscriptions, and CloudWatch alarm (hardcoded)
    topic_arns = setup_sns_and_cloudwatch()

    # Step 2: Send hardcoded notifications using actual topic ARNs
    send_notifications(topic_arns)

    return {
        'statusCode': 200,
        'body': json.dumps("SNS topics, CloudWatch alarms, and notifications successfully set up and sent.")
    }
