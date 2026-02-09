import argparse
import subprocess
import re #optional if regex patterns being scanned -ma delete
import sys
import os
import json

def load_database(db_folderpath):
    #fxn to load all db files (.json format) - returns a list of all .json files within target db folder
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

def db_compare_arc(databases, start_pin, visited=None, depth=0):
    if visited is None:
        visited = set()
    indent = "  " * depth

    if start_pin == "N/A":
        return True
    # check if the pin exists in any database
    pin_exists_anywhere = any(start_pin in db for db in databases)
    # if the pin doesn't exist...
    if not pin_exists_anywhere:
        if len(visited) == 0:
            # Case A: User gave an invalid starting pin
            print(f"[!] ERROR: Starting pin '{start_pin}' is invalid (not found in any DB).")
            return False
        else:
            # Case B:  reached a terminal related_pin (standard leaf node)
            print(f"{indent}[RELATED_PIN] {start_pin}")
            return True

    # to prevent infinite traversal
    if start_pin in visited:
        print(f"{indent}PIN: {start_pin} (Already visited, skipping)")
        return True

    # consistency Check: to verify if given start_pin is in ALL databases?
    if not all(start_pin in db for db in databases):
        print(f"{indent}PIN: {start_pin}")
        print(f"{indent}  [!] ERROR: Structural Mismatch. Pin missing in some DBs.")
        return False

    print(f"{indent}PIN: {start_pin}")
    visited.add(start_pin)

    all_arc_lists = [db[start_pin] for db in databases]
    if len(set(len(l) for l in all_arc_lists)) > 1:
        print(f"{indent}  [!] ERROR: Arc count mismatch.")
        return False

    for i, arc_group in enumerate(zip(*all_arc_lists)):
        related_pins = [arc.get("related_pin") for arc in arc_group]
        next_pin = related_pins[0]

        if len(set(related_pins)) > 1:
            print(f"{indent}  [!] PATH MISMATCH at arc {i}: {related_pins}")
            return False

        print(f"{indent}  [Arc {i}] {start_pin} ---> {next_pin}")

        if next_pin and next_pin != "N/A":
            if not db_compare_arc(databases, next_pin, visited, depth + 1):
                return False
        else:
            print(f"{indent}    [RELATED_PIN] N/A")

    return True

def attribute_retrival():

    pass

def attribute_spread():
    pass

def main():
    parser = argparse.ArgumentParser(description="Automated Timing Database Comparison Tool")
    #input arguments
    parser.add_argument("folderpath", help="Path to the directory containing JSON database files")    #mandatory argument
    parser.add_argument("--compare", action="store_true", help="Enable structural path tracing across all databases")    
    parser.add_argument("--arc", nargs="+", help="The starting pin(s) to begin the DFS traversal")    
    parser.add_argument("--all", action = "store_true", help = "Passes entire list of \"key\" \ \"parent\" pins to required fxn")
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

        overall_trace_success = True
        
        for start_pin in args.arc:
            print(f"\n--- Tracing Arc Chain for: {start_pin} ---")
            
            # initialize a fresh visited set for every starting arc & initial depth is 0 for proper indentation
            is_consistent = db_compare_arc(all_dbs, start_pin, visited=set(), depth=0)
            
            if not is_consistent:
                overall_trace_success = False
                print(f"\nResult: [FAILED] Path discrepancy found starting at {start_pin}")
            else:
                print(f"\nResult: [PASSED] Path is consistent across all DBs for {start_pin}")

        print("\n" + "="*50)
        if overall_trace_success:
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

    
