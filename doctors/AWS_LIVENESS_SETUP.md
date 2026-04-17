# AWS Face Liveness Setup

## What this project expects

The backend and browser do not use the same AWS permissions.

1. The Django backend creates the session and fetches results.
2. The backend then assumes a short-lived frontend role.
3. The browser uses that temporary role to stream the liveness check.

Because of that split, the backend policy and frontend role policy are different.

## Backend IAM policy

Attach this to the IAM user or role that owns the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `CareConnect_backend/.env`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "rekognition:CreateFaceLivenessSession",
        "rekognition:GetFaceLivenessSessionResults",
        "rekognition:CompareFaces"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::027024089921:role/LivenessFrontendRole"
    }
  ]
}
```

## Frontend role permissions

Attach this to `arn:aws:iam::027024089921:role/LivenessFrontendRole`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "rekognition:StartFaceLivenessSession",
      "Resource": "*"
    }
  ]
}
```

If this permission is missing, the browser liveness widget fails even when session creation works.

## Frontend role trust policy

The target role also needs a trust relationship that allows the backend IAM principal to assume it.

Replace `BACKEND_PRINCIPAL_ARN` with the IAM user or role ARN that matches your backend access keys.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "BACKEND_PRINCIPAL_ARN"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

## Required `.env` values

```env
AWS_ACCESS_KEY_ID=your_backend_iam_access_key
AWS_SECRET_ACCESS_KEY=your_backend_iam_secret
AWS_REGION=us-east-1
AWS_LIVENESS_ROLE_ARN=arn:aws:iam::027024089921:role/LivenessFrontendRole
AWS_LIVENESS_SCORE_THRESHOLD=75
```

Use plain `KEY=value` lines. Avoid extra spaces around `=`.
