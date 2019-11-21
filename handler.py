import os
import json
import urllib.request
import shutil
import zipfile
import boto3
from botocore.exceptions import ClientError
import time
import logging


rds_client = boto3.client('rds-data')
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
db_name = os.environ['DB_NAME']
db_arn = os.environ['DB_RESOURCE_ARN']
secret_arn = os.environ['DB_SECRET_ARN']
bucket_name = os.environ['S3_BUCKET_NAME']
transaction_no = 0

def download_restore_db(event, context):
    TEMP_ZIP_FILENAME = "/tmp/db.zip"
    DB_SCRIPTS_DIR = "/tmp/ecor_db_scripts"

    print("Starting download...")

    url = os.environ['DB_FILE_URL']
    if url is None:
        print("Database url is not set. Exiting...")
        return False

    urllib.request.urlretrieve(url, TEMP_ZIP_FILENAME)

    print("Downloaded database file")

    print("Unzipping database file...")
    with zipfile.ZipFile(TEMP_ZIP_FILENAME, 'r') as zip_ref:
        zip_ref.extractall(DB_SCRIPTS_DIR)

    print("Starting restore...")
    drop_all_tables()

    global transaction_no
    transaction_no = 0
    for root, dirs, files in os.walk(DB_SCRIPTS_DIR):
        files = sorted( (f for f in files if f.endswith(".sql") and not f.startswith('.')))
        for file in files:
            file_path = os.path.join(root, file)
            process_script_file(file_path)

    print("Deleting temp files...")
    os.remove(TEMP_ZIP_FILENAME)
    shutil.rmtree(DB_SCRIPTS_DIR)

    account_id = context.invoked_function_arn.split(":")[4]
    function_name = os.environ['FUNCTION_ARN'] % account_id
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType='Event',
        Payload='{"total": %d}' % transaction_no
    )
    if response['StatusCode'] == 202:
        print("Started running %d transactions in order" % transaction_no)
    else:
        print("Failed to start running transactions")


def process_script_file(file_path):
    print("Processing " + file_path)
    global transaction_no

    with open(file_path) as fp:
        line = fp.readline()
        sql = ""
        while line:
            if line == "/*! START TRANSACTION */;\n":
                sql = ""
            elif line == "/*! COMMIT */;\n":
                transaction_no += 1
                upload_transaction(sql, transaction_no)
                print("sent transaction %d of size %d" % (transaction_no, len(sql)))
            else:
                sql += line
            line = fp.readline()
        print("Processed " + file_path)


def run_transaction(event, context):
    DOWNLOAD_DIR = "/tmp/ecor_transactions_download"

    start_time = time.time()
    transaction_id = db_start_transaction()

    transaction_no = event.get('transaction', 1)
    total_count = event.get('total', 1)
    filename = "%d.sql" % transaction_no

    print("Downloading " + filename)
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    s3_client.download_file(bucket_name, filename, file_path)

    with open(file_path) as fp:
        line = fp.readline()
        sql = ""
        while line:
            if line.endswith(";\n"):
                sql += line
                db_execute_sql(sql, transaction_id)
                sql = ""
            else:
                sql += line
            line = fp.readline()

    status = db_commit_transaction(transaction_id)
    os.remove(file_path)
    s3_client.delete_object(Bucket=bucket_name, Key=filename)
    end_time = time.time()
    print("Commited transaction %d: %s for %d seconds" % (transaction_no, status, (end_time - start_time)))

    if transaction_no < total_count:
        account_id = context.invoked_function_arn.split(":")[4]
        function_name = os.environ['FUNCTION_ARN'] % account_id
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event',
            Payload='{"transaction": %d, "total": %d}' % (transaction_no + 1, total_count)
        )


def upload_transaction(sql, transaction_no):
    UPLOAD_DIR = "/tmp/ecor_transactions_upload"
    filename = "%d.sql" % transaction_no
    file_path = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(file_path, 'w+') as fp:
        fp.write(sql)
    try:
        s3_client.upload_file(file_path, bucket_name, filename)
    except ClientError as e:
        logging.error(e)
        return False
    os.remove(file_path)
    return True


def db_start_transaction():
    response = rds_client.begin_transaction(
        secretArn=secret_arn,
        database=db_name,
        resourceArn=db_arn,
    )
    return response.get("transactionId", None)


def db_commit_transaction(transaction_id):
    response = rds_client.commit_transaction(
        secretArn=secret_arn,
        resourceArn=db_arn,
        transactionId=transaction_id
    )
    return response.get("transactionStatus", None)


def db_execute_sql(sql, transaction_id):
    rds_client.execute_statement(
        secretArn=secret_arn,
        resourceArn=db_arn,
        sql=sql,
        transactionId=transaction_id
    )


def drop_all_tables():
    transaction_id = db_start_transaction()
    
    table_names = [
        "content_model_reference", "job_zone_reference", "occupation_data", "scales_reference",
        "ete_categories", "level_scale_anchors", "occupation_level_metadata", "survey_booklet_locations",
        "task_categories", "work_context_categories", "abilities", "education_training_experience",
        "interests", "job_zones", "knowledge", "skills",
        "task_statements", "task_ratings", "work_activities", "work_context",
        "work_styles", "work_values", "green_occupations", "green_task_statements",
        "iwa_reference", "dwa_reference", "tasks_to_dwas", "green_dwa_reference",
        "tasks_to_green_dwas", "emerging_tasks", "career_changers_matrix", "career_starters_matrix",
        "unspsc_reference", "tools_and_technology", "alternate_titles", "sample_of_reported_titles",
        "technology_skills", "tools_used"
    ]
    db_execute_sql("SET FOREIGN_KEY_CHECKS = 0;", transaction_id)

    for tablename in table_names:
        sql = "DROP TABLE IF EXISTS `" + tablename + "`;"
        db_execute_sql(sql, transaction_id)

    db_execute_sql("SET FOREIGN_KEY_CHECKS = 1;", transaction_id)
    db_commit_transaction(transaction_id)


if __name__ == '__main__':
    download_restore_db('', '')
