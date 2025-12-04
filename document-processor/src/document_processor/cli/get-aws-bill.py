#!/usr/bin/env python3
"""Get current AWS bill for this billing period."""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add project root to path for imports
_script_dir = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from shared.config import Settings


def get_current_month_costs(ce_client):
    """Get costs for the current month to date."""
    # Current month start and tomorrow (end date is exclusive in AWS API)
    today = datetime.now()
    start_date = today.replace(day=1).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
        return response
    except ClientError as e:
        print(f"Error fetching AWS costs: {e}")
        return None


def get_service_breakdown(ce_client):
    """Get detailed breakdown by service for current month."""
    # End date must be after start date (exclusive in AWS API)
    today = datetime.now()
    start_date = today.replace(day=1).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost', 'UsageQuantity'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
        return response
    except ClientError as e:
        print(f"Error fetching service breakdown: {e}")
        return None


def get_daily_costs(ce_client, days=7):
    """Get daily costs for the last N days."""
    # End date must be after start date (exclusive in AWS API)
    today = datetime.now()
    start_date = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost']
        )
        return response
    except ClientError as e:
        print(f"Error fetching daily costs: {e}")
        return None


def format_currency(amount):
    """Format amount as currency."""
    return f"${float(amount):,.2f}"


def print_summary(response):
    """Print summary of AWS costs."""
    if not response or 'ResultsByTime' not in response:
        print("No cost data available")
        return
    
    total_cost = 0.0
    services = {}
    
    # Aggregate costs by service
    for result in response['ResultsByTime']:
        if 'Groups' in result:
            for group in result['Groups']:
                service = group['Keys'][0]
                amount = float(group['Metrics']['UnblendedCost']['Amount'])
                
                if service in services:
                    services[service] += amount
                else:
                    services[service] = amount
                
                total_cost += amount
    
    # Print header
    today = datetime.now()
    month_name = today.strftime('%B %Y')
    print(f"\n{'='*70}")
    print(f"AWS Cost Report - {month_name}")
    print(f"Period: {today.replace(day=1).strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}")
    print(f"{'='*70}\n")
    
    # Print total
    print(f"Total Cost (Month-to-Date): {format_currency(total_cost)}\n")
    
    # Print service breakdown
    if services:
        print("Cost by Service:")
        print(f"{'Service':<40} {'Cost':>15}")
        print(f"{'-'*40} {'-'*15}")
        
        # Sort by cost descending
        sorted_services = sorted(services.items(), key=lambda x: x[1], reverse=True)
        
        for service, cost in sorted_services:
            # Only show services with non-zero costs
            if cost > 0.01:
                percentage = (cost / total_cost * 100) if total_cost > 0 else 0
                print(f"{service:<40} {format_currency(cost):>15} ({percentage:5.1f}%)")
    
    print(f"\n{'='*70}\n")


def print_daily_trend(response, days=7):
    """Print daily cost trend."""
    if not response or 'ResultsByTime' not in response:
        print("No daily cost data available")
        return
    
    print(f"\nDaily Cost Trend (Last {days} days):")
    print(f"{'Date':<15} {'Cost':>15}")
    print(f"{'-'*15} {'-'*15}")
    
    for result in response['ResultsByTime']:
        date = result['TimePeriod']['Start']
        cost = float(result['Total']['UnblendedCost']['Amount'])
        print(f"{date:<15} {format_currency(cost):>15}")
    
    print()


def print_json(response):
    """Print raw JSON response."""
    print(json.dumps(response, indent=2, default=str))


def main():
    """Main entry point."""
    # Parse arguments
    show_daily = '--daily' in sys.argv
    show_json = '--json' in sys.argv
    show_help = '--help' in sys.argv or '-h' in sys.argv
    
    if show_help:
        print("Usage: get-aws-bill [OPTIONS]")
        print("\nGet current AWS billing information for this period.")
        print("\nOptions:")
        print("  --daily     Show daily cost trend (last 7 days)")
        print("  --json      Output raw JSON response")
        print("  -h, --help  Show this help message")
        print("\nExamples:")
        print("  get-aws-bill              # Show current month summary")
        print("  get-aws-bill --daily      # Include daily trend")
        print("  get-aws-bill --json       # Raw JSON output")
        sys.exit(0)
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"Error loading settings: {e}")
        print("\nMake sure .env file exists with AWS credentials:")
        print("  AWS_ACCESS_KEY_ID=your-key")
        print("  AWS_SECRET_ACCESS_KEY=your-secret")
        print("  AWS_REGION=us-east-1")
        sys.exit(1)
    
    # Check for AWS credentials
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        print("Error: AWS credentials not configured")
        print("\nSet AWS credentials in .env file:")
        print("  AWS_ACCESS_KEY_ID=your-key")
        print("  AWS_SECRET_ACCESS_KEY=your-secret")
        print("  AWS_REGION=us-east-1")
        sys.exit(1)
    
    # Create Cost Explorer client
    try:
        ce_client = boto3.client(
            'ce',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name='us-east-1'  # Cost Explorer is only available in us-east-1
        )
    except NoCredentialsError:
        print("Error: AWS credentials not found")
        print("Please configure AWS credentials in .env file")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating AWS client: {e}")
        sys.exit(1)
    
    # Get current month costs
    print("Fetching AWS billing data...")
    response = get_service_breakdown(ce_client)
    
    if response:
        if show_json:
            print_json(response)
        else:
            print_summary(response)
            
            # Show daily trend if requested
            if show_daily:
                daily_response = get_daily_costs(ce_client, days=7)
                if daily_response:
                    print_daily_trend(daily_response)
    else:
        print("\nFailed to retrieve AWS billing data.")
        print("\nCommon issues:")
        print("  1. AWS credentials may not have Cost Explorer permissions")
        print("  2. Add 'ce:GetCostAndUsage' permission to your IAM user/role")
        print("  3. Cost Explorer may not be enabled in your AWS account")
        sys.exit(1)


if __name__ == "__main__":
    main()