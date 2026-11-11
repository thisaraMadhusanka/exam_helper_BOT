with open('app.py', 'r') as f:
    content = f.read()

# Fix the delete endpoint indentation
old = '''        # Phase 2: Delete document endpoint
        @app.delete("/documents/{document_id}", response_model=DeleteResponse)
        async def delete_document_endpoint(
            request: Request,
            document_id: str,
        ):
        """
        Delete all chunks for a document in the current workspace.
    
        Requires Authorization: ****** header.
        Only deletes chunks belonging to the verified workspace.
        """
        # Verify workspace token
        workspace_id = get_workspace_id_from_request(request)
    
        # Validate document_id format
        try:
            UUID(document_id)
        except ValueError:
            return create_error_response(
                "INVALID_DOCUMENT_ID",
                "Invalid document ID format",
                status.HTTP_400_BAD_REQUEST
            )
    
        try:
            deleted_count = delete_document(workspace_id, document_id)
        
            logger.info(
                "Document deleted: workspace=%s, document=%s, chunks_deleted=%d",
                workspace_id,
                document_id,
                deleted_count,
            )
        
            return DeleteResponse(
                document_id=document_id,
                chunks_deleted=deleted_count,
                status="deleted" if deleted_count > 0 else "not_found"
            )
    
        except VectorStoreConnectionError as e:
            logger.error("Vector store connection error: %s", e)
            return create_error_response(
                e.code,
                e.message,
                status.HTTP_503_SERVICE_UNAVAILABLE
            )
    
        except VectorStoreOperationError as e:
            logger.error("Vector store operation error: %s", e)
            return create_error_response(
                e.code,
                e.message,
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
        except Exception as e:
            logger.exception("Unexpected error during document deletion")
            return create_error_response(
                "DELETE_FAILED",
                "An unexpected error occurred while deleting the document",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


    # Exception handlers for cleaner error responses'''

new = '''# Phase 2: Delete document endpoint
@app.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete_document_endpoint(
    request: Request,
    document_id: str,
):
    """
    Delete all chunks for a document in the current workspace.

    Requires Authorization: ****** header.
    Only deletes chunks belonging to the verified workspace.
    """
    # Verify workspace token
    workspace_id = get_workspace_id_from_request(request)

    # Validate document_id format
    try:
        UUID(document_id)
    except ValueError:
        return create_error_response(
            "INVALID_DOCUMENT_ID",
            "Invalid document ID format",
            status.HTTP_400_BAD_REQUEST
        )

    try:
        deleted_count = delete_document(workspace_id, document_id)

        logger.info(
            "Document deleted: workspace=%s, document=%s, chunks_deleted=%d",
            workspace_id,
            document_id,
            deleted_count,
        )

        return DeleteResponse(
            document_id=document_id,
            chunks_deleted=deleted_count,
            status="deleted" if deleted_count > 0 else "not_found"
        )

    except VectorStoreConnectionError as e:
        logger.error("Vector store connection error: %s", e)
        return create_error_response(
            e.code,
            e.message,
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    except VectorStoreOperationError as e:
        logger.error("Vector store operation error: %s", e)
        return create_error_response(
            e.code,
            e.message,
            status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    except Exception as e:
        logger.exception("Unexpected error during document deletion")
        return create_error_response(
            "DELETE_FAILED",
            "An unexpected error occurred while deleting the document",
            status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Exception handlers for cleaner error responses'''

content = content.replace(old, new)

with open('app.py', 'w') as f:
    f.write(content)

print('Fixed!')