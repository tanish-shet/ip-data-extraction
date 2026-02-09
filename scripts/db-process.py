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

    # sort files to ensure consistent order during DFS traversal/comparison
    filenames = sorted([f for f in os.listdir(db_folderpath) if f.endswith('.json')])

    for filename in filenames:
        filepath = os.path.join(db_folderpath, filename)
        try:
            with open(filepath, 'r') as f:
                all_databases.append(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error: Skipping {filename} due to load error: {e}")
                
    return all_databases


def db_compare_arc(databases, start_pin, visited=None, depth=0): #fxn to compare arc/ path consistency across dbs
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

    # consistency check: to verify if given start_pin is in "ALL" databases files?
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


def attribute_retrieval(databases, start_pin, target_attribute):
    """
    Retrieves and prints a specific attribute for all arcs of a pin,
    organized by database index.
    """
    print(f"\nAttribute Retrieval for Pin: {start_pin}")
    print(f"Target Attribute: {target_attribute}")

    for idx, db in enumerate(databases):
        print(f"\n---- DB Index: {idx} ----")
        # fetch the list of dictionaries for the start_pin
        arcs = db.get(start_pin)    
        if arcs is None:
            print(f"  [!] Error: Pin '{start_pin}' not found in this database.")
            continue            
        # iterate through each arc (dictionary)
        for i, arc in enumerate(arcs):
            related_pin = arc.get("related_pin", "N/A")
            mode = arc.get("mode", "N/A")
            
            # retrieve the specific attribute value
            attr_value = arc.get(target_attribute, "NOT FOUND")
            
            # formatting the output as requested
            print(f"  Arc {i} {{{related_pin} | {mode}}}")
            print(f"    {target_attribute} : {attr_value}")

def attribute_spread():
    pass

def main():
    parser = argparse.ArgumentParser(description="Automated Timing Database Comparison Tool")
    parser.add_argument("folderpath", help="Path to the directory containing JSON database files")
    parser.add_argument("--compare", action="store_true", help="Enable structural path tracing")    
    parser.add_argument("--pins", nargs="+", help="The starting pin(s) to begin the DFS traversal")    
    parser.add_argument("--all", action="store_true", help="Process all parent pins from the reference DB")
    parser.add_argument("--get_attribute", help=" to fetch values across PVTX db for a given attribue type")
    parser.add_argument("--spread", nargs="+", help="Attribute names to check for numerical spread")
    args = parser.parse_args()

    # load Data
    all_dbs = load_database(args.folderpath)
    if not all_dbs:
        print("Error: No valid JSON databases found.")
        sys.exit(1)

    print(f"Successfully loaded {len(all_dbs)} database(s).")
    ref_db = all_dbs[0]

    # pin selection Logic - either select all pins (when --all) else just those mentioned with --arc option
    pins_to_trace = [] 
    if args.all:
        print("Mode: Tracing ALL pins from reference database.")
        pins_to_trace = list(ref_db.keys())
    elif args.pins:
        pins_to_trace = args.pins

    # comparison of timing arc relations across DBs
    if args.compare:
        if not pins_to_trace:
            print("Error: --compare requires either --pins or --all.")
            sys.exit(1)

        overall_trace_success = True
        global_visited = set()  # Avoid re-tracing shared paths
            
        print("\n" + "="*50)
        print("STARTING PATH INTEGRITY CHECK")
        print("="*50)

        for start_pin in pins_to_trace:
            # to be skipped if this pin was already covered as a sub-arc of a previous trace
            if start_pin not in global_visited:
                print(f"\n--- Tracing Arc Chain for: {start_pin} ---")                
                # use global_visited to mark every node in the path as "processed"
                is_consistent = db_compare_arc(all_dbs, start_pin, visited=global_visited, depth=0)
                
                if not is_consistent:
                    overall_trace_success = False
                    print(f"Result: [FAILED] Discrepancy found starting at {start_pin}") #might add debug path for failing/ inconsistent DB
                else:
                    print(f"Result: [PASSED] {start_pin} chain is consistent.")

        print("\n" + "="*50)
        print("ALL PATHS CONSISTENT" if overall_trace_success else "STRUCTURAL MISMATCH DETECTED")
        print("="*50)

    # attribute retrieval
    elif args.pins and args.get_attribute:
        for pin in args.pins:
            attribute_retrieval(all_dbs, pin, args.get_attribute)

    # placeholder
    if args.spread:
        # attribute_spread(all_dbs, pins_to_trace, args.spread)
        pass

if __name__ == "__main__":
    main()

    
