# standard library
import sys
import re
from typing import Any, Dict, List, Literal, Tuple, Union
import os
import json
import subprocess
import time

# third-party libraries
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects

# local
from validate_utils import write_report_to_dir


# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                      INPUT                      #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

if len(sys.argv) < 3:
    print("ERROR: you should specify args:")
    print("  #1 GWAS summary statistics file in tsv format")
    print("  #2 path to json config file specifying which columns are which, or string \"standard\"")
    print("  #3 (optional) output: dir name to save textual and graphical report")
    exit(1)

# GWAS_FILE has to be in a tabular tab-sep format with a header on the first line
GWAS_FILE = sys.argv[1]
JSON_CONFIG = sys.argv[2]


REPORT_DIR = None
REPORT_ABS_DIR = None
if len(sys.argv) > 3 and sys.argv[3]:
    REPORT_DIR = sys.argv[3]
    REPORT_ABS_DIR = os.path.abspath(REPORT_DIR)


def file_exists(path: str):
    return os.path.isfile(path)
def dir_exists(path: str):
    return os.path.isdir(path)

if not file_exists(GWAS_FILE):
    print(f"ERROR: provided gwas file doesn't exist: {GWAS_FILE}")
    exit(1)


GWAS_FILE_o = open(GWAS_FILE, 'r')

if JSON_CONFIG == "standard":
    cols_i: Dict[str, int] = {
        "Chr":   0,
        "BP":    1,
        "rsID":  2,
        "OA":    3,
        "EA":    4,
        "EAF":   5,
        "beta":  6,
        "SE":    7,
        "pval":  8,
        "N":     9,
        "INFO": 10,
    }
else:
    if not file_exists(GWAS_FILE):
        print(f"ERROR: provided gwas file doesn't exist: {JSON_CONFIG}")
        exit(1)
    cols_i: Dict[str, int] = json.load(open(JSON_CONFIG,))



# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                 USER SETTINGS                   #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

# tick labels. Numerical value will be inferred from this string.
x = ["0", "1e-8", "1e-5", "1e-3", ".03", ".3", "1"]

separator = '\t'

ticks_width_rule_setting: Literal['even', 'log10'] = 'log10'





##### Validation of user settings #####

# p-value interval points:
ticks = [float(x_label) for x_label in x]

ticks_width_rule: Literal['even', 'log10'] = ticks_width_rule_setting

assert ticks == sorted(ticks) and len(ticks) == len(set(ticks)), "Ticks have to be in strictly ascending order"
assert ticks[0] >= 0 and ticks[-1] <= 1, "Ticks have to be in range from 0 to 1"



# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                    CONSTANTS                    #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

GOOD_ENTRY = 0
MISSING_P_VALUE = 1
INVALID_ENTRY = 2


# indices for boolean values in a list of issues for each SNP
INVALID_ROW = 0
INVALID_RSID = 1
INVALID_CHR = 2
INVALID_BP = 3
INVALID_EA = 4
INVALID_OA = 5
INVALID_EAF = 6
INVALID_SE = 7
INVALID_ES = 8
ISSUES=[
    INVALID_ROW,
    INVALID_RSID,
    INVALID_CHR,
    INVALID_BP,
    INVALID_EA,
    INVALID_OA,
    INVALID_EAF,
    INVALID_SE,
    INVALID_ES,
]
ISSUES_LABELS = [
    "format",
    "rsID",
    "Chr",
    "BP",
    "EA",
    "OA",
    "EAF",
    "SE",
    "beta",
]
ISSUES_COLORS=[
    "#ff0000", # format
    "#777ae5", # rsID
    "#cf44a1", # Chr
    "#ff4481", # BP
    "#ffa121", # EA
    "#ff9191", # OA
    "#fdbc64", # EAF
    "#563E3E", # std. err.
    "#175a63", # beta

]

NUCLEOTIDES = ['a', 't', 'c', 'g']
NO_NUCLEOTIDE = '.'

ALLOW_MULTI_NUCLEOTIDE_POLYMORPHISMS = True

CATEGORY_CHR = [
'1', '01', '2', '02', '3', '03', '4', '04', '5', '05', '6', '06', '7', '07', '8', '08', '9', '09',
'10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
'21', '22', '23', 'X', 'x', 'Y', 'y', 'M', 'm']
# CATEGORY_CHR = [
# '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
# '21', '22', '23', 'X', 'x', 'Y', 'y', 'M', 'm']



# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                    FUNCTIONS                    #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

# https://stackoverflow.com/a/850962/6041933  # a comment to the answer
# https://gist.github.com/zed/0ac760859e614cd03652
def wccount(filename: str):
    """counts the number of lines in the file"""
    out = subprocess.Popen(['wc', '-l', filename],
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT
                         ).communicate()[0]
    return int(out.partition(b' ')[0])


def is_null(val: str) -> bool:
    return val.lower() in ["", " ", ".", "-", "na", "nan"]




# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#       FUNCTION THAT CHECKS EACH SNP ENTRY       #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

def check_row(line_cols: List[str]) -> Union[
        # "good" entry
        Tuple[float, Literal[0], List[bool]],
        # "missing p-value" entry
        Tuple[None,  Literal[1], List[bool]],
        # "invalid" entry, having some issues (listed in the list)
        Tuple[float, Literal[2], List[bool]],
    ]:
    """
    This function runs for EVERY LINE of the input file,
    which may be MILLIONS OF TIMES per script execution

    Returns:
        - a p-value of a SNP,
        - a report of whether a SNP entry is valid,
        - and a list of issues with it
    """

    issues = [False] * len(ISSUES)

    ### First check if p-value itself is present ###
    try:
        pval = line_cols[cols_i["pval"]]
        if is_null(pval) or not (0 <= float(pval) <= 1):
            return None, MISSING_P_VALUE, issues
        pval = float(pval)
    except:
        return None, MISSING_P_VALUE, issues


    ### Try getting all columns. If some not present, will throw ###
    try:
        rsid  = line_cols[cols_i["rsID"]]
        chrom = line_cols[cols_i["Chr"]]
        bp    = line_cols[cols_i["BP"]]
        ea    = line_cols[cols_i["EA"]]
        oa    = line_cols[cols_i["OA"]]
        af    = line_cols[cols_i["EAF"]]
        se    = line_cols[cols_i["SE"]]
        es    = line_cols[cols_i["beta"]]
        # n     = line_cols[cols_i["N"]]

    except:
        issues[INVALID_ROW] = True
        return pval, INVALID_ENTRY, issues

    ### Check any reasons this SNP will be discarded later ###

    # 1. rsID
    try:
        if not re.match("^rs\d+$", rsid):
            issues[INVALID_RSID] = True
    except:
        issues[INVALID_RSID] = True

    # 2. chromosome
    try:
        if chrom not in CATEGORY_CHR and chrom[3:] not in CATEGORY_CHR:
            issues[INVALID_CHR] = True
    except:
        issues[INVALID_CHR] = True

    # 3. base pair position
    try:
        bp = int(float(bp)) # using float allows sci notation string
        if bp < 0:
            issues[INVALID_BP] = True
    except:
        issues[INVALID_BP] = True

    # 4. effect allele
    try:
        if ea == '':
            issues[INVALID_EA] = True
        elif ea == NO_NUCLEOTIDE:
            issues[INVALID_EA] = False
        elif ALLOW_MULTI_NUCLEOTIDE_POLYMORPHISMS:
            for char in ea.lower():
                if char not in NUCLEOTIDES:
                    issues[INVALID_EA] = True
        else:
            if ea.lower() not in NUCLEOTIDES:
                issues[INVALID_EA] = True
    except:
        issues[INVALID_EA] = True

    # 5. other allele
    try:
        if oa == '':
            issues[INVALID_OA] = True
        elif oa == NO_NUCLEOTIDE:
            issues[INVALID_OA] = False
        elif ALLOW_MULTI_NUCLEOTIDE_POLYMORPHISMS:
            for char in oa.lower():
                if char not in NUCLEOTIDES:
                    issues[INVALID_OA] = True
        else:
            if oa.lower() not in NUCLEOTIDES:
                issues[INVALID_OA] = True
    except:
        issues[INVALID_OA] = True

    # 6. effect allele frequency or minor allele frequency
    try:
        if not (0 <= float(af) <= 1):
            issues[INVALID_EAF] = True
    except:
        issues[INVALID_EAF] = True

    # 7. standard error
    try:
        float(se) # will throw if not float
        if is_null(se):
            issues[INVALID_SE] = True
    except:
        issues[INVALID_SE] = True

    # 8. effect size (odds ratio or beta-value)
    try:
        float(es) # will throw if not float
        if is_null(es):
            issues[INVALID_ES] = True
    except:
        issues[INVALID_ES] = True

    # # 9. n - sample size
    # #sometimes sample size is fractional
    # if null_entry(n) or not (0 < float(n)):
    #     return INVALID_ENTRY, pval


    if any(issues):
        return pval, INVALID_ENTRY, issues
    else:
        # all good?
        return pval, GOOD_ENTRY, issues




# # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                 #
#                      MAIN                       #
#                                                 #
# # # # # # # # # # # # # # # # # # # # # # # # # #

MAIN_start_time = STEP1_start_time = time.time()


#
# STEP #1
#    read the file line by line and check the validity of each SNP entry,
#    and save the report and the p-value if present
#

num_of_lines = wccount(GWAS_FILE)
num_of_snps = num_of_lines - 1
print(f"number of lines in the file: {num_of_lines}")

line_i=0
# skip the first line that is the header
GWAS_FILE_o.readline()
line_i+=1

SNPs_pval = np.empty(num_of_snps, dtype=float)
SNPs_report = np.empty(num_of_snps, dtype=int)
SNPs_issues = np.empty((num_of_snps, len(ISSUES)), dtype=bool)

### populate the allocated array with report for each SNP as well as its p-value ###
try:
    snp_i = 0
    while True:
        SNPs_pval[snp_i], SNPs_report[snp_i], SNPs_issues[snp_i] = check_row(GWAS_FILE_o.readline().replace('\n','').split(separator))
        snp_i += 1

except Exception as e:
    if isinstance(e, IndexError) or isinstance(e, EOFError):
        # it reached the end of the file
        pass
    else:
        print(f'An error occured on line {line_i} of the GWAS SS file (see below)')
        raise e
### ###


GWAS_FILE_o.close()
print("--- STEP1: %s seconds ---" % (time.time() - STEP1_start_time))

# result: SNPs_report, SNPs_pval


#
# STEP #2
#    sum up the reports and calculate the parameters before plotting
#
STEP2_start_time = time.time()


# 2.1
"""
Bar widths start from the right, i.e. the last bar refers to the range between the last two ticks.
The very first bar is "no p-value" bar, it has unit width and goes to the left of the first tick.

If the very first tick is zero, then the bin size from zero to the next tick is 2 units.

User may have choosen the rule of ticks width to either 'even' or 'log10':
 • With 'even', all bars will have unit width, regardless of the numerical difference between ticks
 • With 'log10', all bars will have widths adjusted in accord to log10 scale,
   with a constant unit_width defined here
"""
bars_widths = [1.]

if ticks_width_rule == 'even':
    for i in range(1, len(ticks)):
        bars_widths.append(1.)

elif ticks_width_rule == 'log10':
    unit_width = np.log10(1) - np.log10(1e-2)
    for i in range(1, len(ticks)):
        if ticks[i-1] == 0:
            bars_widths.append(2.)
        else:
            bars_widths.append(
                (np.log10(ticks[i]) - np.log10(ticks[i-1]))
                                / unit_width
            )

else:
    raise ValueError(f'unknown ticks_width_rule: {ticks_width_rule}')

negative_bars_widths = list(-np.array(bars_widths))


# 2.2
"""
Ticks location (ticks_loc) equals to cumulative of bars_widths,
shifted by the very first bar width to the left, so the tick #1 equals 0
"""
ticks_loc: List[float] = []
cumulative = -bars_widths[0] # starting such that the first loc is 0
for width in bars_widths:
    cumulative += width
    ticks_loc.append(cumulative)
del cumulative


assert len(ticks) == len(bars_widths) == len(ticks_loc), "lists: `ticks`, `ticks_loc`, and `bars_widths` should have the same lengths"


# 2.3
### Counting how many entries are valid, don't have p-value, or invalid for other reasons ###
missing_pval_bins = [0]*len(ticks)
good_entry_bins = [0]*len(ticks)
invalid_entry_bins = [0]*len(ticks)
# besides total, for each of the bin we'll store the number of invalid entries for each type
invalid_entry_bins_reason_bins = np.zeros((len(ticks), max(ISSUES)+1)).astype(int)

for line_i in range(len(SNPs_report)):

    if SNPs_report[line_i] == MISSING_P_VALUE:
        missing_pval_bins[0] += 1

    elif SNPs_report[line_i] == GOOD_ENTRY:
        for j in range(1,len(ticks)):
            if SNPs_pval[line_i] <= ticks[j]:
                good_entry_bins[j] += 1
                break

    elif SNPs_report[line_i] == INVALID_ENTRY:
        for j in range(1, len(ticks)):
            if SNPs_pval[line_i] <= ticks[j]:
                invalid_entry_bins[j] += 1
                invalid_entry_bins_reason_bins[j] += SNPs_issues[line_i]
                break

### ###

print("--- STEP2: %s seconds ---" % (time.time() - STEP2_start_time))

print("=== MAIN: %s seconds ===" % (time.time() - MAIN_start_time)) # plotting doesn't count



#
# STEP #3
#     save csv file with report for each issue
#

if REPORT_ABS_DIR:
    if not dir_exists(REPORT_ABS_DIR):
        os.makedirs(REPORT_ABS_DIR)


issues_count: Dict[str, int] = {}

for issue_i in range(0, len(ISSUES)):
    issues_count[ISSUES_LABELS[issue_i]] = sum([invalid_entry_bins_reason_bins[i][issue_i] for i in range(len(invalid_entry_bins))])

issues_count["pval"] = sum(missing_pval_bins)

issues_count["total_entries"] = num_of_snps

print(f"issues_count = {issues_count}")

if REPORT_ABS_DIR: 
    write_report_to_dir(issues_count, REPORT_ABS_DIR)



#
# STEP #4
#    plot
#

### CALC: proportion of invalid entries in total ###

invalid_entries_totally = sum(invalid_entry_bins) + sum(missing_pval_bins)
proportion_of_invalid_entries_totally = invalid_entries_totally / num_of_snps
percentage_of_invalid_entries_totally = proportion_of_invalid_entries_totally * 100
percentage_of_invalid_entries_totally_str = str(np.round(percentage_of_invalid_entries_totally, 1)) + "%"


### PLOT: the figure, labels, ticks, bars ###

fig, ax = plt.subplots(num="valid/invalid SNPs")

image_name = GWAS_FILE.split('/')[-1]
fig.canvas.set_window_title(image_name) # sets the window title to the filename

ax.set_title(
    f"invalid SNPs: {invalid_entries_totally}/{num_of_snps} ({percentage_of_invalid_entries_totally_str})")

# # Hide the right and top spines
# ax.spines['right'].set_visible(False)
# ax.spines['top'].set_visible(False)

ax.tick_params(axis='x', labelsize=9)

ax.set_xticks(ticks_loc)
ax.set_xticklabels(x)
ax.bar(ticks_loc, missing_pval_bins, negative_bars_widths, color='#7f7f7f', align='edge')
ax.bar(ticks_loc, good_entry_bins, negative_bars_widths, color='#0000ff', align='edge', label="valid SNPs")
ax.bar(ticks_loc, invalid_entry_bins, negative_bars_widths, color='#ff0000', align='edge', bottom=good_entry_bins, label="invalid SNPs")
ax.set_xlabel("p-value", fontweight="heavy", fontsize=14)
ax.set_ylabel("N of SNPs", fontweight="heavy", fontsize=14)
ax.set_xlim([ticks_loc[0]+negative_bars_widths[0], ticks_loc[-1]])

max_bar_height = max(
    np.array(missing_pval_bins) + np.array(good_entry_bins) + np.array(invalid_entry_bins) # np arrays add element-wise
)

plt_bottom, plt_top = ax.set_ylim(0, max_bar_height*1.15 if max_bar_height else 1)
plt_height = plt_top - plt_bottom


### CALC: points right at the middle of each bin ###
bins_mid_points = list(np.array(ticks_loc) - np.array(bars_widths)/2)


### PLOT: caption for "no p-value" bin ###
ax.text(x=bins_mid_points[0], y=plt_top*-0.08, s="no\np-value",
    horizontalalignment='center',
)


### CALC: total entries, proportion and percentage of invalid entries  ###

total_p_value_entries_bins = [good_entry_bins[i]+invalid_entry_bins[i] for i in range(len(good_entry_bins))]

proportion_of_invalid_entries_bins = [0.] + [
    invalid_entry_bins[i]/total_p_value_entries_bins[i] if total_p_value_entries_bins[i] else 0.
                for i in range(1, len(good_entry_bins))]

percentage_of_invalid_entries_bins = np.round(np.array(proportion_of_invalid_entries_bins)*100).astype(int)
percentage_of_invalid_entries_bins_str = np.char.array(percentage_of_invalid_entries_bins) + "%" # type: ignore # pylance mistakenly doesn't recognize np.char



### PLOT: representation of the percentage of invalid entries for each bin ###
# the bottom and the top spines of the plot represent 0% and 100%
# skipping the first, "no p-value" bin

ax.plot(
    # X: points right at the mid of bins (except the no p-value bin)
    bins_mid_points[1:],

    # Y: how much proportion -> that much height within the plot
    np.array(proportion_of_invalid_entries_bins[1:]) * plt_height + plt_bottom,

    linestyle='-',
    color="red",
    alpha=0.5,
    linewidth=2,
)


### PLOT: Captions above the points of the plot ###
# shows percentage of invalid entries for each bin in text
# skipping the first, "no p-value" bin

# points right at the mid of bins
X = bins_mid_points
# how much proportion -> that much height within the plot, also lifted 5%
Y = (np.array(proportion_of_invalid_entries_bins) * plt_height) + plt_height*0.05 + plt_bottom

for i in range(1, len(percentage_of_invalid_entries_bins_str)):
    if proportion_of_invalid_entries_bins[i] > 0.15:
        text = ax.text(X[i], Y[i], s=percentage_of_invalid_entries_bins_str[i],
            horizontalalignment='center',
            color="#bf3f3f", # caption may overlap with the red stuff from stacked bar
            fontsize=10,
            fontweight="demibold",
        )
    else:
        text = ax.text(X[i], Y[i], s=percentage_of_invalid_entries_bins_str[i],
            horizontalalignment='center',
            color="#ff0000",
            fontsize=10,
        )
    # text.set_path_effects([path_effects.Stroke(linewidth=1, foreground='#000000'),
    #                        path_effects.Normal()])


if REPORT_ABS_DIR: fig.savefig(os.path.join(REPORT_ABS_DIR, image_name+'.png'))


### PLOT: bar chart for issues in each of the p-value bins ###
for i in range(1, len(invalid_entry_bins)):
    image_name = f'bin_{i}__{x[i-1]}—{x[i]}'
    plot_i, ax = plt.subplots(num=image_name)

    issues_proportions = [0] * len(ISSUES)
    total_invalids = invalid_entry_bins[i]
    total_snps = invalid_entry_bins[i] + good_entry_bins[i]

    proportion_of_invalids = total_invalids / total_snps if total_snps else 0
    percentage_of_invalids = proportion_of_invalids * 100
    percentage_of_invalids_str = str(np.round(percentage_of_invalids, 1)) + "%"

    ax.set_title(f'issues in p-value: {x[i-1]} — {x[i]}\ninvalid SNPs: {total_invalids}/{total_snps} ({percentage_of_invalids_str})')
    ax.set_ylim(0, total_invalids if total_invalids > 0 else 1)
    ax.set_ylabel("N of invalid SNPs", fontweight="demibold", fontsize=14)

    if total_invalids == 0:
        ax.bar(ISSUES_LABELS, height=issues_proportions, width=1, color=ISSUES_COLORS)
    else:
        for issue in range(len(ISSUES)): # for each ISSUE
            issues_proportions[issue] = invalid_entry_bins_reason_bins[i][issue] / total_invalids
        ax.bar(ISSUES_LABELS, height=invalid_entry_bins_reason_bins[i], width=1, color=ISSUES_COLORS)

    if REPORT_ABS_DIR: plot_i.savefig(os.path.join(REPORT_ABS_DIR, image_name+'.png'))




### FINALLY: display results and the figure (if report directory was not set) ###

# print(f'missing_pval_bins = {missing_pval_bins}')
# print(f'good_entry_bins = {good_entry_bins}')
# print(f'invalid_entry_bins = {invalid_entry_bins}')

# print(f'proportion_of_invalid_entries_bins = {proportion_of_invalid_entries_bins}')

# for i in range(1, len(invalid_entry_bins)):
#     print(f"{x[i-1]} — {x[i]}: {[invalid_entry_bins_reason_bins[i][issue] for issue in ISSUES]}")



if not REPORT_DIR:
    plt.show()
    input("")
    input("")






