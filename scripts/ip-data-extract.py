import argparse
import subprocess
import re
import csv
import sys
import os

#default output directory
DEFAULT_DIR = "../extracted_data/pipecore-data"
#Scratch/ dummy output directory
TEST_DIR = "../extracted_data/test-data"

def extract_4_4(raw_str):
    if not raw_str or raw_str == "N/A": return "N/A"
    clean = raw_str.replace('\\', ' ').replace('"', ' ').replace('\n', ' ')
    tokens = [t.strip() for t in re.split(r'[\s,]+', clean) if t.strip()]
    num_tokens = len(tokens)
    if num_tokens > 27:
        return tokens[27]  
    elif num_tokens > 3:
        return tokens[3]   
    else :
        return tokens [0]
    return "N/A"

def flush_buffer(writer, buffer):
    # Writes the accumulated data for a specific pin/related_pin/mode to the CSV.
    if not buffer:
        return
    writer.writerow([
        buffer["pin"], buffer["direction"], buffer["related_pin"], buffer["mode"],
        buffer["setup_rise"], buffer["setup_fall"], buffer["hold_rise"], buffer["hold_fall"],
        buffer["comb_setup_rise"], buffer["comb_setup_fall"], buffer["comb_hold_rise"], buffer["comb_hold_fall"],
        buffer["seq_clk_arc"], buffer["seq_setup_rise"], buffer["seq_setup_fall"], buffer["seq_hold_rise"], buffer["seq_hold_fall"]
    ])

def read_directory_file(directory_list):
    # Reads a file containing a list of directory paths.
    if not os.path.exists(directory_list):
        print(f"Error: The manifest file '{directory_list}' was not found.")
        return []
    
    with open(directory_list, 'r') as f:
        # Returns list of absolute paths, ignoring empty lines
        return [os.path.join(os.path.abspath(line.strip()), "") 
                for line in f if line.strip()]

def parse_lib_gz(input_file, output_csv):
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)

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

    with open(output_csv, 'w', newline='') as f_csv:
        writer = csv.writer(f_csv)
        writer.writerow([
            "pin", "direction", "related_pin", "mode", "setup_rise", "setup_fall", "hold_rise", "hold_fall", 
            "comb_setup_rise", "comb_setup_fall", "comb_hold_rise", "comb_hold_fall",
            "seq_clk_arc", "seq_setup_rise", "seq_setup_fall", "seq_hold_rise", "seq_hold_fall"
        ])

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
                accumulator[active_table_key] = extract_4_4(value_buffer.split(");", 1)[0])
                capturing_values, active_table_key, pending_base_name = False, None, None

            # End of Timing Block processing
            if bracket_depth == 0:
                in_timing = False
                t_type = accumulator.get("timing_type", "N/A")
                if not any(x in t_type for x in req_types): continue

                rel_pin = accumulator.get("related_pin", "N/A")
                mode = accumulator.get("mode", "N/A")
                is_min = "true" in str(accumulator.get("min_delay_flag", "")).lower()

                # Flush logic if key attributes change
                if row_buffer and (row_buffer["pin"] != current_pin or row_buffer["related_pin"] != rel_pin or row_buffer["mode"] != mode):
                    flush_buffer(writer, row_buffer)
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

        # call fxn that writes to csv log file
        flush_buffer(writer, row_buffer)
        proc.terminate()

def main():
    parser = argparse.ArgumentParser(description="Automated Extraction Dispatcher")
    parser.add_argument("filepath", help="File containing list of directory paths to scan")
    args = parser.parse_args()

    dir_list = read_directory_file(args.filepath)
    file_list = []

    for path in dir_list:
        if not os.path.isdir(path):
            print(f"Skipping: {path} (Not a directory)")
            continue
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith(".lib.gz"):
                    file_list.append(os.path.join(root, f))

    total_files = len(file_list)
    if total_files == 0:
        print("No .lib.gz files found.")
        return

    print(f"Found {total_files} files. Starting analysis...")
    
    for idx, full_input_path in enumerate(file_list, 1):
        filename = os.path.basename(full_input_path)
        output_name = filename.replace(".lib.gz", ".csv")
        output_csv_path = os.path.join(TEST_DIR, output_name)
        print(f" Progress: [{idx}/{total_files}] analyzing {filename}...", end="\r")
        parse_lib_gz(full_input_path, output_csv_path)

    print("\nCompleted extraction of all files.")

if __name__ == "__main__":
    main()
