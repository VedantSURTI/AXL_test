"""
FastAPI Backend for Kubernetes Accelerator
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.routers import upload, build, files

app = FastAPI(
    title="Kubernetes Accelerator API",
    description="Backend API for Dockerfile generation and Docker image building",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(build.router, prefix="/api", tags=["build"])
app.include_router(files.router, prefix="/api", tags=["files"])

# Serve static files (if needed)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"message": "Kubernetes Accelerator API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/aws-status")
async def aws_status():
    """Check AWS credentials and configuration status"""
    from app.services.build_and_push import check_aws_credentials
    
    try:
        credentials_valid = check_aws_credentials()
        aws_account_id = os.getenv('AWS_ACCOUNT_ID', 'Not set')
        aws_region = os.getenv('AWS_DEFAULT_REGION', 'Not set')
        ecr_region = os.getenv('ECR_REGION', 'Not set')
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
        
        return {
            "aws_credentials_valid": credentials_valid,
            "aws_account_id": aws_account_id,
            "aws_default_region": aws_region,
            "ecr_region": ecr_region,
            "env_file_loaded": aws_access_key != '',
            "access_key_preview": aws_access_key[:8] + "..." if aws_access_key else "Not set",
            "secret_key_configured": os.getenv('AWS_SECRET_ACCESS_KEY') is not None
        }
    except Exception as e:
        return {
            "aws_credentials_valid": False,
            "error": str(e),
            "env_file_loaded": os.getenv('AWS_ACCESS_KEY_ID') is not None
        }

@app.post("/test-aws-credentials")
async def test_aws_credentials():
    """Detailed AWS credentials testing"""
    from app.services.build_and_push import get_aws_session
    import boto3
    
    try:
        # Test 1: Environment variables
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '')
        region = os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
        
        if not aws_access_key or not aws_secret_key:
            return {
                "success": False,
                "error": "AWS credentials not found in environment variables",
                "tests": {
                    "env_vars_present": False,
                    "credentials_format": "N/A",
                    "sts_test": "N/A",
                    "ecr_test": "N/A"
                }
            }
        
        # Test 2: Credentials format
        access_key_valid = aws_access_key.startswith('AKIA') and len(aws_access_key) == 20
        secret_key_valid = len(aws_secret_key) == 40
        
        # Test 3: STS call
        try:
            session = get_aws_session()
            sts = session.client('sts')
            identity = sts.get_caller_identity()
            sts_success = True
            sts_error = None
        except Exception as e:
            sts_success = False
            sts_error = str(e)
            identity = {}
        
        # Test 4: ECR access
        try:
            session = get_aws_session()
            ecr = session.client('ecr', region_name=region)
            ecr.describe_repositories(maxResults=1)  # Simple test call
            ecr_success = True
            ecr_error = None
        except Exception as e:
            ecr_success = False
            ecr_error = str(e)
        
        return {
            "success": sts_success and ecr_success,
            "identity": identity,
            "tests": {
                "env_vars_present": True,
                "access_key_format_valid": access_key_valid,
                "secret_key_format_valid": secret_key_valid,
                "access_key_preview": aws_access_key[:8] + "..." if aws_access_key else "Not set",
                "sts_test": {
                    "success": sts_success,
                    "error": sts_error
                },
                "ecr_test": {
                    "success": ecr_success,
                    "error": ecr_error
                }
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Test failed: {str(e)}",
            "tests": {}
        }
