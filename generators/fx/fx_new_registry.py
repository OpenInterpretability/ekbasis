"""WS-FX families built by FX: family -> (generator module, allowed forms). Filled per module as each one is built."""
NEW = {}
try:
    import fx_shell_new as _sh
    for _fam, _forms in _sh.FAMILY_FORMS.items():
        NEW[_fam] = ("fx_shell_new", _forms)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_py_new as _py
    for _fam, _t in _py.FAMILY_TEMPLATES.items():
        NEW[_fam] = ("fx_py_new", _t)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_sql_new as _sq
    for _fam, _t in _sq.FAMILY_TEMPLATES.items():
        NEW[_fam] = ("fx_sql_new", _t)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_pg as _pg
    for _fam, _t in _pg.FAMILY_TEMPLATES.items():
        NEW[_fam] = ("fx_pg", _t)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_git_new as _gn
    for _fam, _t in _gn.FAMILY_FORMS.items():
        NEW[_fam] = ("fx_git_new", _t)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_apps as _ap
    for _fam, _t in _ap.FAMILY_FORMS.items():
        NEW[_fam] = ("fx_apps", _t)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_ext_shio as _sh2
    for _fam, _t in _sh2.FAMILY_FORMS.items():
        NEW[_fam] = ("fx_ext_shio", _t)
except Exception:  # noqa: BLE001
    pass
try:
    import fx_side as _se
    for _fam, _t in _se.FAMILY_FORMS.items():
        NEW[_fam] = ("fx_side", _t)
except Exception:  # noqa: BLE001
    pass
