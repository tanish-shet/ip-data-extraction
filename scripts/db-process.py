import argparse
import subprocess
import re
import csv
import sys
import os
import json

def load_database(db_folderpath):
    """
    Loads all JSON files from a directory into a list of dictionaries 
    to facilitate cross-database comparison.
    """
    all_databases = []
    
    if not os.path.isdir(db_folderpath):
        print(f"Error: {db_folderpath} is not a valid directory.")
        return all_databases

    # Sort files to ensure consistent order during DFS traversal/comparison
    filenames = sorted([f for f in os.listdir(db_folderpath) if f.endswith('.json')])

    for filename in filenames:
        filepath = os.path.join(db_folderpath, filename)
        try:
            with open(filepath, 'r') as f:
                all_databases.append(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error: Skipping {filename} due to load error: {e}")
                
    return all_databases

def db_compare_arc(databases, start_pin, visited=None, depth=0): #start pin may later be a list of starpins instead od single element
    """
    Validates path integrity and prints the specific arc links being traced.
    """
    if visited is None:
        visited = set()

    indent = "  " * depth

    if start_pin == "N/A":
        return True
    
    if start_pin in visited:
        print(f"{indent}--> {start_pin} (Already visited, skipping)")
        return True
    
    # check if the pin exists as a key in the DBs
    if not any(start_pin in db for db in databases):
        print(f"{indent}[RELATED_PIN] {start_pin}")
        return True

    print(f"{indent}PIN: {start_pin}")
    visited.add(start_pin)

    # sanity check for start pin consistency
    if not all(start_pin in db for db in databases):
        print(f"{indent}  [!] ERROR: Key '{start_pin}' missing in some DBs.")
        return False

    all_arc_lists = [db[start_pin] for db in databases]

    if len(set(len(l) for l in all_arc_lists)) > 1:
        print(f"{indent}  [!] ERROR: Arc count mismatch at {start_pin}")
        return False

    # iterate through each timing arc for this pin
    for i, arc_list in enumerate(zip(*all_arc_lists)):
        # arc_list is a tuple of the i-th arc from each database
        related_pins = [arc.get("related_pin") for arc in arc_list]
        next_pin = related_pins[0]

        # verification of arc count for given pin
        if len(set(related_pins)) > 1:
            print(f"{indent}  [!] ARC MISMATCH at index {i}: {related_pins}")
            return False

        # print the trace for this specific arc
        print(f"{indent}  [Arc {i}] {start_pin} ---> {next_pin}")

        # recurse for related_pin arc
        if next_pin and next_pin != "N/A":
            if not db_compare_arc(databases, next_pin, visited, depth + 1):
                return False

    return True

def attribute_validate():
    #fxn to check if a given attribute for a given pin is valid/ NA/ or if even the pin is a parent_pin (not a leaf_node to another pin) or a related_pin
    pass


def attribute_retrival():

    pass

def attribute_spread():
    pass
def main():
    parser = argparse.ArgumentParser(description="Automated Timing Database Comparison Tool")
    
    # Arguments
    parser.add_argument("folderpath", help="Path to the directory containing JSON database files")    
    parser.add_argument("--compare", action="store_true", help="Enable structural path tracing across all databases")    
    parser.add_argument("--arc", nargs="+", help="The starting pin(s) to begin the DFS traversal")    
    parser.add_argument("--spread", nargs="+", help="Attribute names to check for numerical spread (e.g., setup_rise)")

    args = parser.parse_args()

    # load all databases from the folder
    all_dbs = load_database(args.folderpath)
    
    if not all_dbs:
        print("Error: No valid JSON databases found in the specified directory.")
        sys.exit(1)

    print(f"Successfully loaded {len(all_dbs)} database(s).")

    # execute comparison/ trace Logic
    if args.compare:
        if not args.arc:
            print("Error: --compare requires at least one starting pin via --arc.")
            sys.exit(1)

        print("\n" + "="*50)
        print("STARTING PATH INTEGRITY CHECK")
        print("="*50)

        overall_success = True
        
        for start_pin in args.arc:
            print(f"\n--- Tracing Arc Chain for: {start_pin} ---")
            
            # initialize a fresh visited set for every starting arc
            # initial depth is 0 for proper indentation
            is_consistent = db_compare_arc(all_dbs, start_pin, visited=set(), depth=0)
            
            if not is_consistent:
                overall_success = False
                print(f"\nResult: [FAILED] Path discrepancy found starting at {start_pin}")
            else:
                print(f"\nResult: [PASSED] Path is consistent across all DBs for {start_pin}")

        print("\n" + "="*50)
        if overall_success:
            print("ALL PATHS CONSISTENT")
        else:
            print("STRUCTURAL MISMATCH DETECTED")
        print("="*50)

    '''# 3. Placeholder for future spread logic
    if args.spread:
        # This will be called once attribute_spread is implemented
        print("\nSpread analysis requested for:", args.spread)
        # attribute_spread(all_dbs, args.arc, args.spread)'''

if __name__ == "__main__":
    main()

    
