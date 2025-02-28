# standard library
import sys
from typing import Dict, Union
import json
import os

# local
from utils import run_bash
from file import resolve_bare_text_file
from standard_column_order import STANDARD_COLUMN_ORDER


# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                      INPUT                      #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

if len(sys.argv) < 3:  # the very first 0th arg is the name of this script
    print("ERROR: you should specify args:")
    print("  #1 GWAS summary statistics file in tsv format (bare, zipped, or gzipped), that has a corresponding config file (suffixed \".json\") with column indices and build")
    print("  #2 output file name, prepared GWAS summary statistics file with all the columns in the standard order")
    exit(1)

# INPUT_GWAS_FILE has to be in a tabular tab-sep format with a header on the first line
INPUT_GWAS_FILE = sys.argv[1]
JSON_CONFIG = sys.argv[1] + '.json'
OUTPUT_FILE = sys.argv[2]


if not os.path.isfile(INPUT_GWAS_FILE):
    print(f"ERROR: provided GWAS SS file doesn't exist: {INPUT_GWAS_FILE}")
    exit(2)

if not os.path.isfile(JSON_CONFIG):
    print(f"ERROR: there's no corresponding json config file: {JSON_CONFIG}. Please create one based on config.example.json file")
    exit(2)


config: Dict[str, Union[int,str]] = json.load(open(JSON_CONFIG,))


# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                      MAIN                       #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #


#
# STEP #1
#    Parse config file
#

cols_i: Dict[str, int] = {}
for key, value in config.items():
    if isinstance(key, str) and isinstance(value, int):
        cols_i[key] = value


#
# STEP #2
#    Unpack if the input file is an archive
#
BARE_GWAS_FILE = resolve_bare_text_file(INPUT_GWAS_FILE, f"{INPUT_GWAS_FILE}.tsv")



#
# STEP #3
#    Reorder the columns using paste(1),
#    while cutting with cut(1) on the fly using bash process substitution,
#    and FINALLY save to the output filename specified by user
#


BASH_CMD = ["paste", "-d$'\\t'"]

for i in range(len(STANDARD_COLUMN_ORDER)):
    col_name = STANDARD_COLUMN_ORDER[i]

    if col_name in cols_i.keys():
        # user specifies column indices as starting with 0,
        # whereas Unix cut(1) counts columns starting with 1
        c_i = current_col_index = cols_i[col_name] + 1

        # for any relevant column that's present, cut it.
        # if this is a chromosome column, make sure there's no "chr" prefix
        if col_name == 'Chr':
            BASH_CMD.append(f"<(awk -F $'\\t' '{{if (${c_i} ~ /^chr/) {{print substr(${c_i},4)}} else {{print ${c_i}}} }}' < \"{BARE_GWAS_FILE}\")")
        else:
            BASH_CMD.append(f"<(cut -d$'\\t' -f{c_i} \"{BARE_GWAS_FILE}\")")
    else:
        # if user didn't specify index for the column, a template column is added (header only)
        # in this case, paste(1) will leave such columns empty, i.e. values are the empty string
        BASH_CMD.append(f"<(echo {col_name}_rehab)")

BASH_CMD = BASH_CMD + [f">\"{OUTPUT_FILE}\""]


bash_code = ' '.join(BASH_CMD)
run_bash(bash_code)


exit(0)
