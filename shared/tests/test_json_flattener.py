"""Tests for JSON flattening utilities.

Run with: pytest shared/tests/test_json_flattener.py -v
"""

import pytest
import pandas as pd
from uuid import uuid4
from datetime import datetime, timezone

from shared.json_flattener import (
    flatten_dict,
    flatten_with_arrays_as_json,
    flatten_to_dataframe,
    analyze_json_structure,
    pivot_time_series
)


class TestFlattenDict:
    """Test flatten_dict function."""
    
    def test_simple_nested_dict(self):
        """Test flattening simple nested dictionary."""
        data = {
            'a': {
                'b': {
                    'c': 1
                }
            }
        }
        result = flatten_dict(data)
        assert result == {'a.b.c': 1}
    
    def test_multiple_keys(self):
        """Test flattening with multiple keys."""
        data = {
            'vendor': 'PG&E',
            'bill': {
                'amount': 123.45,
                'due_date': '2024-01-15'
            }
        }
        result = flatten_dict(data)
        assert result == {
            'vendor': 'PG&E',
            'bill.amount': 123.45,
            'bill.due_date': '2024-01-15'
        }
    
    def test_array_of_primitives(self):
        """Test flattening array of primitive values."""
        data = {
            'tags': ['bill', 'utility', 'pge']
        }
        result = flatten_dict(data)
        assert result == {
            'tags.0': 'bill',
            'tags.1': 'utility',
            'tags.2': 'pge'
        }
    
    def test_array_of_objects(self):
        """Test flattening array of objects."""
        data = {
            'line_items': [
                {'description': 'Electric', 'amount': 100},
                {'description': 'Gas', 'amount': 50}
            ]
        }
        result = flatten_dict(data)
        assert result == {
            'line_items.0.description': 'Electric',
            'line_items.0.amount': 100,
            'line_items.1.description': 'Gas',
            'line_items.1.amount': 50
        }
    
    def test_max_depth(self):
        """Test max_depth parameter."""
        data = {
            'a': {
                'b': {
                    'c': {
                        'd': 1
                    }
                }
            }
        }
        result = flatten_dict(data, max_depth=2)
        # Should stop at depth 2, keeping nested dict
        assert 'a.b.c' in result
        assert isinstance(result['a.b.c'], dict)
    
    def test_custom_separator(self):
        """Test custom separator."""
        data = {
            'a': {
                'b': 1
            }
        }
        result = flatten_dict(data, sep='_')
        assert result == {'a_b': 1}
    
    def test_empty_dict(self):
        """Test empty dictionary."""
        result = flatten_dict({})
        assert result == {}
    
    def test_empty_array(self):
        """Test empty array is skipped."""
        data = {'items': []}
        result = flatten_dict(data)
        assert result == {}


class TestFlattenWithArraysAsJson:
    """Test flatten_with_arrays_as_json function."""
    
    def test_arrays_as_json_strings(self):
        """Test that arrays are kept as JSON strings."""
        import json
        
        data = {
            'vendor': 'PG&E',
            'tags': ['bill', 'utility'],
            'line_items': [
                {'description': 'Electric', 'amount': 100}
            ]
        }
        result = flatten_with_arrays_as_json(data)
        
        assert result['vendor'] == 'PG&E'
        assert result['tags'] == json.dumps(['bill', 'utility'])
        assert 'line_items' in result
        assert isinstance(result['line_items'], str)
    
    def test_nested_dicts_still_flattened(self):
        """Test that nested dicts are still flattened."""
        data = {
            'bill': {
                'amount': 123.45,
                'tags': ['utility']
            }
        }
        result = flatten_with_arrays_as_json(data)
        
        assert 'bill.amount' in result
        assert result['bill.amount'] == 123.45


class TestFlattenToDataframe:
    """Test flatten_to_dataframe function."""
    
    def test_simple_documents(self):
        """Test converting simple documents to DataFrame."""
        docs = [
            {
                'id': str(uuid4()),
                'created_at': datetime.now(timezone.utc),
                'structured_data': {
                    'vendor': 'PG&E',
                    'amount': 123.45
                }
            },
            {
                'id': str(uuid4()),
                'created_at': datetime.now(timezone.utc),
                'structured_data': {
                    'vendor': 'SCL',
                    'amount': 89.99
                }
            }
        ]
        
        df = flatten_to_dataframe(docs)
        
        assert len(df) == 2
        assert 'vendor' in df.columns
        assert 'amount' in df.columns
        assert 'id' in df.columns
        assert df['vendor'].tolist() == ['PG&E', 'SCL']
    
    def test_metadata_columns(self):
        """Test including specific metadata columns."""
        docs = [
            {
                'id': 'abc123',
                'created_at': '2024-01-01',
                'document_type': 'bill',
                'summary': 'Test bill',
                'extra_field': 'should_not_include',
                'structured_data': {'amount': 100}
            }
        ]
        
        df = flatten_to_dataframe(
            docs,
            metadata_columns=['id', 'document_type']
        )
        
        assert 'id' in df.columns
        assert 'document_type' in df.columns
        assert 'summary' not in df.columns
        assert 'extra_field' not in df.columns
    
    def test_array_strategy_flatten(self):
        """Test flatten array strategy."""
        docs = [
            {
                'id': '1',
                'structured_data': {
                    'tags': ['a', 'b', 'c']
                }
            }
        ]
        
        df = flatten_to_dataframe(docs, array_strategy='flatten')
        
        assert 'tags.0' in df.columns
        assert 'tags.1' in df.columns
        assert 'tags.2' in df.columns
    
    def test_array_strategy_json(self):
        """Test json array strategy."""
        import json
        
        docs = [
            {
                'id': '1',
                'structured_data': {
                    'tags': ['a', 'b', 'c']
                }
            }
        ]
        
        df = flatten_to_dataframe(docs, array_strategy='json')
        
        assert 'tags' in df.columns
        assert df['tags'][0] == json.dumps(['a', 'b', 'c'])
    
    def test_array_strategy_first(self):
        """Test first array strategy."""
        docs = [
            {
                'id': '1',
                'structured_data': {
                    'tags': ['first', 'second', 'third']
                }
            }
        ]
        
        df = flatten_to_dataframe(docs, array_strategy='first')
        
        assert 'tags' in df.columns
        assert df['tags'][0] == 'first'
    
    def test_array_strategy_count(self):
        """Test count array strategy."""
        docs = [
            {
                'id': '1',
                'structured_data': {
                    'tags': ['a', 'b', 'c']
                }
            }
        ]
        
        df = flatten_to_dataframe(docs, array_strategy='count')
        
        assert 'tags_count' in df.columns
        assert df['tags_count'][0] == 3
    
    def test_empty_documents(self):
        """Test empty documents list."""
        df = flatten_to_dataframe([])
        assert df.empty
    
    def test_missing_structured_data(self):
        """Test documents without structured_data."""
        docs = [
            {
                'id': '1',
                'created_at': '2024-01-01'
            }
        ]
        
        df = flatten_to_dataframe(docs)
        
        assert len(df) == 1
        assert 'id' in df.columns
    
    def test_custom_separator(self):
        """Test custom separator in column names."""
        docs = [
            {
                'id': '1',
                'structured_data': {
                    'bill': {
                        'amount': 100
                    }
                }
            }
        ]
        
        df = flatten_to_dataframe(docs, sep='_')
        
        assert 'bill_amount' in df.columns


class TestAnalyzeJsonStructure:
    """Test analyze_json_structure function."""
    
    def test_analyze_list_of_dicts(self):
        """Test analyzing list of dictionaries."""
        data = [
            {'vendor': 'PG&E', 'amount': 100, 'nested': {'key': 'value1'}},
            {'vendor': 'SCL', 'amount': 200, 'nested': {'key': 'value2'}},
            {'vendor': 'State Farm', 'nested': {'key': 'value3'}}
        ]
        
        result = analyze_json_structure(data)
        
        assert 'vendor' in result
        assert 'amount' in result
        assert 'nested.key' in result
        
        # Check vendor is in all 3 documents
        assert result['vendor']['count'] == 3
        
        # Check amount is in only 2 documents
        assert result['amount']['count'] == 2
    
    def test_analyze_single_dict(self):
        """Test analyzing single dictionary."""
        data = {
            'vendor': 'PG&E',
            'amount': 123.45
        }
        
        result = analyze_json_structure(data)
        
        assert 'vendor' in result
        assert 'amount' in result
        assert result['vendor']['type'] == 'str'
        assert result['amount']['type'] == 'float'
    
    def test_sample_limit(self):
        """Test max_samples parameter."""
        data = [
            {'value': i} for i in range(10)
        ]
        
        result = analyze_json_structure(data, max_samples=3)
        
        assert len(result['value']['samples']) <= 3


class TestPivotTimeSeries:
    """Test pivot_time_series function."""
    
    def test_simple_pivot(self):
        """Test simple time series pivot."""
        df = pd.DataFrame({
            'created_at': pd.date_range('2024-01-01', periods=12, freq='M'),
            'amount': [100, 110, 105, 115, 120, 125, 130, 135, 140, 145, 150, 155]
        })
        
        result = pivot_time_series(df, freq='M')
        
        assert isinstance(result, pd.Series)
        assert len(result) > 0
    
    def test_pivot_with_index(self):
        """Test pivot with index column."""
        df = pd.DataFrame({
            'created_at': pd.date_range('2024-01-01', periods=6, freq='M').tolist() * 2,
            'vendor': ['PG&E'] * 6 + ['SCL'] * 6,
            'amount': [100, 110, 120, 130, 140, 150] * 2
        })
        
        result = pivot_time_series(
            df,
            index_column='vendor',
            freq='M'
        )
        
        assert isinstance(result, pd.DataFrame)
        assert 'PG&E' in result.columns or 'PG&E' in result.index


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_full_workflow(self):
        """Test complete workflow from nested JSON to DataFrame."""
        # Simulate documents from database
        docs = [
            {
                'id': str(uuid4()),
                'created_at': datetime(2024, 1, 1, tzinfo=timezone.utc),
                'document_type': 'utility_bill',
                'structured_data': {
                    'vendor': 'PG&E',
                    'account_number': '12345',
                    'bill_details': {
                        'amount': 123.45,
                        'due_date': '2024-01-15',
                        'line_items': [
                            {'description': 'Electric', 'amount': 100.00},
                            {'description': 'Gas', 'amount': 23.45}
                        ]
                    }
                }
            },
            {
                'id': str(uuid4()),
                'created_at': datetime(2024, 2, 1, tzinfo=timezone.utc),
                'document_type': 'utility_bill',
                'structured_data': {
                    'vendor': 'PG&E',
                    'account_number': '12345',
                    'bill_details': {
                        'amount': 145.67,
                        'due_date': '2024-02-15',
                        'line_items': [
                            {'description': 'Electric', 'amount': 120.00},
                            {'description': 'Gas', 'amount': 25.67}
                        ]
                    }
                }
            }
        ]
        
        # Flatten to DataFrame
        df = flatten_to_dataframe(docs, array_strategy='flatten')
        
        # Verify structure
        assert len(df) == 2
        assert 'vendor' in df.columns
        assert 'bill_details.amount' in df.columns
        assert 'bill_details.line_items.0.description' in df.columns
        
        # Verify values
        assert df['vendor'].tolist() == ['PG&E', 'PG&E']
        assert df['bill_details.amount'].tolist() == [123.45, 145.67]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])