import os
import json
import urllib.request
import shutil
import zipfile
import boto3


rds_client = boto3.client('rds-data')
db_name = os.environ['DB_NAME']
db_arn = os.environ['DB_RESOURCE_ARN']
secret_arn = os.environ['DB_SECRET_ARN']


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

    for root, dirs, files in os.walk(DB_SCRIPTS_DIR):
        files = sorted( (f for f in files if f.endswith(".sql") and not f.startswith('.')))
        for file in files:
            file_path = os.path.join(root, file)
            process_script_file(file_path)

    print("Deleting temp files...")
    os.remove(TEMP_ZIP_FILENAME)
    shutil.rmtree(DB_SCRIPTS_DIR)


def process_script_file(file_path):
    print("Processing " + file_path)
    
    with open(file_path) as fp:
        line = fp.readline()
        transaction_id = None
        sql = ""
        while line:
            if line == "/*! START TRANSACTION */;\n":
                transaction_id = db_start_transaction()
            elif line == "/*! COMMIT */;\n":
                status = db_commit_transaction(transaction_id)
                print("commit a transaction: "+ status)
            else:
                sql += line
                if line.endswith(";\n"):
                    db_execute_sql(sql, transaction_id)
                    sql = ""
            line = fp.readline()
        print("Processed")

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
