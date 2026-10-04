"""Workbook writers (openpyxl): public dataset, hidden truth, master scoring.

All competition data lives in xlsx workbooks; scoring is Excel formulas only.
The master workbook follows the organizer's template layout:

  Master sheet   scoreboard: one block per scenario (Avg. Premium,
                 Policies Won, Lost Ratio (%), Qualified? (Bool), Rank (#))
                 with one column per team
  Dataset        the generated test dataset (attributes for every TEST_ID)
  Train_*        the generated base-world train history
  Truth          hidden claims per scoring seed
  Team A..T      one staging sheet per team (paste PREMIUM, row-aligned)
  Subs/Alloc/By_Scenario/Checks   merged helper sheets (formula-driven)
"""

import re
import string

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import config

_HEAD_FILL = PatternFill('solid', fgColor='1F4E78')
_HEAD_FONT = Font(color='FFFFFF', bold=True)
_LABEL_FONT = Font(bold=True)
_TITLE_FONT = Font(bold=True, size=14)


def _style_header(ws, row=1, ncols=None):
    ncols = ncols or ws.max_column
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = _HEAD_FILL
        cell.font = _HEAD_FONT
        cell.alignment = Alignment(horizontal='center')
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _write_data_sheets(path, sheets):
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    wb = load_workbook(path)
    for name in sheets:
        _style_header(wb[name[:31]])
    wb.save(path)


def _team_names(n_teams=None, names=None):
    """Display names: explicit list wins, else Team A.. by count."""
    if names:
        return list(names)
    n_teams = n_teams or config.N_TEAMS
    out = []
    for i in range(n_teams):
        out.append(f'Team {string.ascii_uppercase[i]}' if i < 26 else f'Team {i + 1:02d}')
    return out


_INVALID_SHEET_CHARS = re.compile(r'[\\/?*\[\]:]')


def _sheet_names(preferred):
    """Excel-safe, unique sheet names (31 chars, no \\ / ? * [ ] :)."""
    used = set()
    names = []
    for name in preferred:
        clean = _INVALID_SHEET_CHARS.sub('_', str(name)).strip() or 'Team'
        clean = clean[:31]
        base = clean
        k = 1
        while clean.lower() in used:
            suffix = f'~{k:02d}'
            clean = base[:31 - len(suffix)] + suffix
            k += 1
        used.add(clean.lower())
        names.append(clean)
    return names


def _sheet_ref(name):
    """Quoted Excel sheet reference (apostrophes escaped)."""
    return "'" + str(name).replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Public dataset (teams)
# ---------------------------------------------------------------------------

def write_public_dataset(path, train_policies, train_claims, test_policies,
                         train_label='base'):
    """Team workbook: base train history + combined all-scenario test set."""
    _write_data_sheets(path, {
        'Train_Policies': train_policies,
        'Train_Claims': train_claims,
        'Test_Policies': test_policies,
    })
    wb = load_workbook(path)

    ws = wb.create_sheet('Instructions', 0)
    ws['A1'] = 'COMPETITION DATASET — Excel-only pricing game'
    ws['A1'].font = _TITLE_FONT
    scenarios = list(dict.fromkeys(test_policies['SCENARIO']))
    notes = [
        f'Train history: "{train_label}" world only (Train_Policies + Train_Claims).',
        f'Test set: {len(test_policies):,} policies across {len(scenarios)} scenarios '
        f'({", ".join(scenarios)}).',
        'Price every TEST_ID in the Submission sheet; do not add or drop rows.',
        f'Premium bounds: RM{config.PREMIUM_MIN:,} – RM{config.PREMIUM_MAX:,}.',
        'Save the Submission sheet as CSV (TEST_ID,PREMIUM) and submit before the deadline.',
        '',
        'SCORING',
        '  Cheapest premium wins each policy; ties split equally (share = 1 / k).',
        '  Claims come from hidden replications of the same customers (pooled seeds).',
        '  LR = shared claims / shared premium, computed PER SCENARIO.',
        '  Any scenario with LR >= 100% disqualifies the team overall.',
        '  Leaderboard: total fractional policies won among non-disqualified teams.',
        '',
        'NOTE: each scenario is an independent world (stress levels, book mix,',
        'climate). Use the base-world train history to estimate base costs, then',
        'adjust per scenario as the briefs describe.',
    ]
    for i, text in enumerate(notes, start=2):
        ws.cell(row=i, column=1, value=text)
    ws.column_dimensions['A'].width = 110
    if scenarios:
        scen_ws = wb.create_sheet('Scenarios')
        scen_ws.append(['SCENARIO', 'TEST_ROWS', 'NOTE'])
        from .build_dataset import load_rounds  # local import to avoid cycle
        labels = {r['name']: r.get('label', r['name']) for r in load_rounds()}
        for s in scenarios:
            scen_ws.append([s, int((test_policies['SCENARIO'] == s).sum()),
                            labels.get(s, s)])
        _style_header(scen_ws, ncols=3)

    ws = wb.create_sheet('Submission')
    ws['A1'] = 'Submission — fill PREMIUM for every TEST_ID'
    ws['A1'].font = _TITLE_FONT
    ws['A3'] = 'TEST_ID'
    ws['B3'] = 'PREMIUM'
    for cell in ('A3', 'B3'):
        ws[cell].fill = _HEAD_FILL
        ws[cell].font = _HEAD_FONT
    n = len(test_policies)
    for i, tid in enumerate(test_policies['TEST_ID'].tolist(), start=4):
        ws.cell(row=i, column=1, value=tid)
    if n:
        dv = DataValidation(type='decimal', operator='between',
                            formula1=str(config.PREMIUM_MIN),
                            formula2=str(config.PREMIUM_MAX), allow_blank=True)
        dv.error = f'Premium must be between RM{config.PREMIUM_MIN} and RM{config.PREMIUM_MAX}'
        dv.errorTitle = 'Out of bounds'
        ws.add_data_validation(dv)
        dv.add(f'B4:B{n + 3}')
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 14

    wb.save(path)
    return path


def write_truth_workbook(path, truth):
    """Organizer-only truth: TEST_ID + SCENARIO + one claim column per seed."""
    _write_data_sheets(path, {'Truth': truth})
    return path


# ---------------------------------------------------------------------------
# Master workbook (organizer) — sample_master.xlsm layout
# ---------------------------------------------------------------------------

def write_master_workbook(path, truth, dataset, train_policies=None,
                          train_claims=None, n_teams=None, team_names=None):
    """Organizer workbook: dataset + truth + per-team imports + scoreboard.

    Sheet 'Master sheet' mirrors the approved template: one block per
    scenario with Avg. Premium / Policies Won / Lost Ratio (%) /
    Qualified? (Bool) / Rank (#), one column per team.
    Team count/names are free: pass `team_names` (or a count) and the
    workbook sizes itself.
    """
    display_names = _team_names(n_teams, team_names)
    sheet_names = _sheet_names(display_names)
    n_teams = len(display_names)
    seed_cols = [c for c in truth.columns if c.startswith('CLAIMS_S')]
    scenarios = list(dict.fromkeys(truth['SCENARIO']))
    n_test = len(truth)
    last = n_test + 1
    team_names = display_names
    team_sheets = sheet_names

    # column map on helper sheets
    subs_team_first = 2
    subs_team_last = 1 + n_teams
    subs_letters = [get_column_letter(c) for c in range(subs_team_first, subs_team_last + 1)]
    total_subs_col = get_column_letter(subs_team_last + 1)
    scenario_subs_col = get_column_letter(subs_team_last + 2)

    bs_first = 2
    bs_last = 1 + len(scenarios) * n_teams
    overall_first = bs_last + 1
    overall_last = bs_last + n_teams

    wb = Workbook()

    # --- Master sheet (scoreboard) ------------------------------------------
    ws = wb.active
    ws.title = 'Master sheet'
    ws['A1'] = 'MASTER — one block per scenario; one column per team'
    ws['A1'].font = _TITLE_FONT
    blocks_start = 3
    for si, scenario in enumerate(scenarios):
        top = blocks_start + si * 7
        ws.cell(row=top, column=1, value=f'Scenario: {scenario}').font = _LABEL_FONT
        ws.cell(row=top, column=2, value='Team')
        for j, name in enumerate(team_names):
            ws.cell(row=top, column=3 + j, value=name)
        for k, label in enumerate(['Avg. Premium', 'Policies Won', 'Lost Ratio (%)',
                                   'Qualified? (Bool)', 'Rank (#)']):
            ws.cell(row=top + 1 + k, column=1, value=label)
        block_first = bs_first + si * n_teams
        block_last = block_first + n_teams - 1
        for j in range(n_teams):
            col = 3 + j
            cl = get_column_letter(col)
            r = block_first + j
            ws.cell(row=top + 1, column=col,
                    value=f'=IF(By_Scenario!$C{r}=0,"",By_Scenario!$D{r}/By_Scenario!$C{r})')
            ws.cell(row=top + 2, column=col, value=f'=By_Scenario!$C{r}')
            ws.cell(row=top + 3, column=col, value=f'=By_Scenario!$F{r}')
            ws.cell(row=top + 4, column=col,
                    value=f'=IF(By_Scenario!$G{r}="OK",TRUE,FALSE)')
            ws.cell(row=top + 5, column=col,
                    value=f'=IF({cl}{top + 4}=FALSE,"n/a",'
                          f'RANK(By_Scenario!$C{r},By_Scenario!$C${block_first}:$C${block_last}))')
    overall_top = blocks_start + len(scenarios) * 7
    ws.cell(row=overall_top, column=1, value='OVERALL').font = _LABEL_FONT
    ws.cell(row=overall_top, column=2, value='Team')
    for k, label in enumerate(['Avg. Premium', 'Policies Won', 'Lost Ratio (%)',
                               'Qualified? (Bool)', 'Rank (#)']):
        ws.cell(row=overall_top + 1 + k, column=1, value=label)
    for j, name in enumerate(team_names):
        col = 3 + j
        cl = get_column_letter(col)
        r = overall_first + j
        ws.cell(row=overall_top, column=col, value=name)
        ws.cell(row=overall_top + 1, column=col,
                value=f'=IF(By_Scenario!$C{r}=0,"",By_Scenario!$D{r}/By_Scenario!$C{r})')
        ws.cell(row=overall_top + 2, column=col, value=f'=By_Scenario!$C{r}')
        ws.cell(row=overall_top + 3, column=col, value=f'=By_Scenario!$F{r}')
        ws.cell(row=overall_top + 4, column=col,
                value=f'=IF(By_Scenario!$G{r}="DQ",FALSE,TRUE)')
        ws.cell(row=overall_top + 5, column=col,
                value=f'=IF({cl}{overall_top + 4}=FALSE,"n/a",'
                      f'RANK(By_Scenario!$C{r},By_Scenario!$C${overall_first}:$C${overall_last}))')
    for c in range(1, 3 + n_teams):
        ws.cell(row=blocks_start - 1, column=c).fill = _HEAD_FILL

    # --- Dataset + train history + truth ------------------------------------
    ws = wb.create_sheet('Dataset')
    ws.append(list(dataset.columns))
    for row in dataset.itertuples(index=False, name=None):
        ws.append(list(row))
    _style_header(ws, ncols=len(dataset.columns))

    if train_policies is not None:
        ws = wb.create_sheet('Train_Policies')
        ws.append(list(train_policies.columns))
        for row in train_policies.itertuples(index=False, name=None):
            ws.append(list(row))
        _style_header(ws, ncols=len(train_policies.columns))
    if train_claims is not None:
        ws = wb.create_sheet('Train_Claims')
        ws.append(list(train_claims.columns))
        for row in train_claims.itertuples(index=False, name=None):
            ws.append(list(row))
        _style_header(ws, ncols=len(train_claims.columns))

    ws = wb.create_sheet('Truth')
    truth_headers = list(truth.columns) + ['TOTAL_CLAIMS']
    ws.append(truth_headers)
    seed_values = truth[seed_cols].to_numpy(dtype=float)
    first_seed_col = truth.columns.get_loc(seed_cols[0]) + 1
    last_seed_col = truth.columns.get_loc(seed_cols[-1]) + 1
    for r in range(n_test):
        vals = [truth['TEST_ID'].iloc[r], truth['SCENARIO'].iloc[r]]
        for col_name in ('POLID', 'SIM_YEAR'):
            vals.append(truth[col_name].iloc[r] if col_name in truth.columns else '')
        ws.append(vals + [float(v) for v in seed_values[r]]
                  + [f'=SUM({get_column_letter(first_seed_col)}{r + 2}:'
                     f'{get_column_letter(last_seed_col)}{r + 2})'])
    _style_header(ws, ncols=len(truth_headers))

    # --- Team staging sheets -------------------------------------------------
    for j, name in enumerate(team_sheets):
        ws = wb.create_sheet(name)
        ws['A1'] = 'TEST_ID'
        ws['B1'] = 'PREMIUM'
        for cell in ('A1', 'B1'):
            ws[cell].fill = _HEAD_FILL
            ws[cell].font = _HEAD_FONT
        for r in range(2, last + 1):
            ws.cell(row=r, column=1, value=f'=Dataset!B{r}')
        dv = DataValidation(type='decimal', operator='between',
                            formula1=str(config.PREMIUM_MIN),
                            formula2=str(config.PREMIUM_MAX), allow_blank=True)
        dv.error = 'Out of bounds'
        ws.add_data_validation(dv)
        dv.add(f'B2:B{last}')
        ws.column_dimensions['A'].width = 34
        ws.column_dimensions['B'].width = 14

    # --- Subs (merged import) ------------------------------------------------
    ws = wb.create_sheet('Subs')
    ws.cell(row=1, column=1, value='TEST_ID')
    for c, name in enumerate(team_names, start=subs_team_first):
        ws.cell(row=1, column=c, value=name)
    ws.cell(row=1, column=subs_team_last + 1, value='TOTAL_CLAIMS')
    ws.cell(row=1, column=subs_team_last + 2, value='SCENARIO')
    for r in range(2, last + 1):
        ws.cell(row=r, column=1, value=f'=Dataset!B{r}')
        for j, name in enumerate(team_names):
            ws.cell(row=r, column=subs_team_first + j,
                    value=(f"=IF({_sheet_ref(team_sheets[j])}!B{r}<=0,\"\","
                           f"{_sheet_ref(team_sheets[j])}!B{r})"))
        ws.cell(row=r, column=subs_team_last + 1,
                value=f'=IFERROR(XLOOKUP($A{r},Truth!$A$2:$A${last},'
                      f'Truth!${get_column_letter(len(truth_headers))}$2:'
                      f'${get_column_letter(len(truth_headers))}${last},0),0)')
        ws.cell(row=r, column=subs_team_last + 2,
                value=f'=IFERROR(XLOOKUP($A{r},Truth!$A$2:$A${last},Truth!$B$2:$B${last},""),"")')
    _style_header(ws, ncols=subs_team_last + 2)

    # --- Alloc ----------------------------------------------------------------
    ws = wb.create_sheet('Alloc')
    ws.cell(row=1, column=1, value='TEST_ID')
    for c, name in enumerate(team_names, start=subs_team_first):
        ws.cell(row=1, column=c, value=f'{name} share')
    min_col = get_column_letter(subs_team_last + 1)
    tie_col = get_column_letter(subs_team_last + 2)
    sum_col = get_column_letter(subs_team_last + 3)
    ws.cell(row=1, column=subs_team_last + 1, value='MIN_PREM')
    ws.cell(row=1, column=subs_team_last + 2, value='TIE_K')
    ws.cell(row=1, column=subs_team_last + 3, value='ROW_SHARE_SUM')
    for r in range(2, last + 1):
        ws.cell(row=r, column=1, value=f'=Subs!A{r}')
        ws.cell(row=r, column=subs_team_last + 1,
                value=f'=IF(COUNT(Subs!$B{r}:${subs_letters[-1]}{r})=0,"",'
                      f'MIN(Subs!$B{r}:${subs_letters[-1]}{r}))')
        ws.cell(row=r, column=subs_team_last + 2,
                value=f'=IF(${min_col}{r}="","",'
                      f'COUNTIF(Subs!$B{r}:${subs_letters[-1]}{r},${min_col}{r}))')
        for c, letter in enumerate(subs_letters, start=subs_team_first):
            ws.cell(row=r, column=c,
                    value=(f'=IF(Subs!{letter}{r}="","",'
                           f'IF(Subs!{letter}{r}=${min_col}{r},1/${tie_col}{r},0))'))
        ws.cell(row=r, column=subs_team_last + 3,
                value=f'=SUM(B{r}:{subs_letters[-1]}{r})')
    _style_header(ws, ncols=subs_team_last + 3)

    # --- By_Scenario ----------------------------------------------------------
    ws = wb.create_sheet('By_Scenario')
    for c, h in enumerate(['SCENARIO', 'Team', 'Policies', 'Premium', 'Claims',
                           'LR (%)', 'DQ'], start=1):
        ws.cell(row=1, column=c, value=h)
    r = bs_first
    for scenario in scenarios:
        for j, name in enumerate(team_names):
            letter = subs_letters[j]
            ws.cell(row=r, column=1, value=scenario)
            ws.cell(row=r, column=2, value=name)
            ws.cell(row=r, column=3,
                    value=(f'=SUMPRODUCT(--(Subs!${scenario_subs_col}$2:${scenario_subs_col}${last}=$A{r}),'
                           f'Alloc!{letter}$2:{letter}${last})'))
            ws.cell(row=r, column=4,
                    value=(f'=SUMPRODUCT(--(Subs!${scenario_subs_col}$2:${scenario_subs_col}${last}=$A{r}),'
                           f'Alloc!{letter}$2:{letter}${last},Subs!{letter}$2:{letter}${last})'))
            ws.cell(row=r, column=5,
                    value=(f'=SUMPRODUCT(--(Subs!${scenario_subs_col}$2:${scenario_subs_col}${last}=$A{r}),'
                           f'Alloc!{letter}$2:{letter}${last},Subs!${total_subs_col}$2:${total_subs_col}${last})'))
            ws.cell(row=r, column=6, value=f'=IF(D{r}=0,"",E{r}/D{r}*100)')
            ws.cell(row=r, column=7,
                    value=f'=IF(D{r}=0,"no wins",IF(E{r}>=D{r},"DQ","OK"))')
            r += 1
    for j, name in enumerate(team_names):
        ws.cell(row=r, column=1, value='OVERALL')
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3,
                value=f'=SUMIFS($C${bs_first}:$C${bs_last},$B${bs_first}:$B${bs_last},'
                      f'$B{r},$G${bs_first}:$G${bs_last},"<>DQ")')
        ws.cell(row=r, column=4,
                value=f'=SUMIFS($D${bs_first}:$D${bs_last},$B${bs_first}:$B${bs_last},'
                      f'$B{r},$G${bs_first}:$G${bs_last},"<>DQ")')
        ws.cell(row=r, column=5,
                value=f'=SUMIFS($E${bs_first}:$E${bs_last},$B${bs_first}:$B${bs_last},'
                      f'$B{r},$G${bs_first}:$G${bs_last},"<>DQ")')
        ws.cell(row=r, column=6, value=f'=IF(D{r}=0,"",E{r}/D{r}*100)')
        ws.cell(row=r, column=7,
                value=f'=IF(COUNTIFS($B${bs_first}:$B${bs_last},$B{r},'
                      f'$G${bs_first}:$G${bs_last},"DQ")>0,"DQ",'
                      f'IF(COUNTIFS($B${bs_first}:$B${bs_last},$B{r},'
                      f'$G${bs_first}:$G${bs_last},"OK")=0,"no wins","OK"))')
        r += 1
    _style_header(ws, ncols=7)

    # --- Checks ---------------------------------------------------------------
    ws = wb.create_sheet('Checks')
    three_d = f"'{team_sheets[0]}:{team_sheets[-1]}'!B2:B{last}"
    checks = [
        ('Dataset rows', f'=COUNTA(Dataset!$A$2:$A${last})'),
        ('Truth rows', f'=COUNTA(Truth!$A$2:$A${last})'),
        ('Scenarios in truth',
         f'=SUMPRODUCT(1/COUNTIF(Truth!$B$2:$B${last},Truth!$B$2:$B${last}))'),
        ('Priced cells across teams', f'=COUNT({three_d})'),
        ('Test ids with zero submissions',
         f'=SUMPRODUCT(--(COUNTIF(Subs!$B$2:${subs_letters[-1]}${last},"")={n_teams}))'),
        ('Prices below floor',
         f'=SUMPRODUCT((Subs!$B$2:${subs_letters[-1]}${last}<>"")*'
         f'(Subs!$B$2:${subs_letters[-1]}${last}<{config.PREMIUM_MIN}))'),
        ('Prices above cap',
         f'=SUMPRODUCT((Subs!$B$2:${subs_letters[-1]}${last}<>"")*'
         f'(Subs!$B$2:${subs_letters[-1]}${last}>{config.PREMIUM_MAX}))'),
        ('Allocation row sums off 1 (submitted rows only)',
         f'=SUMPRODUCT(--(ABS(Alloc!${sum_col}$2:${sum_col}${last}-1)>0.0000001),'
         f'--(Alloc!${min_col}$2:${min_col}${last}<>""))'),
    ]
    for i, (name, formula) in enumerate(checks, start=1):
        ws.cell(row=i, column=1, value=name)
        if formula:
            ws.cell(row=i, column=2, value=formula)
    ws.column_dimensions['A'].width = 55
    ws.column_dimensions['B'].width = 20

    # --- Instructions ----------------------------------------------------------
    ws = wb.create_sheet('Instructions')
    for i, line in enumerate([
        'ORGANIZER MASTER — all scenarios in one workbook',
        '',
        f'Dataset: {n_test:,} test policies across {len(scenarios)} scenarios '
        f'(sheet Dataset); hidden claims in sheet Truth.',
        f'Teams: {n_teams} staging sheets ({team_sheets[0]} .. {team_sheets[-1]});',
        '   add/remove names in competition/teams.txt and rebuild the master.',
        '',
        '1. Import each team submission into its own staging sheet: paste PREMIUM',
        '   values into column B, starting at B2, in the Dataset/TEST_ID order.',
        '   (Column A mirrors Dataset TEST_ID so rows line up.)',
        '2. Sheets Subs/Alloc/By_Scenario update automatically: cheapest premium',
        '   wins each policy; ties split equally (share = 1 / k).',
        '3. Master sheet scoreboard: one block per scenario with Avg. Premium,',
        '   Policies Won, Lost Ratio (%), Qualified? (Bool), Rank (#).',
        '4. Any scenario with LR >= 100% -> Qualified FALSE and excluded from the',
        '   OVERALL eligible totals.',
        '5. Checks sheet must read 0 (except the informational rows) before',
        '   publishing results.',
        '6. Winner = highest OVERALL Policies Won among Qualified teams.',
        '',
        'MISSING ENTRIES',
        '  A blank premium is treated as "no bid": that policy is not awarded to',
        '  that team, and a test row with no bid from ANY team is won by nobody.',
        '  A team with no winning business shows "no wins" (not Qualified, not DQ);',
        '  DQ triggers only when LR >= 100% in a scenario it actually won business.',
    ], start=1):
        ws.cell(row=i, column=1, value=line)
    ws.column_dimensions['A'].width = 100

    wb.save(path)
    return path
