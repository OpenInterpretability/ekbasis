"""WS-FX family registry: family -> (generator module, allowed templates or None, split). Splits follow SPEC.md and
Addendum 1: held-out families and the Memos app never appear in train or val."""
CORE = {
    # shell (WS-F templates, new seeds)
    "sh_remove": ("shell", ["rm_file", "rm_missing", "rm_f_missing", "rm_dir_plain", "rm_r_dir", "rm_glob", "rm_star",
                            "rm_hidden", "rm_link", "rm_link_slash", "find_delete", "find_empty_delete", "find_exec_rm",
                            "xargs_rm", "cd_then_wipe"]),
    "sh_copy": ("shell", ["cp_dir_no_r", "cp_glob_to_file", "cp_into_dir", "cp_new", "cp_overwrite", "cp_r_into_existing",
                          "cp_r_merge_dot", "rsync"]),
    "sh_move": ("shell", ["mv_dir_into_dir", "mv_glob_into", "mv_into_dir", "mv_into_missing_slash", "mv_overwrite",
                          "mv_rename", "mv_same"]),
    "sh_redirect": ("shell", ["redir_cat_into", "redir_echo", "redir_missing_dir", "redir_same_file", "redir_tee",
                              "redir_to_dir", "redir_truncate", "false_then"]),
    "sh_links": ("shell", ["ln_dir", "ln_hard", "ln_s"]),
    "sh_archive": ("shell", ["tar_create", "tar_extract", "gzip_file"]),
    "sh_edit_misc": ("shell", ["sed_i", "sed_i_missing", "touch", "mkdir", "chmod_read", "unquoted_space"]),
    # git
    "git_reset": ("gitfam", ["reset_hard", "reset_hard_path", "reset_hard_prev", "reset_keep", "reset_merge", "reset_mixed",
                             "reset_origin", "reset_path", "reset_soft"]),
    "git_checkout_restore": ("gitfam", ["checkout", "checkout_f", "checkout_file", "checkout_ours", "checkout_rev",
                                        "checkout_rev_file", "restore", "restore_all", "restore_both", "restore_source",
                                        "restore_staged", "switch", "switch_c", "switch_detach", "switch_f"]),
    "git_stash": ("gitfam", ["stash", "stash_a", "stash_apply", "stash_clear", "stash_drop", "stash_keep_index",
                             "stash_path", "stash_pop", "stash_u"]),
    "git_clean": ("gitfam", ["clean_d", "clean_f", "clean_fX", "clean_fd", "clean_fdx", "clean_n"]),
    "git_merge_pull": ("gitfam", ["merge", "merge_abort", "merge_continue", "merge_no_commit", "merge_squash", "pull",
                                  "pull_rebase", "fetch"]),
    "git_rebase_cherry_revert": ("gitfam", ["rebase", "rebase_abort", "rebase_continue", "rebase_skip", "cherry_abort",
                                            "cherry_continue", "cherry_pick", "cherry_pick_n", "revert"]),
    "git_branch_commit": ("gitfam", ["add_commit", "add_resolved", "amend", "branch_D", "branch_f", "branch_new", "commit",
                                     "commit_a", "mv", "mv_f", "rm", "rm_cached", "rm_f"]),
    "git_sparse_remote": ("gitfam", ["sparse_disable", "sparse_set", "push_force", "wt_remove", "wt_remove_f"]),
    # SQLite
    "sql_delete": ("sqlfam", ["del_all", "del_c_eq_null", "del_c_ge", "del_c_is_null", "del_c_ne", "del_p_id", "del_p_in",
                              "del_p_like"]),
    "sql_insert_conflict": ("sqlfam", ["ins_c_null_tag", "ins_c_parent", "ins_dup_name", "ins_ignore", "ins_replace",
                                       "replace_into", "upsert", "upd_or_ignore", "upd_or_replace", "t_upsert_where",
                                       "t_multirow_dup"]),
    "sql_fk": ("sqlfam", ["drop_parent", "fk_off_then_delete", "fk_on_then_delete", "ins_c_missing_parent", "upd_fk",
                          "t_deferred_fk", "t_on_update_cascade"]),
    "sql_null": ("sqlfam", ["t_concat_null", "t_in_null_list", "t_not_in_null_list", "t_not_in_subquery_null",
                            "t_null_arith"]),
    "sql_txn_ddl_types": ("sqlfam", ["txn_commit", "txn_rollback", "rollback_no_begin", "t_or_fail_partial", "alter_add",
                                     "alter_drop", "alter_rename", "t_int_div", "t_swap", "t_rowid_reuse", "upd_qty",
                                     "ins_c_text_in_int"]),
    # Python
    "py_alias_mutation": ("pyfam", ["alias_append", "list_mult_alias", "mutable_default", "shallow_nested", "tuple_iadd",
                                    "iadd_vs_add", "keys_view_live", "dict_iter_mutate", "remove_while_iter",
                                    "string_immutable_method"]),
    "py_control_exc": ("pyfam", ["finally_return", "unbound_local", "key_error", "late_binding", "gen_exhaust",
                                 "default_arg_eval_time", "file_mode_w"]),
    "py_numeric": ("pyfam", ["floordiv_neg", "int_trunc", "round_half", "float_eq", "chained_compare", "and_or_value",
                             "int_parse"]),
    "py_strings_seq": ("pyfam", ["split_spaces", "strip_chars", "slice_vs_index", "str_compare_numbers", "str_int_concat",
                                 "sort_returns_none", "print_sep", "range_stop", "zip_truncate", "remove_first_only",
                                 "dict_merge_order"]),
}
HELD_OUT_FAMILIES = {"se_shell_heldout", "se_sql_heldout", "sh_text", "sh_perm", "git_tag", "git_bare_push", "sql_triggers", "pg_txn_abort", "pg_ddl_cascade",
                     "py_collections", "py_classes", "vk_sharing_teams", "ext_shio_eval"}
HELD_OUT_APP_PREFIX = "mm_"   # Memos, the held-out app
SEEDS = {"train": 20_000_000, "val": 21_000_000, "eval": 22_000_000, "trainplus": 23_000_000}


def split_of(family):
    if family.startswith(HELD_OUT_APP_PREFIX):
        return "eval_app"
    if family in HELD_OUT_FAMILIES:
        return "eval_family"
    return "train"
