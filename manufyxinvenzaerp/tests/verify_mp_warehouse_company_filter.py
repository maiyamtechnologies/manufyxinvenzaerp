"""Raw Materials Warehouse offers this plan's own company, and somewhere stock can sit.

The field had no query on it at all -- not an empty one, none -- so it offered every
Warehouse on the site. There are 23 here and only 8 belong to the operating company;
the other 15 are the three `_Test` companies' trees, which exist because the test
harness created them and which no plan will ever legitimately name.

Naming one is not a cosmetic slip. Every stock read the plan makes keys on
for_warehouse -- check_stock_availability, the Material Mapping batch query,
reserve_batches, _job_stock_at_supplier -- so a plan pointed at another company's
shed measures its requirement against a place its material is not, and reports the
whole thing as a shortfall. It is the same fault that
verify_mapping_batch_warehouse.py was written for, one field upstream: there the
batch was in the wrong warehouse, here the warehouse itself is in the wrong company.

is_group = 0 is the second half of it. A group warehouse is a tree node, not a
location -- nothing is ever stored in "All Warehouses - MIPL". get_batch_qty returns
nothing for one, so picking it reads as "no stock anywhere" rather than as the
mis-pick it actually is.

Two things about the mechanism, both verified against frappe rather than assumed:

  * The callback form of set_query is re-run on every dropdown open. link.js calls
    set_custom_query on each `input` event, and that calls get_query(frm.doc, ...)
    fresh -- so the filter re-reads frm.doc.company each time and needs no company
    handler to stay current. What it does NOT do is clear a for_warehouse already
    chosen under the old company; see the last section.
  * apply_link_field_filters() spreads df.link_filters OVER args.filters, which is
    how it resets a get_query (the case public/js/item.js lock_item_group_filter
    exists for). It only fires when df.link_filters is non-empty, and this docfield
    has none -- so the hazard does not apply here, and this checks that it stays
    that way.

material_planning.js is doctype JS, not public/js -- it is NOT bundled. FormMeta
reads it off disk per form load, and with developer_mode on it is not even cached,
so there is nothing to build and nothing to restart. This reads what the form is
actually served, not just the file, so a stale meta cache would show up here.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_mp_warehouse_company_filter.run
"""

import frappe

checks = []


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-60s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _js_path():
    return frappe.get_app_path("manufyxinvenzaerp", "production_management", "doctype",
                               "material_planning", "material_planning.js")


def _query_block(js):
    """Just the for_warehouse set_query call, so a mention of the field 12 lines
    further down cannot satisfy a check about the query."""
    marker = 'frm.set_query("for_warehouse"'
    if marker not in js:
        return ""
    block = js.split(marker, 1)[1]
    # stops at the next set_query -- the batch/material_mapping one that follows it
    return block.split("frm.set_query(", 1)[0]


def run():
    js = open(_js_path()).read()
    block = _query_block(js)

    print("=== the form asks for a filtered list ===")
    check("the field has a query at all", bool(block), True)
    # Parent field, so the two-argument form. The three-argument form
    # set_query(field, parent_fieldname, fn) writes to a grid field that does not
    # exist for a parent Link and would silently do nothing.
    check("declared as a parent-field query, not a child-table one",
          'frm.set_query("for_warehouse", function' in js, True)
    check("not addressed through a child table",
          'frm.set_query("for_warehouse", "' in js, False)
    check("it filters on the plan's own company", "company: frm.doc.company" in block, True)
    check("and on warehouses that can hold stock", "is_group: 0" in block, True)
    # A callback that closed over a value read once at refresh would go stale the
    # moment company changed. It must read frm.doc, not a captured local.
    check("company is read off frm.doc, not captured",
          "frm.doc.company" in block, True)
    check("it is inside the refresh handler",
          'frm.set_query("for_warehouse"' in js.split("\trefresh(frm) {", 1)[1]
          .split("\n\tafter_save(frm) {", 1)[0], True)

    print()
    print("=== and that is what the form is actually served ===")
    # Doctype JS is read from disk by FormMeta.add_code into __js and handed to the
    # browser with the meta bundle. Nothing is bundled and nothing is compiled, so
    # this string reaching __js is the whole deployment.
    from frappe.desk.form.meta import get_meta as get_form_meta

    served = get_form_meta("Material Planning").get("__js") or ""
    check("the served doctype JS is not empty", len(served) > 1000, True)
    check("it carries the for_warehouse query",
          'frm.set_query("for_warehouse"' in served, True)
    check("with the company filter", "company: frm.doc.company" in served, True)
    check("with the is_group filter", "is_group: 0" in served, True)

    print()
    print("=== nothing overrides it ===")
    # link.js: args.filters = { ...args.filters, ...apply_link_field_filters() }.
    # A link_filters entry on the same key wins over anything set_query returned.
    df = frappe.get_meta("Material Planning").get_field("for_warehouse")
    check("the docfield carries no link_filters to override us",
          bool(df.get("link_filters")), False)
    check("nor any df.filters", bool(df.get("filters")), False)
    check("it is still a Link to Warehouse", (df.fieldtype, df.options), ("Link", "Warehouse"))
    check("company is mandatory, so the filter is never blank by design",
          bool(frappe.get_meta("Material Planning").get_field("company").reqd), True)
    # One query, in one place. A second set_query on the same field would make which
    # one wins a matter of handler order.
    check("only one set_query targets this field", js.count('set_query("for_warehouse"'), 1)
    scripts = frappe.get_all("Client Script", filters={"dt": "Material Planning", "enabled": 1},
                             pluck="script")
    check("no enabled Client Script touches it",
          [s for s in scripts if "for_warehouse" in (s or "")], [])

    print()
    print("=== the filter demonstrably narrows the list ===")
    total = frappe.db.count("Warehouse")
    company = frappe.db.get_value("Material Planning", {"docstatus": ["<", 2]}, "company") \
        or frappe.db.get_value("Company", {"name": ("not like", "\\_Test%")}, "name")
    print("   company under test:", company, "| warehouses on site:", total)
    offered = frappe.get_all(
        "Warehouse", filters={"company": company, "is_group": 0}, pluck="name")
    # Not "0 < 23": an empty list would satisfy that and leave the user with a field
    # that offers nothing. It has to narrow AND still have something in it.
    check("the plan's company has leaf warehouses to offer", len(offered) > 0, True)
    check("and fewer of them than the site has warehouses", len(offered) < total, True)
    excluded = [w for w in frappe.get_all("Warehouse", fields=["name", "company", "is_group"])
                if w.name not in offered]
    print("   offered: %d | excluded: %d" % (len(offered), len(excluded)))
    check("something is actually excluded", len(excluded) > 0, True)
    # The two reasons a warehouse is excluded, each proven to be represented -- so a
    # site where one clause stopped working could not pass this section.
    check("including another company's warehouses",
          len([w for w in excluded if w.company != company]) > 0, True)
    check("and this company's own group node",
          len([w for w in excluded if w.company == company and w.is_group]) > 0, True)
    check("no group warehouse survives the filter",
          [w for w in offered if frappe.db.get_value("Warehouse", w, "is_group")], [])
    check("no other company's warehouse survives it",
          [w for w in offered
           if frappe.db.get_value("Warehouse", w, "company") != company], [])

    print()
    print("=== known gap, stated rather than asserted ===")
    # set_query filters what is OFFERED. It does not revisit what was already
    # chosen, and there is no company(frm) handler here and no server-side check
    # that for_warehouse belongs to company -- so changing company on a saved plan
    # leaves the old company's warehouse sitting in the field, and it saves.
    # public/js/item.js does clear the dependent field (custom_parent_item_group ->
    # frm.set_value("item_group", "")); this field does not. Flagged, not failed:
    # closing it is a separate change.
    has_company_handler = "\n\tcompany(frm) {" in js
    print("   company(frm) handler clearing a stale warehouse:",
          "present" if has_company_handler else "ABSENT -- stale value survives a company change")
    stale = frappe.db.sql(
        """SELECT p.name, p.company, p.for_warehouse
           FROM `tabMaterial Planning` p JOIN tabWarehouse w ON w.name = p.for_warehouse
           WHERE IFNULL(p.for_warehouse,'') != ''
             AND (w.company != p.company OR w.is_group = 1)""", as_dict=True)
    for s in stale[:5]:
        print("   CROSS-COMPANY %s: company=%s warehouse=%s" % (s.name, s.company, s.for_warehouse))
    # This one IS asserted: whatever the form allows, no plan on this site should
    # currently be pointed at a warehouse the filter would not offer.
    check("no existing plan points outside its own company", stale, [])

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
