"""
Upload router for handling Excel file uploads
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import pandas as pd
import os
from typing import List, Dict, Any
import shutil

router = APIRouter()

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)):
    """Upload and validate Excel file"""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx or .xls)")
    
    # Save uploaded file
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Parse Excel and validate
        df = pd.read_excel(file_path)
        
        # Basic validation - check required columns
        required_columns = ['base_image']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required columns: {missing_columns}"
            )
        
        # Convert DataFrame to list of dictionaries for JSON response
        # Replace NaN values with None to make it JSON serializable
        df_clean = df.fillna('')  # Replace NaN with empty strings
        config_data = df_clean.to_dict('records')
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "total_apps": len(config_data),
            "config_preview": config_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@router.get("/config-preview")
async def get_config_preview():
    """Get preview of the last uploaded configuration"""
    # Find the most recent Excel file
    try:
        excel_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith(('.xlsx', '.xls'))]
        if not excel_files:
            raise HTTPException(status_code=404, detail="No Excel file found")
        
        # Get the most recent file
        latest_file = max(excel_files, key=lambda x: os.path.getctime(os.path.join(UPLOAD_DIR, x)))
        file_path = os.path.join(UPLOAD_DIR, latest_file)
        
        df = pd.read_excel(file_path)
        # Replace NaN values with empty strings to make it JSON serializable
        df_clean = df.fillna('')
        config_data = df_clean.to_dict('records')
        
        return {
            "filename": latest_file,
            "total_apps": len(config_data),
            "configurations": config_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading configuration: {str(e)}")
