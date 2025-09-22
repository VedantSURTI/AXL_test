"""
Build router for Docker image building and pushing operations
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import os
import asyncio
import json
from typing import Dict, Any
import sys
sys.path.append('..')

from app.services.dockerfile_creation import create_dockerfiles_for_all_apps
from app.services.build_and_push import build_image, push_image, BuildPushError

router = APIRouter()

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"

@router.post("/generate-dockerfiles")
async def generate_dockerfiles():
    """Generate Dockerfiles from the uploaded Excel configuration"""
    try:
        # Find the most recent Excel file
        excel_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(('.xlsx', '.xls'))]
        if not excel_files:
            raise HTTPException(status_code=404, detail="No Excel file found")
        
        latest_file = max(excel_files, key=lambda x: os.path.getctime(os.path.join(UPLOAD_DIR, x)))
        excel_path = os.path.join(UPLOAD_DIR, latest_file)
        
        # Generate Dockerfiles
        create_dockerfiles_for_all_apps(excel_path, OUTPUT_DIR)
        
        # List generated apps
        app_folders = [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d)) and not d.startswith('.')]
        
        return {
            "message": "Dockerfiles generated successfully",
            "excel_file_used": latest_file,
            "generated_apps": app_folders,
            "total_apps": len(app_folders)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating Dockerfiles: {str(e)}")

@router.get("/apps")
async def list_apps():
    """List all generated applications"""
    try:
        app_folders = [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d))]
        
        apps_info = []
        for app_name in app_folders:
            app_path = os.path.join(OUTPUT_DIR, app_name)
            dockerfile_exists = os.path.exists(os.path.join(app_path, "Dockerfile"))
            
            apps_info.append({
                "name": app_name,
                "path": app_path,
                "dockerfile_exists": dockerfile_exists
            })
        
        return {
            "apps": apps_info,
            "total_apps": len(apps_info)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing apps: {str(e)}")

@router.post("/build/{app_name}")
async def build_app(app_name: str, background_tasks: BackgroundTasks):
    """Build Docker image for a specific app"""
    try:
        app_folder = os.path.join(OUTPUT_DIR, app_name)
        if not os.path.exists(app_folder):
            raise HTTPException(status_code=404, detail=f"App {app_name} not found")
        
        dockerfile_path = os.path.join(app_folder, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            raise HTTPException(status_code=404, detail=f"Dockerfile not found for {app_name}")
        
        # Create a valid ECR repository name
        # ECR repo names must be 2-256 characters, lowercase, and contain only letters, numbers, hyphens, underscores, periods, and slashes
        repo_name = app_name.lower().replace('_', '-')
        
        # Ensure minimum length and add prefix if needed
        if len(repo_name) < 2:
            repo_name = f"k8s-app-{repo_name}"
        elif not repo_name.startswith(('k8s-', 'app-')):
            repo_name = f"k8s-{repo_name}"
        
        tag = "latest"
        
        # Build image using environment variables for AWS config
        image_uri = build_image(
            folder=app_folder,
            repo_name=repo_name,
            tag=tag
        )
        
        return {
            "message": f"Build completed for {app_name}",
            "image_uri": image_uri,
            "app_name": app_name
        }
    
    except BuildPushError as e:
        raise HTTPException(status_code=500, detail=f"Build error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/push/{app_name}")
async def push_app(app_name: str):
    """Push Docker image for a specific app to ECR"""
    try:
        # Get AWS configuration from environment
        aws_account_id = os.getenv('AWS_ACCOUNT_ID')
        region = os.getenv('ECR_REGION', os.getenv('AWS_DEFAULT_REGION', 'ap-south-1'))
        
        if not aws_account_id:
            raise HTTPException(status_code=400, detail="AWS_ACCOUNT_ID not configured in environment")
        
        # Use the same repository naming logic as the build endpoint
        repo_name = app_name.lower().replace('_', '-')
        if len(repo_name) < 2:
            repo_name = f"k8s-app-{repo_name}"
        elif not repo_name.startswith(('k8s-', 'app-')):
            repo_name = f"k8s-{repo_name}"
        
        tag = "latest"
        image_uri = f"{aws_account_id}.dkr.ecr.{region}.amazonaws.com/{repo_name}:{tag}"
        
        # Push image
        push_image(image_uri)
        
        return {
            "message": f"Push completed for {app_name}",
            "image_uri": image_uri,
            "app_name": app_name
        }
    
    except BuildPushError as e:
        raise HTTPException(status_code=500, detail=f"Push error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/build-all")
async def build_all_apps():
    """Build Docker images for all apps"""
    try:
        # Get all app directories, not just those starting with "app_"
        app_folders = [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d)) and not d.startswith('.')]
        
        results = []
        for app_name in app_folders:
            try:
                app_folder = os.path.join(OUTPUT_DIR, app_name)
                
                # Use the same repository naming logic as the individual build
                repo_name = app_name.lower().replace('_', '-')
                if len(repo_name) < 2:
                    repo_name = f"k8s-app-{repo_name}"
                elif not repo_name.startswith(('k8s-', 'app-')):
                    repo_name = f"k8s-{repo_name}"
                
                tag = "latest"
                
                # Use environment variables for AWS config
                image_uri = build_image(
                    folder=app_folder,
                    repo_name=repo_name,
                    tag=tag
                )
                
                results.append({
                    "app_name": app_name,
                    "status": "success",
                    "image_uri": image_uri
                })
            
            except Exception as e:
                results.append({
                    "app_name": app_name,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "message": "Build all completed",
            "results": results,
            "total_apps": len(app_folders),
            "successful_builds": len([r for r in results if r["status"] == "success"])
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building all apps: {str(e)}")
