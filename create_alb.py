import json
import boto3
from botocore.exceptions import ClientError

# Initialize boto3 clients
ec2_client = boto3.client('ec2')
elbv2_client = boto3.client('elbv2')

def create_alb(vpc_id, subnet_ids, security_group_id, alb_name="deb-alb-sep25"):
    """Creates an Application Load Balancer (ALB)"""
    try:
        # Create the Application Load Balancer
        response = elbv2_client.create_load_balancer(
            Name=alb_name,
            Subnets=subnet_ids,
            SecurityGroups=[security_group_id],
            Scheme='internet-facing',  # Use 'internal' for internal ALB
            Tags=[{'Key': 'Name', 'Value': alb_name}],
            Type='application',  # ALB type
            IpAddressType='ipv4'
        )
        
        load_balancer_arn = response['LoadBalancers'][0]['LoadBalancerArn']
        print(f"ALB created with ARN: {load_balancer_arn}")
        
        return load_balancer_arn
    except ClientError as e:
        print(f"Error creating ALB: {e}")
        raise

def create_target_group(vpc_id, target_group_name="Deb-target-group-sep25"):
    """Creates a target group for the ALB"""
    try:
        response = elbv2_client.create_target_group(
            Name=target_group_name,
            Protocol='HTTP',
            Port=80,
            VpcId=vpc_id,
            HealthCheckProtocol='HTTP',
            HealthCheckPort='80',
            HealthCheckPath='/',
            Matcher={'HttpCode': '200'},
            TargetType='instance'  # We're using EC2 instances as targets
        )
        
        target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
        print(f"Target group created with ARN: {target_group_arn}")
        
        return target_group_arn
    except ClientError as e:
        print(f"Error creating target group: {e}")
        raise

def register_targets(target_group_arn, instance_ids):
    """Registers EC2 instances with the target group"""
    try:
        targets = [{'Id': instance_id} for instance_id in instance_ids]
        
        response = elbv2_client.register_targets(
            TargetGroupArn=target_group_arn,
            Targets=targets
        )
        
        print(f"EC2 instances registered with target group: {instance_ids}")
    except ClientError as e:
        print(f"Error registering instances: {e}")
        raise

def create_listener(load_balancer_arn, target_group_arn):
    """Creates a listener for the ALB to forward traffic to the target group"""
    try:
        response = elbv2_client.create_listener(
            LoadBalancerArn=load_balancer_arn,
            Protocol='HTTP',
            Port=80,
            DefaultActions=[{
                'Type': 'forward',
                'TargetGroupArn': target_group_arn
            }]
        )
        
        listener_arn = response['Listeners'][0]['ListenerArn']
        print(f"Listener created with ARN: {listener_arn}")
        
        return listener_arn
    except ClientError as e:
        print(f"Error creating listener: {e}")
        raise

def deploy_alb_with_ec2(vpc_id, subnet_ids, security_group_id, instance_ids):
    """Deploys an ALB and registers EC2 instances"""
    
    # Step 1: Create the ALB
    alb_arn = create_alb(vpc_id, subnet_ids, security_group_id)
    
    # Step 2: Create a Target Group
    target_group_arn = create_target_group(vpc_id)
    
    # Step 3: Register EC2 instances with the Target Group
    register_targets(target_group_arn, instance_ids)
    
    # Step 4: Create a Listener for the ALB
    create_listener(alb_arn, target_group_arn)

def lambda_handler(event, context):
    """Lambda function handler to deploy ALB and register EC2 instances"""
    try:
        # Replace with actual details or extract from the event
        vpc_id = 'vpc-03d760fe88b18680f'  # Replace with your VPC ID
        subnet_ids = ['subnet-0fd07baca9b6e64fa', 'subnet-065776c35c7785b4d']  # Replace with your subnet IDs
        security_group_id = 'sg-0ae83dc5b0560641b'  # Replace with the security group ID for the ALB
        instance_ids = ['i-0eb03044b7278fb4f']  # Replace with the EC2 instance IDs
        
        # Deploy the ALB and register the EC2 instances
        deploy_alb_with_ec2(vpc_id, subnet_ids, security_group_id, instance_ids)
        
        return {
            'statusCode': 200,
            'body': json.dumps("ALB and EC2 registration successful.")
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
