# 🔒 AWS Security Setup Instructions

## ⚠️ CRITICAL: AWS Credentials Security

**NEVER commit AWS credentials to GitHub!** This will trigger quarantine policies.

## Setup Instructions

### 1. Configure AWS Credentials
```bash
# Navigate to aws_credential_keys folder
cd document_app/aws_credential_keys/

# Copy the template
copy config_template.py config.py

# Edit config.py with your actual AWS credentials
# Get credentials from AWS Academy/Console
```

### 2. Update config.py
```python
AWS_CONFIG = {
    'AWS_ACCESS_KEY_ID': 'ASIA...',      # Your actual access key
    'AWS_SECRET_ACCESS_KEY': 'xyz...',   # Your actual secret key
    'AWS_SESSION_TOKEN': 'IQoJ...',      # Your actual session token
    'REGION': 'us-east-1',
    'S3_BUCKET': 'your-bucket-name',
    'DYNAMODB_TABLE': 'Documents'
}
```

### 3. Verify Security
- ✅ `config.py` is in `.gitignore`
- ✅ Only `config_template.py` gets committed
- ✅ Real credentials stay local only

## 🚨 If Credentials Are Exposed
1. Immediately rotate AWS keys in AWS Console
2. Remove credentials from Git history
3. Contact security team

## Team Setup
Each team member must:
1. Clone repository
2. Copy `config_template.py` to `config.py`
3. Add their own AWS credentials to `config.py`