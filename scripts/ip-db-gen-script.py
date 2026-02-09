import argparse
import subprocess
import re
import csv
import sys
import os
import json

# default output directory
DEFAULT_DIR = "../extracted_data/pipecore-data"
# scratch/ dummy output directory
TEST_DIR = "../extracted_data/test-data"

def read_directory_list_file(directory_list_file):
    # reads a file containing a list of directory paths.
    if not os.path.exists(directory_list_file):
        print(f"Error: The manifest file '{directory_list_file}' was not found.")
        return []
    
    with open(directory_list_file, 'r') as f:
        # returns list of absolute paths, ignoring empty lines
        return [os.path.join(os.path.abspath(line.strip()), "") 
                for line in f if line.strip()]
    

#fxn to walk through directries in input arg directory list, fetch candidate files, create a list of such files to be passed to actual parse worker fxn
def create_file_list(directory_list): 

    # directory_list is just list of directories, returned by read_directory_list_file fxn
    file_list =  []
    for path in directory_list:
        if not os.path.isdir(path):
            print(f"Skipping: {path} (Not a directory)")
            continue
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith(".lib.gz"):
                    file_list.append(os.path.join(root, f))    
    return file_list 
  
def extract_values(raw_str):
    if not raw_str or raw_str == "N/A": return "N/A"
    clean = raw_str.replace('\\', ' ').replace('"', ' ').replace('\n', ' ')
    tokens = [t.strip() for t in re.split(r'[\s,]+', clean) if t.strip()]
    num_tokens = len(tokens)
    if num_tokens > 27:
        return tokens[27]  
    elif num_tokens > 3:
        return tokens[3]   
    '''else :
        return tokens [0]'''
    return "N/A"

#fxn to parse input lib file and yiedls a row_buffer ( a dictionary); with all the fields of interest as keys
def parse_lib(input_file):
    
    # Regex Patterns for required fields that need to be extracted from .lib
    re_pin = re.compile(r'pin\s*\(\s*"?([^"\)\s]+)"?\s*\)\s*\{', re.IGNORECASE)
    re_direction = re.compile(r'direction\s*:\s*([^;\s]+)\s*;', re.IGNORECASE)
    re_timing_open = re.compile(r'timing\s*\(\s*\)\s*\{', re.IGNORECASE)
    re_type = re.compile(r'timing_type\s*:\s*([^;\s]+)\s*;', re.IGNORECASE)
    re_related = re.compile(r'related_pin\s*:\s*"?([^";\s]+)"?\s*;', re.IGNORECASE)
    re_mode = re.compile(r'mode\s*\(.*?,\s*"([^"]+)"\)', re.IGNORECASE)
    re_sigma_type = re.compile(r'sigma_type\s*:\s*"?([^";\s]+)"?\s*;', re.IGNORECASE)
    re_min_flag = re.compile(r'min_delay_flag\s*:\s*([^;\s]+)\s*;', re.IGNORECASE)

    req_types = ["setup_rising", "setup_falling", "hold_rising", "hold_falling", "combinational", "rising_edge", "falling_edge"]
    base_tables = ["cell_rise", "cell_fall", "rise_constraint", "fall_constraint"]
    ocv_tables = ["ocv_sigma_cell_rise", "ocv_sigma_cell_fall", "ocv_sigma_rise_constraint", "ocv_sigma_fall_constraint"]
    acc_keys = base_tables + [f"{t}_early" for t in ocv_tables] + [f"{t}_late" for t in ocv_tables]

    cmd = ['zcat', input_file]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)

    current_pin = "N/A"
    current_direction = "N/A"
    row_buffer = {}
    in_timing = False
    bracket_depth = 0
    accumulator = {}
    capturing_values = False
    value_buffer = ""
    active_table_key = None
    pending_base_name = None

    for line in proc.stdout:
        raw_line = line.strip()
        if not raw_line: continue

        if not in_timing:
            pin_match = re_pin.search(raw_line)
            if pin_match: 
                current_pin = pin_match.group(1)
            
            dir_match = re_direction.search(raw_line)
            if dir_match:
                current_direction = dir_match.group(1).strip()

            if re_timing_open.search(raw_line):
                in_timing = True
                bracket_depth = 1
                accumulator = {k: "N/A" for k in acc_keys + ["related_pin", "mode", "timing_type", "min_delay_flag"]}
            continue

        bracket_depth += raw_line.count('{')
        bracket_depth -= raw_line.count('}')

        # capture timing_type, realted_pin, mode etc - that occur right after timing() block starts
        if "timing_type" in raw_line:
            tm = re_type.search(raw_line)
            if tm: accumulator["timing_type"] = tm.group(1).strip()
        if "related_pin" in raw_line:
            rm = re_related.search(raw_line)
            if rm: accumulator["related_pin"] = rm.group(1)
        if "mode" in raw_line:
            mm = re_mode.search(raw_line)
            if mm: accumulator["mode"] = mm.group(1).strip()
        if "min_delay_flag" in raw_line:
            mf = re_min_flag.search(raw_line)
            if mf: accumulator["min_delay_flag"] = mf.group(1).strip().lower()

        # Table logic (fxn to log sigma values based on argument is still  to be added)
        sigma_match = re_sigma_type.search(raw_line)
        if sigma_match and pending_base_name:
            active_table_key = f"{pending_base_name}_{sigma_match.group(1).strip()}"
        
        if not capturing_values:
            for t in ocv_tables + base_tables:
                if re.search(r'\b' + t + r'\s*\(', raw_line):
                    if t in ocv_tables: pending_base_name = t
                    else: active_table_key = t
                    break
        
        if active_table_key and "values (" in raw_line:
            capturing_values, value_buffer = True, raw_line.split("values (", 1)[1]
        elif capturing_values:
            value_buffer += " " + raw_line
        
        if capturing_values and ");" in raw_line:
            accumulator[active_table_key] = extract_values(value_buffer.split(");", 1)[0])
            capturing_values, active_table_key, pending_base_name = False, None, None

        # End of Timing Block processing
        if bracket_depth == 0:
            in_timing = False
            t_type = accumulator.get("timing_type", "N/A")
            if not any(x in t_type for x in req_types): continue

            rel_pin = accumulator.get("related_pin", "N/A")
            mode = accumulator.get("mode", "N/A")
            is_min = "true" in str(accumulator.get("min_delay_flag", "")).lower()

            if row_buffer and (row_buffer["pin"] != current_pin or row_buffer["related_pin"] != rel_pin or row_buffer["mode"] != mode):
                yield row_buffer # <--- HAND OFF DATA TO LOGGER
                row_buffer = {}

            if not row_buffer:
                row_buffer = {
                    "pin": current_pin, "direction": current_direction, "related_pin": rel_pin, "mode": mode,
                    "setup_rise": "N/A", "setup_fall": "N/A", "hold_rise": "N/A", "hold_fall": "N/A",
                    "comb_setup_rise": "N/A", "comb_setup_fall": "N/A", "comb_hold_rise": "N/A", "comb_hold_fall": "N/A",
                    "seq_clk_arc": "N/A", "seq_setup_rise": "N/A", "seq_setup_fall": "N/A", "seq_hold_rise": "N/A", "seq_hold_fall": "N/A"
                }

            # conditional writes to buffer based on timing_type
            if "combinational" in t_type:
                if is_min: 
                    row_buffer["comb_hold_rise"], row_buffer["comb_hold_fall"] = accumulator.get("cell_rise", "N/A"), accumulator.get("cell_fall", "N/A")
                else: 
                    row_buffer["comb_setup_rise"], row_buffer["comb_setup_fall"] = accumulator.get("cell_rise", "N/A"), accumulator.get("cell_fall", "N/A")
            elif "setup" in t_type:
                row_buffer["setup_rise"], row_buffer["setup_fall"] = accumulator.get("rise_constraint", "N/A"), accumulator.get("fall_constraint", "N/A")
            elif "hold" in t_type:
                row_buffer["hold_rise"], row_buffer["hold_fall"] = accumulator.get("rise_constraint", "N/A"), accumulator.get("fall_constraint", "N/A")
            elif "edge" in t_type:
                row_buffer["seq_clk_arc"] = "R" if "rising" in t_type else "F"
                if is_min: 
                    row_buffer["seq_hold_rise"], row_buffer["seq_hold_fall"] = accumulator.get("cell_rise", "N/A"), accumulator.get("cell_fall", "N/A")
                else: 
                    row_buffer["seq_setup_rise"], row_buffer["seq_setup_fall"] = accumulator.get("cell_rise", "N/A"), accumulator.get("cell_fall", "N/A")
    
    if row_buffer:
        yield row_buffer
        
    proc.terminate()

#fxn that creates blocks to be written to json db
def create_json_db_block(input_file):
    database = {}
    
    for pin_data_buffer in parse_lib(input_file):
        pin_name = pin_data_buffer.get("pin")
        if not pin_name:
            continue

        # create the arc data object
        arc_entry = {
            "related_pin": pin_data_buffer.get("related_pin"),
            "direction": pin_data_buffer.get("direction"),
            "mode": pin_data_buffer.get("mode"),
            "setup_rise": pin_data_buffer.get("setup_rise"),
            "setup_fall": pin_data_buffer.get("setup_fall"),
            "hold_rise": pin_data_buffer.get("hold_rise"),
            "hold_fall": pin_data_buffer.get("hold_fall"),
            "comb_setup_rise": pin_data_buffer.get("comb_setup_rise"),
            "comb_setup_fall": pin_data_buffer.get("comb_setup_fall"),
            "comb_hold_rise": pin_data_buffer.get("comb_hold_rise"),
            "comb_hold_fall": pin_data_buffer.get("comb_hold_fall"),
            "seq_clk_arc": pin_data_buffer.get("seq_clk_arc"),
            "seq_setup_rise": pin_data_buffer.get("seq_setup_rise"),
            "seq_setup_fall": pin_data_buffer.get("seq_setup_fall"),
            "seq_hold_rise": pin_data_buffer.get("seq_hold_rise"),
            "seq_hold_fall": pin_data_buffer.get("seq_hold_fall")
        }

        # if this is the first time we see the pin, create a list
        if pin_name not in database:
            database[pin_name] = []

        # add the arc to the list (No overwriting!)
        database[pin_name].append(arc_entry)

    return database
def json_db_logger(database_content, output_json_path):
    """
    Accepts the dictionary returned by create_json_db_block 
    and saves it as a formatted JSON file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    with open(output_json_path, 'w', encoding='utf-8') as f_json:
        json.dump(database_content, f_json, indent=4, sort_keys=False)

    print(f"Successfully logged database to: {output_json_path}")

    
def flush_buffer(writer, buffer):
    # writes the accumulated data for a specific pin/related_pin/mode to the CSV.
    # writer here is the object created by csv.writer() method in csv_logger() fxn
    if not buffer:
        return
    writer.writerow([
        buffer["pin"], buffer["direction"], buffer["related_pin"], buffer["mode"],
        buffer["setup_rise"], buffer["setup_fall"], buffer["hold_rise"], buffer["hold_fall"],
        buffer["comb_setup_rise"], buffer["comb_setup_fall"], buffer["comb_hold_rise"], buffer["comb_hold_fall"],
        buffer["seq_clk_arc"], buffer["seq_setup_rise"], buffer["seq_setup_fall"], buffer["seq_hold_rise"], buffer["seq_hold_fall"]
    ])

#fxn to log data to csv
def csv_logger(input_file, output_csv):
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    with open(output_csv, 'w', newline='') as f_csv:
        writer = csv.writer(f_csv)
        
        # Write the Header
        writer.writerow([
            "pin", "direction", "related_pin", "mode", "setup_rise", "setup_fall", "hold_rise", "hold_fall", 
            "comb_setup_rise", "comb_setup_fall", "comb_hold_rise", "comb_hold_fall",
            "seq_clk_arc", "seq_setup_rise", "seq_setup_fall", "seq_hold_rise", "seq_hold_fall"
        ])

        # iterate through the generator
        # this calls parse_lib and waits for it to 'yield' data & pin_data_buffer is the variable that holds row_buffer once it yields
        for pin_data_buffer in parse_lib(input_file):
            flush_buffer(writer, pin_data_buffer)

def main():
    parser = argparse.ArgumentParser(description="Automated Extraction Dispatcher")
    parser.add_argument("filepath", help="File containing list of directory paths to scan")
    parser.add_argument("--csv",action = "store_true",help="Logs extracted data for a lib file in csv format")
    parser.add_argument("--db",action = "store_true", help="Logs data into a db in json format")
    args = parser.parse_args()

    #fxn call that returns directory_list after reading a given directory-list file
    dir_list = read_directory_list_file(args.filepath)
    
    #fxn call that returns file list within all the directories in dir_list, given they match a specific condn
    f_list = create_file_list(dir_list)

    total_files = len(f_list)
    if total_files == 0:
        print("No .lib.gz files found.")
        return

    print(f"Found {total_files} files. Starting analysis...")
    
    for idx, full_input_path in enumerate(f_list, 1):
        filename = os.path.basename(full_input_path)

        csv_log_name = filename.replace(".lib.gz", ".csv")
        json_db_name = filename.replace(".lib.gz", ".json")

        output_csv_path = os.path.join(TEST_DIR, csv_log_name)
        output_json_path = os.path.join(TEST_DIR, json_db_name)

        print(f" Progress: [{idx}/{total_files}] analyzing {filename}...", end="\r")

        if args.csv:
            csv_logger(full_input_path, output_csv_path)

        elif args.db:
            db_block = create_json_db_block(full_input_path)
            json_db_logger(db_block, output_json_path)
        else:
            csv_logger(full_input_path, output_csv_path)


    print("\nCompleted extraction of all files.")

if __name__ == "__main__":
    main()
