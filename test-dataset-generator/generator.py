#!/usr/bin/env python3
"""
Test Dataset Generator for ALFRD
Generates realistic document images for testing the document processing pipeline.
"""

import asyncio
import os
import random
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from faker import Faker

fake = Faker()

class DocumentGenerator:
    """Generates realistic test documents from HTML templates."""
    
    def __init__(self, persona_path: str, output_dir: str = "output"):
        self.base_dir = Path(__file__).parent
        self.output_dir = self.base_dir / output_dir
        self.templates_dir = self.base_dir / "templates"
        
        # Load persona
        with open(persona_path, 'r') as f:
            self.persona = yaml.safe_load(f)
        
        # Set up Jinja2 environment
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True
        )
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Track generated document counts
        self.stats = {
            'total_generated': 0,
            'by_type': {}
        }
    
    async def render_to_image(self, html_content: str, output_path: Path):
        """Render HTML to JPG using Playwright."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={'width': 850, 'height': 1100})
            
            await page.set_content(html_content)
            
            # Wait for fonts and rendering
            await page.wait_for_timeout(500)
            
            # Take screenshot as JPG
            await page.screenshot(
                path=str(output_path),
                type='jpeg',
                quality=85,
                full_page=True
            )
            
            await browser.close()
    
    def generate_pge_bill_data(self, month: int, year: int) -> Dict[str, Any]:
        """Generate data for PG&E utility bill."""
        bill_date = datetime(year, month, random.randint(20, 28))
        due_date = bill_date + timedelta(days=15)
        
        # Seasonal usage variation
        base_kwh = 720
        if month in [6, 7, 8, 9]:  # Summer - AC usage
            kwh_usage = base_kwh + random.randint(200, 400)
        elif month in [12, 1, 2]:  # Winter - heating
            kwh_usage = base_kwh + random.randint(100, 250)
        else:
            kwh_usage = base_kwh + random.randint(-100, 100)
        
        therms_usage = random.randint(15, 45)
        
        # Calculate charges
        electric_generation = kwh_usage * 0.14 + random.uniform(-5, 5)
        electric_delivery = kwh_usage * 0.08 + random.uniform(-3, 3)
        gas_charges = therms_usage * 1.85 + random.uniform(-2, 2)
        taxes_fees = (electric_generation + electric_delivery + gas_charges) * 0.08
        total_amount = electric_generation + electric_delivery + gas_charges + taxes_fees
        
        return {
            'bill_date': bill_date.strftime('%B %d, %Y'),
            'due_date': due_date.strftime('%B %d, %Y'),
            'account_number': self.persona['utilities'][0]['account'],
            'customer_name': self.persona['personal']['name'],
            'address_line1': self.persona['address']['street'],
            'address_city': self.persona['address']['city'],
            'address_state': self.persona['address']['state'],
            'address_zip': self.persona['address']['zip'],
            'kwh_usage': kwh_usage,
            'therms_usage': therms_usage,
            'billing_days': 30,
            'electric_generation': electric_generation,
            'electric_delivery': electric_delivery,
            'gas_charges': gas_charges,
            'taxes_fees': taxes_fees,
            'total_amount': total_amount,
            'billing_period': f"{bill_date.strftime('%B %d')} - {(bill_date + timedelta(days=30)).strftime('%B %d, %Y')}"
        }
    
    def generate_rent_receipt_data(self, month: int, year: int) -> Dict[str, Any]:
        """Generate data for rent receipt."""
        payment_date = datetime(year, month, 1)  # Always on 1st
        date_issued = payment_date + timedelta(days=1)
        
        rent = self.persona['housing']['rent']
        late_fee = 0
        
        # 10% chance of late payment
        if random.random() < 0.1:
            late_fee = 100
            payment_date = datetime(year, month, random.randint(5, 10))
        
        total_paid = rent + late_fee
        
        period_start = datetime(year, month, 1)
        if month == 12:
            period_end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = datetime(year, month + 1, 1) - timedelta(days=1)
        
        return {
            'receipt_number': f"RENT-{year}{month:02d}-{random.randint(1000, 9999)}",
            'date_issued': date_issued.strftime('%B %d, %Y'),
            'tenant_name': self.persona['personal']['name'],
            'property_address': self.persona['address']['street'],
            'property_city': self.persona['address']['city'],
            'property_state': self.persona['address']['state'],
            'property_zip': self.persona['address']['zip'],
            'landlord_name': self.persona['housing']['landlord'],
            'landlord_email': self.persona['housing']['landlord_email'],
            'landlord_phone': self.persona['housing']['landlord_phone'],
            'rental_period': f"{period_start.strftime('%B %Y')}",
            'property_unit': self.persona['housing']['unit_number'],
            'payment_date': payment_date.strftime('%B %d, %Y'),
            'payment_method': random.choice(['Check', 'Bank Transfer', 'Online Payment']),
            'base_rent': rent,
            'late_fee': late_fee,
            'total_paid': total_paid,
            'notes': 'Thank you for your timely payment.' if late_fee == 0 else 'Late fee applied per lease agreement.',
            'property_manager': self.persona['housing']['property_manager'],
            'manager_signature': f"{self.persona['housing']['property_manager']}"
        }
    
    def generate_tuition_bill_data(self, semester: str, year: int) -> Dict[str, Any]:
        """Generate data for tuition bill."""
        school = self.persona['school']
        
        if semester == 'spring':
            statement_date = datetime(year, 1, 10)
            due_date = datetime(year, 1, 31)
            semester_name = f"Spring {year}"
            semester_dates = f"January {year} - May {year}"
        else:  # fall
            statement_date = datetime(year, 8, 10)
            due_date = datetime(year, 8, 31)
            semester_name = f"Fall {year}"
            semester_dates = f"August {year} - December {year}"
        
        # Course data
        courses = [
            {'code': 'CS 450', 'name': 'Distributed Systems', 'units': 3},
            {'code': 'CS 451', 'name': 'Cloud Computing', 'units': 3},
            {'code': 'CS 480', 'name': 'Software Engineering', 'units': 3},
            {'code': 'MATH 335', 'name': 'Linear Algebra', 'units': 3},
        ]
        
        credit_hours = sum(c['units'] for c in courses)
        per_unit_cost = 708  # ~$8500 / 12 units
        
        tuition = school['tuition_per_semester']
        services_fee = school['enrollment_fee']
        tech_fee = 150
        health_fee = 200
        tuition_subtotal = tuition + services_fee + tech_fee + health_fee
        
        # No housing/meal plan for this persona
        total_due = tuition_subtotal
        
        return {
            'university_name': school['name'],
            'university_short': 'sfsu',
            'university_address': '1600 Holloway Ave, San Francisco, CA 94132',
            'student_name': self.persona['personal']['name'],
            'student_id': school['student_id'],
            'student_email': school['email'],
            'major': school['major'],
            'address_line1': self.persona['address']['street'],
            'address_city': self.persona['address']['city'],
            'address_state': self.persona['address']['state'],
            'address_zip': self.persona['address']['zip'],
            'semester_name': semester_name,
            'semester_dates': semester_dates,
            'credit_hours': credit_hours,
            'per_unit_cost': per_unit_cost,
            'tuition': tuition,
            'services_fee': services_fee,
            'tech_fee': tech_fee,
            'health_fee': health_fee,
            'tuition_subtotal': tuition_subtotal,
            'has_housing': False,
            'has_meal_plan': False,
            'has_financial_aid': False,
            'total_due': total_due,
            'due_date': due_date.strftime('%B %d, %Y'),
            'statement_date': statement_date.strftime('%B %d, %Y'),
            'account_number': f"STU-{school['student_id']}",
            'office_phone': '(415) 338-1111',
            'office_email': 'bursar@sfsu.edu',
            'courses': courses
        }
    
    def generate_insurance_bill_data(self, month: int, year: int) -> Dict[str, Any]:
        """Generate data for auto insurance bill."""
        vehicle = self.persona['vehicle']
        insurance = vehicle['insurance']
        
        bill_date = datetime(year, month, random.randint(1, 5))
        due_date = bill_date + timedelta(days=20)
        
        # Coverage premiums
        bodily_injury_premium = 45.00
        property_damage_premium = 25.00
        comprehensive_premium = 30.00
        collision_premium = 35.00
        uninsured_premium = 8.00
        medical_premium = 5.00
        roadside_premium = 2.00
        
        amount_due = (bodily_injury_premium + property_damage_premium + 
                     comprehensive_premium + collision_premium + 
                     uninsured_premium + medical_premium + roadside_premium)
        
        period_start = bill_date
        period_end = bill_date + timedelta(days=30)
        
        return {
            'insurance_company': insurance['company'],
            'company_tagline': 'Like a good neighbor',
            'amount_due': amount_due,
            'due_date': due_date.strftime('%B %d, %Y'),
            'customer_name': self.persona['personal']['name'],
            'address_line1': self.persona['address']['street'],
            'address_city': self.persona['address']['city'],
            'address_state': self.persona['address']['state'],
            'address_zip': self.persona['address']['zip'],
            'policy_number': insurance['policy_number'],
            'policy_period': f"{datetime(year, 1, 1).strftime('%B %d, %Y')} - {datetime(year, 12, 31).strftime('%B %d, %Y')}",
            'billing_period': f"{period_start.strftime('%B %d')} - {period_end.strftime('%B %d, %Y')}",
            'vehicle_year': vehicle['year'],
            'vehicle_make': vehicle['make'],
            'vehicle_model': vehicle['model'],
            'vehicle_vin': vehicle['vin'],
            'license_plate': vehicle['license_plate'],
            'vehicle_color': vehicle['color'],
            'bodily_injury_limit': '$250,000/$500,000',
            'bodily_injury_premium': bodily_injury_premium,
            'property_damage_limit': '$100,000',
            'property_damage_premium': property_damage_premium,
            'comprehensive_deductible': 500,
            'comprehensive_premium': comprehensive_premium,
            'collision_deductible': 500,
            'collision_premium': collision_premium,
            'uninsured_limit': '$250,000/$500,000',
            'uninsured_premium': uninsured_premium,
            'medical_limit': '$5,000',
            'medical_premium': medical_premium,
            'roadside_premium': roadside_premium,
            'company_website': 'statefarm.com',
            'payment_phone': '1-800-STATE-FARM',
            'po_box': '2311',
            'mail_city': 'Bloomington',
            'mail_state': 'IL',
            'mail_zip': '61704',
            'agent_name': insurance['agent'],
            'agent_phone': insurance['agent_phone'],
            'agent_email': 'john.smith@statefarm.com',
            'customer_service_phone': '1-800-STATE-FARM',
            'company_address': 'One State Farm Plaza, Bloomington, IL 61710',
            'statement_date': bill_date.strftime('%B %d, %Y')
        }
    
    async def generate_document(self, template_name: str, data: Dict[str, Any], 
                               output_filename: str, doc_type: str):
        """Generate a single document."""
        template = self.jinja_env.get_template(template_name)
        html_content = template.render(**data)
        
        # Create type-specific output directory
        type_dir = self.output_dir / doc_type
        type_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = type_dir / output_filename
        
        print(f"Generating: {output_path}")
        await self.render_to_image(html_content, output_path)
        
        # Update stats
        self.stats['total_generated'] += 1
        self.stats['by_type'][doc_type] = self.stats['by_type'].get(doc_type, 0) + 1
    
    async def generate_year(self, year: int = 2024):
        """Generate all documents for a full year."""
        print(f"\n{'='*60}")
        print(f"Generating Test Dataset for {year}")
        print(f"Persona: {self.persona['personal']['name']}")
        print(f"{'='*60}\n")
        
        tasks = []
        
        # Monthly documents
        for month in range(1, 13):
            month_name = datetime(year, month, 1).strftime('%B').lower()
            
            # PG&E bill
            pge_data = self.generate_pge_bill_data(month, year)
            tasks.append(self.generate_document(
                'bills/pge_utility.html',
                pge_data,
                f'pge_{year}_{month:02d}.jpg',
                'bills'
            ))
            
            # Rent receipt
            rent_data = self.generate_rent_receipt_data(month, year)
            tasks.append(self.generate_document(
                'property/rent_receipt.html',
                rent_data,
                f'rent_{year}_{month:02d}.jpg',
                'property'
            ))
            
            # Insurance bill
            insurance_data = self.generate_insurance_bill_data(month, year)
            tasks.append(self.generate_document(
                'vehicle/insurance_bill.html',
                insurance_data,
                f'insurance_{year}_{month:02d}.jpg',
                'vehicle'
            ))
        
        # Semester tuition bills
        # Spring (January)
        spring_data = self.generate_tuition_bill_data('spring', year)
        tasks.append(self.generate_document(
            'school/tuition_bill.html',
            spring_data,
            f'tuition_spring_{year}.jpg',
            'school'
        ))
        
        # Fall (August)
        fall_data = self.generate_tuition_bill_data('fall', year)
        tasks.append(self.generate_document(
            'school/tuition_bill.html',
            fall_data,
            f'tuition_fall_{year}.jpg',
            'school'
        ))
        
        # Generate all documents
        await asyncio.gather(*tasks)
        
        print(f"\n{'='*60}")
        print(f"Generation Complete!")
        print(f"{'='*60}")
        print(f"Total documents generated: {self.stats['total_generated']}")
        print(f"\nBy type:")
        for doc_type, count in sorted(self.stats['by_type'].items()):
            print(f"  {doc_type}: {count}")
        print(f"\nOutput directory: {self.output_dir}")
        print(f"{'='*60}\n")


async def main():
    """Main entry point."""
    base_dir = Path(__file__).parent
    persona_path = base_dir / "personas" / "alex_johnson.yaml"
    
    generator = DocumentGenerator(str(persona_path))
    await generator.generate_year(2024)


if __name__ == "__main__":
    asyncio.run(main())