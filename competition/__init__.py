"""Competition data factory — Python builds datasets only; Excel does the rest.

This is an APPLICATION built on the `voltvision` engine. It imports the
engine's public API (`build_panel`, `replay_claims`, assumptions, schema); the
engine never imports this package.

Layout:
  config.py        defaults (seeds, bounds, split sizes, paths, round list)
  sanitize.py      public-vs-hidden column whitelists
  build_dataset.py CLI: one public workbook + hidden truth + master workbook
  workbooks.py     xlsx writers (public dataset, truth, master scoring)
  make_master.py   CLI: rebuild the master workbook from hidden truth
  rounds.json      scenario list (scales freely)
  teams.txt        team names (scales freely)
"""
