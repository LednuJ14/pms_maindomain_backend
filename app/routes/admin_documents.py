"""
Admin Document Management Routes
"""
import os
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from sqlalchemy import text
from werkzeug.utils import secure_filename
from app import db
from app.utils.decorators import admin_required
from app.utils.error_handlers import handle_api_error

admin_documents_bp = Blueprint('admin_documents', __name__)

# Allowed file extensions for legal documents
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_document_folder(document_type):
    """Get the appropriate folder based on document type"""
    folder_mapping = {
        'property_title': 'property_titles',
        'business_permit': 'business_permits', 
        'zoning_certificate': 'zoning_certificates',
        'tax_declaration': 'tax_declarations',
        'other': 'other'
    }
    return folder_mapping.get(document_type, 'other')

@admin_documents_bp.route('/documents', methods=['GET'])
@admin_required
def get_all_documents(current_user):
    """
    Get all documents (Admin)
    ---
    tags:
      - Admin Documents
    summary: Get all legal documents
    description: Retrieve all legal documents uploaded by property owners from both main domain and subdomain
    security:
      - Bearer: []
    responses:
      200:
        description: Documents retrieved successfully
        schema:
          type: object
          properties:
            documents:
              type: array
              items:
                type: object
      401:
        description: Unauthorized
      403:
        description: Forbidden - Admin access required
      500:
        description: Server error
    """
    try:
        current_app.logger.info(f"Admin documents request - User: {current_user.id}")
        
        documents = []
        
        # 1. Get property legal documents (from main domain)
        query_sql = text("""
            SELECT 
                p.id as property_id,
                p.title as property_title,
                p.building_name,
                p.legal_documents,
                p.created_at as upload_date,
                p.status as property_status,
                u.first_name,
                u.last_name,
                u.email as owner_email
            FROM properties p
            LEFT JOIN users u ON p.owner_id = u.id
            WHERE p.legal_documents IS NOT NULL 
            AND p.legal_documents != ''
            ORDER BY p.created_at DESC
        """)
        
        results = db.session.execute(query_sql).fetchall()
        
        for row in results:
            # Parse legal_documents JSON if it exists
            legal_docs = row.legal_documents or '[]'
            try:
                import json
                doc_list = json.loads(legal_docs) if isinstance(legal_docs, str) else legal_docs
                if not isinstance(doc_list, list):
                    doc_list = []
            except:
                doc_list = []
            
            for doc in doc_list:
                if isinstance(doc, dict):
                    documents.append({
                        'id': f"main_{row.property_id}_{doc.get('type', 'unknown')}",
                        'source': 'main_domain',
                        'property_id': row.property_id,
                        'property_title': row.property_title or row.building_name or 'Unnamed Property',
                        'owner_name': f"{row.first_name or ''} {row.last_name or ''}".strip() or 'Unknown',
                        'owner_email': row.owner_email or '',
                        'document_type': doc.get('type', 'Unknown'),
                        'file_name': doc.get('filename', 'Unknown'),
                        'file_path': doc.get('path', ''),
                        'file_size': doc.get('size', 'Unknown'),
                        'upload_date': row.upload_date.isoformat() if row.upload_date else None,
                        'status': doc.get('status', 'pending'),
                        'property_status': row.property_status
                    })
        
        # 2. Get documents from subdomain (all tenant/staff/manager uploaded documents)
        try:
            import requests
            subdomain_api_url = os.environ.get('SUBDOMAIN_API_URL', 'http://localhost:5001/api')
            subdomain_docs_url = f"{subdomain_api_url}/documents/all"
            
            # Optional: Add API key if configured
            headers = {}
            api_key = os.environ.get('CROSS_DOMAIN_API_KEY')
            if api_key:
                headers['X-API-Key'] = api_key
            
            # Fetch all documents from subdomain (no pagination for now, or use pagination)
            response = requests.get(subdomain_docs_url, params={'per_page': 1000}, headers=headers, timeout=10)
            
            if response.status_code == 200:
                subdomain_data = response.json()
                subdomain_docs = subdomain_data.get('documents', [])
                
                # Transform subdomain documents to match main domain format
                for doc in subdomain_docs:
                    documents.append({
                        'id': f"subdomain_{doc.get('id')}",
                        'source': 'subdomain',
                        'property_id': doc.get('property_id'),
                        'property_title': doc.get('property_name') or f"Property {doc.get('property_id', 'N/A')}",
                        'property_subdomain': doc.get('property_subdomain'),
                        'owner_name': doc.get('uploader_name', 'Unknown'),
                        'owner_email': doc.get('uploader_email', ''),
                        'document_type': doc.get('document_type', 'other'),
                        'file_name': doc.get('filename') or doc.get('name', 'Unknown'),
                        'file_path': doc.get('file_path', ''),
                        'file_size': doc.get('file_size', 'Unknown'),
                        'upload_date': doc.get('created_at'),
                        'status': 'approved',  # Subdomain documents are considered approved
                        'visibility': doc.get('visibility', 'private'),
                        'uploader_role': doc.get('uploader_role', '')
                    })
                
                current_app.logger.info(f"Fetched {len(subdomain_docs)} documents from subdomain")
            else:
                current_app.logger.warning(f"Failed to fetch subdomain documents: {response.status_code}")
        except Exception as subdomain_error:
            current_app.logger.error(f'Error fetching subdomain documents: {subdomain_error}')
            # Continue without subdomain documents if fetch fails
        
        current_app.logger.info(f"Found {len(documents)} total documents ({len([d for d in documents if d.get('source') == 'main_domain'])} main domain, {len([d for d in documents if d.get('source') == 'subdomain'])} subdomain)")
        
        return jsonify({
            'documents': documents,
            'total': len(documents)
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Get documents error: {e}')
        import traceback
        current_app.logger.error(f'Traceback: {traceback.format_exc()}')
        return handle_api_error(500, 'Failed to retrieve documents')

@admin_documents_bp.route('/documents/<document_id>/status', methods=['PUT'])
@admin_required
def update_document_status(current_user, document_id):
    """Update the status of a document (approve/reject)"""
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['approved', 'rejected', 'pending']:
            return handle_api_error(400, 'Invalid status')
        
        # Parse document_id to get property_id and document_type
        # Format: main_{property_id}_{document_type}
        # Example: main_11_legal_document
        if not document_id.startswith('main_'):
            return handle_api_error(400, 'Invalid document ID format. Expected format: main_{property_id}_{document_type}')
        
        # Remove 'main_' prefix
        doc_id_without_prefix = document_id.replace('main_', '', 1)
        
        # Split by underscore - first part is property_id, rest is document_type
        parts = doc_id_without_prefix.split('_')
        if len(parts) < 2:
            current_app.logger.error(f"Invalid document ID format: {document_id}, parts after removing prefix: {parts}")
            return handle_api_error(400, 'Invalid document ID format')
        
        try:
            property_id = int(parts[0])  # Convert to int for database query
        except ValueError:
            current_app.logger.error(f"Invalid property_id in document ID: {document_id}, property_id: {parts[0]}")
            return handle_api_error(400, 'Invalid property ID in document ID')
        
        # Join the rest as document_type (may contain underscores)
        doc_type = '_'.join(parts[1:])
        
        current_app.logger.info(f"Parsed document ID: {document_id} -> property_id: {property_id}, doc_type: {doc_type}")
        
        # Get current property data
        query_sql = text("""
            SELECT legal_documents 
            FROM properties 
            WHERE id = :property_id
        """)
        
        result = db.session.execute(query_sql, {'property_id': property_id}).fetchone()
        
        if not result:
            current_app.logger.error(f"Property not found: {property_id}")
            return handle_api_error(404, 'Property not found')
        
        # Update document status in legal_documents JSON
        legal_docs = result.legal_documents or '[]'
        try:
            import json
            doc_list = json.loads(legal_docs) if isinstance(legal_docs, str) else legal_docs
            if not isinstance(doc_list, list):
                doc_list = []
        except:
            doc_list = []
        
        # Find and update the specific document
        updated = False
        for doc in doc_list:
            if isinstance(doc, dict) and doc.get('type') == doc_type:
                doc['status'] = new_status
                doc['reviewed_by'] = current_user.id
                doc['reviewed_at'] = datetime.utcnow().isoformat()
                updated = True
                break
        
        if not updated:
            return handle_api_error(404, 'Document not found')
        
        # Save back to database
        update_sql = text("""
            UPDATE properties 
            SET legal_documents = :legal_docs
            WHERE id = :property_id
        """)
        
        db.session.execute(update_sql, {
            'legal_docs': json.dumps(doc_list),
            'property_id': property_id
        })
        db.session.commit()
        
        # Notify property manager about document status update
        try:
            from app.services.notification_service import NotificationService
            # Get property owner and name
            prop_info = db.session.execute(
                text("""
                    SELECT owner_id, title, building_name
                    FROM properties
                    WHERE id = :property_id
                """),
                {'property_id': property_id}
            ).mappings().first()
            
            if prop_info:
                manager_id = prop_info.get('owner_id')
                property_name = prop_info.get('title') or prop_info.get('building_name') or 'Property'
                
                if new_status == 'approved':
                    NotificationService.notify_document_approved(
                        manager_id=manager_id,
                        property_id=property_id,
                        property_name=property_name,
                        document_type=doc_type
                    )
                elif new_status == 'rejected':
                    # Get rejection reason if available
                    reason = None
                    for doc in doc_list:
                        if isinstance(doc, dict) and doc.get('type') == doc_type:
                            reason = doc.get('rejection_reason') or doc.get('notes')
                            break
                    
                    NotificationService.notify_document_rejected(
                        manager_id=manager_id,
                        property_id=property_id,
                        property_name=property_name,
                        document_type=doc_type,
                        reason=reason
                    )
        except Exception as notif_error:
            current_app.logger.error(f"Failed to send document notification: {str(notif_error)}")
            # Don't fail the request if notification fails
        
        current_app.logger.info(f"Document {document_id} status updated to {new_status} by admin {current_user.id}")
        
        return jsonify({
            'message': f'Document {new_status} successfully',
            'status': new_status
        }), 200
        
    except Exception as e:
        current_app.logger.error(f'Update document status error: {e}')
        db.session.rollback()
        return handle_api_error(500, 'Failed to update document status')

@admin_documents_bp.route('/documents/<document_id>/download', methods=['GET'])
@admin_required
def download_document(current_user, document_id):
    """Download a specific document (from main domain or subdomain)"""
    try:
        # Check if this is a subdomain document
        if document_id.startswith('subdomain_'):
            # Extract subdomain document ID
            subdomain_doc_id = document_id.replace('subdomain_', '')
            
            # Validate document ID is numeric
            try:
                int(subdomain_doc_id)
            except ValueError:
                current_app.logger.error(f'Invalid subdomain document ID format: {subdomain_doc_id}')
                return handle_api_error(400, 'Invalid subdomain document ID format')
            
            # Fetch document from subdomain
            try:
                subdomain_api_url = os.environ.get('SUBDOMAIN_API_URL', 'http://localhost:5001/api')
                subdomain_download_url = f"{subdomain_api_url}/documents/{subdomain_doc_id}/download"
                
                current_app.logger.info(f'Attempting to download subdomain document from: {subdomain_download_url}')
                
                # Optional: Add API key if configured
                headers = {}
                api_key = os.environ.get('CROSS_DOMAIN_API_KEY')
                if api_key:
                    headers['X-API-Key'] = api_key
                    current_app.logger.info('Using API key for subdomain access')
                
                # Download from subdomain (endpoint allows access without JWT for main domain)
                response = requests.get(
                    subdomain_download_url, 
                    headers=headers, 
                    timeout=30, 
                    stream=True, 
                    allow_redirects=True
                )
                
                current_app.logger.info(f'Subdomain download response status: {response.status_code}')
                
                if response.status_code == 200:
                    # Stream the file back to the client
                    from flask import Response
                    filename = response.headers.get('Content-Disposition', '').split('filename=')[-1].strip('"') or 'document'
                    current_app.logger.info(f'Successfully downloading subdomain document: {filename}')
                    return Response(
                        response.iter_content(chunk_size=8192),
                        mimetype=response.headers.get('Content-Type', 'application/octet-stream'),
                        headers={
                            'Content-Disposition': f'attachment; filename="{filename}"'
                        }
                    )
                else:
                    error_text = response.text[:500] if hasattr(response, 'text') else 'No error details'
                    current_app.logger.error(f'Subdomain download failed: {response.status_code}, Error: {error_text}')
                    
                    # Try to parse error message
                    try:
                        error_data = response.json()
                        error_message = error_data.get('error', 'Failed to download document from subdomain')
                    except:
                        error_message = f'Failed to download document from subdomain (Status: {response.status_code})'
                    
                    return handle_api_error(response.status_code, error_message)
            except requests.exceptions.ConnectionError as conn_error:
                current_app.logger.error(f'Connection error to subdomain server: {conn_error}')
                return handle_api_error(503, 'Subdomain server is not available. Please ensure the subdomain server is running.')
            except requests.exceptions.Timeout as timeout_error:
                current_app.logger.error(f'Timeout error connecting to subdomain server: {timeout_error}')
                return handle_api_error(504, 'Subdomain server request timed out. Please try again later.')
            except Exception as subdomain_error:
                current_app.logger.error(f'Error downloading from subdomain: {subdomain_error}')
                import traceback
                current_app.logger.error(traceback.format_exc())
                return handle_api_error(500, f'Failed to download document from subdomain: {str(subdomain_error)}')
        
        # Main domain document download (existing logic)
        # Parse document_id to get property_id and document_type
        if not document_id.startswith('main_'):
            return handle_api_error(400, 'Invalid document ID format')
        
        # Remove 'main_' prefix and split on first underscore
        doc_id_without_prefix = document_id.replace('main_', '', 1)
        parts = doc_id_without_prefix.split('_', 1)
        if len(parts) != 2:
            current_app.logger.error(f"Invalid document ID format: {document_id}, parts: {parts}")
            return handle_api_error(400, 'Invalid document ID format')
        
        try:
            property_id = int(parts[0])  # Convert to int for database query
        except ValueError:
            current_app.logger.error(f"Invalid property_id in document ID: {document_id}")
            return handle_api_error(400, 'Invalid property ID in document ID')
        
        doc_type = parts[1]  # This is the document type (e.g., 'legal_document', 'property_title', etc.)
        
        current_app.logger.info(f"Downloading document: property_id={property_id}, doc_type={doc_type}")
        
        # Get document info from database
        query_sql = text("""
            SELECT legal_documents 
            FROM properties 
            WHERE id = :property_id
        """)
        
        result = db.session.execute(query_sql, {'property_id': property_id}).fetchone()
        
        if not result:
            current_app.logger.error(f"Property {property_id} not found")
            return handle_api_error(404, 'Property not found')
        
        # Find the specific document
        legal_docs = result.legal_documents or '[]'
        try:
            import json
            doc_list = json.loads(legal_docs) if isinstance(legal_docs, str) else legal_docs
            if not isinstance(doc_list, list):
                doc_list = []
        except Exception as parse_error:
            current_app.logger.error(f"Error parsing legal_documents JSON: {parse_error}")
            doc_list = []
        
        # Find document by type (exact match or flexible matching)
        document = None
        for doc in doc_list:
            if isinstance(doc, dict):
                doc_type_in_json = doc.get('type', '')
                # Try exact match first
                if doc_type_in_json == doc_type:
                    document = doc
                    break
                # Try case-insensitive match
                if doc_type_in_json.lower() == doc_type.lower():
                    document = doc
                    break
        
        if not document:
            current_app.logger.error(f"Document with type '{doc_type}' not found in property {property_id}. Available types: {[d.get('type') for d in doc_list if isinstance(d, dict)]}")
            return handle_api_error(404, f'Document not found. Available document types: {[d.get("type") for d in doc_list if isinstance(d, dict)]}')
        
        # Construct file path
        file_path = document.get('path', '')
        if not file_path:
            current_app.logger.error(f"Document found but file path is missing: {document}")
            return handle_api_error(404, 'File path not found in document record')
        
        # Check if path is a blob URL (browser-generated temporary URL)
        if file_path.startswith('blob:') or file_path.startswith('http://') or file_path.startswith('https://'):
            current_app.logger.error(f"Document path is a blob/URL, not a server path: {file_path}")
            return jsonify({
                'error': 'Document file has not been uploaded to the server',
                'message': 'This document was created but the file was never uploaded to the server. The file path is a temporary browser URL that is no longer valid. Please ask the property manager to re-upload this document.',
                'details': f'File path: {file_path[:100]}...' if len(file_path) > 100 else f'File path: {file_path}'
            }), 400
        
        # Try multiple path resolution strategies
        full_path = None
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        
        possible_paths = [
            # Strategy 1: Path relative to instance_path/uploads
            os.path.join(current_app.instance_path, upload_folder, file_path.lstrip('/')),
            # Strategy 2: Absolute path (if already absolute)
            file_path,
            # Strategy 3: Relative to root_path/uploads
            os.path.join(current_app.root_path, '..', upload_folder, file_path.lstrip('/')),
            # Strategy 4: Relative to instance_path (no uploads subfolder)
            os.path.join(current_app.instance_path, file_path.lstrip('/')),
            # Strategy 5: Relative to root_path (no uploads subfolder)
            os.path.join(current_app.root_path, '..', file_path.lstrip('/')),
            # Strategy 6: Relative to current working directory
            os.path.join(os.getcwd(), file_path.lstrip('/')),
        ]
        
        for path_attempt in possible_paths:
            try:
                normalized_path = os.path.normpath(path_attempt)
                if os.path.exists(normalized_path) and os.path.isfile(normalized_path):
                    full_path = normalized_path
                    current_app.logger.info(f"Found file at: {full_path}")
                    break
            except Exception as path_error:
                current_app.logger.debug(f"Path resolution attempt failed for {path_attempt}: {path_error}")
                continue
        
        if not full_path:
            current_app.logger.error(f"File not found. Tried paths: {possible_paths}, original path: {file_path}")
            # Return helpful error message
            return jsonify({
                'error': 'File not found on server',
                'message': 'The document file could not be found on the server. The document may not have been properly uploaded, or the file may have been moved or deleted.',
                'details': f'Attempted to find file at: {file_path}'
            }), 404
        
        current_app.logger.info(f"Document {document_id} downloaded by admin {current_user.id} from {full_path}")
        
        return send_file(
            full_path,
            as_attachment=True,
            download_name=document.get('filename', 'document.pdf')
        )
        
    except Exception as e:
        current_app.logger.error(f'Download document error: {e}')
        return handle_api_error(500, 'Failed to download document')

@admin_documents_bp.route('/documents/stats', methods=['GET'])
@admin_required
def get_document_stats(current_user):
    """Get document statistics for admin dashboard"""
    try:
        # Get basic counts
        query_sql = text("""
            SELECT 
                COUNT(*) as total_properties,
                COUNT(CASE WHEN legal_documents IS NOT NULL AND legal_documents != '' THEN 1 END) as properties_with_docs
            FROM properties
        """)
        
        result = db.session.execute(query_sql).fetchone()
        
        # For now, return basic stats - can be enhanced with actual document status counts
        stats = {
            'total_properties': result.total_properties or 0,
            'properties_with_documents': result.properties_with_docs or 0,
            'pending_review': 0,  # Would need to parse JSON to get accurate counts
            'approved': 0,
            'rejected': 0
        }
        
        return jsonify(stats), 200
        
    except Exception as e:
        current_app.logger.error(f'Get document stats error: {e}')
        return handle_api_error(500, 'Failed to retrieve document statistics')
