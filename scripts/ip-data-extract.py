import subprocess
import re
import csv
import sys
import os

def extract_4_4(raw_str):
    """
    Extracts the (4,4) value from a Liberty LUT string.
    Maps to index 27 for an 8x8 table.
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
    # Ensure output directory exists
    out_dir = os.path.dirname(output_csv)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # --- Regex Patterns ---
    re_pin = re.compile(r'pin\s*\(\s*"?([^"\)\s]+)"?\s*\)\s*\{', re.IGNORECASE)
    re_timing_open = re.compile(r'timing\s*\(\s*\)\s*\{', re.IGNORECASE)
    re_type = re.compile(r'timing_type\s*:\s*([^;\s]+)\s*;', re.IGNORECASE)
    re_related = re.compile(r'related_pin\s*:\s*"?([^";\s]+)"?\s*;', re.IGNORECASE)
    re_mode = re.compile(r'mode\s*\(.*?,\s*"([^"]+)"\)', re.IGNORECASE)
    re_sigma_type = re.compile(r'sigma_type\s*:\s*"?([^";\s]+)"?\s*;', re.IGNORECASE)
    re_min_flag = re.compile(r'min_delay_flag\s*:\s*([^;\s]+)\s*;', re.IGNORECASE)

    # --- Table Keys ---
    req_types = ["setup_rising", "setup_falling", "hold_rising", "hold_falling", "combinational", "rising_edge", "falling_edge"]
    base_tables = ["cell_rise", "rise_transition", "cell_fall", "fall_transition", "rise_constraint", "fall_constraint"]
    ocv_tables = ["ocv_sigma_cell_rise", "ocv_sigma_cell_fall", "ocv_sigma_rise_constraint", "ocv_sigma_fall_constraint"]

    acc_keys = base_tables + [f"{t}_early" for t in ocv_tables] + [f"{t}_late" for t in ocv_tables]

    # Use zcat to stream the .gz file
    cmd = ['zcat', input_file]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)

    with open(output_csv, 'w', newline='') as f_csv:
        writer = csv.writer(f_csv)
        # Header aligned with variable logic
        writer.writerow([
            "pin", "related_pin", "mode", "setup_rise", "setup_fall", "hold_rise", "hold_fall", 
            "comb_setup_rise", "comb_setup_fall", "comb_hold_rise", "comb_hold_fall",
            "seq_clk_arc", "seq_setup_rise", "seq_setup_fall", "seq_hold_rise", "seq_hold_fall"
        ])

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

            # --- State 1: Outside Timing Block ---
            if not in_timing:
                pin_match = re_pin.search(raw_line)
                if pin_match: current_pin = pin_match.group(1)
                if re_timing_open.search(raw_line):
                    in_timing = True
                    bracket_depth = 1
                    # Reset accumulator for new arc
                    accumulator = {k: "N/A" for k in acc_keys + ["related_pin", "mode", "timing_type", "min_delay_flag"]}
                continue

            # --- State 2: Inside Timing Block ---
            bracket_depth += raw_line.count('{')
            bracket_depth -= raw_line.count('}')

            # Metadata Capture
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

            # Handle Sigma Type (Early/Late)
            sigma_match = re_sigma_type.search(raw_line)
            if sigma_match and pending_base_name:
                active_table_key = f"{pending_base_name}_{sigma_match.group(1).strip()}"

            # Table Search
            if not capturing_values:
                for t in ocv_tables:
                    if re.search(r'\b' + t + r'\s*\(', raw_line):
                        pending_base_name = t
                        break
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

            # --- State 3: Block Exit ---
            if bracket_depth == 0:
                t_type = accumulator.get("timing_type", "N/A")
                is_min = "true" in str(accumulator.get("min_delay_flag", "")).lower()
                
                if any(x in t_type for x in req_types):
                    # Local variables initialized for every row to prevent NameError
                    s_rm, s_fm, h_rm, h_fm = "N/A", "N/A", "N/A", "N/A"
                    c_s_r, c_s_f, c_h_r, c_h_f = "N/A", "N/A", "N/A", "N/A"
                    seq_clk, seq_s_r, seq_s_f, seq_h_r, seq_h_f = "N/A", "N/A", "N/A", "N/A", "N/A"

                    # 1. Combinational Mapping
                    if "combinational" in t_type:
                        cr, cf = accumulator["cell_rise"], accumulator["cell_fall"]
                        if is_min: c_h_r, c_h_f = cr, cf
                        else: c_s_r, c_s_f = cr, cf

                    # 2. Constraint Mapping (Setup/Hold)
                    elif "setup" in t_type:
                        s_rm = accumulator.get("rise_constraint", "N/A")
                        s_fm = accumulator.get("fall_constraint", "N/A")
                    elif "hold" in t_type:
                        h_rm = accumulator.get("rise_constraint", "N/A")
                        h_fm = accumulator.get("fall_constraint", "N/A")

                    # 3. Sequential Mapping (rising_edge/falling_edge)
                    elif "edge" in t_type:
                        seq_clk = "R" if "rising" in t_type else "F"
                        cr, cf = accumulator["cell_rise"], accumulator["cell_fall"]
                        if is_min: seq_h_r, seq_h_f = cr, cf
                        else: seq_s_r, seq_s_f = cr, cf

                    writer.writerow([
                        current_pin, accumulator["related_pin"], accumulator["mode"], 
                        s_rm, s_fm, h_rm, h_fm, 
                        c_s_r, c_s_f, c_h_r, c_h_f,
                        seq_clk, seq_s_r, seq_s_f, seq_h_r, seq_h_f
                    ])
                
                in_timing = False

        proc.terminate()
    print(f"Extraction complete: {output_csv}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 script.py <input.lib.gz>")
    else:
        # Default output path adjusted to a local relative path for safety
        parse_lib_gz(sys.argv[1], "../extracted_data/extracted_log.csv")