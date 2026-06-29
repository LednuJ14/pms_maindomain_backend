"""
Inquiry Attachments API Routes
Handles file uploads (images, videos, documents) for inquiries
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from app import db
from app.models.inquiry import Inquiry
from app.models.inquiry_attachment import InquiryAttachment, FileType
from app.utils.decorators import tenant_required, manager_required, auth_required
from app.utils.error_handlers import handle_api_error

inquiry_attachments_bp = Blueprint('inquiry_attachments', __name__)

# Configuration
ALLOWED_EXTENSIONS = {
    'image': {'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'},
    'video': {'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'},
    'document': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf'},
    'other': {'zip', 'rar', '7z'}
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads', 'inquiries')

def allowed_file(filename, file_type):
    """Check if file extension is allowed for the given file type."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS.get(file_type, set())

def get_file_type(filename):
    """Determine file type based on extension."""
    if '.' not in filename:
        return 'other'
    ext = filename.rsplit('.', 1)[1].lower()
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return 'other'

def ensure_upload_directory(inquiry_id):
    """Ensure upload directory exists for the inquiry."""
    inquiry_dir = os.path.join(UPLOAD_FOLDER, str(inquiry_id))
    try:
        os.makedirs(inquiry_dir, exist_ok=True)
    except Exception as e:
        current_app.logger.error(f'Error creating upload directory {inquiry_dir}: {str(e)}')
        raise
    return inquiry_dir

@inquiry_attachments_bp.route('/<int:inquiry_id>/attachments', methods=['POST'])
@auth_required
def upload_attachment(current_user, inquiry_id):
    """
    Upload inquiry attachments
    ---
    tags:
      - Inquiry Attachments
    summary: Upload files to an inquiry
    description: Upload one or more files (images, videos, documents) to an inquiry. Both tenant and manager can upload.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: inquiry_id
        type: integer
        required: true
        description: The inquiry ID
      - in: formData
        name: files
        type: file
        required: true
        description: One or more files to upload (max 50MB per file)
    responses:
      201:
        description: Files uploaded successfully
        schema:
          type: object
          properties:
            message:
              type: string
            attachments:
              type: array
              items:
                type: object
      400:
        description: Validation error or no files provided
      401:
        description: Unauthorized
      403:
        description: Forbidden - No access to this inquiry
      404:
        description: Inquiry not found
      500:
        description: Server error
    """
    try:
        # Verify inquiry exists and user has access using raw SQL to avoid relationship issues
        from sqlalchemy import text
        inquiry_row = db.session.execute(text(
            "SELECT id, tenant_id, property_manager_id FROM inquiries WHERE id = :iid"
        ), {'iid': inquiry_id}).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, 'Inquiry not found')
        
        # Check if user is tenant or manager for this inquiry
        if current_user.id != inquiry_row.get('tenant_id') and current_user.id != inquiry_row.get('property_manager_id'):
            return handle_api_error(403, 'You do not have permission to upload files to this inquiry')
        
        if 'files' not in request.files:
            return handle_api_error(400, 'No files provided')
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return handle_api_error(400, 'No files selected')
        
        uploaded_files = []
        errors = []
        
        for file in files:
            if file.filename == '':
                continue
            
            # Validate file
            filename = secure_filename(file.filename)
            file_type = get_file_type(filename)
            
            if not allowed_file(filename, file_type):
                errors.append(f'{filename}: File type not allowed')
                continue
            
            # Check file size
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > MAX_FILE_SIZE:
                errors.append(f'{filename}: File size exceeds {MAX_FILE_SIZE / (1024*1024)}MB limit')
                continue
            
            # Generate unique filename
            file_ext = filename.rsplit('.', 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
            
            # Ensure upload directory exists
            inquiry_dir = ensure_upload_directory(inquiry_id)
            file_path = os.path.join(inquiry_dir, unique_filename)
            
            # Save file
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                file.save(file_path)
                
                # Get MIME type
                mime_type = file.content_type or 'application/octet-stream'
                
                # Create attachment record using raw SQL to avoid enum/relationship issues
                try:
                    # Check if table exists first
                    try:
                        db.session.execute(text("SELECT 1 FROM inquiry_attachments LIMIT 1"))
                    except Exception as table_check_error:
                        current_app.logger.error(f'inquiry_attachments table does not exist: {str(table_check_error)}')
                        errors.append(f'{filename}: Attachments table not found. Please run the database migration.')
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        continue
                    
                    result = db.session.execute(text(
                        """
                        INSERT INTO inquiry_attachments 
                        (inquiry_id, uploaded_by, file_name, file_path, file_type, file_size, mime_type, created_at, updated_at)
                        VALUES 
                        (:inquiry_id, :uploaded_by, :file_name, :file_path, :file_type, :file_size, :mime_type, NOW(), NOW())
                        """
                    ), {
                        'inquiry_id': inquiry_id,
                        'uploaded_by': current_user.id,
                        'file_name': filename,
                        'file_path': file_path,
                        'file_type': file_type,
                        'file_size': file_size,
                        'mime_type': mime_type
                    })
                    db.session.flush()
                    attachment_id = result.lastrowid
                    
                    # Fetch the created attachment to return
                    att_row = db.session.execute(text(
                        """
                        SELECT id, inquiry_id, uploaded_by, file_name, file_path, file_type, 
                               file_size, mime_type, is_deleted, created_at, updated_at
                        FROM inquiry_attachments
                        WHERE id = :aid
                        """
                    ), {'aid': attachment_id}).mappings().first()
                    
                    if att_row:
                        uploaded_files.append({
                            'id': att_row.get('id'),
                            'inquiry_id': att_row.get('inquiry_id'),
                            'file_name': att_row.get('file_name'),
                            'file_path': att_row.get('file_path'),
                            'file_type': str(att_row.get('file_type')).lower() if att_row.get('file_type') else 'other',
                            'file_size': att_row.get('file_size'),
                            'mime_type': att_row.get('mime_type'),
                            'uploaded_by': att_row.get('uploaded_by'),
                            'created_at': att_row.get('created_at').isoformat() if att_row.get('created_at') else None,
                            'is_deleted': bool(att_row.get('is_deleted'))
                        })
                    else:
                        errors.append(f'{filename}: Failed to retrieve created attachment record')
                        
                except Exception as db_error:
                    current_app.logger.error(f'Database error creating attachment for {filename}: {str(db_error)}', exc_info=True)
                    errors.append(f'{filename}: Failed to create attachment record')
                    # Clean up file if it was created
                    if os.path.exists(file_path):
                        os.remove(file_path)
                
            except Exception as e:
                current_app.logger.error(f'Error saving file {filename}: {str(e)}', exc_info=True)
                errors.append(f'{filename}: Failed to save file - {str(e)}')
                # Clean up file if it was created
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
        
        if not uploaded_files and errors:
            db.session.rollback()
            return jsonify({
                'error': 'Failed to upload files',
                'details': errors
            }), 400
        
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully uploaded {len(uploaded_files)} file(s)',
            'attachments': uploaded_files,
            'errors': errors if errors else None
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error uploading attachment: {str(e)}', exc_info=True)
        return handle_api_error(500, 'Failed to upload attachment')

@inquiry_attachments_bp.route('/<int:inquiry_id>/attachments', methods=['GET'])
@auth_required
def get_attachments(current_user, inquiry_id):
    """
    Get inquiry attachments
    ---
    tags:
      - Inquiry Attachments
    summary: Get all attachments for an inquiry
    description: Retrieve all attachments (files) associated with an inquiry
    security:
      - Bearer: []
    parameters:
      - in: path
        name: inquiry_id
        type: integer
        required: true
        description: The inquiry ID
    responses:
      200:
        description: Attachments retrieved successfully
        schema:
          type: object
          properties:
            attachments:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  file_name:
                    type: string
                  file_type:
                    type: string
                  file_size:
                    type: integer
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Inquiry not found
      500:
        description: Server error
    """
    try:
        # Verify inquiry exists and user has access using raw SQL to avoid relationship issues
        from sqlalchemy import text
        inquiry_row = db.session.execute(text(
            "SELECT id, tenant_id, property_manager_id FROM inquiries WHERE id = :iid"
        ), {'iid': inquiry_id}).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, 'Inquiry not found')
        
        # Check if user is tenant or manager for this inquiry
        if current_user.id != inquiry_row.get('tenant_id') and current_user.id != inquiry_row.get('property_manager_id'):
            return handle_api_error(403, 'You do not have permission to view attachments for this inquiry')
        
        # Query attachments using raw SQL to avoid enum/relationship issues
        try:
            attachments_rows = db.session.execute(text(
                """
                SELECT id, inquiry_id, uploaded_by, file_name, file_path, file_type, 
                       file_size, mime_type, is_deleted, created_at, updated_at
                FROM inquiry_attachments
                WHERE inquiry_id = :iid AND (is_deleted IS NULL OR is_deleted = 0)
                ORDER BY created_at DESC
                """
            ), {'iid': inquiry_id}).mappings().all()
            
            attachments_data = []
            for row in attachments_rows:
                file_path = row.get('file_path')
                
                # Verify file exists before including in response
                # This prevents 404 errors on the frontend for missing files
                if file_path:
                    file_path = os.path.normpath(file_path)
                    
                    # Check if file exists
                    file_exists = os.path.exists(file_path)
                    
                    # If not absolute path, try relative to UPLOAD_FOLDER
                    if not file_exists and not os.path.isabs(file_path):
                        alternative_path = os.path.join(UPLOAD_FOLDER, str(inquiry_id), os.path.basename(file_path))
                        if os.path.exists(alternative_path):
                            file_path = alternative_path
                            file_exists = True
                    
                    # Only include attachment if file exists
                    if not file_exists:
                        current_app.logger.warning(f'Attachment {row.get("id")} file not found at: {file_path}')
                        continue  # Skip this attachment - file doesn't exist
                
                attachments_data.append({
                    'id': row.get('id'),
                    'inquiry_id': row.get('inquiry_id'),
                    'file_name': row.get('file_name'),
                    'file_path': file_path,  # Use verified path
                    'file_type': str(row.get('file_type')).lower() if row.get('file_type') else 'other',
                    'file_size': row.get('file_size'),
                    'mime_type': row.get('mime_type'),
                    'uploaded_by': row.get('uploaded_by'),
                    'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
                    'is_deleted': bool(row.get('is_deleted'))
                })
            
            return jsonify({
                'attachments': attachments_data
            }), 200
            
        except Exception as query_error:
            # If table doesn't exist, return empty array
            current_app.logger.warning(f'Error querying attachments table (may not exist yet): {str(query_error)}')
            return jsonify({
                'attachments': []
            }), 200
        
    except Exception as e:
        current_app.logger.error(f'Error fetching attachments: {str(e)}', exc_info=True)
        return handle_api_error(500, f'Failed to fetch attachments: {str(e)}')

@inquiry_attachments_bp.route('/attachments/<int:attachment_id>', methods=['GET'])
@auth_required
def download_attachment(current_user, attachment_id):
    """
    Download inquiry attachment
    ---
    tags:
      - Inquiry Attachments
    summary: Download a specific attachment file
    description: Download a specific attachment file from an inquiry
    security:
      - Bearer: []
    parameters:
      - in: path
        name: attachment_id
        type: integer
        required: true
        description: The attachment ID
    responses:
      200:
        description: File downloaded successfully
        schema:
          type: file
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Attachment not found
      500:
        description: Server error
    """
    try:
        from sqlalchemy import text
        
        # Fetch attachment using raw SQL to avoid ORM issues
        att_row = db.session.execute(text(
            """
            SELECT id, inquiry_id, uploaded_by, file_name, file_path, file_type, 
                   file_size, mime_type, is_deleted, created_at, updated_at
            FROM inquiry_attachments
            WHERE id = :aid AND (is_deleted IS NULL OR is_deleted = 0)
            """
        ), {'aid': attachment_id}).mappings().first()
        
        if not att_row:
            return handle_api_error(404, 'Attachment not found')
        
        # Verify inquiry access using raw SQL
        inquiry_row = db.session.execute(text(
            """
            SELECT id, tenant_id, property_manager_id
            FROM inquiries
            WHERE id = :iid
            """
        ), {'iid': att_row.get('inquiry_id')}).mappings().first()
        
        if not inquiry_row:
            return handle_api_error(404, 'Inquiry not found')
        
        tenant_id = inquiry_row.get('tenant_id')
        manager_id = inquiry_row.get('property_manager_id')
        
        if current_user.id != tenant_id and current_user.id != manager_id:
            return handle_api_error(403, 'You do not have permission to download this attachment')
        
        # Get file path
        file_path = att_row.get('file_path')
        file_name = att_row.get('file_name')
        
        if not file_path:
            return handle_api_error(404, 'File path not found')
        
        # Normalize the path (handle Windows paths correctly)
        file_path = os.path.normpath(file_path)
        
        # Check if file exists
        if not os.path.exists(file_path):
            current_app.logger.warning(f'File not found at path: {file_path}')
            # Try to construct the path from UPLOAD_FOLDER if it's a relative path
            if not os.path.isabs(file_path):
                alternative_path = os.path.join(UPLOAD_FOLDER, str(att_row.get('inquiry_id')), os.path.basename(file_path))
                if os.path.exists(alternative_path):
                    file_path = alternative_path
                else:
                    return handle_api_error(404, f'File not found on server. Expected at: {file_path}')
            else:
                return handle_api_error(404, f'File not found on server. Expected at: {file_path}')
        
        # Get directory and filename
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        try:
            return send_from_directory(
                directory,
                filename,
                as_attachment=True,
                download_name=file_name
            )
        except Exception as send_error:
            current_app.logger.error(f'Error sending file: {str(send_error)}')
            # Fallback: try to read and send the file directly
            try:
                from flask import Response
                with open(file_path, 'rb') as f:
                    file_data = f.read()
                return Response(
                    file_data,
                    mimetype=att_row.get('mime_type') or 'application/octet-stream',
                    headers={
                        'Content-Disposition': f'attachment; filename="{file_name}"'
                    }
                )
            except Exception as fallback_error:
                current_app.logger.error(f'Fallback file send also failed: {str(fallback_error)}')
                return handle_api_error(500, f'Failed to send file: {str(send_error)}')
        
    except Exception as e:
        current_app.logger.error(f'Error downloading attachment: {str(e)}', exc_info=True)
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, f'Failed to download attachment: {str(e)}')

@inquiry_attachments_bp.route('/attachments/<int:attachment_id>', methods=['DELETE'])
@auth_required
def delete_attachment(current_user, attachment_id):
    """
    Delete inquiry attachment
    ---
    tags:
      - Inquiry Attachments
    summary: Delete an attachment (soft delete)
    description: Soft delete an attachment. Only uploader, tenant, or manager can delete.
    security:
      - Bearer: []
    parameters:
      - in: path
        name: attachment_id
        type: integer
        required: true
        description: The attachment ID
    responses:
      200:
        description: Attachment deleted successfully
        schema:
          type: object
          properties:
            message:
              type: string
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Attachment not found
      500:
        description: Server error
    """
    try:
        attachment = InquiryAttachment.query.get(attachment_id)
        if not attachment:
            return handle_api_error(404, 'Attachment not found')
        
        # Verify inquiry access
        inquiry = Inquiry.query.get(attachment.inquiry_id)
        if not inquiry:
            return handle_api_error(404, 'Inquiry not found')
        
        # Only allow deletion by uploader, tenant, or manager
        if (current_user.id != attachment.uploaded_by and 
            current_user.id != inquiry.tenant_id and 
            current_user.id != inquiry.property_manager_id):
            return handle_api_error(403, 'You do not have permission to delete this attachment')
        
        # Soft delete
        attachment.is_deleted = True
        db.session.commit()
        
        return jsonify({
            'message': 'Attachment deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Error deleting attachment: {str(e)}', exc_info=True)
        return handle_api_error(500, 'Failed to delete attachment')

