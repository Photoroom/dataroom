import argparse
import os
import shutil
import threading
import time
import traceback
import zipfile
from pathlib import Path

import boto3
from flask import Flask, send_from_directory

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEEPSCATTER_PATH = BACKEND_DIR / 'static_deepscatter'
ZIP_FILE_PATH = BACKEND_DIR / 'static_tmp' / 'tiles.zip'
BUCKET_NAME = 'dataroom-media-prod2'
S3_FILE_KEY = 'deepscatter/tiles.zip'

DOWNLOAD_INTERVAL = 60 * 10  # 10 minutes


def download_tiles_task(bucket_name=BUCKET_NAME, s3_file_key=S3_FILE_KEY):
    our_last_modified = None
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_S3_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_S3_SECRET_ACCESS_KEY'),
    )

    while True:
        start_time = time.time()

        try:
            ZIP_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

            # Check if file is newer
            print(f"Checking s3://{bucket_name}/{s3_file_key} ...")  # noqa
            response = s3_client.head_object(Bucket=bucket_name, Key=s3_file_key)
            last_modified = response['LastModified']

            if our_last_modified is None or last_modified > our_last_modified:
                our_last_modified = last_modified

                # Download the zip file from S3
                print(f"Downloading s3://{bucket_name}/{s3_file_key} ...")  # noqa
                s3_client.download_file(bucket_name, s3_file_key, ZIP_FILE_PATH)
                download_time_taken = time.time() - start_time
                print(f"Download finished in {download_time_taken:.2f}s")  # noqa

                # Clear existing directory
                if DEEPSCATTER_PATH.exists():
                    shutil.rmtree(DEEPSCATTER_PATH)
                DEEPSCATTER_PATH.mkdir(parents=True, exist_ok=True)

                # Extract the zip file
                zip_start_time = time.time()
                print(f"Extracting zip to {DEEPSCATTER_PATH} ...")  # noqa
                with zipfile.ZipFile(ZIP_FILE_PATH, 'r') as zip_ref:
                    zip_ref.extractall(DEEPSCATTER_PATH)
                zip_time_taken = time.time() - zip_start_time
                print(f"Extracting zip finished in {zip_time_taken:.2f}s")  # noqa
            else:
                print(f"Download skipped because file is not newer")  # noqa

        except Exception:
            traceback.print_exc()

        # Sleep until next run
        end_time = time.time()
        total_time_taken = end_time - start_time
        sleep_time = max(1.0, DOWNLOAD_INTERVAL - total_time_taken)
        print(f"Task completed in {total_time_taken:.2f}s! Sleeping until next run...")  # noqa
        time.sleep(sleep_time)


app = Flask(__name__)


@app.route('/deepscatter/_health')
def health_check():
    return 'ok'


@app.route('/deepscatter/<path:filename>')
def serve_tiles(filename):
    return send_from_directory(DEEPSCATTER_PATH, filename)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--bucket', action='store', default=BUCKET_NAME)
    args = parser.parse_args()

    # download tiles task
    task_thread = threading.Thread(
        target=download_tiles_task,
        kwargs={
            'bucket_name': args.bucket,
        },
    )
    task_thread.daemon = True
    task_thread.start()

    # static files
    app.run(debug=args.debug, port=9000)
