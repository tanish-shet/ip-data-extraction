import argparse
import subprocess
import re #optional if regex patterns being scanned -ma delete
import sys
import os
import json
import matplotlib.pyplot as plt

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

def db_compare_arc(databases, start_pin, visited=None, depth=0):
    """Compare arc/path consistency across databases"""
    if visited is None:
        visited = set()
    indent = "  " * depth

    # Handle N/A pins
    if start_pin == "N/A":
        return True
    
    # Check if the pin exists in any database
    pin_exists_anywhere = any(start_pin in db for db in databases)
    
    # If the pin doesn't exist...
    if not pin_exists_anywhere:
        if len(visited) == 0:
            # Case A: User gave an invalid starting pin
            print(f"[!] ERROR: Starting pin '{start_pin}' is invalid (not found in any DB).")
            return False
        else:
            # Case B: Reached a terminal related_pin (standard leaf node)
            print(f"{indent}[RELATED_PIN] {start_pin}")
            return True

    # Prevent infinite traversal
    if start_pin in visited:
        print(f"{indent}PIN: {start_pin} (Already visited, skipping)")
        return True

    # Consistency check: verify if given start_pin is in ALL databases
    if not all(start_pin in db for db in databases):
        print(f"{indent}PIN: {start_pin}")
        print(f"{indent}  [!] ERROR: Structural Mismatch. Pin missing in some DBs.")
        return False

    print(f"{indent}PIN: {start_pin}")
    visited.add(start_pin)

    # Get all arc lists for this pin from all databases
    all_arc_lists = [db[start_pin] for db in databases]
    
    # Check if all databases have the same number of arcs
    num_arcs_per_db = []
    for db_arcs in all_arc_lists:
        num_arcs_per_db.append(len(db_arcs))
    
    first_count = num_arcs_per_db[0]
    all_same_count = True
    for count in num_arcs_per_db:
        if count != first_count:
            all_same_count = False
            break
    
    if not all_same_count:
        print(f"{indent}  [!] ERROR: Arc count mismatch.")
        print(f"{indent}      Arc counts: {num_arcs_per_db}")
        return False

    # Get the number of arcs (they're all the same at this point)
    num_arcs = len(all_arc_lists[0])

    # Check each arc position
    for arc_index in range(num_arcs):
        # Collect all related_pins at this arc position
        pins_at_this_arc = []
        for db_arcs in all_arc_lists:
            pin = db_arcs[arc_index].get("related_pin")
            pins_at_this_arc.append(pin)
        
        # Check if they're all the same
        first_pin = pins_at_this_arc[0]
        all_same = True
        
        for pin in pins_at_this_arc:
            if pin != first_pin:
                all_same = False
                break
        
        if not all_same:
            print(f"{indent}  [!] PATH MISMATCH at arc {arc_index}")
            print(f"{indent}      Found: {pins_at_this_arc}")
            return False
        
        # All databases agree on this arc
        next_pin = first_pin
        print(f"{indent}  [Arc {arc_index}] {start_pin} ---> {next_pin}")
        
        # Recurse if needed
        if next_pin and next_pin != "N/A":
            if not db_compare_arc(databases, next_pin, visited, depth + 1):
                return False
        else:
            print(f"{indent}    [RELATED_PIN] N/A")

    return True



def attribute_retrieval(databases, start_pin, target_attribute):
    """
    Extracts raw data. Values are converted to float where possible.
    Returns: { db_index: [ {related_pin, mode, value}, ... ] }
    """
    raw_results = {}
    for idx, db in enumerate(databases):
        arcs = db.get(start_pin)
        if arcs is None:
            raw_results[idx] = None
            continue
        
        db_arcs = []
        for arc in arcs:
            val = arc.get(target_attribute, "N/A")
            # Convert to float for math; use None for non-numeric data
            try:
                num_val = float(val)
            except (ValueError, TypeError):
                num_val = None
                
            db_arcs.append({
                "related_pin": arc.get("related_pin", "N/A"),
                "mode": arc.get("mode", "N/A"),
                "value": num_val
            })
        raw_results[idx] = db_arcs
    return raw_results

#fxn to print retrieed attributes
def attribute_print_pretty(data_map, start_pin, target_attribute):
    print(f"\nAttribute Retrieval for Pin: {start_pin}")
    print(f"Target Attribute: {target_attribute}")

    for db_idx, arcs in data_map.items():
        print(f"\n---- DB Index: {db_idx} ----")
        
        if arcs is None:
            print(f"  [!] Pin '{start_pin}' not found in this database.")
            continue

        for i, arc in enumerate(arcs):
            # print format: arc i {related_pin | mode}
            print(f"  Arc {i} {{{arc['related_pin']} | {arc['mode']}}}")
            print(f"    {target_attribute} : {arc['value']}")



def attribute_spread(databases, start_pin, target_attribute):

    #Fetch data using retrieval function
    data_map = attribute_retrieval(databases, start_pin, target_attribute)
    
    #Extract valid numerical values for analysis
    numeric_values = [
        arc["value"] for arcs in data_map.values() 
        if arcs for arc in arcs if arc["value"] is not None
    ]

    if not numeric_values:
        print(f"[!] No valid numerical data found for '{target_attribute}' on pin '{start_pin}'.")
        return

    #Stats Calculation
    v_min, v_max = min(numeric_values), max(numeric_values)
    v_spread = v_max - v_min

    print(f"\n" + "="*40)
    print(f"SPREAD ANALYSIS: {start_pin}")
    print(f"Attribute: {target_attribute}")
    print("-" * 40)
    print(f"Minimum Value: {v_min:.6f}")
    print(f"Maximum Value: {v_max:.6f}")
    print(f"Total Spread:  {v_spread:.6f}")
    print("="*40 + "\n")

    #Histogram Generation
    plt.figure(figsize=(10, 6))
    plt.hist(numeric_values, bins='auto', color='#3498db', edgecolor='black', alpha=0.8)
    
    # Visual cues: vertical lines for Min/Max
    plt.axvline(v_min, color='red', linestyle='dashed', linewidth=1, label=f'Min: {v_min:.4f}')
    plt.axvline(v_max, color='green', linestyle='dashed', linewidth=1, label=f'Max: {v_max:.4f}')
    
    plt.title(f"Histogram of {target_attribute}\nPin: {start_pin}")
    plt.xlabel("Attribute Value")
    plt.ylabel("Frequency (Arc Occurrences)")
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Automated Timing Database Comparison Tool")
    parser.add_argument("folderpath", help="Path to the directory containing JSON database files")
    parser.add_argument("--compare", action="store_true", help="Enable structural path tracing")    
    parser.add_argument("--pins", nargs="+", help="The starting pin(s) to begin the DFS traversal")    
    parser.add_argument("--all", action="store_true", help="Process all parent pins from the reference DB")
    parser.add_argument("--get_attribute", help=" to fetch values across PVTX db for a given attribue type")
    parser.add_argument("--spread", action="store_true", help="Flag to trigger spread/histogram analysis")
    args = parser.parse_args()

    # load Data
    all_dbs = load_database(args.folderpath)
    if not all_dbs:
        print("Error: No valid JSON databases found.")
        sys.exit(1)

    print(f"Successfully loaded {len(all_dbs)} database(s).")
    ref_db = all_dbs[0]

    # pin selection Logic - either select all pins (when --all) else just those mentioned with --arc option
    target_pins = [] 
    if args.all:
        print("Mode: Tracing ALL pins from reference database.")
        target_pins = list(ref_db.keys())
    elif args.pins:
        target_pins = args.pins

    # comparison of timing arc relations across DBs
    if args.compare:
        if not target_pins:
            print("Error: --compare requires either --pins or --all.")
            sys.exit(1)

        overall_trace_success = True
        global_visited = set()  # avoid re-tracing shared paths
            
        print("\n" + "="*50)
        print("STARTING PATH INTEGRITY CHECK")
        print("="*50)

        for start_pin in target_pins:
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

    #spread analysis
    elif args.spread:
        if not args.pins or not args.get_attribute:
            sys.exit("Error: --spread requires --pin and --get_attribute.")
        for p in args.pins:
            attribute_spread(all_dbs, p, args.get_attribute)
    
    # attribute retrieval
    elif args.pins and args.get_attribute:
        for pin in args.pins:
            results = attribute_retrieval(all_dbs, pin, args.get_attribute)
            attribute_print_pretty(results, pin, args.get_attribute)

if __name__ == "__main__":
    main()

    
