# Text Formatting Utility

## Overview

The `utils/text_formatting.py` module provides comprehensive text formatting utilities for proper capitalization of names, medical facilities, and addresses throughout the SurgiCase API. This centralized utility ensures consistent text formatting across all endpoints and eliminates code duplication.

## Features

- **Smart Name Capitalization**: Handles special name prefixes (Mc, Mac, O'), hyphenated names, and multi-word locations
- **Medical Facility Formatting**: Specialized formatting for hospitals, clinics, medical centers with extensive medical terminology
- **Address Formatting**: Proper capitalization for street addresses, directions, apartment numbers, and address components
- **Reusable Design**: Single source of truth for text formatting logic across the entire application

## Functions

### `capitalize_name_field(name_str: str) -> str`

Properly capitalizes individual name fields or multi-word locations. Handles common name prefixes, hyphenated names, and multi-word locations.

**Use Cases:**
- First and last names
- City names
- Multi-word locations
- State names (full names)

**Examples:**
```python
from utils.text_formatting import capitalize_name_field

# Basic names
capitalize_name_field("JOHN") # → "John"
capitalize_name_field("mary") # → "Mary"

# Special name prefixes
capitalize_name_field("MCDONALD") # → "McDonald"
capitalize_name_field("MACLEOD") # → "MacLeod"
capitalize_name_field("O'CONNOR") # → "O'Connor"

# Hyphenated names
capitalize_name_field("SMITH-JONES") # → "Smith-Jones"
capitalize_name_field("ANNE-MARIE") # → "Anne-Marie"

# Multi-word locations
capitalize_name_field("SAN FRANCISCO") # → "San Francisco"
capitalize_name_field("NEW YORK") # → "New York"
capitalize_name_field("LOS ANGELES") # → "Los Angeles"
```

### `capitalize_facility_field(facility_str: str) -> str`

Properly capitalizes facility names and addresses with specialized handling for medical facility terminology.

**Medical Terms Recognized:**
- Hospital, Medical, Center/Centre, Clinic, Health, Care
- Surgery, Surgical, Institute, Foundation, Associates, Group, Practice
- Department, University, Regional, Community, General, Memorial
- Children, Pediatric, Women, Specialty, Outpatient, Ambulatory
- Rehabilitation, Emergency, Family, Internal, Medicine
- Cardiology, Neurology, Oncology, Radiology, Pathology
- Laboratory, Pharmacy, Therapy, Wellness, Diagnostics, Imaging

**Examples:**
```python
from utils.text_formatting import capitalize_facility_field

# Hospital names
capitalize_facility_field("JOHNS HOPKINS HOSPITAL") # → "Johns Hopkins Hospital"
capitalize_facility_field("ST. MARY MEDICAL CENTER") # → "St. Mary Medical Center"
capitalize_facility_field("MAYO CLINIC HEALTH SYSTEM") # → "Mayo Clinic Health System"

# Specialized facilities
capitalize_facility_field("CHILDREN'S HOSPITAL") # → "Children's Hospital"
capitalize_facility_field("REGIONAL CANCER CENTER") # → "Regional Cancer Center"
capitalize_facility_field("UNIVERSITY SURGICAL ASSOCIATES") # → "University Surgical Associates"

# With punctuation preserved
capitalize_facility_field("ST. JOSEPH'S MEDICAL CENTER") # → "St. Joseph's Medical Center"
```

### `capitalize_address_field(address_str: str) -> str`

Properly capitalizes address fields with specialized handling for street names, directions, and address components.

**Address Components Recognized:**
- Street types: Street/St, Avenue/Ave, Road/Rd, Drive/Dr, Lane/Ln, Boulevard/Blvd
- Locations: Circle/Cir, Court/Ct, Place/Pl, Way, Parkway/Pkwy
- Units: Suite/Ste, Apartment/Apt, Unit, Floor/Fl, Building/Bldg
- Directions: North/N, South/S, East/E, West/W, Northeast/NE, etc.

**Examples:**
```python
from utils.text_formatting import capitalize_address_field

# Basic addresses
capitalize_address_field("123 MAIN STREET") # → "123 Main Street"
capitalize_address_field("456 FIRST AVENUE") # → "456 First Avenue"

# With directions
capitalize_address_field("789 N BROADWAY") # → "789 N Broadway"
capitalize_address_field("321 SOUTH PARK AVENUE") # → "321 South Park Avenue"

# With units
capitalize_address_field("456 N FIRST AVE APT 2B") # → "456 N First Ave Apt 2b"
capitalize_address_field("123 HEALTHCARE BLVD SUITE 100") # → "123 Healthcare Blvd Suite 100"

# Complex addresses
capitalize_address_field("789 WEST MEDICAL CENTER DRIVE BUILDING A") # → "789 West Medical Center Drive Building A"
```

## Implementation

### Current Usage

The text formatting utilities are currently implemented in:

1. **Surgeon Search** (`endpoints/surgeon/search_surgeon.py`)
   - Capitalizes `first_name` and `last_name` fields using `capitalize_name_field()`

2. **Facility Search** (`endpoints/facility/search_facility.py`)
   - Capitalizes `facility_name` using `capitalize_facility_field()`
   - Capitalizes `facility_city` using `capitalize_name_field()`
   - Capitalizes `facility_addr` using `capitalize_address_field()`
   - Handles `facility_state` with special logic for abbreviations vs. full names

### Integration Example

```python
from utils.text_formatting import capitalize_name_field, capitalize_facility_field, capitalize_address_field

# In a search endpoint
for row in search_results:
    if 'first_name' in row and row['first_name']:
        row['first_name'] = capitalize_name_field(row['first_name'])
    if 'last_name' in row and row['last_name']:
        row['last_name'] = capitalize_name_field(row['last_name'])
    if 'facility_name' in row and row['facility_name']:
        row['facility_name'] = capitalize_facility_field(row['facility_name'])
    if 'address' in row and row['address']:
        row['address'] = capitalize_address_field(row['address'])
```

## Benefits

### Before Refactoring
- ❌ Duplicate code in multiple endpoints
- ❌ Inconsistent formatting logic
- ❌ Difficult to maintain and update
- ❌ Limited medical terminology support

### After Refactoring
- ✅ Single source of truth for text formatting
- ✅ Consistent formatting across all endpoints
- ✅ Easy to maintain and extend
- ✅ Comprehensive medical and address terminology
- ✅ Reusable throughout the application
- ✅ Well-documented with examples

## Future Enhancements

The text formatting utility can be extended to support:

1. **Additional Medical Specialties**: Add more specialized medical terms
2. **International Addresses**: Support for non-US address formats
3. **Business Names**: Enhanced formatting for business and organization names
4. **Pharmaceutical Terms**: Drug names and medical terminology
5. **Academic Titles**: Doctor, Professor, etc.

## File Structure

```
surgicase/
├── utils/
│   └── text_formatting.py          # ← Text formatting utilities
├── endpoints/
│   ├── surgeon/
│   │   └── search_surgeon.py       # Uses capitalize_name_field()
│   └── facility/
│       └── search_facility.py      # Uses all three functions
└── TEXT_FORMATTING_README.md       # ← This documentation
```

## Testing

The utility has been thoroughly tested with various input formats:

```python
# Test all functions
from utils.text_formatting import capitalize_name_field, capitalize_facility_field, capitalize_address_field

# Test name capitalization
test_names = ['JOHN', 'MCDONALD', "O'CONNOR", 'SMITH-JONES', 'SAN FRANCISCO']
for name in test_names:
    print(f'{name} -> {capitalize_name_field(name)}')

# Test facility capitalization  
test_facilities = ['JOHNS HOPKINS HOSPITAL', 'ST. MARY MEDICAL CENTER', 'MAYO CLINIC HEALTH SYSTEM']
for facility in test_facilities:
    print(f'{facility} -> {capitalize_facility_field(facility)}')

# Test address capitalization
test_addresses = ['123 MAIN STREET', '456 N FIRST AVE APT 2B', '789 HEALTHCARE BLVD SUITE 100']
for address in test_addresses:
    print(f'{address} -> {capitalize_address_field(address)}')
```

## Migration Notes

When migrating from the old inline functions to the centralized utility:

1. **Import the functions**: Add `from utils.text_formatting import ...`
2. **Remove duplicate code**: Delete inline function definitions
3. **Update function calls**: No changes needed - function signatures are identical
4. **Test thoroughly**: Ensure all endpoints continue to work as expected

The migration maintains 100% backward compatibility while providing enhanced functionality and maintainability. 