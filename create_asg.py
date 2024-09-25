import json
import boto3
from botocore.exceptions import ClientError

# Initialize boto3 clients
ec2_client = boto3.client('ec2')
autoscaling_client = boto3.client('autoscaling')
cloudwatch_client = boto3.client('cloudwatch')

def create_launch_template_from_instance(instance_id, key_name, template_name="my-launch-template"):
    """Creates a Launch Template from an existing EC2 instance"""
    try:
        # Describe the instance to retrieve necessary details
        instance_description = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance_data = instance_description['Reservations'][0]['Instances'][0]

        # Get security group IDs
        security_group_ids = [sg['GroupId'] for sg in instance_data['SecurityGroups']]

        # Filter BlockDeviceMappings to include only valid parameters, excluding 'None' values
        filtered_block_device_mappings = []
        for block_device in instance_data.get('BlockDeviceMappings', []):
            if 'Ebs' in block_device:
                ebs_data = {
                    'DeleteOnTermination': block_device['Ebs'].get('DeleteOnTermination'),
                    'Iops': block_device['Ebs'].get('Iops'),
                    'SnapshotId': block_device['Ebs'].get('SnapshotId'),
                    'VolumeSize': block_device['Ebs'].get('VolumeSize'),
                    'VolumeType': block_device['Ebs'].get('VolumeType'),
                    'Encrypted': block_device['Ebs'].get('Encrypted'),
                    'KmsKeyId': block_device['Ebs'].get('KmsKeyId'),
                    'Throughput': block_device['Ebs'].get('Throughput')
                }
                
                # Remove any parameters that have a None value
                filtered_ebs_data = {k: v for k, v in ebs_data.items() if v is not None}
                
                if filtered_ebs_data:
                    filtered_mapping = {
                        'DeviceName': block_device['DeviceName'],
                        'Ebs': filtered_ebs_data
                    }
                    filtered_block_device_mappings.append(filtered_mapping)

        # Create a Launch Template using the instance details and KeyName
        response = ec2_client.create_launch_template(
            LaunchTemplateName=template_name,
            VersionDescription='Template created from existing EC2 instance',
            LaunchTemplateData={
                'InstanceType': instance_data['InstanceType'],
                'ImageId': instance_data['ImageId'],
                'KeyName': key_name,  # Specify the key pair name here
                'BlockDeviceMappings': filtered_block_device_mappings,
                'NetworkInterfaces': [{
                    'DeviceIndex': 0,
                    'SubnetId': instance_data['SubnetId'],
                    'AssociatePublicIpAddress': True,
                    'Groups': security_group_ids  # Add security group IDs here
                }],
                'TagSpecifications': [{
                    'ResourceType': 'instance',
                    'Tags': instance_data['Tags']
                }]
            }
        )
        
        launch_template_id = response['LaunchTemplate']['LaunchTemplateId']
        print(f"Launch Template created with ID: {launch_template_id}")
        return launch_template_id
    except ClientError as e:
        print(f"Error creating launch template: {e}")
        raise

def create_auto_scaling_group(launch_template_id, asg_name, vpc_zone_identifier):
    """Creates an Auto Scaling Group (ASG)"""
    try:
        response = autoscaling_client.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            LaunchTemplate={
                'LaunchTemplateId': launch_template_id,
                'Version': '$Latest'
            },
            MinSize=1,
            MaxSize=3,  # Adjust based on your scaling requirements
            DesiredCapacity=1,
            VPCZoneIdentifier=vpc_zone_identifier,  # Comma-separated subnet IDs
            HealthCheckType='EC2',
            HealthCheckGracePeriod=300
        )
        print(f"Auto Scaling Group '{asg_name}' created.")
    except ClientError as e:
        print(f"Error creating Auto Scaling Group: {e}")
        raise

def create_scaling_policy(asg_name, policy_name, metric_type="CPUUtilization"):
    """Creates a scaling policy based on CPU utilization or NetworkIn"""
    try:
        if metric_type == "CPUUtilization":
            metric = {
                'MetricName': 'CPUUtilization',
                'Namespace': 'AWS/EC2'
            }
        elif metric_type == "NetworkIn":
            metric = {
                'MetricName': 'NetworkIn',
                'Namespace': 'AWS/EC2'
            }

        # Create CloudWatch alarm for scaling out (high CPU or network traffic)
        cloudwatch_client.put_metric_alarm(
            AlarmName=f'{policy_name}-scale-out',
            MetricName=metric['MetricName'],
            Namespace=metric['Namespace'],
            Statistic='Average',
            Period=300,  # Check every 5 minutes
            EvaluationPeriods=1,
            Threshold=70.0,  # Example: Scale out if CPU > 70%
            ComparisonOperator='GreaterThanThreshold',
            AlarmActions=[],  # Add action if needed (SNS, etc.)
            Dimensions=[{
                'Name': 'AutoScalingGroupName',
                'Value': asg_name
            }]
        )

        # Create CloudWatch alarm for scaling in (low CPU or network traffic)
        cloudwatch_client.put_metric_alarm(
            AlarmName=f'{policy_name}-scale-in',
            MetricName=metric['MetricName'],
            Namespace=metric['Namespace'],
            Statistic='Average',
            Period=300,
            EvaluationPeriods=1,
            Threshold=30.0,  # Example: Scale in if CPU < 30%
            ComparisonOperator='LessThanThreshold',
            AlarmActions=[],  # Add action if needed
            Dimensions=[{
                'Name': 'AutoScalingGroupName',
                'Value': asg_name
            }]
        )

        print(f"CloudWatch alarms created for scaling based on {metric['MetricName']}.")
    except ClientError as e:
        print(f"Error creating scaling policy: {e}")
        raise

def lambda_handler(event, context):
    """Lambda function handler to create ASG with scaling policies"""
    try:
        # Replace with actual details or extract from the event
        instance_id = 'i-0eb03044b7278fb4f'  # Provided EC2 instance ID
        asg_name = 'Deb-auto-scaling-group-sep25'  # Provided Auto Scaling Group name
        vpc_zone_identifier = 'subnet-0fd07baca9b6e64fa,subnet-065776c35c7785b4d'  # Provided VPC subnets
        policy_name = 'deb-scaling-policy-sept25'  # Provided scaling policy name
        key_name = 'deb-key-pair-sept25'  # Provided EC2 key pair name
        
        # Define the launch template name here
        launch_template_name = 'Deb-launch-template-sep25-02'

        # Step 1: Create Launch Template from existing EC2 instance
        launch_template_id = create_launch_template_from_instance(instance_id, key_name, launch_template_name)
        
        # Step 2: Create Auto Scaling Group (ASG)
        create_auto_scaling_group(launch_template_id, asg_name, vpc_zone_identifier)
        
        # Step 3: Create scaling policies based on CPU utilization
        create_scaling_policy(asg_name, policy_name, metric_type="CPUUtilization")
        
        return {
            'statusCode': 200,
            'body': json.dumps("Auto Scaling Group and scaling policies successfully created.")
        }
    except ClientError as e:
        return {
            'statusCode': 400,
            'body': json.dumps(f"Error: {str(e)}")
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"Unexpected error: {str(e)}")
        }
