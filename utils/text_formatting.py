# Created: 2025-07-23
# Last Modified: 2025-08-28 20:16:23
# Author: Scott Cadreau

# utils/text_formatting.py
"""
Text formatting utilities for proper capitalization of names, facilities, and addresses.
Provides consistent text formatting across the application.
"""

def capitalize_name_field(name_str: str) -> str:
    """
    Properly capitalize an individual name field or multi-word location.
    Handles common name prefixes, hyphenated names, and multi-word locations.
    
    Args:
        name_str: The name or location string to capitalize
        
    Returns:
        Properly capitalized string
        
    Examples:
        capitalize_name_field("JOHN") -> "John"
        capitalize_name_field("MCDONALD") -> "McDonald"
        capitalize_name_field("O'CONNOR") -> "O'Connor"
        capitalize_name_field("SMITH-JONES") -> "Smith-Jones"
        capitalize_name_field("SAN FRANCISCO") -> "San Francisco"
    """
    if not name_str:
        return name_str
    
    name_str = name_str.strip()
    
    def fix_special_casing(word):
        # Handles common name prefixes
        word = word.lower()
        if word.startswith("mc") and len(word) > 2:
            return "Mc" + word[2:].capitalize()
        if word.startswith("mac") and len(word) > 3:
            return "Mac" + word[3:].capitalize()
        if "'" in word:
            return "'".join([w.capitalize() for w in word.split("'")])
        return word.capitalize()
    
    def fix_hyphenated(part):
        # Proper-case each hyphenated sub-part
        return '-'.join(fix_special_casing(p) for p in part.split('-'))

    # Handle multi-word strings (like city names)
    if ' ' in name_str:
        words = name_str.split()
        return ' '.join(fix_hyphenated(word) for word in words)
    else:
        return fix_hyphenated(name_str)


def capitalize_facility_field(facility_str: str) -> str:
    """
    Properly capitalize facility names and addresses.
    Handles facility-specific formatting like medical centers, hospitals, etc.
    
    Args:
        facility_str: The facility name or address string to capitalize
        
    Returns:
        Properly capitalized string
        
    Examples:
        capitalize_facility_field("JOHNS HOPKINS HOSPITAL") -> "Johns Hopkins Hospital"
        capitalize_facility_field("ST. MARY MEDICAL CENTER") -> "St. Mary Medical Center"
        capitalize_facility_field("MAYO CLINIC HEALTH SYSTEM") -> "Mayo Clinic Health System"
    """
    if not facility_str:
        return facility_str
    
    facility_str = facility_str.strip()
    
    # Common medical facility words that should be title case
    medical_words = {
        'hospital': 'Hospital',
        'medical': 'Medical', 
        'center': 'Center',
        'centre': 'Centre',
        'clinic': 'Clinic',
        'health': 'Health',
        'care': 'Care',
        'surgery': 'Surgery',
        'surgical': 'Surgical',
        'institute': 'Institute',
        'foundation': 'Foundation',
        'associates': 'Associates',
        'group': 'Group',
        'practice': 'Practice',
        'department': 'Department',
        'university': 'University',
        'regional': 'Regional',
        'community': 'Community',
        'general': 'General',
        'memorial': 'Memorial',
        'children': 'Children',
        'pediatric': 'Pediatric',
        'women': 'Women',
        'specialty': 'Specialty',
        'outpatient': 'Outpatient',
        'ambulatory': 'Ambulatory',
        'rehabilitation': 'Rehabilitation',
        'rehab': 'Rehab',
        'emergency': 'Emergency',
        'urgent': 'Urgent',
        'family': 'Family',
        'internal': 'Internal',
        'medicine': 'Medicine',
        'orthopedic': 'Orthopedic',
        'cardiology': 'Cardiology',
        'neurology': 'Neurology',
        'oncology': 'Oncology',
        'radiology': 'Radiology',
        'pathology': 'Pathology',
        'laboratory': 'Laboratory',
        'lab': 'Lab',
        'pharmacy': 'Pharmacy',
        'therapies': 'Therapies',
        'therapy': 'Therapy',
        'wellness': 'Wellness',
        'diagnostics': 'Diagnostics',
        'imaging': 'Imaging'
    }
    
    # Split into words and process each
    words = facility_str.lower().split()
    capitalized_words = []
    
    for word in words:
        # Remove punctuation for checking but preserve it
        clean_word = word.strip('.,!?;:()[]{}')
        punctuation = word[len(clean_word):]
        
        if clean_word in medical_words:
            capitalized_words.append(medical_words[clean_word] + punctuation)
        else:
            # Use the same logic as name fields for other words
            capitalized_words.append(capitalize_name_field(clean_word) + punctuation)
    
    return ' '.join(capitalized_words)


def capitalize_address_field(address_str: str) -> str:
    """
    Properly capitalize address fields.
    Handles street names, directions, and common address components.
    
    Args:
        address_str: The address string to capitalize
        
    Returns:
        Properly capitalized address string
        
    Examples:
        capitalize_address_field("123 MAIN STREET") -> "123 Main Street"
        capitalize_address_field("456 N FIRST AVE APT 2B") -> "456 N First Ave Apt 2b"
    """
    if not address_str:
        return address_str
    
    address_str = address_str.strip()
    
    # Common address words and their proper capitalization
    address_words = {
        'street': 'Street',
        'st': 'St',
        'avenue': 'Avenue', 
        'ave': 'Ave',
        'road': 'Road',
        'rd': 'Rd',
        'drive': 'Drive',
        'dr': 'Dr',
        'lane': 'Lane',
        'ln': 'Ln',
        'boulevard': 'Boulevard',
        'blvd': 'Blvd',
        'circle': 'Circle',
        'cir': 'Cir',
        'court': 'Court',
        'ct': 'Ct',
        'place': 'Place',
        'pl': 'Pl',
        'way': 'Way',
        'parkway': 'Parkway',
        'pkwy': 'Pkwy',
        'suite': 'Suite',
        'ste': 'Ste',
        'apartment': 'Apartment',
        'apt': 'Apt',
        'unit': 'Unit',
        'floor': 'Floor',
        'fl': 'Fl',
        'building': 'Building',
        'bldg': 'Bldg',
        'north': 'North',
        'n': 'N',
        'south': 'South',
        's': 'S',
        'east': 'East',
        'e': 'E',
        'west': 'West',
        'w': 'W',
        'northeast': 'Northeast',
        'ne': 'NE',
        'northwest': 'Northwest',
        'nw': 'NW',
        'southeast': 'Southeast',
        'se': 'SE',
        'southwest': 'Southwest',
        'sw': 'SW'
    }
    
    # Split into words and process each
    words = address_str.lower().split()
    capitalized_words = []
    
    for word in words:
        # Remove punctuation for checking but preserve it
        clean_word = word.strip('.,!?;:()[]{}')
        punctuation = word[len(clean_word):]
        
        # Check if it's a number (keep as-is)
        if clean_word.isdigit():
            capitalized_words.append(word)
        elif clean_word in address_words:
            capitalized_words.append(address_words[clean_word] + punctuation)
        else:
            # Use name field logic for other words
            capitalized_words.append(capitalize_name_field(clean_word) + punctuation)
    
    return ' '.join(capitalized_words)


def normalize_email_for_tier_lookup(email: str) -> str:
    """
    Extract the base email address by removing any "+tag" portion for tier lookup purposes.
    This allows users with tagged emails (e.g., user+tag@domain.com) to inherit the tier
    from their base email address (user@domain.com).
    
    Args:
        email: The email address to normalize
        
    Returns:
        The base email address with any "+tag" portion removed
        
    Examples:
        normalize_email_for_tier_lookup("pamela.burford+scott@palmsurgicalbilling.com") 
        -> "pamela.burford@palmsurgicalbilling.com"
        
        normalize_email_for_tier_lookup("john.doe+provider1@clinic.com") 
        -> "john.doe@clinic.com"
        
        normalize_email_for_tier_lookup("admin+test+dev@hospital.org") 
        -> "admin@hospital.org"
        
        normalize_email_for_tier_lookup("regular@email.com") 
        -> "regular@email.com" (unchanged)
    """
    if not email or '@' not in email:
        return email
    
    # Split email into local part (before @) and domain part (after @)
    try:
        local_part, domain_part = email.rsplit('@', 1)
        
        # If there's a + in the local part, remove everything from + onwards
        if '+' in local_part:
            base_local_part = local_part.split('+')[0]
            return f"{base_local_part}@{domain_part}"
        
        # If no + found, return original email
        return email
        
    except ValueError:
        # If email format is invalid, return as-is
        return email 