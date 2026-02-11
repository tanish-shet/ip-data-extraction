# Repository structure:
```
.
├── extracted_data  #default parent directory for extracted logs, db
│   ├── pipecore-data
│   ├── pipecore-lib-data
│   └── test-data #current ip-lib database directory
└── scripts
    ├── db-process.py  #script to access db attributes, compare arcs across databses etc
    ├── ip-data-extract.py #redudant script 
    ├── ip-db-gen-script.py #script responsible for db generation and csv logging
    └── ip-directory-list.txt #filelist doc (parsed by db-gen script to get folder paths for IP libs)

```

# Usage: 

## 1) For creating a database of timing info from ip .lib files
The database creation requires running the "ip-db-gen-script.py" as folows:
```
    python3 ip-db-gen-script.py <filepath for filelist doc [ex: ../ip-data-extraction/scripts/ip-directory-list.txt]>
```
The above cmd creates the database in json format by default. The output target folder is currently hardcoded in the same script \
Additionally, we may also log the extracted timing info from the lib files onto a csv file per lib - as follows:
```
    python3 ip-db-gen-script.py <filepath for filelist doc [ex: ../ip-data-extraction/scripts/ip-directory-list.txt]> --csv
```
To dump out both database in json format and data logs in csv:
```
    python3 ip-db-gen-script.py <filepath for filelist doc [ex: ../ip-data-extraction/scripts/ip-directory-list.txt]> --csv --db
```
## 2) For accessing database attributes:
"db-process.py" is the script to be used for accesing different aspects/ attributes of the database
``` 
    python3 db-process.py <database directory path [ex: ../ip-data-extraction/extracted_data/db-dir/]> --option arguments
```
### i) Comparing arcs across databases:
```
    python3 db-process.py <database directory path [ex: ../ip-data-extraction/extracted_data/db-dir/]> --compare --pins <list of pins to compare>
```
for comparing all pins across all databases, use:
```
    python3 db-process.py <database directory path [ex: ../ip-data-extraction/extracted_data/db-dir/]> --compare --all
```

### ii) To access attributes for a given pin:
```
    python3 db-process.py <database directory path [ex: ../ip-data-extraction/extracted_data/db-dir/]> --pins <pin list> --get_attribute <attribute_name [ex: comb_setup_rise, comb_hold_rise etc]>
```
```
    python3 db-process.py <database directory path [ex: ../ip-data-extraction/extracted_data/db-dir/]> --pins <target_pin> --arc <related_pin and mode that characterises an arc from target_pin> --get_attribute
```

### iii) To get histogram spread for a given attribute of an arc:
```
    python3 db-process.py <database directory path [ex: ../ip-data-extraction/extracted_data/db-dir/]> --pins <target_pin> --arc <related_pin and mode that characterises an arc from target_pin> --get_attribute --spread
```

