import io
import uuid
import os
import boto3
from app.config import settings
from botocore.config import Config

get_settings = settings()

s3_client = boto3.client(
    's3',
    aws_access_key_id=get_settings.AWS_ACCESS_KEY,
    aws_secret_access_key=get_settings.AWS_SECRET_ACCESS_KEY,
    region_name=get_settings.AWS_REGION,
    config=Config(
        signature_version='s3v4',
        retries={'max_attempts': 10},
        s3={'addressing_style': 'virtual'}
    )
)

async def upload_to_s3(file, filename: str):
    clean_name = os.path.basename(filename)
    s3_key = f"resumes/{uuid.uuid4()}-{clean_name}"
    file_content = await file.read()
    s3_client.upload_fileobj(
        io.BytesIO(file_content), 
        get_settings.AWS_BUCKET_NAME, 
        s3_key,
        ExtraArgs={"ContentType": file.content_type}
    )
    presigned_url = s3_client.generate_presigned_url('get_object',
        Params={'Bucket': get_settings.AWS_BUCKET_NAME, 'Key': s3_key},
        ExpiresIn=3600
    )
    return presigned_url, s3_key

def get_secure_url(s3_key: str):
    return s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': get_settings.AWS_BUCKET_NAME, 'Key': s3_key},
        ExpiresIn=900
    )