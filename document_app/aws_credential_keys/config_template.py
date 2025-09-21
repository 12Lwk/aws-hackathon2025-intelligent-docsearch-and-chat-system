# AWS Configuration Template
# Copy this file to config.py and fill in your actual AWS credentials
# NEVER commit config.py to GitHub!

import time

AWS_CONFIG = {
    'AWS_ACCESS_KEY_ID': 'YOUR_ACCESS_KEY_HERE',
    'AWS_SECRET_ACCESS_KEY': 'YOUR_SECRET_KEY_HERE', 
    'AWS_SESSION_TOKEN': 'YOUR_SESSION_TOKEN_HERE',
    'REGION': 'us-east-1',
    'S3_BUCKET': 'your-bucket-name',
    'DYNAMODB_TABLE': 'Documents',
    'LAMBDA_FUNCTION': 'DocProcessingFunction'
}

# Set to True to enable AWS integration, False for mock mode
AWS_ENABLED = True