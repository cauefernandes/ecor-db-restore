# ecor-db-restore

## Prerequistics
1. Make sure a AWS Aurora RDS database is configured with Data API enabled and gather following info:
* Database ARN
* Database secret ARN 

2. Get the url of database zip file and set it accordingly in serverless.yml

3. Add a serverless.env.yml which contains Aurora database secret ARN from AWS Secrets Manager, just like below:
```python
dev:
  DB_SECRET_ARN: {some arn string}
```
## Deployment
```
$ sls deploy
```

## Usage
```
$ sls invoke -f restoreDb
```