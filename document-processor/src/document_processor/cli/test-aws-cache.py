#!/usr/bin/env python3
"""Test AWS caching with OCR and LLM operations.

This script tests the disk-based caching system by making duplicate
Textract and Bedrock requests.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path for imports
_script_dir = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

from shared.aws_clients import AWSClientManager


async def test_textract_cache(aws_manager, image_path):
    """Test Textract caching."""
    print("\n" + "="*80)
    print("TEST 1: TEXTRACT OCR (First call - should be CACHE MISS)")
    print("="*80)
    
    # Read image bytes
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    
    result1 = await aws_manager.extract_text_textract(image_bytes, use_cache=True)
    print(f"✅ Extracted {len(result1['extracted_text'])} chars")
    print(f"   Cached: {result1.get('cached', False)}")
    print(f"   Confidence: {result1['confidence']:.2%}")
    
    print("\n" + "="*80)
    print("TEST 2: TEXTRACT OCR (Second call - should be CACHE HIT)")
    print("="*80)
    
    result2 = await aws_manager.extract_text_textract(image_bytes, use_cache=True)
    print(f"✅ Extracted {len(result2['extracted_text'])} chars")
    print(f"   Cached: {result2.get('cached', False)}")
    print(f"   Confidence: {result2['confidence']:.2%}")
    
    return result1['extracted_text']


def test_bedrock_cache(aws_manager, text):
    """Test Bedrock caching."""
    print("\n" + "="*80)
    print("TEST 3: BEDROCK LLM (First call - should be CACHE MISS)")
    print("="*80)
    
    response1 = aws_manager.invoke_bedrock_simple(
        system="You are a document classifier.",
        user_message=f"What type of document is this?\n\n{text[:500]}",
        temperature=0.0,
        use_cache=True
    )
    print(f"✅ Response: {response1[:100]}...")
    
    print("\n" + "="*80)
    print("TEST 4: BEDROCK LLM (Second call - should be CACHE HIT)")
    print("="*80)
    
    response2 = aws_manager.invoke_bedrock_simple(
        system="You are a document classifier.",
        user_message=f"What type of document is this?\n\n{text[:500]}",
        temperature=0.0,
        use_cache=True
    )
    print(f"✅ Response: {response2[:100]}...")
    print(f"   Responses match: {response1 == response2}")


async def main():
    """Run cache test."""
    print("="*80)
    print("AWS CACHE TEST - OCR + LLM")
    print("="*80)
    
    # Initialize AWS manager
    print("\nInitializing AWS clients...")
    aws = AWSClientManager()
    
    # Find a sample image
    sample_files = list(Path("samples").glob("*.jpg")) + list(Path("samples").glob("*.png"))
    if not sample_files:
        print("❌ No sample images found in samples/ directory")
        return
    
    sample_image = sample_files[0]
    print(f"\n📄 Using sample: {sample_image}")
    
    # Clear cache first
    print("\n🗑️  Clearing cache...")
    aws.clear_cache()
    
    # Get initial stats
    print("\n📊 Initial cache stats:")
    stats = aws.get_cache_stats()
    print(f"   Cache enabled: {stats.get('cache_enabled', False)}")
    print(f"   Cache dir: {stats.get('cache_dir', 'N/A')}")
    print(f"   Cached items: {stats.get('cached_items', 0)}")
    
    # Test Textract caching
    extracted_text = await test_textract_cache(aws, sample_image)
    
    # Check cache stats after OCR
    stats_after_ocr = aws.get_cache_stats()
    print(f"\n📊 Cache stats after OCR:")
    print(f"   Hits: {stats_after_ocr.get('hits', 0)}")
    print(f"   Misses: {stats_after_ocr.get('misses', 0)}")
    print(f"   Cached items: {stats_after_ocr.get('cached_items', 0)}")
    
    # Test Bedrock caching
    test_bedrock_cache(aws, extracted_text)
    
    # Final stats
    print("\n" + "="*80)
    print("FINAL STATS")
    print("="*80)
    
    cache_stats = aws.get_cache_stats()
    print(f"\n📊 Cache Statistics:")
    print(f"   Hits: {cache_stats.get('hits', 0)}")
    print(f"   Misses: {cache_stats.get('misses', 0)}")
    print(f"   Hit rate: {cache_stats.get('hit_rate_percent', 0):.1f}%")
    print(f"   Cached items: {cache_stats.get('cached_items', 0)}")
    print(f"   Cache dir: {cache_stats.get('cache_dir', 'N/A')}")
    
    cost_stats = aws.get_cost_stats()
    print(f"\n💰 Cost Statistics:")
    print(f"   Textract pages: {cost_stats['textract']['pages_processed']}")
    print(f"   Textract cost: ${cost_stats['textract']['estimated_cost_usd']:.4f}")
    print(f"   Bedrock tokens: {cost_stats['bedrock']['total_tokens']}")
    print(f"   Bedrock cost: ${cost_stats['bedrock']['estimated_cost_usd']:.4f}")
    print(f"   Total cost: ${cost_stats['total_estimated_cost_usd']:.4f}")
    
    print("\n✅ Test complete!")
    print(f"\nExpected results:")
    print(f"  - 2 cache hits (one OCR, one LLM)")
    print(f"  - 2 cache misses (one OCR, one LLM)")
    print(f"  - Hit rate: 50%")
    print(f"  - 2 cached items on disk")
    print(f"\nCache directory: {cache_stats.get('cache_dir', 'N/A')}")
    print(f"Run: ls -lh {cache_stats.get('cache_dir', 'N/A')}")


if __name__ == '__main__':
    asyncio.run(main())