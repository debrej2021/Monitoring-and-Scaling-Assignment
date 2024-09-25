import json
import boto3
import botocore

def lambda_handler(event, context):
    bucket_name = 'your-webapp-static-files-deb-sep25'
    region = 'us-west-2'
    s3 = boto3.client('s3', region_name=region)
    
    try:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
        return {
            'statusCode': 200,
            'body': json.dumps(f"Bucket '{bucket_name}' created successfully.")
        }
    except botocore.exceptions.ClientError as e:
        return {
            'statusCode': 400,
            'body': json.dumps(f"Error: {e}")
        }
