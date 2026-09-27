import importlib, io, contextlib, frappe
SUSPECTS = ["verify_mip_consolidated_allocation", "verify_pr_sequential_allocation",
            "verify_manual_mr_multi_supplier", "verify_mip_post_purchase_refresh",
            "verify_consolidate_alternate_item", "verify_batch_receipt_line_match"]
def run():
    for n in SUSPECTS:
        buf = io.StringIO()
        try:
            mod = importlib.import_module("manufyxinvenzaerp.tests." + n)
            with contextlib.redirect_stdout(buf):
                mod.run()
            out = buf.getvalue()
            verdict = "FAIL" if ("CHECKS FAILED" in out or "FAIL " in out) else "pass"
        except Exception as e:
            verdict = "ERROR %s: %s" % (type(e).__name__, str(e)[:70])
        finally:
            frappe.db.rollback()
        print("  %-44s %s" % (n, verdict))
