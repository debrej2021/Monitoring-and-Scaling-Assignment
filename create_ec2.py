import json
import boto3
from botocore.exceptions import ClientError
from ipaddress import IPv4Network

def get_available_cidr_block(vpc_id):
    """Calculate an available CIDR block that does not overlap with existing subnets."""
    ec2_client = boto3.client('ec2')

    # Get the VPC's CIDR block
    vpc_response = ec2_client.describe_vpcs(
        VpcIds=[vpc_id]
    )
    
    vpc_cidr_block = vpc_response['Vpcs'][0]['CidrBlock']
    print(f"VPC CIDR Block: {vpc_cidr_block}")

    # Get all subnets in the VPC
    subnets_response = ec2_client.describe_subnets(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )
    
    # Get the CIDR blocks of all existing subnets
    existing_cidrs = [subnet['CidrBlock'] for subnet in subnets_response['Subnets']]
    print(f"Existing Subnet CIDR Blocks: {existing_cidrs}")
    
    # Create an IPv4Network object for the VPC CIDR block
    vpc_network = IPv4Network(vpc_cidr_block)
    
    # Generate candidate subnets from the VPC network
    subnet_prefix = 26  # Change to use a smaller subnet if needed
    print(f"Looking for available subnets with prefix size {subnet_prefix}.")

    for subnet in vpc_network.subnets(new_prefix=subnet_prefix):
        # Check if this subnet conflicts with any existing subnets
        if all(IPv4Network(existing_cidr).overlaps(subnet) is False for existing_cidr in existing_cidrs):
            print(f"Found available CIDR Block: {subnet}")
            return str(subnet)

    raise ValueError(f"No available CIDR block found in VPC {vpc_id}")

def create_internet_gateway(vpc_id):
    """Create and attach an internet gateway to the VPC if it doesn't already exist."""
    ec2_client = boto3.client('ec2')

    # Check if there is an internet gateway attached to the VPC
    igw_response = ec2_client.describe_internet_gateways(
        Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
    )
    
    if igw_response['InternetGateways']:
        # Internet gateway already exists
        return igw_response['InternetGateways'][0]['InternetGatewayId']
    
    # If no Internet Gateway, create a new one
    igw = ec2_client.create_internet_gateway()
    igw_id = igw['InternetGateway']['InternetGatewayId']
    
    # Attach the Internet Gateway to the VPC
    ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    
    return igw_id

def create_public_subnet(vpc_id, availability_zone):
    """Create a public subnet in the VPC and ensure it has a route to the Internet Gateway."""
    ec2_client = boto3.client('ec2')

    # Find an available CIDR block
    cidr_block = get_available_cidr_block(vpc_id)

    # Create the subnet
    subnet_response = ec2_client.create_subnet(
        VpcId=vpc_id,
        CidrBlock=cidr_block,
        AvailabilityZone=availability_zone
    )
    
    subnet_id = subnet_response['Subnet']['SubnetId']

    # Modify subnet to auto-assign public IPs to instances
    ec2_client.modify_subnet_attribute(
        SubnetId=subnet_id,
        MapPublicIpOnLaunch={'Value': True}
    )
    
    return subnet_id

def create_route_to_internet_gateway(subnet_id, vpc_id):
    """Create a route to the internet gateway for the public subnet."""
    ec2_client = boto3.client('ec2')

    # Create or find an Internet Gateway for the VPC
    igw_id = create_internet_gateway(vpc_id)
    
    # Get or create the route table for the VPC
    route_tables = ec2_client.describe_route_tables(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )
    
    route_table_id = route_tables['RouteTables'][0]['RouteTableId']
    
    # Add a route to the internet gateway
    ec2_client.create_route(
        RouteTableId=route_table_id,
        DestinationCidrBlock='0.0.0.0/0',
        GatewayId=igw_id
    )
    
    # Associate the route table with the public subnet
    ec2_client.associate_route_table(
        RouteTableId=route_table_id,
        SubnetId=subnet_id
    )

def get_public_subnet_from_vpc(vpc_id):
    """Retrieve the first available public subnet or create one if none exist."""
    ec2_client = boto3.client('ec2')

    # Describe all subnets in the VPC
    response = ec2_client.describe_subnets(
        Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
    )
    
    # Find the first public subnet (one with `MapPublicIpOnLaunch` set to True)
    for subnet in response['Subnets']:
        if subnet['MapPublicIpOnLaunch']:
            return subnet['SubnetId']
    
    # If no public subnets exist, create a new one
    availability_zones = ec2_client.describe_availability_zones()['AvailabilityZones']
    availability_zone = availability_zones[0]['ZoneName']
    
    public_subnet_id = create_public_subnet(vpc_id, availability_zone)
    create_route_to_internet_gateway(public_subnet_id, vpc_id)
    
    return public_subnet_id

def launch_ec2_instance():
    """Launch an EC2 instance in the first available public subnet of the given VPC."""
    ec2 = boto3.resource('ec2')

    # Manually set your VPC ID
    vpc_id = 'vpc-03d760fe88b18680f'  # Replace with your VPC ID
    
    # Retrieve the first available public subnet or create one
    subnet_id = get_public_subnet_from_vpc(vpc_id)

    group_name = 'deb-sep1'
    description = 'Allow SSH and HTTP'

    # Check if the security group already exists in the VPC
    existing_groups = list(ec2.security_groups.filter(
        Filters=[
            {'Name': 'group-name', 'Values': [group_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    ))

    if existing_groups:
        sg = existing_groups[0]
    else:
        # Create the security group if it doesn't exist
        sg = ec2.create_security_group(
            GroupName=group_name,
            Description=description,
            VpcId=vpc_id
        )
        # Add ingress rules
        sg.authorize_ingress(
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # Allow SSH from anywhere
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # Allow HTTP from anywhere
                }
            ]
        )

    # User data script for EC2 instance to install Nginx
    user_data = '''#!/bin/bash
    yum update -y
    yum install -y nginx
    systemctl start nginx
    systemctl enable nginx

    # Create a simple web page
    echo "<html><body><h1>Welcome to my EC2 web server with Nginx!</h1><p>This is a simple web app served by Nginx.</p></body></html>" > /usr/share/nginx/html/index.html
    '''

    # Launch EC2 instance with a network interface (no SubnetId at the instance level)
    instances = ec2.create_instances(
        ImageId='ami-08d8ac128e0a1b91c',  # Replace with your preferred Amazon Linux 2 AMI ID
        InstanceType='t2.micro',
        UserData=user_data,
        MinCount=1,
        MaxCount=1,
        NetworkInterfaces=[{
            'SubnetId': subnet_id,
            'DeviceIndex': 0,
            'AssociatePublicIpAddress': True,
            'Groups': [sg.id]
        }]
    )

    instance = instances[0]
    instance.wait_until_running()  # Wait until the instance is running
    instance.reload()  # Reload the instance to get the updated attributes

    return instance

def lambda_handler(event, context):
    """Lambda function handler to launch the EC2 instance."""
    try:
        instance = launch_ec2_instance()
        return {
            'statusCode': 200,
            'body': json.dumps(f"EC2 instance launched with ID: {instance.id}, Public IP: {instance.public_ip_address}")
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
