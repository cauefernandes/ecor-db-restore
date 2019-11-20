# ecor-db-restore

## Prerequistics
1. Make sure a AWS Aurora RDS database is configured with Data API enabled and gather following info:
* Database ARN
* Database secret ARN 

2. Get the url of database zip file

3. Add or edit config.{env}.yml and add following variables in it:
```python
DB_NAME: {database name string}
DB_RESOURCE_ARN: {some arn string}
DB_SECRET_ARN: {some arn string}
DB_FILE_URL: {database file url}
```

3. Add a serverless.env.yml which contains Aurora database secret ARN from AWS Secrets Manager, just like below:
## Deployment
```
$ sls deploy --stage dev
```

## Usage
```
$ sls invoke -f restoreDb
```