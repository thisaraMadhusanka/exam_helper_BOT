with open('app.py', 'r') as f:
    lines = f.readlines()

# Find the delete endpoint and fix its indentation
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Check if we're at the delete endpoint
    if '# Phase 2: Delete document endpoint' in line and line.startswith('        '):
        # Skip the old indented version and write the new unindented version
        new_lines.append('# Phase 2: Delete document endpoint\n')
        new_lines.append('@app.delete("/documents/{document_id}", response_model=DeleteResponse)\n')
        new_lines.append('async def delete_document_endpoint(\n')
        new_lines.append('    request: Request,\n')
        new_lines.append('    document_id: str,\n')
        new_lines.append('):\n')
        new_lines.append('    """\n')
        new_lines.append('    Delete all chunks for a document in the current workspace.\n')
        new_lines.append('\n')
        new_lines.append('    Requires Authorization: ****** header.\n')
        new_lines.append('    Only deletes chunks belonging to the verified workspace.\n')
        new_lines.append('    """\n')
        new_lines.append('    # Verify workspace token\n')
        new_lines.append('    workspace_id = get_workspace_id_from_request(request)\n')
        new_lines.append('\n')
        new_lines.append('    # Validate document_id format\n')
        new_lines.append('    try:\n')
        new_lines.append('        UUID(document_id)\n')
        new_lines.append('    except ValueError:\n')
        new_lines.append('        return create_error_response(\n')
        new_lines.append('            "INVALID_DOCUMENT_ID",\n')
        new_lines.append('            "Invalid document ID format",\n')
        new_lines.append('            status.HTTP_400_BAD_REQUEST\n')
        new_lines.append('        )\n')
        new_lines.append('\n')
        new_lines.append('    try:\n')
        new_lines.append('        deleted_count = delete_document(workspace_id, document_id)\n')
        new_lines.append('\n')
        new_lines.append('        logger.info(\n')
        new_lines.append('            "Document deleted: workspace=%s, document=%s, chunks_deleted=%d",\n')
        new_lines.append('            workspace_id,\n')
        new_lines.append('            document_id,\n')
        new_lines.append('            deleted_count,\n')
        new_lines.append('        )\n')
        new_lines.append('\n')
        new_lines.append('        return DeleteResponse(\n')
        new_lines.append('            document_id=document_id,\n')
        new_lines.append('            chunks_deleted=deleted_count,\n')
        new_lines.append('            status="deleted" if deleted_count > 0 else "not_found"\n')
        new_lines.append('        )\n')
        new_lines.append('\n')
        new_lines.append('    except VectorStoreConnectionError as e:\n')
        new_lines.append('        logger.error("Vector store connection error: %s", e)\n')
        new_lines.append('        return create_error_response(\n')
        new_lines.append('            e.code,\n')
        new_lines.append('            e.message,\n')
        new_lines.append('            status.HTTP_503_SERVICE_UNAVAILABLE\n')
        new_lines.append('        )\n')
        new_lines.append('\n')
        new_lines.append('    except VectorStoreOperationError as e:\n')
        new_lines.append('        logger.error("Vector store operation error: %s", e)\n')
        new_lines.append('        return create_error_response(\n')
        new_lines.append('            e.code,\n')
        new_lines.append('            e.message,\n')
        new_lines.append('            status.HTTP_500_INTERNAL_SERVER_ERROR\n')
        new_lines.append('        )\n')
        new_lines.append('\n')
        new_lines.append('    except Exception as e:\n')
        new_lines.append('        logger.exception("Unexpected error during document deletion")\n')
        new_lines.append('        return create_error_response(\n')
        new_lines.append('            "DELETE_FAILED",\n')
        new_lines.append('            "An unexpected error occurred while deleting the document",\n')
        new_lines.append('            status.HTTP_500_INTERNAL_SERVER_ERROR\n')
        new_lines.append('        )\n')
        new_lines.append('\n')
        new_lines.append('\n')
        new_lines.append('# Exception handlers for cleaner error responses\n')
        
        # Skip the old indented lines until we reach the exception handler
        while i < len(lines) and not ('# Exception handlers for cleaner error responses' in lines[i] and not lines[i].startswith('    ')):
            i += 1
        # Don't increment i here, let the loop handle it
        continue
    new_lines.append(line)
    i += 1

with open('app.py', 'w') as f:
    f.writelines(new_lines)

print('Fixed!')