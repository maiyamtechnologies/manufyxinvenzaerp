import inspect
def run():
    from manufyxinvenzaerp.subcontracting_management import material_issue_plan_transfer as t
    src = inspect.getsource(t.create_mip_partial_transfer)
    import re
    print("VAL", [m.start() for m in re.finditer(r"_validate_return_na\(", src)])
    print("COMMIT", [m.start() for m in re.finditer(r"frappe\.db\.commit\(\)", src)])
    i = src.index("_validate_return_na(")
    print("CTX", repr(src[i-80:i+40]))
