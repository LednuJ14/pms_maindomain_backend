"""
File upload and handling utilities
"""
import os
import uuid
import secrets
from werkzeug.utils import secure_filename as werkzeug_secure_filename
from PIL import Image
from flask import current_app

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'pdf', 'doc', 'docx'}
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}

# MIME type mapping for validation
ALLOWED_MIME_TYPES = {
    'image/jpeg': {'jpg', 'jpeg'},
    'image/png': {'png'},
    'image/gif': {'gif'},
    'application/pdf': {'pdf'},
    'application/msword': {'doc'},
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': {'docx'},
}

# File signatures (magic numbers) for validation
FILE_SIGNATURES = {
    b'\xff\xd8\xff': 'image/jpeg',  # JPEG
    b'\x89PNG\r\n\x1a\n': 'image/png',  # PNG
    b'GIF87a': 'image/gif',  # GIF87a
    b'GIF89a': 'image/gif',  # GIF89a
    b'%PDF': 'application/pdf',  # PDF
    b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': 'application/msword',  # DOC (old format)
}

def allowed_file(filename, allowed_extensions=None):
    """
    Check if file has allowed extension.
    
    Args:
        filename (str): Filename to check
        allowed_extensions (set): Set of allowed extensions
        
    Returns:
        bool: True if file extension is allowed
    """
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', ALLOWED_EXTENSIONS)
    
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def detect_file_type(file_content: bytes) -> str:
    """
    Detect file type from file content (magic numbers).
    
    Args:
        file_content: First bytes of the file
        
    Returns:
        Detected MIME type or None
    """
    if not file_content:
        return None
    
    # Check file signatures
    for signature, mime_type in FILE_SIGNATURES.items():
        if file_content.startswith(signature):
            return mime_type
    
    # Check for DOCX (ZIP-based format)
    if file_content.startswith(b'PK') and b'word/' in file_content[:1024]:
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    
    return None


def validate_file_mime_type(file, filename: str, allowed_extensions: set):
    """
    Validate file MIME type matches extension.
    
    Args:
        file: File object (must support read() and seek())
        filename: Original filename
        allowed_extensions: Set of allowed extensions
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        # Get file extension
        if '.' not in filename:
            return False, "File has no extension"
        
        ext = filename.rsplit('.', 1)[1].lower()
        
        # Read first bytes to check file signature
        current_pos = file.tell()
        file.seek(0)
        file_header = file.read(1024)  # Read first 1KB
        file.seek(current_pos)  # Restore position
        
        if not file_header:
            return False, "File appears to be empty"
        
        # Detect actual file type
        detected_mime = detect_file_type(file_header)
        
        if not detected_mime:
            # If we can't detect, still allow if extension is valid (for compatibility)
            # But log a warning
            current_app.logger.warning(f'Could not detect MIME type for file: {filename}')
            return True, None
        
        # Check if detected MIME type matches allowed extensions
        expected_extensions = ALLOWED_MIME_TYPES.get(detected_mime, set())
        
        if ext not in expected_extensions:
            return False, f"File type mismatch: detected {detected_mime} but extension is .{ext}"
        
        # Additional validation: check if extension is in allowed list
        if ext not in allowed_extensions:
            return False, f"File extension .{ext} is not allowed"
        
        return True, None
        
    except Exception as e:
        current_app.logger.error(f'Error validating file MIME type: {str(e)}', exc_info=True)
        return False, f"Error validating file: {str(e)}"

def secure_filename(filename):
    """
    Generate secure filename (clean, without UUID prefix).
    Handles duplicates by appending numbers.
    
    Args:
        filename (str): Original filename
        
    Returns:
        str: Secure filename (clean, with number suffix if duplicate)
    """
    # Get secure filename from werkzeug
    secure_name = werkzeug_secure_filename(filename)
    
    # Return clean filename (no UUID prefix)
    # Duplicates will be handled by the save_uploaded_file function
    return secure_name

def save_uploaded_file(file, upload_folder, allowed_extensions=None, max_size=None, validate_mime=True):
    """
    Save uploaded file with comprehensive validation including MIME type checking.
    
    Args:
        file: Flask file upload object
        upload_folder (str): Directory to save file
        allowed_extensions (set): Allowed file extensions
        max_size (int): Maximum file size in bytes
        validate_mime (bool): Whether to validate MIME type against file content
        
    Returns:
        tuple: (success: bool, filename: str, error_message: str)
    """
    try:
        # Check if file was uploaded
        if not file or file.filename == '':
            return False, None, "No file selected"
        
        if allowed_extensions is None:
            allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', ALLOWED_EXTENSIONS)
        
        # Check file extension
        if not allowed_file(file.filename, allowed_extensions):
            return False, None, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        
        # Validate MIME type against file content (prevents extension spoofing)
        if validate_mime:
            is_valid, mime_error = validate_file_mime_type(file, file.filename, allowed_extensions)
            if not is_valid:
                return False, None, mime_error or "File type validation failed"
        
        # Check file size
        if max_size:
            # Seek to end to get size
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)  # Reset to beginning
            
            if size > max_size:
                return False, None, f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB"
        
        # Generate secure filename (clean, no UUID)
        original_filename = secure_filename(file.filename)
        
        # Create upload directory if it doesn't exist
        os.makedirs(upload_folder, exist_ok=True)
        
        # Handle duplicate filenames by appending numbers
        file_extension = os.path.splitext(original_filename)[1] if '.' in original_filename else ''
        file_base_name = os.path.splitext(original_filename)[0] if '.' in original_filename else original_filename
        
        # Check if file already exists, if so append a number
        filename = original_filename
        counter = 1
        while os.path.exists(os.path.join(upload_folder, filename)):
            filename = f"{file_base_name}_{counter}{file_extension}"
            counter += 1
        
        # Save file
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        return True, filename, None
        
    except Exception as e:
        current_app.logger.error(f'Error saving file: {str(e)}', exc_info=True)
        return False, None, f"Error saving file: {str(e)}"


def delete_file(file_path):
    """
    Safely delete a file.
    
    Args:
        file_path (str): Path to file to delete
        
    Returns:
        bool: True if file was deleted successfully
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False

def get_file_size(file_path):
    """
    Get file size in bytes.
    
    Args:
        file_path (str): Path to file
        
    Returns:
        int: File size in bytes, or 0 if file doesn't exist
    """
    try:
        return os.path.getsize(file_path) if os.path.exists(file_path) else 0
    except Exception:
        return 0

def format_file_size(size_bytes):
    """
    Format file size in human readable format.
    
    Args:
        size_bytes (int): File size in bytes
        
    Returns:
        str: Formatted file size
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"
