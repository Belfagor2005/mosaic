#!/usr/bin/env python3
"""
UNIVERSAL translation update script for Enigma2 plugins.
Supports multiple directory structures including Mosaic and M3UConverter.
"""

import os
import re
import sys
import subprocess
import shutil
from pathlib import Path

# ===== CONFIGURATION =====
# Get plugin name from environment or use default
PLUGIN_NAME = os.environ.get('PLUGIN_NAME', 'Mosaic')

# If plugin name contains path, extract just the name
if '/' in PLUGIN_NAME:
    PLUGIN_NAME = Path(PLUGIN_NAME).name

print("=" * 70)
print(f"PLUGIN NAME: {PLUGIN_NAME}")
print("=" * 70)

# ===== 1. DETECT PLUGIN STRUCTURE =====
def detect_plugin_structure():
    """Detect where the plugin files are located"""
    
    print("\n1. Detecting plugin structure...")
    
    # Possible plugin root locations (in order of preference)
    possible_roots = [
        Path("src"),                      # Mosaic structure
        Path("."),                        # Root directory
        Path("usr/lib/enigma2/python/Plugins/Extensions"),  # M3UConverter structure
    ]
    
    plugin_dir = None
    plugin_root = None
    
    for root in possible_roots:
        if not root.exists():
            continue
            
        # Check if this looks like a plugin directory
        # Option 1: Directory with plugin name exists
        plugin_path = root / PLUGIN_NAME
        if plugin_path.exists():
            plugin_dir = plugin_path
            plugin_root = root
            print(f"✓ Found plugin directory: {plugin_dir}")
            break
            
        # Option 2: Directory contains setup.xml or plugin.py directly
        setup_files = list(root.glob("setup*.xml"))
        py_files = list(root.glob("*.py"))
        if setup_files or py_files:
            plugin_dir = root
            plugin_root = root.parent if root != Path(".") else root
            print(f"✓ Found plugin files directly in: {plugin_dir}")
            break
    
    if not plugin_dir:
        print(f"ERROR: Could not find plugin '{PLUGIN_NAME}'")
        print("Searched in:")
        for root in possible_roots:
            print(f"  • {root}")
        sys.exit(1)
    
    return plugin_dir, plugin_root

# Detect structure
PLUGIN_DIR, PLUGIN_ROOT = detect_plugin_structure()

# ===== 2. FIND LOCALE DIRECTORY =====
def find_locale_directory():
    """Find locale directory based on detected structure"""
    
    print("\n2. Finding locale directory...")
    
    # Try standard locations
    possible_locations = [
        PLUGIN_DIR / "locale",
        PLUGIN_DIR / "po",
        PLUGIN_ROOT / "po",                # For Mosaic: ../po from src/
        Path(".") / "po",                  # po in repository root
        PLUGIN_DIR / "locales",
        PLUGIN_DIR / "translations",
    ]
    
    for loc in possible_locations:
        if loc.exists():
            print(f"✓ Found locale at: {loc}")
            return loc
    
    # Search recursively
    print("Searching recursively...")
    for root, dirs, _ in os.walk(PLUGIN_DIR):
        for dir_name in dirs:
            if dir_name.lower() in ['locale', 'locales', 'po', 'translations', 'i18n']:
                locale_path = Path(root) / dir_name
                print(f"✓ Found locale at: {locale_path}")
                return locale_path
    
    # Create default
    print("No locale directory found, creating default...")
    locale_dir = PLUGIN_DIR / "locale"
    locale_dir.mkdir(parents=True, exist_ok=True)
    return locale_dir

LOCALE_DIR = find_locale_directory()

# ===== 3. DETERMINE POT FILE LOCATION =====
def find_pot_file():
    """Find or create POT file"""
    
    # First check in locale directory
    pot_in_locale = LOCALE_DIR / f"{PLUGIN_NAME}.pot"
    if pot_in_locale.exists():
        print(f"✓ Found POT file: {pot_in_locale}")
        return pot_in_locale
    
    # Check in po directory
    po_dir = Path(".") / "po"
    if po_dir.exists():
        pot_in_po = po_dir / f"{PLUGIN_NAME}.pot"
        if pot_in_po.exists():
            print(f"✓ Found POT file: {pot_in_po}")
            return pot_in_po
        
        # Check for any .pot file in po directory
        pot_files = list(po_dir.glob("*.pot"))
        if pot_files:
            print(f"✓ Using existing POT: {pot_files[0]}")
            return pot_files[0]
    
    # Create new in locale directory
    print(f"Creating new POT file: {pot_in_locale}")
    return pot_in_locale

POT_FILE = find_pot_file()
print(f"Using POT file: {POT_FILE}")

# ===== 4. VERIFY STRUCTURE =====
def check_structure():
    """Verify plugin structure"""
    
    if not PLUGIN_DIR.exists():
        print(f"ERROR: Plugin directory not found: {PLUGIN_DIR}")
        return False
    
    print(f"✓ Plugin directory: {PLUGIN_DIR}")
    
    # Check for setup.xml
    setup_files = list(PLUGIN_DIR.glob("setup*.xml"))
    if setup_files:
        print(f"✓ Found {len(setup_files)} setup XML file(s)")
    else:
        print("No setup.xml files found")
    
    # Check Python files
    py_files = list(PLUGIN_DIR.rglob("*.py"))
    print(f"✓ Found {len(py_files)} Python file(s)")
    
    return True

# ===== 5. EXTRACT FROM SETUP.XML =====
def extract_from_xml():
    """Extract strings from setup.xml files"""
    
    strings = set()
    setup_files = list(PLUGIN_DIR.glob("setup*.xml"))
    
    if not setup_files:
        print("No setup XML files found")
        return []
    
    print(f"\n3. Extracting from {len(setup_files)} XML file(s)...")
    
    for xml_file in setup_files:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            extracted = 0
            for elem in root.iter():
                for attr in ['text', 'description', 'title', 'caption', 'value']:
                    if attr in elem.attrib:
                        text = elem.attrib[attr].strip()
                        if text and text not in ["None", ""]:
                            if not re.match(r'^#[0-9a-fA-F]{6,8}$', text):
                                strings.add(text)
                                extracted += 1
            
            print(f"  {xml_file.name}: {extracted} strings")
        except Exception as e:
            print(f"  ERROR parsing {xml_file}: {e}")
    
    print(f"✓ Total XML strings: {len(strings)}")
    return sorted(strings)

# ===== 6. EXTRACT FROM PYTHON FILES =====
def extract_from_python():
    """Extract strings from Python files"""
    
    py_files = list(PLUGIN_DIR.rglob("*.py"))
    
    if not py_files:
        print("No Python files found")
        return []
    
    print(f"\n4. Extracting from {len(py_files)} Python file(s)...")
    
    original_cwd = os.getcwd()
    os.chdir(PLUGIN_DIR)
    
    try:
        temp_pot = Path("temp_py.pot")
        cmd = [
            'xgettext',
            '--no-wrap',
            '-L', 'Python',
            '--from-code=UTF-8',
            '-o', str(temp_pot),
        ] + [str(f.relative_to(PLUGIN_DIR)) for f in py_files]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0 and "warning" not in result.stderr.lower():
            print(f"xgettext warning: {result.stderr[:200]}")
        
        strings = set()
        if temp_pot.exists():
            with open(temp_pot, 'r', encoding='utf-8') as f:
                content = f.read()
                for match in re.finditer(r'msgid "([^"]+)"', content):
                    text = match.group(1)
                    if text and text.strip() and text not in ['""', '']:
                        strings.add(text.strip())
            
            temp_pot.unlink()
        
        print(f"✓ Python strings: {len(strings)}")
        return sorted(strings)
        
    except Exception as e:
        print(f"ERROR with xgettext: {e}")
        return []
    finally:
        os.chdir(original_cwd)

# ===== 7. UPDATE .POT FILE =====
def update_pot_file(xml_strings, py_strings):
    """Update POT file with new strings"""
    
    all_strings = sorted(set(xml_strings + py_strings))
    
    if not all_strings:
        print("No strings to process")
        return 0
    
    # Ensure directory exists
    POT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Read existing strings
    existing_strings = set()
    if POT_FILE.exists():
        with open(POT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            for match in re.finditer(r'msgid "([^"]+)"', content):
                existing_strings.add(match.group(1))
    
    # Find new strings
    new_strings = [s for s in all_strings if s not in existing_strings]
    
    if not new_strings:
        print("No new strings for .pot file")
        return 0
    
    print(f"\n5. Adding {len(new_strings)} new strings to {POT_FILE.name}...")
    
    # Append new strings
    with open(POT_FILE, 'a', encoding='utf-8') as f:
        f.write('\n# New strings\n')
        for text in new_strings:
            escaped = text.replace('"', '\\"')
            f.write(f'\nmsgid "{escaped}"\n')
            f.write('msgstr ""\n')
    
    return len(new_strings)

# ===== 8. FIND ALL .PO FILES =====
def find_all_po_files():
    """Find all PO files in the project"""
    
    print("\n6. Finding all .po files...")
    
    po_files = []
    
    # Search in common locations
    search_locations = [
        Path(".") / "po",                     # Repository root /po
        LOCALE_DIR,                           # Main locale directory
        Path(".") / "src" / "locale",         # Mosaic structure
        PLUGIN_DIR / "locale",                # Plugin locale directory
    ]
    
    for location in search_locations:
        if location.exists():
            print(f"  Searching in: {location}")
            found = list(location.rglob("*.po"))
            po_files.extend(found)
            if found:
                for f in found[:3]:  # Show first 3
                    print(f"    • {f.relative_to(Path('.'))}")
                if len(found) > 3:
                    print(f"    ... and {len(found) - 3} more")
    
    # Remove duplicates (same file found in multiple locations)
    unique_files = []
    seen_paths = set()
    
    for po_file in po_files:
        real_path = po_file.resolve()
        if real_path not in seen_paths:
            seen_paths.add(real_path)
            unique_files.append(po_file)
    
    print(f"✓ Found {len(unique_files)} unique .po files")
    return unique_files

# ===== 9. UPDATE .PO FILES =====
def update_po_files():
    """Update all PO files with msgmerge"""
    
    if not POT_FILE.exists():
        print("ERROR: .pot file not found")
        return 0
    
    po_files = find_all_po_files()
    
    if not po_files:
        print("No .po files found")
        return 0
    
    print(f"\n7. Updating {len(po_files)} .po file(s)...")
    
    updated = 0
    for po_file in po_files:
        try:
            # Get language code
            lang = po_file.stem if po_file.stem != PLUGIN_NAME else po_file.parent.parent.name
            
            print(f"  Updating {lang}...", end=" ")
            
            cmd = [
                'msgmerge',
                '--update',
                '--backup=none',
                '--no-wrap',
                '--sort-output',
                str(po_file),
                str(POT_FILE)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✓")
                updated += 1
            else:
                print(f"✗")
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    return updated

# ===== 10. SYNC PO FILES BETWEEN DIRECTORIES =====
def sync_po_files():
    """Sync PO files between /po and locale structures"""
    
    print("\n8. Syncing PO files between directories...")
    
    # Find all PO files again
    po_files = find_all_po_files()
    
    # Group by language
    files_by_lang = {}
    for po_file in po_files:
        if po_file.name == f"{PLUGIN_NAME}.po":
            lang = po_file.parent.parent.name
        else:
            lang = po_file.stem
        files_by_lang.setdefault(lang, []).append(po_file)
    
    synced = 0
    for lang, files in files_by_lang.items():
        if len(files) > 1:
            # Multiple files for same language, sync them
            source_file = files[0]
            for target_file in files[1:]:
                if source_file != target_file:
                    try:
                        shutil.copy2(source_file, target_file)
                        print(f"  Synced {lang}: {source_file.name} → {target_file.relative_to(Path('.'))}")
                        synced += 1
                    except Exception as e:
                        print(f"  Error syncing {lang}: {e}")
    
    if synced > 0:
        print(f"✓ Synced {synced} file(s)")
    else:
        print("✓ No sync needed")
    
    return synced

# ===== 11. COMPILE .MO FILES =====
def compile_mo_files():
    """Compile PO files to MO files"""
    
    po_files = find_all_po_files()
    
    if not po_files:
        print("No .po files to compile")
        return 0
    
    print(f"\n9. Compiling {len(po_files)} .po file(s) to .mo...")
    
    compiled = 0
    for po_file in po_files:
        try:
            mo_file = po_file.with_suffix('.mo')
            lang = po_file.stem if po_file.stem != PLUGIN_NAME else po_file.parent.parent.name
            
            print(f"  Compiling {lang}...", end=" ")
            
            cmd = ['msgfmt', '-o', str(mo_file), str(po_file)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                file_size = mo_file.stat().st_size if mo_file.exists() else 0
                print(f"✓ ({file_size} bytes)")
                compiled += 1
            else:
                print(f"✗")
                
        except Exception as e:
            print(f"✗ Error: {e}")
    
    return compiled

# ===== 12. MAIN FUNCTION =====
def main():
    """Main execution function"""
    
    print("\n" + "=" * 70)
    print(f"TRANSLATION UPDATE FOR: {PLUGIN_NAME}")
    print("=" * 70)
    
    # 1. Check structure
    if not check_structure():
        sys.exit(1)
    
    # 2. Extract strings
    xml_strings = extract_from_xml()
    py_strings = extract_from_python()
    
    # 3. Update POT file
    new_strings = update_pot_file(xml_strings, py_strings)
    
    # 4. Update PO files
    updated_po = update_po_files()
    
    # 5. Sync files between directories
    sync_po_files()
    
    # 6. Compile MO files
    compiled_mo = compile_mo_files()
    
    print("\n" + "=" * 70)
    print("TRANSLATION UPDATE COMPLETED")
    print("-" * 70)
    print(f"Plugin:          {PLUGIN_NAME}")
    print(f"Plugin dir:      {PLUGIN_DIR}")
    print(f"New strings:     {new_strings}")
    print(f"Updated .po:     {updated_po}")
    print(f"Compiled .mo:    {compiled_mo}")
    print("=" * 70)

if __name__ == "__main__":
    main()