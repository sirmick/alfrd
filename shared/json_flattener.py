"""JSON Flattener for extracting deeply nested JSONB data into pandas DataFrames.

This module provides utilities to flatten nested JSON structures from ALFRD documents
into tabular format for analysis, with special handling for arrays and nested objects.

Example Usage:
    from shared.json_flattener import flatten_documents_to_dataframe
    
    # Flatten documents from a file
    df = await flatten_documents_to_dataframe(db, file_id=file_uuid)
    
    # Flatten with custom options
    df = await flatten_documents_to_dataframe(
        db, 
        file_id=file_uuid,
        max_depth=5,
        array_strategy='explode'
    )
"""

from typing import Any, Dict, List, Optional, Union
from uuid import UUID
import pandas as pd
from collections.abc import Mapping


def flatten_dict(
    data: Dict[str, Any],
    parent_key: str = '',
    sep: str = '.',
    max_depth: Optional[int] = None,
    current_depth: int = 0
) -> Dict[str, Any]:
    """Recursively flatten a nested dictionary.
    
    Args:
        data: Dictionary to flatten
        parent_key: Key prefix for nested values
        sep: Separator between nested keys (default: '.')
        max_depth: Maximum nesting depth to flatten (None = unlimited)
        current_depth: Current recursion depth (internal use)
        
    Returns:
        Flattened dictionary with dot-notation keys
        
    Examples:
        >>> flatten_dict({'a': {'b': {'c': 1}}})
        {'a.b.c': 1}
        
        >>> flatten_dict({'a': [1, 2, 3]})
        {'a.0': 1, 'a.1': 2, 'a.2': 3}
    """
    items = []
    
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        
        # Stop flattening at max_depth
        if max_depth is not None and current_depth >= max_depth:
            items.append((new_key, v))
            continue
        
        if isinstance(v, Mapping):
            # Recursively flatten nested dictionaries
            items.extend(
                flatten_dict(
                    v, 
                    new_key, 
                    sep=sep, 
                    max_depth=max_depth, 
                    current_depth=current_depth + 1
                ).items()
            )
        elif isinstance(v, (list, tuple)) and v:
            # Handle arrays based on content type
            if all(isinstance(item, Mapping) for item in v):
                # Array of objects - flatten each with index
                for i, item in enumerate(v):
                    items.extend(
                        flatten_dict(
                            item, 
                            f"{new_key}.{i}", 
                            sep=sep, 
                            max_depth=max_depth, 
                            current_depth=current_depth + 1
                        ).items()
                    )
            else:
                # Array of primitives - index each element
                for i, item in enumerate(v):
                    items.append((f"{new_key}.{i}", item))
        else:
            # Primitive value
            items.append((new_key, v))
    
    return dict(items)


def flatten_with_arrays_as_json(
    data: Dict[str, Any],
    parent_key: str = '',
    sep: str = '.',
    max_depth: Optional[int] = None,
    current_depth: int = 0
) -> Dict[str, Any]:
    """Flatten dictionary but keep arrays as JSON strings.
    
    This is useful when you want to preserve array structures for later processing.
    
    Args:
        data: Dictionary to flatten
        parent_key: Key prefix for nested values
        sep: Separator between nested keys
        max_depth: Maximum nesting depth
        current_depth: Current recursion depth
        
    Returns:
        Flattened dictionary with arrays as JSON strings
    """
    import json
    
    items = []
    
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        
        if max_depth is not None and current_depth >= max_depth:
            items.append((new_key, v))
            continue
        
        if isinstance(v, (list, tuple)):
            # Keep arrays as JSON strings
            items.append((new_key, json.dumps(v)))
        elif isinstance(v, Mapping):
            # Recursively flatten nested dictionaries
            items.extend(
                flatten_with_arrays_as_json(
                    v, 
                    new_key, 
                    sep=sep, 
                    max_depth=max_depth, 
                    current_depth=current_depth + 1
                ).items()
            )
        else:
            items.append((new_key, v))
    
    return dict(items)


def flatten_to_dataframe(
    documents: List[Dict[str, Any]],
    structured_data_key: str = 'structured_data',
    include_metadata: bool = True,
    metadata_columns: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    array_strategy: str = 'flatten',
    sep: str = '.'
) -> pd.DataFrame:
    """Convert list of documents with nested JSONB to pandas DataFrame.
    
    Args:
        documents: List of document dicts from database
        structured_data_key: Key containing nested JSON (default: 'structured_data')
        include_metadata: Include document metadata columns (id, created_at, etc.)
        metadata_columns: Specific metadata columns to include (default: id, created_at, document_type)
        max_depth: Maximum nesting depth to flatten
        array_strategy: How to handle arrays:
            - 'flatten': Expand arrays into indexed columns (a.0, a.1, etc.)
            - 'json': Keep arrays as JSON strings
            - 'first': Take only first element
            - 'count': Replace with array length
        sep: Separator for nested keys
        
    Returns:
        pandas DataFrame with flattened columns
        
    Examples:
        >>> docs = [{'id': 'abc', 'structured_data': {'vendor': 'PG&E', 'amount': 123.45}}]
        >>> df = flatten_to_dataframe(docs)
        >>> df.columns
        Index(['id', 'vendor', 'amount'])
    """
    if not documents:
        return pd.DataFrame()
    
    # Default metadata columns
    if metadata_columns is None:
        metadata_columns = ['id', 'created_at', 'document_type', 'summary']
    
    rows = []
    
    for doc in documents:
        row = {}
        
        # Add metadata columns
        if include_metadata:
            for col in metadata_columns:
                if col in doc:
                    row[col] = doc[col]
        
        # Extract and flatten structured_data
        structured_data = doc.get(structured_data_key)
        
        if structured_data:
            # Handle different array strategies
            if array_strategy == 'json':
                flattened = flatten_with_arrays_as_json(
                    structured_data, 
                    sep=sep, 
                    max_depth=max_depth
                )
            elif array_strategy == 'flatten':
                flattened = flatten_dict(
                    structured_data, 
                    sep=sep, 
                    max_depth=max_depth
                )
            elif array_strategy == 'first':
                # Take first element of arrays
                def take_first(d):
                    result = {}
                    for k, v in d.items():
                        if isinstance(v, (list, tuple)) and v:
                            result[k] = v[0]
                        elif isinstance(v, Mapping):
                            result[k] = take_first(v)
                        else:
                            result[k] = v
                    return result
                
                flattened = flatten_dict(
                    take_first(structured_data), 
                    sep=sep, 
                    max_depth=max_depth
                )
            elif array_strategy == 'count':
                # Replace arrays with their length
                def count_arrays(d):
                    result = {}
                    for k, v in d.items():
                        if isinstance(v, (list, tuple)):
                            result[f"{k}_count"] = len(v)
                        elif isinstance(v, Mapping):
                            result.update(count_arrays(v))
                        else:
                            result[k] = v
                    return result
                
                flattened = flatten_dict(
                    count_arrays(structured_data), 
                    sep=sep, 
                    max_depth=max_depth
                )
            else:
                raise ValueError(f"Unknown array_strategy: {array_strategy}")
            
            row.update(flattened)
        
        rows.append(row)
    
    return pd.DataFrame(rows)


async def flatten_documents_to_dataframe(
    db,
    file_id: Optional[UUID] = None,
    tags: Optional[List[str]] = None,
    document_ids: Optional[List[UUID]] = None,
    include_metadata: bool = True,
    metadata_columns: Optional[List[str]] = None,
    max_depth: Optional[int] = None,
    array_strategy: str = 'flatten',
    sep: str = '.'
) -> pd.DataFrame:
    """Fetch documents from database and convert to flattened DataFrame.
    
    Args:
        db: AlfrdDatabase instance
        file_id: Optional file UUID to fetch documents from
        tags: Optional list of tags to filter documents
        document_ids: Optional specific document IDs to fetch
        include_metadata: Include document metadata columns
        metadata_columns: Specific metadata columns to include
        max_depth: Maximum nesting depth to flatten
        array_strategy: How to handle arrays ('flatten', 'json', 'first', 'count')
        sep: Separator for nested keys
        
    Returns:
        pandas DataFrame with flattened document data
        
    Examples:
        >>> db = AlfrdDatabase(database_url)
        >>> await db.initialize()
        >>> 
        >>> # Get all PG&E bills as DataFrame
        >>> df = await flatten_documents_to_dataframe(db, tags=['series:pge'])
        >>> df.head()
        >>> 
        >>> # Get documents from a specific file
        >>> df = await flatten_documents_to_dataframe(db, file_id=file_uuid)
    """
    # Fetch documents based on criteria
    if document_ids:
        documents = []
        for doc_id in document_ids:
            doc = await db.get_document_full(doc_id)
            if doc:
                documents.append(doc)
    elif file_id:
        documents = await db.get_file_documents(file_id)
    elif tags:
        documents = await db.get_documents_by_tags(tags=tags, limit=10000)
    else:
        # Get all completed documents
        documents = await db.list_documents(limit=10000, status='completed')
    
    return flatten_to_dataframe(
        documents,
        include_metadata=include_metadata,
        metadata_columns=metadata_columns,
        max_depth=max_depth,
        array_strategy=array_strategy,
        sep=sep
    )


def analyze_json_structure(data: Union[Dict[str, Any], List[Dict[str, Any]]], max_samples: int = 5) -> Dict[str, Any]:
    """Analyze the structure of nested JSON to understand its schema.
    
    Useful for exploring unfamiliar JSON structures before flattening.
    
    Args:
        data: Dictionary or list of dictionaries to analyze
        max_samples: Number of sample values to show per field
        
    Returns:
        Dict describing the structure with types and sample values
    """
    from collections import defaultdict
    
    if isinstance(data, list):
        # Analyze list of documents
        all_keys = defaultdict(lambda: {'type': set(), 'samples': []})
        
        for item in data:
            if isinstance(item, dict):
                flat = flatten_dict(item)
                for key, value in flat.items():
                    all_keys[key]['type'].add(type(value).__name__)
                    if len(all_keys[key]['samples']) < max_samples:
                        all_keys[key]['samples'].append(value)
        
        # Convert sets to lists for JSON serialization
        result = {}
        for key, info in all_keys.items():
            result[key] = {
                'types': sorted(info['type']),
                'samples': info['samples'][:max_samples],
                'count': len([d for d in data if key in flatten_dict(d)])
            }
        
        return result
    else:
        # Analyze single document
        flat = flatten_dict(data)
        return {
            key: {
                'type': type(value).__name__,
                'value': value
            }
            for key, value in flat.items()
        }


def pivot_time_series(
    df: pd.DataFrame,
    date_column: str = 'created_at',
    value_column: str = 'amount',
    index_column: Optional[str] = None,
    freq: str = 'M'
) -> pd.DataFrame:
    """Pivot flattened DataFrame into time series format.
    
    Useful for analyzing trends over time (e.g., monthly bills).
    
    Args:
        df: Flattened DataFrame
        date_column: Column containing dates
        value_column: Column containing values to analyze
        index_column: Optional column to use as row index (e.g., vendor)
        freq: Pandas frequency string ('D'=daily, 'M'=monthly, 'Y'=yearly)
        
    Returns:
        Pivoted DataFrame with dates as index
    """
    df = df.copy()
    
    # Ensure date column is datetime
    df[date_column] = pd.to_datetime(df[date_column])
    
    # Set date as index
    df = df.set_index(date_column)
    
    # Resample to desired frequency
    if index_column:
        # Group by index column and resample
        return df.groupby(index_column)[value_column].resample(freq).sum().unstack(level=0)
    else:
        # Simple time series
        return df[value_column].resample(freq).sum()


# Convenience exports
__all__ = [
    'flatten_dict',
    'flatten_to_dataframe',
    'flatten_documents_to_dataframe',
    'analyze_json_structure',
    'pivot_time_series'
]