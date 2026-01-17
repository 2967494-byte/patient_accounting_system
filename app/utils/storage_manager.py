import boto3
from flask import current_app
from botocore.client import Config

class StorageManager:
    """
    Управление медицинскими изображениями в Selectel Object Storage (S3).
    Обрабатывает загрузку, хранение и генерацию ссылок для просмотра.
    """
    
    def __init__(self):
        self._s3 = None
        self._access_key = None
        self._secret_key = None
        self._bucket = None
        self._endpoint = None

    @property
    def s3(self):
        if self._s3 is None:
            self._s3 = boto3.client(
                's3',
                endpoint_url=self.endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version='s3v4')
            )
        return self._s3

    @property
    def access_key(self):
        return current_app.config.get('SELECTEL_S3_ACCESS_KEY')

    @property
    def secret_key(self):
        return current_app.config.get('SELECTEL_S3_SECRET_KEY')

    @property
    def bucket(self):
        return current_app.config.get('SELECTEL_S3_BUCKET', 'medical-dicom')

    @property
    def endpoint(self):
        return current_app.config.get('SELECTEL_S3_ENDPOINT', 'https://s3.selcdn.ru')

    def get_study_files(self, appointment_id):
        """Возвращает список файлов (DICOM) для конкретной записи."""
        prefix = f"appointments/{appointment_id}/"
        response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return [obj['Key'] for obj in response.get('Contents', [])]

    def generate_signed_url(self, file_key, expires_in=3600):
        """Генерирует временную ссылку для скачивания файла ВМ."""
        return self.s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': file_key},
            ExpiresIn=expires_in
        )

    def prepare_study_for_vm(self, appointment_id):
        """
        Метод-заглушка для подготовки данных. 
        В реальности может записывать study-manifest.json в корень папки записи,
        который будет прочитан скриптом на ВМ.
        """
        files = self.get_study_files(appointment_id)
        # TODO: Записать манифест с перечнем файлов и их метаданными
        return files
