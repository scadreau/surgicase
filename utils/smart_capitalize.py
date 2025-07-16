# Created: 2025-07-16 11:24:30
# Last Modified: 2025-07-16 11:27:04

from nameparser import HumanName

def smart_capitalize(name_str: str) -> str:
    def fix_hyphenated(part):
        # Proper-case each hyphenated sub-part
        return '-'.join(p.capitalize() for p in part.split('-'))

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

    # Parse the name and auto-capitalize with nameparser
    human_name = HumanName(name_str)
    human_name.capitalize()

    # Fix individual components
    human_name.first = fix_hyphenated(fix_special_casing(human_name.first))
    human_name.middle = fix_hyphenated(fix_special_casing(human_name.middle))
    human_name.last = fix_hyphenated(fix_special_casing(human_name.last))
    human_name.suffix = human_name.suffix.upper()  # e.g., "jr" → "JR"

    return str(human_name) 