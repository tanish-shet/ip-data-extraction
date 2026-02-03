import subprocess
import re
import csv
import sys
import os

def extract_4_4(raw_str):
    """
    Adaptive extraction:
    - Returns index 27 (4th row, 4th col for 8x8).
    - If only 1 row exists: returns index 3.
    """
    if not raw_str or raw_str == "N/A": return "N/A"
    
    clean = raw_str.replace('\\', ' ').replace('"', ' ').replace('\n', ' ')
    tokens = [t.strip() for t in re.split(r'[\s,]+', clean) if t.strip()]
    
    num_tokens = len(tokens)
    if num_tokens > 27:
        return tokens[27]  
    elif num_tokens > 3:
        return tokens[3]   
    return "N/A"

def parse_lib_gz(input_file, output_csv):
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    # Core Regex Patterns
    re_pin = re.compile(r'pin\s*\(\s*"?([^"\)\s]+)"?\s*\)\s*\{', re.IGNORECASE)
    re_timing_open = re.compile(r'timing\s*\(\s*\)\s*\{', re.IGNORECASE)
    re_type = re.compile(r'timing_type\s*:\s*([^;\s]+)\s*;', re.IGNORECASE)
    re_related = re.compile(r'related_pin\s*:\s*"?([^";\s]+)"?\s*;', re.IGNORECASE)
    #re_mode = re.compile(r'mode\s*\(([^)]+)\)', re.IGNORECASE)
    re_mode = re.compile(r'mode\s*\(.*?,\s*"([^"]+)"\)', re.IGNORECASE)
    re_sigma_type = re.compile(r'sigma_type\s*:\s*"?([^";\s]+)"?\s*;', re.IGNORECASE)

    req_types = ["setup_rising", "setup_falling", "hold_rising", "hold_falling", "combinational", "rising_edge", "falling_edge"]
    
    # Base tables and OCV tables
    base_tables = ["cell_rise", "rise_transition", "cell_fall", "fall_transition", "rise_constraint", "fall_constraint"]
    ocv_tables = ["ocv_sigma_cell_rise", "ocv_sigma_rise_transition", "ocv_sigma_cell_fall", "ocv_sigma_fall_transition", "ocv_sigma_rise_constraint", "ocv_sigma_fall_constraint"]

    # Initialize accumulator keys
    acc_keys = base_tables + [f"{t}_early" for t in ocv_tables] + [f"{t}_late" for t in ocv_tables]

    cmd = ['zcat', input_file]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)

    with open(output_csv, 'w', newline='') as f_csv:
        writer = csv.writer(f_csv)
  
        writer.writerow(["pin", "related_pin", "mode", "setup", "hold", "comb_setup", "comb_hold", "sequential_setup", "sequential_hold"])

        current_pin = "N/A"
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
                if pin_match: current_pin = pin_match.group(1)
                if re_timing_open.search(raw_line):
                    in_timing = True
                    bracket_depth = 1
                    accumulator = {k: "N/A" for k in acc_keys + ["related_pin", "mode", "timing_type"]}
                continue

            bracket_depth += raw_line.count('{')
            bracket_depth -= raw_line.count('}')

            # Detect sigma_type to define the specific key
            sigma_match = re_sigma_type.search(raw_line)
            if sigma_match and pending_base_name:
                active_table_key = f"{pending_base_name}_{sigma_match.group(1).strip()}"

            # Metadata
            if "timing_type" in raw_line:
                tm = re_type.search(raw_line)
                if tm: accumulator["timing_type"] = tm.group(1).strip()
            if "related_pin" in raw_line:
                rm = re_related.search(raw_line)
                if rm: accumulator["related_pin"] = rm.group(1)
            if "mode" in raw_line:
                mm = re_mode.search(raw_line)
                if mm: accumulator["mode"] = mm.group(1).replace('""', '').strip()

            # Table Detection
            if not capturing_values:
                # Check OCV first
                for t in ocv_tables:
                    if re.search(r'\b' + t + r'\s*\(', raw_line):
                        pending_base_name = t
                        break
                # Check Base (Mean) tables
                for t in base_tables:
                    if re.search(r'\b' + t + r'\s*\(', raw_line):
                        active_table_key = t
                        break
            
            # Value Buffering
            if active_table_key and "values (" in raw_line:
                capturing_values = True
                value_buffer = raw_line.split("values (", 1)[1]
            elif capturing_values:
                value_buffer += " " + raw_line

            if capturing_values and ");" in raw_line:
                data_str = value_buffer.split(");", 1)[0]
                accumulator[active_table_key] = extract_4_4(data_str)
                capturing_values = False
                active_table_key = None
                pending_base_name = None

            # Final Accumulator Processing
            if bracket_depth == 0:
                t_type = accumulator.get("timing_type", "N/A")
                if any(x in t_type for x in req_types):
                    setup, hold, comb_setup, comb_hold, sequential_setup, sequential_hold = "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
                    
                    if "combinational" in t_type:
                        # Extract required components
                        cr = accumulator["cell_rise"]
                        cf = accumulator["cell_fall"]
                        sr_early = accumulator["ocv_sigma_cell_rise_early"]
                        sf_early = accumulator["ocv_sigma_cell_fall_early"]
                        sr_late = accumulator["ocv_sigma_cell_rise_late"]
                        sf_late = accumulator["ocv_sigma_cell_fall_late"]

                        # Format: R (cell_rise, sigma); F (cell_fall, sigma)
                        comb_setup = f"R ({cr}, {sr_late}); F ({cf}, {sf_late})"
                        comb_hold = f"R ({cr}, {sr_early}); F ({cf}, {sf_early})"
                        
                    elif "setup" in t_type or "hold" in t_type:
                        rm = accumulator["rise_constraint"]
                        fm = accumulator["fall_constraint"]
                        # Defaulting to late sigma for constraints, adjust if early is needed
                        rs = accumulator["ocv_sigma_rise_constraint_late"]
                        fs = accumulator["ocv_sigma_fall_constraint_late"]
                        
                        pref = "R" if "rising" in t_type else "F"
                        formatted = f'{pref} (({rm}, {rs}); ({fm}, {fs}))'
                        if "setup" in t_type: setup = formatted
                        else: hold = formatted
                    elif "rising_edge" in t_type or "falling_edge":
                        s_cr = accumulator["cell_rise"]
                        s_cf = accumulator["cell_fall"]
                        s_sr_early = accumulator["ocv_sigma_cell_rise_early"]
                        s_sf_early = accumulator["ocv_sigma_cell_fall_early"]
                        s_sr_late = accumulator["ocv_sigma_cell_rise_late"]
                        s_sf_late = accumulator["ocv_sigma_cell_fall_late"]
                        if "rising_edge" in t_type :
                            sequential_setup = f"R (R ({s_cr}, {s_sr_late}); F ({s_cf},{s_sf_late}))"
                        elif "falling_edge" in t_type :
                            sequential_hold = f"F (R ({s_cr}, {s_sr_late}); F ({s_cf},{s_sf_late}))"
                    writer.writerow([current_pin, accumulator["related_pin"], accumulator["mode"].replace('""', ''), setup, hold, comb_setup, comb_hold, sequential_setup, sequential_hold])
                
                in_timing = False

        proc.terminate()
    print(f"Extraction complete: {output_csv}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 script.py <file.lib.gz>")
    else:
        parse_lib_gz(sys.argv[1], "../extracted_data/log-1.csv")