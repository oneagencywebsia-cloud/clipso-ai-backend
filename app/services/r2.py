"""Cloudflare R2 — Storage S3-compatible"""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from datetime import timedelta
from typing import BinaryIO
import uuid
from loguru import logger

from app.core.config import settings


class R2Client:
    """Cliente R2 para upload/download de vídeos"""

    def __init__(self):
        self._client = None
        self.bucket = settings.r2_bucket_name

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.r2_endpoint,
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    region_name="auto",
                    retries={"max_attempts": 3, "mode": "standard"}
                )
            )
        return self._client

    def upload_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: str = "video/mp4",
        metadata: dict | None = None
    ) -> str:
        """Sube un archivo y retorna la key"""
        try:
            self.client.upload_fileobj(
                file_obj,
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": metadata or {}
                }
            )
            logger.info(f"R2 upload OK: {key}")
            return key
        except ClientError as e:
            logger.error(f"R2 upload error: {e}")
            raise

    def generate_upload_url(
        self,
        key: str,
        content_type: str = "video/mp4",
        expires_in: int = 3600
    ) -> str:
        """Genera URL pre-firmada para upload directo desde el cliente"""
        try:
            url = self.client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ContentType": content_type
                },
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            logger.error(f"R2 presigned URL error: {e}")
            raise

    def generate_download_url(
        self,
        key: str,
        expires_in: int = 3600,
        download_filename: str | None = None
    ) -> str:
        """Genera URL pre-firmada para descarga"""
        params = {"Bucket": self.bucket, "Key": key}
        if download_filename:
            params["ResponseContentDisposition"] = (
                f'attachment; filename="{download_filename}"'
            )
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            logger.error(f"R2 download URL error: {e}")
            raise

    def delete_file(self, key: str) -> bool:
        """Elimina un archivo"""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info(f"R2 deleted: {key}")
            return True
        except ClientError as e:
            logger.error(f"R2 delete error: {e}")
            return False

    def exists(self, key: str) -> bool:
        """Verifica si un objeto existe"""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    @staticmethod
    def generate_key(user_id: str, filename: str, kind: str = "input") -> str:
        """Genera una key estructurada: kind/user_id/uuid_filename"""
        unique = uuid.uuid4().hex[:8]
        clean_name = filename.replace("/", "_").replace("\\", "_")
        return f"{kind}/{user_id}/{unique}_{clean_name}"


# Singleton
r2 = R2Client()
