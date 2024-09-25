import boto3
import json

# Initialize boto3 clients
ec2_client = boto3.client('ec2')
sns_client = boto3.client('sns')
cloudwatch_client = boto3.client('cloudwatch')
elb_client = boto3.client('elbv2')
asg_client = boto3.client('autoscaling')
s3_client = boto3.client('s3')

# Infrastructure Parameters
key_name = 'deb-key-pair-sept25'
instance_type = 't2.micro'
ami_id = 'ami-08d8ac128e0a1b91c'
subnet_ids = ['subnet-0fd07baca9b6e64fa', 'subnet-1fd07baca9b6e64fb']  # Replace with your subnet IDs in different AZs
security_group_id = 'sg-0ae83dc5b0560641b'
bucket_name = 'your-webapp-static-files-deb-sep251'
alb_name = 'deb-alb-sep25'
target_group_name = 'Deb-target-group-sep25'
auto_scaling_group_name = 'Deb-auto-scaling-group-sep25'
launch_template_name = 'Deb-launch-template-sep25'
alarm_name = 'HighCPUUtilization-deb-sept25'
lambda_function_arn = 'arn:aws:lambda:us-west-2:975050024946:function:create_s3_deb_sept25'

# Hardcoded email and phone number
email = 'debkiitian@gmail.com'
phone_number = '+919731429550'

# Multiple SNS Topics
sns_topics = {
    "HealthIssuesAlert-deb-sep252": {
        "email": email,
        "sms": phone_number
    },
    "ScalingEventsAlert-deb-sep252": {
        "email": email,
        "sms": phone_number
    },
    "HighTrafficAlert-deb-sep25-2": {
        "email": email,
        "sms": phone_number
    }
}

### DEPLOY INFRASTRUCTURE ###

def create_s3_bucket():
    """Create an S3 bucket to store web app static files"""
    region = 'us-west-2'
    try:
        response = s3_client.head_bucket(Bucket=bucket_name)
        print(f"S3 bucket '{bucket_name}' already exists.")
    except:
        try:
            if region == 'us-east-1':
                s3_client.create_bucket(Bucket=bucket_name)
            else:
                s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={
                        'LocationConstraint': region
                    }
                )
            print(f"S3 bucket '{bucket_name}' created in region {region}.")
        except Exception as e:
            print(f"Error creating S3 bucket: {e}")

def find_ec2_instance_by_name(instance_name):
    """Check if an EC2 instance with the given name exists"""
    filters = [{'Name': 'tag:Name', 'Values': [instance_name]}]
    instances = ec2_client.describe_instances(Filters=filters)
    if instances['Reservations']:
        instance_id = instances['Reservations'][0]['Instances'][0]['InstanceId']
        instance_state = instances['Reservations'][0]['Instances'][0]['State']['Name']
        print(f"Found existing EC2 instance with ID {instance_id} in state {instance_state}.")
        return instance_id, instance_state
    return None, None

def deploy_ec2_instance():
    """Deploy an EC2 instance and wait until it's in running state."""
    instance_id, instance_state = find_ec2_instance_by_name('MyAppInstance')
    
    if instance_id and instance_state == 'running':
        print(f"EC2 instance with ID {instance_id} is already running.")
        return instance_id
    elif instance_id and instance_state != 'terminated':
        print(f"Waiting for EC2 instance {instance_id} to reach running state...")
        ec2_client.get_waiter('instance_running').wait(InstanceIds=[instance_id])
        print(f"EC2 instance {instance_id} is now running.")
        return instance_id
    else:
        print("Launching new EC2 instance...")
        instances = ec2_client.run_instances(
            ImageId=ami_id,
            InstanceType=instance_type,
            KeyName=key_name,
            MinCount=1,
            MaxCount=1,
            NetworkInterfaces=[
                {
                    'SubnetId': subnet_ids[0],
                    'DeviceIndex': 0,
                    'AssociatePublicIpAddress': True,
                    'Groups': [security_group_id]
                }
            ],
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'Name', 'Value': 'MyAppInstance'}]
                }
            ],
            UserData="""#!/bin/bash
            sudo yum update -y
            sudo yum install -y httpd
            sudo systemctl start httpd
            sudo systemctl enable httpd
            echo "Hello from WebApp" > /var/www/html/index.html
            """
        )
        instance_id = instances['Instances'][0]['InstanceId']
        print(f"New EC2 instance launched with ID: {instance_id}")

        # Wait for the instance to enter running state
        print(f"Waiting for EC2 instance {instance_id} to reach running state...")
        ec2_client.get_waiter('instance_running').wait(InstanceIds=[instance_id])
        print(f"EC2 instance {instance_id} is now running.")
        return instance_id

def create_application_load_balancer():
    """Create an Application Load Balancer (ALB)"""
    response = elb_client.describe_load_balancers(Names=[alb_name])
    if response['LoadBalancers']:
        alb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
        print(f"ALB '{alb_name}' already exists with ARN: {alb_arn}")
        return alb_arn
    else:
        response = elb_client.create_load_balancer(
            Name=alb_name,
            Subnets=subnet_ids,
            SecurityGroups=[security_group_id],
            Scheme='internet-facing',
            Type='application',
            IpAddressType='ipv4'
        )
        alb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
        print(f"ALB created with ARN: {alb_arn}")
        return alb_arn

def create_target_group(vpc_id):
    """Create a Target Group for the ALB"""
    response = elb_client.describe_target_groups(Names=[target_group_name])
    if response['TargetGroups']:
        target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
        print(f"Target Group '{target_group_name}' already exists with ARN: {target_group_arn}")
        return target_group_arn
    else:
        response = elb_client.create_target_group(
            Name=target_group_name,
            Protocol='HTTP',
            Port=80,
            VpcId=vpc_id,
            TargetType='instance',
            HealthCheckProtocol='HTTP',
            HealthCheckPath='/'
        )
        target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
        print(f"Target Group created with ARN: {target_group_arn}")
        return target_group_arn

def register_targets(target_group_arn, instance_id):
    """Register EC2 instances with the Target Group"""
    response = elb_client.describe_target_health(TargetGroupArn=target_group_arn)
    targets = [target['Target']['Id'] for target in response['TargetHealthDescriptions']]
    
    if instance_id in targets:
        print(f"EC2 instance {instance_id} is already registered with Target Group {target_group_arn}.")
    else:
        elb_client.register_targets(
            TargetGroupArn=target_group_arn,
            Targets=[{'Id': instance_id}]
        )
        print(f"EC2 instance {instance_id} registered with Target Group {target_group_arn}")

def create_listener(alb_arn, target_group_arn):
    """Create a listener for the ALB"""
    response = elb_client.describe_listeners(LoadBalancerArn=alb_arn)
    if response['Listeners']:
        print(f"Listener already exists for ALB {alb_arn}.")
    else:
        elb_client.create_listener(
            LoadBalancerArn=alb_arn,
            Protocol='HTTP',
            Port=80,
            DefaultActions=[{'Type': 'forward', 'TargetGroupArn': target_group_arn}]
        )
        print(f"Listener created for ALB {alb_arn}")

def create_launch_template():
    """Create a launch template for the ASG"""
    response = ec2_client.describe_launch_templates(LaunchTemplateNames=[launch_template_name])
    if response['LaunchTemplates']:
        template_id = response['LaunchTemplates'][0]['LaunchTemplateId']
        print(f"Launch template '{launch_template_name}' already exists with ID: {template_id}")
        return template_id
    else:
        response = ec2_client.create_launch_template(
            LaunchTemplateName=launch_template_name,
            LaunchTemplateData={
                'ImageId': ami_id,
                'InstanceType': instance_type,
                'KeyName': key_name,
                'NetworkInterfaces': [
                    {
                        'SubnetId': subnet_ids[0],
                        'DeviceIndex': 0,
                        'AssociatePublicIpAddress': True,
                        'Groups': [security_group_id]
                    }
                ],
                'UserData': """#!/bin/bash
                sudo yum update -y
                sudo yum install -y httpd
                sudo systemctl start httpd
                sudo systemctl enable httpd
                echo "Hello from WebApp" > /var/www/html/index.html
                """
            }
        )
        template_id = response['LaunchTemplate']['LaunchTemplateId']
        print(f"Launch template created with ID: {template_id}")
        return template_id

def create_auto_scaling_group(template_id, target_group_arn):
    """Create an Auto Scaling Group (ASG)"""
    response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[auto_scaling_group_name])
    if response['AutoScalingGroups']:
        print(f"Auto Scaling Group '{auto_scaling_group_name}' already exists.")
    else:
        asg_client.create_auto_scaling_group(
            AutoScalingGroupName=auto_scaling_group_name,
            LaunchTemplate={'LaunchTemplateId': template_id},
            MinSize=1,
            MaxSize=3,
            DesiredCapacity=1,
            TargetGroupARNs=[target_group_arn],
            VPCZoneIdentifier=",".join(subnet_ids)
        )
        print(f"Auto Scaling Group '{auto_scaling_group_name}' created.")

# Tear Down Infrastructure

def terminate_ec2_instances():
    """Terminate EC2 Instances"""
    print("Terminating EC2 instances...")
    response = ec2_client.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': ['MyAppInstance']}])
    instance_ids = [instance['InstanceId'] for reservation in response['Reservations'] for instance in reservation['Instances']]
    if instance_ids:
        ec2_client.terminate_instances(InstanceIds=instance_ids)
        print(f"Terminated EC2 instances: {instance_ids}")
    else:
        print("No EC2 instances found.")

def delete_load_balancer():
    """Delete the Application Load Balancer (ALB)"""
    print(f"Deleting ALB '{alb_name}'...")
    response = elb_client.describe_load_balancers(Names=[alb_name])
    if response['LoadBalancers']:
        alb_arn = response['LoadBalancers'][0]['LoadBalancerArn']
        elb_client.delete_load_balancer(LoadBalancerArn=alb_arn)
        print(f"ALB '{alb_name}' deleted.")
    else:
        print(f"ALB '{alb_name}' not found.")

def delete_target_group():
    """Delete the Target Group associated with the ALB"""
    print(f"Deleting Target Group '{target_group_name}'...")
    response = elb_client.describe_target_groups(Names=[target_group_name])
    if response['TargetGroups']:
        target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
        elb_client.delete_target_group(TargetGroupArn=target_group_arn)
        print(f"Target Group '{target_group_name}' deleted.")
    else:
        print(f"Target Group '{target_group_name}' not found.")

def delete_auto_scaling_group():
    """Delete the Auto Scaling Group"""
    print(f"Deleting Auto Scaling Group '{auto_scaling_group_name}'...")
    response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[auto_scaling_group_name])
    if response['AutoScalingGroups']:
        asg_client.delete_auto_scaling_group(AutoScalingGroupName=auto_scaling_group_name, ForceDelete=True)
        print(f"Auto Scaling Group '{auto_scaling_group_name}' deleted.")
    else:
        print(f"Auto Scaling Group '{auto_scaling_group_name}' not found.")

def delete_launch_template():
    """Delete the Launch Template"""
    print(f"Deleting Launch Template '{launch_template_name}'...")
    response = ec2_client.describe_launch_templates(LaunchTemplateNames=[launch_template_name])
    if response['LaunchTemplates']:
        ec2_client.delete_launch_template(LaunchTemplateName=launch_template_name)
        print(f"Launch Template '{launch_template_name}' deleted.")
    else:
        print(f"Launch Template '{launch_template_name}' not found.")

def delete_s3_bucket():
    """Delete the S3 bucket and its contents"""
    print(f"Deleting S3 bucket '{bucket_name}'...")
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        if 'Contents' in response:
            objects = [{'Key': obj['Key']} for obj in response['Contents']]
            s3_client.delete_objects(Bucket=bucket_name, Delete={'Objects': objects})
            print(f"Deleted all objects in bucket {bucket_name}")
        s3_client.delete_bucket(Bucket=bucket_name)
        print(f"S3 bucket '{bucket_name}' deleted.")
    except Exception as e:
        print(f"Error deleting S3 bucket '{bucket_name}': {e}")

def tear_down_infrastructure():
    """Tear down the full infrastructure"""
    
    # 1. Terminate EC2 Instances
    terminate_ec2_instances()
    
    # 2. Delete Load Balancer and Target Group
    delete_load_balancer()
    delete_target_group()

    # 3. Delete Auto Scaling Group and Launch Template
    delete_auto_scaling_group()
    delete_launch_template()

    # 4. Delete S3 Bucket
    delete_s3_bucket()

def deploy_full_infrastructure():
    """Deploy the entire infrastructure"""
    create_s3_bucket()
    ec2_instance_id = deploy_ec2_instance()
    alb_arn = create_application_load_balancer()
    target_group_arn = create_target_group(vpc_id=subnet_ids[0])
    register_targets(target_group_arn, ec2_instance_id)
    create_listener(alb_arn, target_group_arn)
    launch_template_id = create_launch_template()
    create_auto_scaling_group(launch_template_id, target_group_arn)

def update_infrastructure(new_ami_id=None):
    """Update components of the infrastructure"""
    instance_id, instance_state = find_ec2_instance_by_name('MyAppInstance')
    
    if new_ami_id:
        if instance_id and instance_state == 'running':
            update_ec2_instance(instance_id, new_ami_id)

    print("Infrastructure updated.")

### LAMBDA HANDLER ###

def lambda_handler(event, context):
    action = event.get('action', 'deploy')  # Default action is 'deploy'
    
    if action == 'deploy':
        deploy_full_infrastructure()
        return {
            'statusCode': 200,
            'body': json.dumps("Infrastructure deployed successfully.")
        }
    elif action == 'update':
        new_ami_id = event.get('new_ami_id', None)  # Update with new AMI if provided
        update_infrastructure(new_ami_id=new_ami_id)
        return {
            'statusCode': 200,
            'body': json.dumps("Infrastructure updated successfully.")
        }
    elif action == 'teardown':
        tear_down_infrastructure()
        return {
            'statusCode': 200,
            'body': json.dumps("Infrastructure torn down successfully.")
        }
    else:
        return {
            'statusCode': 400,
            'body': json.dumps("Invalid action. Use 'deploy', 'update', or 'teardown'.")
        }
