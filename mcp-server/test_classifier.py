#!/usr/bin/env python3
"""
Simple test script for document classification.

Usage:
    python mcp-server/test_classifier.py
"""
import sys
import os

# Add src to path and change to project root for .env loading
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, project_root)

# Change to project root so Settings can find .env
os.chdir(project_root)

from mcp_server.llm import LLMClient
from mcp_server.tools.classify_document import classify_document

# Sample documents to test
SAMPLE_DOCUMENTS = {
    "electric_bill.txt": """
CITY POWER COMPANY
Account Number: 12345-678
Service Period: Jan 1 - Jan 31, 2024

Current Charges:
Electricity Usage: 450 kWh @ $0.12/kWh    $54.00
Delivery Charge:                           $18.50
Total Amount Due:                          $72.50

Due Date: February 15, 2024
""",
    
    "pizza_flyer.txt": """
TONY'S PIZZA
🍕 GRAND OPENING SPECIAL! 🍕

Buy One Get One FREE
All Large Pizzas

Valid through March 31st
Visit us at 123 Main Street

Call 555-PIZZA for delivery!
Limited time offer - Don't miss out!
""",
    
    "bank_statement.txt": """
FIRST NATIONAL BANK
Statement Period: January 1-31, 2024
Account: ****6789

Beginning Balance:           $5,234.56
Deposits:                    $3,500.00
Withdrawals:                 $2,145.23
Interest Earned:                $12.34
Ending Balance:              $6,601.67

For tax reporting purposes, total interest earned: $12.34
"""
}


def test_classification():
    """Test document classification with sample documents."""
    print("Testing ALFRD Document Classifier")
    print("=" * 50)
    print()
    
    # Initialize Bedrock client
    try:
        print("Initializing Bedrock client...")
        client = LLMClient()
        print("✓ Bedrock client initialized")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize Bedrock client: {e}")
        print("\nMake sure your .env file has:")
        print("  AWS_ACCESS_KEY_ID=your_key")
        print("  AWS_SECRET_ACCESS_KEY=your_secret")
        print("  AWS_REGION=us-east-1")
        return False
    
    # Test each sample document
    all_passed = True
    for filename, text in SAMPLE_DOCUMENTS.items():
        print(f"Testing: {filename}")
        print("-" * 50)
        
        try:
            result = classify_document(
                extracted_text=text,
                filename=filename,
                llm_client=client,
            )
            
            print(f"✓ Classification successful")
            print(f"  Type:       {result.document_type.value}")
            print(f"  Confidence: {result.confidence:.2%}")
            print(f"  Reasoning:  {result.reasoning}")
            print()
            
        except Exception as e:
            print(f"✗ Classification failed: {e}")
            print()
            all_passed = False
    
    if all_passed:
        print("=" * 50)
        print("✓ All tests passed!")
        return True
    else:
        print("=" * 50)
        print("✗ Some tests failed")
        return False


if __name__ == "__main__":
    success = test_classification()
    sys.exit(0 if success else 1)